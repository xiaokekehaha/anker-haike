"""票 30：读图观察 diagnose.vision（03 §1.4 步骤 1；09 §1 CP-in；07 §6 备用模型不支持图片）。

- 只对本 run 新上传、purpose=fault 的图片调用视觉任务（tag=internal），输出 {observations, visible_parts}；
  输出只是「观察」，不是假设，进入 image_observations 供检索补充与 synthesize 使用。
- 观察项再过一次 CP-in（observation_terms：smoke / deformed battery …），R4 命中由调用方直接升级。
- 图片超过链上视觉模型的单请求上限（models.yaml max_images）时只保留最新几张。
- 视觉链全部失败 / 无视觉模型可用：流程不中断，observations 为空并记录 status；
  无视觉能力时给用户一句固定提示「请用文字描述图片内容」（07 §6）。
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from haike_contracts.common import FaultLocalization
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ConfigDict, Field

from app.images.store import ImageStore
from app.models.queue import CapacityExceeded
from app.models.router import ModelInvokeError, ModelRouter
from app.prompts import compose_system_prompt, wrap_data

log = logging.getLogger("diagnose.vision")

TASK = "diagnose.vision"
VISION_BUDGET_MS = 12_000  # 含图轮 run deadline 40 s（08 §8），读图给 12 s
DEFAULT_MAX_IMAGES = 4
VISION_PROMPT_VERSION = "2026-09-14.1"
NO_VISION_TEXT = (
    "当前暂时无法识别图片，请用文字描述一下照片里的情况（例如哪个部件、什么现象），我继续为您排查。"
)

Status = Literal["ok", "skipped", "no_images", "no_vision", "failed"]


class VisionObservation(FaultLocalization):
    """模型输出 schema。"""

    model_config = ConfigDict(extra="forbid")

    observations: list[str] = Field(
        default_factory=list,
        description="图片中可见的客观现象，每条不超过 20 个字（如「滚刷缠绕大量毛发」「底部有烧焦痕迹」）",
    )
    visible_parts: list[str] = Field(
        default_factory=list, description="图片中可辨认的部件名称（如 滚刷、尘盒、滤网、充电座）"
    )


@dataclass
class VisionOutcome:
    status: Status
    observations: list[str] = field(default_factory=list)
    visible_parts: list[str] = field(default_factory=list)
    used_image_ids: list[str] = field(default_factory=list)
    dropped_image_ids: list[str] = field(default_factory=list)
    model_used: str | None = None
    reason: str | None = None
    model_trace: dict[str, Any] | None = None
    fault_localization: dict | None = None
    user_hint: str | None = None  # 需要提示用户的固定文案（无视觉能力时）


INSTRUCTION = (
    "你正在查看用户上传的设备故障照片。输出 findings（part/location/phenomenon/severity/confidence/quote_region）、image_quality（usable/reasons）、model_hint、conflicts_with_text。"
    "部件只用滚刷/边刷/滤网/尘盒/吸口/轮组/传感器/充电触点/电池仓/基站/其他；现象只用缠绕/堵塞/破损/变形/烧焦/漏液/鼓包/污渍/松脱/缺失/正常/其他。"
    "看不清时 usable=false，reasons 从 blurry/too_dark/too_far/wrong_subject/occluded 选择。多图中只要一张可用于判断则 usable=true。型号仅抄录看得清的铭牌，不猜测。"
    "只描述图片中客观可见的现象与可辨认的部件，"
    "不要猜测故障原因、不要给排查步骤、不要编造看不清的细节。"
    "若出现冒烟、烧焦、电池鼓包、漏液、火花等安全相关现象，必须在 observations 中用英文关键词注明"
    "（如 smoke / burnt / swollen battery / leaking）。只输出 JSON。"
)


def image_limit(chain: list[Any]) -> int:
    """链上视觉模型的最小 max_images；都没配置时用默认值。"""
    limits = [
        m.spec.max_images
        for m in chain
        if getattr(m.spec, "vision", False) and getattr(m.spec, "max_images", None)
    ]
    return min(limits) if limits else DEFAULT_MAX_IMAGES


def select_images(refs: list[dict[str, Any]], limit: int) -> tuple[list[dict], list[dict]]:
    """超过单请求上限时只保留最新的 limit 张（按上传顺序，后者为新）。返回 (保留, 丢弃)。"""
    if limit <= 0 or len(refs) <= limit:
        return list(refs), []
    return list(refs[-limit:]), list(refs[:-limit])


def build_messages(
    images: list[tuple[dict[str, Any], bytes]],
    text: str,
    *,
    strategy: str,
    summary: dict[str, Any] | None,
) -> list[Any]:
    content: list[dict[str, Any]] = [
        {"type": "text", "text": f"{INSTRUCTION}\n{wrap_data(text or '（用户未附文字）')}"}
    ]
    for ref, data in images:
        b64 = base64.b64encode(data).decode("ascii")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{ref.get('mime', 'image/jpeg')};base64,{b64}"},
            }
        )
    return [
        SystemMessage(content=compose_system_prompt(strategy, summary)),
        HumanMessage(content=content),
    ]


def _all_skipped_for_vision(exc: ModelInvokeError) -> bool:
    """链上没有任何模型真正看过图：全部因「无视觉能力」或「不可用（缺 key / 未配置）」被跳过。
    models.yaml 校验已保证 needs_vision 链只含视觉模型，所以实际触发多为视觉模型全部不可用、只剩文本模型可服务。"""
    return bool(exc.attempts) and all(a.outcome == "skipped" for a in exc.attempts)


async def observe_images(
    router: ModelRouter | None,
    store: ImageStore | None,
    *,
    session_id: str,
    refs: list[dict[str, Any]],
    text: str,
    lane: str,
    strategy: str = "normal",
    summary: dict[str, Any] | None = None,
    budget_ms: int = VISION_BUDGET_MS,
) -> VisionOutcome:
    fault_refs = [r for r in refs if r.get("purpose", "fault") == "fault"]
    if not fault_refs:
        return VisionOutcome("no_images")
    if router is None or store is None:
        return VisionOutcome(
            "skipped",
            dropped_image_ids=[r["image_id"] for r in fault_refs],
            reason="router or image store unavailable",
            model_trace={"task": TASK, "model_used": "skipped", "lane": lane, "attempts": 1},
        )
    chain = router.registry.chain(TASK, lane)
    keep, dropped = select_images(fault_refs, image_limit(chain))
    images: list[tuple[dict[str, Any], bytes]] = []
    for r in keep:
        got = await store.get(session_id, r["image_id"])
        if got is not None:
            images.append((r, got[1]))
    if not images:
        return VisionOutcome(
            "failed",
            dropped_image_ids=[r["image_id"] for r in fault_refs],
            reason="image bytes not found (expired?)",
        )
    if dropped:
        log.info(
            "vision images truncated session=%s kept=%d dropped=%d",
            session_id,
            len(images),
            len(dropped),
        )
    try:
        res = await router.invoke(
            TASK,
            build_messages(images, text, strategy=strategy, summary=summary),
            VisionObservation,
            budget_ms=budget_ms,
            session_id=session_id,
            lane=lane,
        )
    except ModelInvokeError as exc:
        no_vision = _all_skipped_for_vision(exc)
        log.warning(
            "vision degraded session=%s no_vision=%s reason=%s", session_id, no_vision, exc.reason
        )
        return VisionOutcome(
            "no_vision" if no_vision else "failed",
            used_image_ids=[r["image_id"] for r, _ in images],
            dropped_image_ids=[r["image_id"] for r in dropped],
            reason=exc.reason[:200],
            model_trace={
                "task": TASK,
                "model_used": "skipped",
                "lane": lane,
                "attempts": max(1, len(exc.attempts)),
            },
            user_hint=NO_VISION_TEXT if no_vision else None,
        )
    except CapacityExceeded as exc:
        return VisionOutcome(
            "failed",
            used_image_ids=[r["image_id"] for r, _ in images],
            dropped_image_ids=[r["image_id"] for r in dropped],
            reason=f"CapacityExceeded: {exc}"[:200],
            model_trace={"task": TASK, "model_used": "skipped", "lane": lane, "attempts": 1},
        )
    parsed: VisionObservation = res.parsed
    from app.diagnose.localization import normalize
    localization = normalize(parsed)
    derived = [f"{f['part']}{f['phenomenon']}" for f in localization['findings']]
    obs = [o.strip() for o in parsed.observations if o.strip()][:10]
    obs = list(dict.fromkeys([*obs, *derived]))
    parts = [p.strip() for p in parsed.visible_parts if p.strip()][:10]
    parts = list(dict.fromkeys([*parts, *[f["part"] for f in localization["findings"]]]))
    log.info(
        "vision observed session=%s images=%d observations=%s parts=%s model=%s prompt_ver=%s",
        session_id,
        len(images),
        obs,
        parts,
        res.model_used,
        VISION_PROMPT_VERSION,
    )
    return VisionOutcome(
        "ok",
        fault_localization=localization,
        observations=obs,
        visible_parts=parts,
        used_image_ids=[r["image_id"] for r, _ in images],
        dropped_image_ids=[r["image_id"] for r in dropped],
        model_used=res.model_used,
        model_trace={
            "task": TASK,
            "model_used": res.model_used,
            "lane": res.lane,
            "attempts": max(1, len(res.attempts)),
        },
    )
