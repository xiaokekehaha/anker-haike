"""S2 相关性评分（design.md §3.2）：一次轻量模型调用，对首轮命中逐条给 relevant / irrelevant / unsure，整体给 coverage。

评分不是证据、不进卡片、不改 knowledge_status；只做两件事：
1. 剔除 irrelevant（至少保留 keep_min 条原始分最高的，标 kept_min）；
2. coverage ∈ {sufficient, insufficient, none} 供 S3 代码决策（无相关证据 → 视同无命中，允许一次补检索）。
校验在代码侧：evidence_id 必须在输入集合内，缺失补 unsure，coverage 非法按 insufficient。模型失败 → ungraded，主流程不受影响。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.diagnose.config import GradeConfig
from app.knowledge.adapter import Hit
from app.models.queue import CapacityExceeded
from app.models.router import ModelInvokeError, ModelRouter
from app.prompts import compose_system_prompt, wrap_data

log = logging.getLogger("diagnose.grade")

Verdict = Literal["relevant", "irrelevant", "unsure"]
Coverage = Literal["sufficient", "insufficient", "none"]
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


@dataclass
class EvidenceAssessment:
    status: Literal["graded", "ungraded", "skipped"]
    coverage: Coverage | None = None
    verdicts: dict[str, str] = field(default_factory=dict)
    filtered_ids: list[str] = field(default_factory=list)
    kept_min_ids: list[str] = field(default_factory=list)
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
            "filtered_ids": self.filtered_ids,
            "kept_min_ids": self.kept_min_ids,
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
    "不要推测故障原因，不要改写用户描述，evidence_id 只能用给出的。只输出 JSON："
    '{"items":[{"evidence_id":"…","verdict":"relevant|irrelevant|unsure"}],"coverage":"sufficient|insufficient|none"}'
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
    coverage: Coverage = cov if cov in COVERAGES else "insufficient"  # type: ignore[assignment]
    if coverage == "sufficient" and not any(v == "relevant" for v in verdicts.values()):
        coverage = "insufficient"  # 自相矛盾时取保守
    return verdicts, coverage


def apply_grade(
    hits: list[Hit], verdicts: dict[str, str], *, keep_min: int
) -> tuple[list[Hit], list[str], list[str]]:
    """只剔除 irrelevant；至少保留 keep_min 条（按原始分，反证排后）。返回 (kept, filtered_ids, kept_min_ids)。"""
    for h in hits:
        h.grade = verdicts.get(h.evidence_id)  # type: ignore[assignment]
    kept = [h for h in hits if verdicts.get(h.evidence_id) != "irrelevant"]
    kept_min: list[str] = []
    if len(kept) < keep_min:
        candidates = sorted(
            (h for h in hits if h not in kept), key=lambda h: (h.counter_evidence, -h.score)
        )
        for h in candidates[: keep_min - len(kept)]:
            kept.append(h)
            kept_min.append(h.evidence_id)
        order = {id(h): i for i, h in enumerate(hits)}
        kept.sort(key=lambda h: order[id(h)])
    filtered = [h.evidence_id for h in hits if h not in kept]
    return kept, filtered, kept_min


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
) -> EvidenceAssessment:
    items = hits[: cfg.max_items]
    if not items:
        return EvidenceAssessment("skipped", reason="no_hits")
    ids = [h.evidence_id for h in items]
    snippets = "\n".join(
        f"[{h.evidence_id}] ({h.source}) {(h.full_text or h.snippet)[:200]}" for h in items
    )
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
        return EvidenceAssessment("ungraded", reason=f"model:{type(exc).__name__}")
    verdicts, coverage = normalize_result(res.parsed, ids)
    out = EvidenceAssessment(
        "graded",
        coverage=coverage,
        verdicts=verdicts,
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


def apply_assessment(
    hits: list[Hit], assessment: EvidenceAssessment, *, keep_min: int
) -> list[Hit]:
    """把评分结论作用到命中列表（graded 才过滤），回填 filtered_ids / kept_min_ids。返回保留的命中。"""
    if assessment.status != "graded":
        return hits
    kept, filtered, kept_min = apply_grade(hits, assessment.verdicts, keep_min=keep_min)
    assessment.filtered_ids, assessment.kept_min_ids = filtered, kept_min
    return kept
