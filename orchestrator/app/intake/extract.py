"""一次 internal 调用同时输出：情绪三级 + 产品线索 + 症状 + wants_human（03 §1.1、§1.2）。

- 走 ModelRouter task=intake（轻量档链），tag=internal，输出不进聊天流。
- strategy 由 level 按规则映射（calm→normal, anxious→reassure_first, angry→reassure_and_shorten），不信任模型给的策略。
- 任何失败（路由不可用、链耗尽、容量满）→ 降级：calm / normal、hints 与 symptoms 为空、wants_human=False，不阻断流程。
- wants_human=true 等价于规则 R3 命中：调用方写 safety_flags 并升级。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.queue import CapacityExceeded
from app.models.router import ModelInvokeError, ModelRouter
from app.prompts import PROMPT_VERSION, compose_system_prompt, wrap_data

log = logging.getLogger("intake")

Level = Literal["calm", "anxious", "angry"]
Strategy = Literal["normal", "reassure_first", "reassure_and_shorten"]
STRATEGY_BY_LEVEL: dict[str, Strategy] = {
    "calm": "normal",
    "anxious": "reassure_first",
    "angry": "reassure_and_shorten",
}
INTAKE_BUDGET_MS = 6000


def strategy_for(level: str) -> Strategy:
    return STRATEGY_BY_LEVEL.get(level, "normal")


class IntakeExtraction(BaseModel):
    """模型输出 schema（intake 任务）。"""

    model_config = ConfigDict(extra="forbid")

    emotion_level: Level = Field(
        description="用户情绪：calm 平稳 / anxious 焦急担心 / angry 愤怒不满"
    )
    product_hints: list[str] = Field(
        default_factory=list,
        description="用户提到的产品线索：型号、系列、别名、品类词，原文摘录，不要猜测型号",
    )
    symptoms: list[str] = Field(
        default_factory=list, description="故障现象短语，每条不超过 12 个字，原文归纳"
    )
    wants_human: bool = Field(description="用户是否明确要求人工客服 / 真人 / 投诉")


@dataclass
class IntakeOutcome:
    emotion: dict[str, str]
    product_hints: list[str] = field(default_factory=list)
    symptoms: list[str] = field(default_factory=list)
    wants_human: bool = False
    degraded: bool = False
    degrade_reason: str | None = None
    model_trace: dict[str, Any] | None = None  # ModelTraceItem 形状

    @classmethod
    def degraded_default(cls, reason: str, lane: str) -> IntakeOutcome:
        return cls(
            emotion={"level": "calm", "strategy": "normal"},
            degraded=True,
            degrade_reason=reason,
            model_trace={"task": "intake", "model_used": "skipped", "lane": lane, "attempts": 1},
        )


INSTRUCTION = (
    "从 <data> 段的用户消息中抽取结构化信息。要求：\n"
    "1. emotion_level：结合措辞（感叹号、催促、抱怨、脏话）判断 calm / anxious / angry；\n"
    "2. product_hints：只摘录用户明确写出的型号 / 系列 / 别名 / 品类词（如「S1 Pro」「扫地机」），不要补全或猜测；\n"
    "3. symptoms：把故障现象归纳为短语列表；\n"
    "4. wants_human：只有用户明确要求人工、真人、客服电话、投诉时才为 true。\n"
    "只输出 JSON。"
)

EXAMPLE = (
    "示例输入：「我的 S1 Pro 不吸了，急死了，明天要用！」\n"
    '示例输出：{"emotion_level":"anxious","product_hints":["S1 Pro"],"symptoms":["不吸了"],"wants_human":false}'
)


def build_messages(
    text: str, *, has_image: bool, prev_emotion: dict | None, state_summary: dict | None
) -> list[tuple[str, str]]:
    system = compose_system_prompt(
        strategy=(prev_emotion or {}).get("strategy", "normal"), state_summary=state_summary
    )
    extra = "（用户同时上传了图片）" if has_image else ""
    prev = f"上一轮情绪：{prev_emotion['level']}。" if prev_emotion else ""
    return [
        ("system", system),
        ("human", f"{INSTRUCTION}\n{EXAMPLE}\n{prev}{extra}\n{wrap_data(text)}"),
    ]


async def extract_intake(
    router: ModelRouter | None,
    text: str,
    *,
    session_id: str | None,
    lane: str,
    has_image: bool = False,
    prev_emotion: dict | None = None,
    state_summary: dict | None = None,
    budget_ms: int = INTAKE_BUDGET_MS,
) -> IntakeOutcome:
    if router is None:
        return IntakeOutcome.degraded_default("router unavailable", lane)
    if not text.strip():
        return IntakeOutcome.degraded_default("empty text", lane)
    try:
        res = await router.invoke(
            "intake",
            build_messages(
                text, has_image=has_image, prev_emotion=prev_emotion, state_summary=state_summary
            ),
            IntakeExtraction,
            budget_ms=budget_ms,
            session_id=session_id,
            lane=lane,
        )
    except (ModelInvokeError, CapacityExceeded) as exc:
        log.warning("intake extraction degraded session=%s reason=%s", session_id, str(exc)[:200])
        return IntakeOutcome.degraded_default(f"{type(exc).__name__}: {exc}"[:200], lane)
    parsed: IntakeExtraction = res.parsed
    log.info(
        "intake extracted session=%s level=%s hints=%s symptoms=%s wants_human=%s model=%s prompt_ver=%s",
        session_id,
        parsed.emotion_level,
        parsed.product_hints,
        parsed.symptoms,
        parsed.wants_human,
        res.model_used,
        PROMPT_VERSION,
    )
    return IntakeOutcome(
        emotion={"level": parsed.emotion_level, "strategy": strategy_for(parsed.emotion_level)},
        product_hints=[h.strip() for h in parsed.product_hints if h.strip()][:5],
        symptoms=[s.strip() for s in parsed.symptoms if s.strip()][:8],
        wants_human=parsed.wants_human,
        model_trace={
            "task": "intake",
            "model_used": res.model_used,
            "lane": res.lane,
            "attempts": max(1, sum(1 for a in res.attempts if a.outcome != "skipped")),
        },
    )
