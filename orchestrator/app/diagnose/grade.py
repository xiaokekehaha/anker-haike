"""有界充分性评估：质量标记与缺口供代码决定补查，候选和服务状态保持原样。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.diagnose.config import GradeConfig, RetrievalRounds
from app.knowledge.adapter import Hit
from app.knowledge.context import pack_hits, render_evidence
from app.models.queue import CapacityExceeded
from app.models.router import ModelInvokeError, ModelRouter
from app.prompts import compose_system_prompt, wrap_data

log = logging.getLogger("diagnose.grade")

Verdict = Literal["relevant", "irrelevant", "unsure"]
Coverage = Literal["sufficient", "insufficient", "none", "unknown"]
VERDICTS = ("relevant", "irrelevant", "unsure")
COVERAGES = ("sufficient", "insufficient", "none")


class GradeItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    evidence_id: str
    verdict: str


class GradeResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    items: list[GradeItem] = Field(default_factory=list)
    coverage: str = "insufficient"
    missing_symptoms: list[str] = Field(default_factory=list, max_length=12)


@dataclass
class EvidenceAssessment:
    status: Literal["graded", "ungraded", "skipped"]
    coverage: Coverage | None = None
    verdicts: dict[str, str] = field(default_factory=dict)
    evaluated_ids: list[str] = field(default_factory=list)
    missing_symptoms: list[str] = field(default_factory=list)
    model_used: str | None = None
    latency_ms: int = 0
    reason: str | None = None

    @property
    def relevant_ids(self) -> list[str]:
        return [k for k, v in self.verdicts.items() if v == "relevant"]

    def as_trace(self, **extra: Any) -> dict[str, Any]:
        return {
            "event": "grade_result",
            "status": self.status,
            "coverage": self.coverage,
            "verdicts": self.verdicts,
            "evaluated_ids": self.evaluated_ids,
            "missing_symptoms": self.missing_symptoms,
            "model_used": self.model_used,
            "latency_ms": self.latency_ms,
            "reason": self.reason,
            **extra,
        }


# 不写品类：具体设备已经在系统提示的状态层里，这里再写一个品类名，非扫地机品类的片段
# 会被这句话拉低相关性判定。
INSTRUCTION = (
    "下面是用户对设备故障的描述与系统检索到的知识片段。请逐条判断片段是否与该故障直接相关：\n"
    "- relevant：片段描述的现象、部件或步骤与用户症状对应；\n"
    "- irrelevant：片段讨论的是其他故障、其他部件或与症状无关的内容（文档标题、目录、无关章节也算）；\n"
    "- unsure：无法判断。\n"
    "再给出整体判断 coverage：sufficient（已有片段足以支撑一个排障方向）/ insufficient（有相关片段但不够）/ "
    "none（没有相关片段）。\n"
    "未解决工单只能提供反证，不能仅凭它判 sufficient；故障卡与手册同样需要核对是否支持当前问题。\n"
    "missing_symptoms 只能逐字选择下方有效症状中证据尚未覆盖的项目，不得新增原因或部件。\n"
    "不要推测故障原因，不要改写用户描述，evidence_id 只能用给出的。只输出 JSON："
    '{"items":[{"evidence_id":"…","verdict":"relevant|irrelevant|unsure"}],'
    '"coverage":"sufficient|insufficient|none","missing_symptoms":[]}'
)


def normalize_result(raw: GradeResult, allowed_ids: list[str]) -> tuple[dict[str, str], Coverage]:
    """evidence_id 白名单 + 枚举回退（国产链 json_object 不保证枚举）。"""
    verdicts: dict[str, str] = {}
    allowed = set(allowed_ids)
    for it in raw.items:
        eid = str(it.evidence_id).strip()
        if eid not in allowed or eid in verdicts:
            continue
        v = str(it.verdict).strip().lower()
        verdicts[eid] = v if v in VERDICTS else "unsure"
    for eid in allowed_ids:
        verdicts.setdefault(eid, "unsure")
    cov = str(raw.coverage).strip().lower()
    coverage: Coverage = cov if cov in COVERAGES else "unknown"  # type: ignore[assignment]
    if coverage == "sufficient" and not any(v == "relevant" for v in verdicts.values()):
        coverage = "insufficient"  # 自相矛盾时取保守
    return verdicts, coverage


async def grade_hits(
    router: ModelRouter,
    *,
    hits: list[Hit],
    user_text: str,
    symptoms: list[str],
    product: str | None,
    cfg: GradeConfig,
    budget_ms: int,
    session_id: str | None,
    lane: str,
    strategy: str = "normal",
    retrieval: RetrievalRounds | None = None,
) -> EvidenceAssessment:
    limits = retrieval or RetrievalRounds()
    visible = pack_hits(
        hits, max_items=limits.final_k, max_chars=limits.context_chars, item_chars=limits.item_chars
    )
    selection = pack_hits(
        visible.hits, max_items=cfg.max_items, max_chars=limits.context_chars, item_chars=cfg.max_chars
    )
    items = selection.hits
    if not items:
        return EvidenceAssessment("skipped", reason="no_hits")
    ids = [h.evidence_id for h in items]
    snippets = "\n".join(render_evidence(h.as_internal_item()) for h in items)
    messages = [
        (
            "system",
            compose_system_prompt(
                strategy, {"stage": "diagnose", "product": product, "symptoms": symptoms}
            ),
        ),
        (
            "human",
            INSTRUCTION
            + "\n"
            + wrap_data(" ".join([user_text, *symptoms]), kind="user_message")
            + "\n有效症状：\n"
            + wrap_data("\n".join(symptoms), kind="active_symptoms")
            + "\n"
            + wrap_data(snippets, kind="retrieved_snippets"),
        ),
    ]
    try:
        res = await router.invoke(
            "retrieve.grade",
            messages,
            GradeResult,
            budget_ms=budget_ms,
            session_id=session_id,
            lane=lane,
        )
    except (ModelInvokeError, CapacityExceeded, ValidationError) as exc:
        log.warning("retrieve.grade failed session=%s: %s", session_id, str(exc)[:200])
        return EvidenceAssessment(
            "ungraded", coverage="unknown", evaluated_ids=ids, reason=f"model:{type(exc).__name__}"
        )
    verdicts, coverage = normalize_result(res.parsed, ids)
    if coverage == "sufficient" and not any(
        verdicts.get(h.evidence_id) == "relevant" and not h.counter_evidence for h in items
    ):
        coverage = "insufficient"
    out = EvidenceAssessment(
        "graded",
        coverage=coverage,
        verdicts=verdicts,
        evaluated_ids=ids,
        missing_symptoms=[s for s in dict.fromkeys(res.parsed.missing_symptoms) if s in symptoms],
        model_used=res.model_used,
        latency_ms=res.latency_ms,
    )
    log.info(
        "retrieve.grade session=%s coverage=%s relevant=%d/%d model=%s ms=%d",
        session_id,
        coverage,
        len(out.relevant_ids),
        len(ids),
        res.model_used,
        res.latency_ms,
        extra={"event": "grade", "session_id": session_id, "coverage": coverage},
    )
    return out


def apply_assessment(hits: list[Hit], assessment: EvidenceAssessment) -> list[Hit]:
    """评分只标记质量；被误评的首轮片段仍有机会进入最终诊断。"""
    if assessment.status != "graded":
        return hits
    for hit in hits:
        verdict = assessment.verdicts.get(hit.evidence_id)
        if verdict in ("relevant", "irrelevant", "unsure"):
            hit.grade = verdict
    return hits
