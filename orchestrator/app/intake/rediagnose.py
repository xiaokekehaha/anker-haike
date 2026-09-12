"""rediagnose 的上下文抽取（票 37，03 §1.2 多轮、§1.4.1 多轮更新规则、连续追问设计 §3.2）。

复用 intake 任务（同一条模型链、tag=internal），但提示与 schema 不同：把已确认产品、当前有效症状、最近步骤与反馈
一并交给模型，要求输出**增量**：新增现象、被明确否定 / 纠正的旧现象、产品纠正线索、情绪、wants_human、
以及「指代不明」线索。合并遵循增量语义：

- 未提及 = 保持；新增 = 合并去重；明确否定 = 只删除能对上已知症状的那一条（模型给的否定必须落在已知列表里）。
- 抽取失败 / 空抽取 **不**清空产品与症状；原文含具体故障描述时把原文当一条症状回退（03 §1.4.1 规则 3）。
- 是否澄清、是否升级由后端规则决定（needs_clarification 只是线索，见 graph.rediagnose）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.diagnose.query import dedupe, normalize_query
from app.intake.extract import INTAKE_BUDGET_MS, Level, strategy_for
from app.models.queue import CapacityExceeded
from app.models.router import ModelInvokeError, ModelRouter
from app.prompts import compose_system_prompt, wrap_data

log = logging.getLogger("intake.rediagnose")

REDIAGNOSE_PROMPT_VERSION = "2026-09-13.1"


class RediagnoseExtraction(BaseModel):
    """模型输出 schema（rediagnose 复用 intake 任务）。全部为增量。"""

    model_config = ConfigDict(extra="forbid")

    emotion_level: Level = Field(description="用户情绪：calm / anxious / angry")
    product_hints: list[str] = Field(
        default_factory=list,
        description="仅当用户明确纠正或重新指出型号 / 品类时摘录原文；沿用当前产品则为空",
    )
    new_symptoms: list[str] = Field(
        default_factory=list, description="本轮新增或补充的故障现象短语，每条不超过 12 个字"
    )
    negated_symptoms: list[str] = Field(
        default_factory=list,
        description="用户明确否定或纠正掉的旧现象，必须从「当前有效症状」列表里原文摘录；没有则为空",
    )
    wants_human: bool = Field(description="是否明确要求人工客服 / 真人 / 投诉")
    needs_clarification: bool = Field(
        default=False,
        description="用户在补充或纠正，但指代对象无法唯一确定（如「不是那个」「另一个也坏了」）",
    )


@dataclass
class RediagnoseOutcome:
    emotion: dict[str, str]
    symptoms: list[str]
    product_hints: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    wants_human: bool = False
    needs_clarification: bool = False
    degraded: bool = False
    degrade_reason: str | None = None
    model_trace: dict[str, Any] | None = None

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed or self.product_hints)


INSTRUCTION = (
    "用户正在排障过程中补充或纠正信息。结合 <state> 段里的已确认产品、当前有效症状与最近步骤，"
    "只从 <data> 段的这句话抽取**增量**：\n"
    "1. emotion_level：calm / anxious / angry；\n"
    "2. product_hints：只有用户明确说「不是 X 是 Y」「说错了，是 Y」这类纠正，或重新指出型号 / 品类时才摘录原文；"
    "沿用当前产品则留空，不要重复当前产品；\n"
    "3. new_symptoms：本轮新增的现象短语（如「还有异响」→「异响」）；仅重复旧现象（「还是不吸」）则留空；\n"
    "4. negated_symptoms：用户明确否定的旧现象，必须从「当前有效症状」里原文摘录（如「不是吸力小，是有异响」→ 否定「吸力小」）；\n"
    "5. wants_human：只有明确要求人工 / 真人 / 投诉才为 true；\n"
    "6. needs_clarification：补充或纠正的对象无法唯一确定时为 true。\n"
    "不要推断原因、不要补全型号、不要把步骤操作结果当成新症状。只输出 JSON。"
)

EXAMPLE = (
    "示例：当前有效症状「不吸了、滚刷缠头发」，用户说「其实还有异响」→ "
    '{"emotion_level":"calm","product_hints":[],"new_symptoms":["异响"],"negated_symptoms":[],'
    '"wants_human":false,"needs_clarification":false}'
)


def _state_block(context: dict[str, Any]) -> str:
    product = context.get("product") or "（未确认）"
    symptoms = context.get("symptoms") or []
    steps = context.get("recent_steps") or []
    lines = [
        f"已确认产品：{product}",
        f"当前有效症状：{'、'.join(symptoms) if symptoms else '（无）'}",
    ]
    if steps:
        lines.append(
            "最近步骤与反馈："
            + "；".join(f"{s.get('title', '')}（{s.get('feedback') or '待反馈'}）" for s in steps)
        )
    return "<state>\n" + "\n".join(lines) + "\n</state>"


def build_messages(
    text: str,
    *,
    context: dict[str, Any],
    has_image: bool,
    prev_emotion: dict | None,
) -> list[tuple[str, str]]:
    system = compose_system_prompt(
        strategy=(prev_emotion or {}).get("strategy", "normal"),
        state_summary={
            "stage": "guide",
            "product": context.get("product"),
            "symptoms": context.get("symptoms"),
            "steps_done": len(context.get("recent_steps") or []),
        },
    )
    extra = "（用户同时上传了新图片）" if has_image else ""
    return [
        ("system", system),
        ("human", f"{INSTRUCTION}\n{EXAMPLE}\n{_state_block(context)}\n{extra}\n{wrap_data(text)}"),
    ]


def merge_symptoms(
    current: list[str], *, added: list[str], negated: list[str]
) -> tuple[list[str], list[str], list[str]]:
    """增量合并：否定只删能对上已知症状的项（规范化后相等或互为包含），新增去重追加。

    返回 (合并后症状, 实际新增, 实际删除)。
    """
    cur = dedupe([str(s) for s in current])
    removed: list[str] = []
    for neg in negated:
        key = normalize_query(neg).replace(" ", "")
        if not key:
            continue
        for s in list(cur):
            sk = normalize_query(s).replace(" ", "")
            if sk == key or (len(key) >= 2 and (key in sk or sk in key)):
                cur.remove(s)
                removed.append(s)
    before = {normalize_query(s).replace(" ", "") for s in cur}
    merged = dedupe([*cur, *added])
    actually_added = [s for s in merged if normalize_query(s).replace(" ", "") not in before]
    return merged, actually_added, removed


def _degraded(
    reason: str, *, lane: str, current: list[str], fallback_symptom: str | None, prev_emotion
) -> RediagnoseOutcome:
    merged, added, _ = merge_symptoms(
        current, added=[fallback_symptom] if fallback_symptom else [], negated=[]
    )
    return RediagnoseOutcome(
        emotion=dict(prev_emotion or {"level": "calm", "strategy": "normal"}),
        symptoms=merged,
        added=added,
        degraded=True,
        degrade_reason=reason,
        model_trace={"task": "intake", "model_used": "skipped", "lane": lane, "attempts": 1},
    )


async def extract_rediagnose(
    router: ModelRouter | None,
    text: str,
    *,
    context: dict[str, Any],
    session_id: str | None,
    lane: str,
    has_image: bool = False,
    prev_emotion: dict | None = None,
    fallback_symptom: str | None = None,
    budget_ms: int = INTAKE_BUDGET_MS,
) -> RediagnoseOutcome:
    """一次 intake 任务调用。context = {product, symptoms, recent_steps}。

    fallback_symptom：抽取失败时用作回退症状的原文（调用方已判定它含具体故障描述；否则传 None）。
    """
    current = list(context.get("symptoms") or [])
    if router is None:
        return _degraded(
            "router unavailable", lane=lane, current=current,
            fallback_symptom=fallback_symptom, prev_emotion=prev_emotion,
        )
    if not text.strip():
        # 纯图片补充：没有文本就没有增量，交读图路径
        return RediagnoseOutcome(
            emotion=dict(prev_emotion or {"level": "calm", "strategy": "normal"}),
            symptoms=dedupe([str(s) for s in current]),
            model_trace=None,
        )
    try:
        res = await router.invoke(
            "intake",
            build_messages(text, context=context, has_image=has_image, prev_emotion=prev_emotion),
            RediagnoseExtraction,
            budget_ms=budget_ms,
            session_id=session_id,
            lane=lane,
        )
    except (ModelInvokeError, CapacityExceeded) as exc:
        log.warning("rediagnose extraction degraded session=%s reason=%s", session_id, str(exc)[:200])
        return _degraded(
            f"{type(exc).__name__}: {exc}"[:200], lane=lane, current=current,
            fallback_symptom=fallback_symptom, prev_emotion=prev_emotion,
        )
    parsed: RediagnoseExtraction = res.parsed
    merged, added, removed = merge_symptoms(
        current,
        added=[s.strip() for s in parsed.new_symptoms if s.strip()][:8],
        negated=[s.strip() for s in parsed.negated_symptoms if s.strip()][:8],
    )
    hints = [h.strip() for h in parsed.product_hints if h.strip()][:5]
    log.info(
        "rediagnose extracted session=%s level=%s hints=%s added=%s removed=%s wants_human=%s "
        "needs_clarification=%s model=%s prompt_ver=%s",
        session_id, parsed.emotion_level, hints, added, removed, parsed.wants_human,
        parsed.needs_clarification, res.model_used, REDIAGNOSE_PROMPT_VERSION,
    )
    return RediagnoseOutcome(
        emotion={"level": parsed.emotion_level, "strategy": strategy_for(parsed.emotion_level)},
        symptoms=merged,
        product_hints=hints,
        added=added,
        removed=removed,
        wants_human=parsed.wants_human,
        needs_clarification=parsed.needs_clarification,
        model_trace={
            "task": "intake",
            "model_used": res.model_used,
            "lane": res.lane,
            "attempts": max(1, sum(1 for a in res.attempts if a.outcome != "skipped")),
        },
    )
