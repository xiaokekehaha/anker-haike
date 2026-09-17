"""每个 task 一个适配器：样本 → 调生产函数 → (准确率分, 附加信息)。全部只依赖 router 与配置，不碰会话存储。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.bakeoff import scoring
from app.bakeoff.samples import Sample
from app.diagnose.query import category_label
from app.models.router import ModelRouter
from app.plans.library import PlanLibrary
from app.sessions.cards import get_catalog
from app.settings import settings

Adaptor = Callable[[ModelRouter, Sample, str], Awaitable[tuple[float, dict[str, Any]]]]
_plans: PlanLibrary | None = None


def plans() -> PlanLibrary:
    global _plans
    if _plans is None:
        _plans = PlanLibrary.from_yaml(settings.plans_config_path)
    return _plans


def _summary(sample: Sample) -> dict[str, Any] | None:
    return sample.input.get("state_summary")


async def run_intake(router: ModelRouter, s: Sample, lane: str) -> tuple[float, dict[str, Any]]:
    from app.intake.extract import extract_intake

    out = await extract_intake(
        router,
        s.input["text"],
        session_id=f"bakeoff-{s.id}",
        lane=lane,
        has_image=bool(s.input.get("has_image")),
        state_summary=_summary(s),
        budget_ms=20_000,
    )
    return scoring.score_intake(out, s.expect), {
        "level": out.emotion["level"],
        "hints": out.product_hints,
        "symptoms": out.symptoms,
        "wants_human": out.wants_human,
        "degraded": out.degrade_reason,
    }


async def run_clarify(router: ModelRouter, s: Sample, lane: str) -> tuple[float, dict[str, Any]]:
    from app.sessions.clarify import make_question

    out = await make_question(
        router,
        s.input.get("reason", "product"),
        s.input["text"],
        strategy=s.input.get("strategy", "normal"),
        summary=_summary(s),
        detail=s.input.get("detail") or {},
        session_id=f"bakeoff-{s.id}",
        lane=lane,
        budget_ms=20_000,
    )
    return scoring.score_clarify(out, s.expect), {
        "question": out.text,
        "model_used": out.model_used,
    }


def _evidence_items(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """样本里的 evidence 简写 {id, source, snippet} → 契约 evidence item。"""
    return [
        {
            "evidence_id": e["id"],
            "source": e.get("source", "kb_manual"),
            "doc_id": e.get("doc_id", "manual_rv_v1"),
            "doc_version": "bakeoff",
            "chunk_id": e["id"],
            "snippet": e["snippet"],
            "score": float(e.get("score", 0.8)),
            "status": "ok",
        }
        for e in raw
    ]


async def run_synthesize(router: ModelRouter, s: Sample, lane: str) -> tuple[float, dict[str, Any]]:
    from app.diagnose.synthesize import synthesize

    lib = plans()
    # 样本没写 category 时按 sku / 产品名从目录反查，不默认成某个品类
    sku, product_name = s.input.get("sku"), s.input.get("product")
    category = s.input.get("category") or next(
        (p.category for p in get_catalog().products if p.sku == sku or p.name == product_name), None
    )
    if not category:
        raise ValueError(f"bakeoff 样本 {s.id} 缺少 category，且 sku / product 不在目录里")
    allowed = lib.allowed_for(category=category, sku=sku)
    state = {
        "text": s.input["text"],
        "symptoms": s.input.get("symptoms") or [],
        "product_confirmed": {"name": product_name or category_label(category)},
        "emotion": {"strategy": s.input.get("strategy", "normal")},
    }
    out = await synthesize(
        router,
        state=state,
        allowed=allowed,
        evidence=_evidence_items(s.input.get("evidence") or []),
        observations=s.input.get("observations") or [],
        budget_ms=20_000,
        max_hypotheses=3,
        session_id=f"bakeoff-{s.id}",
        lane=lane,
    )
    return scoring.score_synthesize(out, s.expect), {
        "ranked": [p["plan_id"] for p in out.get("plans_ranked") or []],
        "dropped": out.get("dropped"),
        "degraded": out.get("degraded"),
    }


async def run_stream(router: ModelRouter, s: Sample, lane: str) -> tuple[float, dict[str, Any]]:
    from app.prompts import reassurance_messages, reply_messages
    from app.sessions.streaming import stream_to_writer

    strategy = s.input.get("strategy", "reassure_first")
    if s.input.get("mode", "reassure") == "reassure":
        primary, fallback = reassurance_messages(
            s.input["text"], strategy=strategy, summary=_summary(s)
        )
    else:
        primary, fallback = reply_messages(
            s.input["text"],
            strategy=strategy,
            summary=_summary(s),
            evidence=_evidence_items(s.input.get("evidence") or []),
            knowledge_status=s.input.get("knowledge_status", "ok"),
            fault_card=s.input.get("fault_card"),
        )
    out = await stream_to_writer(
        lambda _ev: None,
        router,
        "reply.stream",
        primary,
        message_id=f"bk{s.id}",
        budget_ms=20_000,
        session_id=f"bakeoff-{s.id}",
        lane=lane,
        fallback_messages=fallback,
    )
    return scoring.score_stream(out, s.expect), {
        "text": out.text[:200],
        "first_visible_ms": out.first_visible_ms,
        "completed": out.completed,
        "error": out.error,
    }


async def run_summary(router: ModelRouter, s: Sample, lane: str) -> tuple[float, dict[str, Any]]:
    from haike_contracts.common import EscalationSummary

    from app.escalation.polish import polish_summary

    base = EscalationSummary.model_validate(
        {
            "product": s.input.get("product", "eufy X10 Pro Omni"),
            "problem": s.input["problem"],
            "observations": [],
            "hypotheses": [],
            "steps": [],
            "reason": {"rule_id": s.input.get("reason", "R1"), "text": "排障步骤已达上限"},
            "emotion": {"level": "calm", "strategy": "normal"},
            "receipt": {"status": "not_collected"},
            "model_trace": [],
        }
    )
    polished = await polish_summary(
        base, router, session_id=f"bakeoff-{s.id}", lane=lane, budget_ms=20_000
    )
    # 模型成功返回即算「给出结果」（含原文已干净逐字相同、候选被 _safe_wording 拒绝后回退原文）；
    # 只有模型不可用 / 失败才记 None → 0 分
    called_ok = any(r.ok for r in getattr(router, "records", []))
    changed = polished.problem != base.problem or any(
        t.task == "escalate.summary" for t in polished.model_trace
    )
    text = polished.problem if (changed or called_ok) else None
    return scoring.score_summary(base.problem, text, s.expect), {
        "problem": polished.problem,
        "applied": changed,
    }


async def run_rewrite(router: ModelRouter, s: Sample, lane: str) -> tuple[float, dict[str, Any]]:
    from app.diagnose.config import get_retrieval_config
    from app.diagnose.rewrite import rewrite_query

    cfg = get_retrieval_config().query_rewrite
    d = await rewrite_query(
        router,
        original=s.input["original"],
        user_text=s.input["text"],
        product=s.input.get("product", "扫地机器人"),
        symptoms=s.input.get("symptoms") or [],
        cfg=cfg,
        category_label=s.input.get("category_label", "扫地机器人"),
        session_id=f"bakeoff-{s.id}",
        lane=lane,
        budget_ms=20_000,
    )
    return scoring.score_rewrite(d, s.expect), {
        "query": d.query,
        "rejected": d.rejected_reason,
        "candidate": d.detail.get("candidate"),
    }


async def run_grade(router: ModelRouter, s: Sample, lane: str) -> tuple[float, dict[str, Any]]:
    """retrieve.grade：样本给命中片段与期望 verdict；评「逐条判定正确率 + coverage 合法且在期望集合内」。"""
    from app.diagnose.config import get_retrieval_config
    from app.diagnose.grade import grade_hits
    from app.knowledge.adapter import Hit

    hits = [
        Hit(
            evidence_id=h["id"],
            knowledge_id="k",
            chunk_id=h["id"],
            doc_id=h.get("doc_id", "manual_rv_v1"),
            doc_version="bakeoff",
            source=h.get("source", "kb_manual"),
            snippet=h["snippet"],
            score=float(h.get("score", 0.5)),
        )
        for h in s.input["hits"]
    ]
    out = await grade_hits(
        router,
        hits=hits,
        user_text=s.input["text"],
        symptoms=s.input.get("symptoms") or [],
        product=s.input.get("product"),
        cfg=get_retrieval_config().grade,
        budget_ms=20_000,
        session_id=f"bakeoff-{s.id}",
        lane=lane,
    )
    return scoring.score_grade(out, s.expect), {
        "status": out.status,
        "coverage": out.coverage,
        "verdicts": out.verdicts,
        "model_used": out.model_used,
        "reason": out.reason,
    }


async def _put_images(sample: Sample, purpose: str):
    from app.images.store import InMemoryImageStore

    store = InMemoryImageStore()
    sid = f"bakeoff-{sample.id}"
    refs = []
    for mime, data in sample.images:
        ref = await store.put(sid, purpose, data, mime)
        refs.append({**ref.public(), "run_id": "bk"})
    return store, sid, refs


async def run_vision(router: ModelRouter, s: Sample, lane: str) -> tuple[float, dict[str, Any]]:
    from app.diagnose.vision import observe_images

    if not s.images:
        return 0.0, {"status": "no_image_material"}
    store, sid, refs = await _put_images(s, "fault")
    out = await observe_images(
        router,
        store,
        session_id=sid,
        refs=refs,
        lane=lane,
        text=s.input.get("text", ""),
        budget_ms=30_000,
    )
    return scoring.score_vision(out, s.expect), {
        "status": out.status,
        "observations": out.observations,
        "parts": out.visible_parts,
        "reason": out.reason,
        "findings": ((out.fault_localization or {}).get("findings")) or [],
        "model_hint": (out.fault_localization or {}).get("model_hint"),
        "model_hint_verified": (out.fault_localization or {}).get("model_hint_verified"),
        "model_hint_cell": out.reread_cell,
        "reread_verdict": out.reread_verdict,
        "conflicts": ((out.fault_localization or {}).get("conflicts_with_text")) or [],
        # 像素层门控命中时本轮没有任何模型调用，schema 首过率不该按「无记录」记 0
        "gated_without_model_call": out.status == "unusable",
        "metrics": scoring.vision_metrics(out, s.expect),
    }


async def run_receipt(router: ModelRouter, s: Sample, lane: str) -> tuple[float, dict[str, Any]]:
    from app.sessions.receipt import extract_receipt

    if not s.images:
        return 0.0, {"status": "no_image_material"}
    store, sid, refs = await _put_images(s, "receipt")
    out = await extract_receipt(
        router,
        store,
        session_id=sid,
        image_ids=[r["image_id"] for r in refs],
        refs=refs,
        lane=lane,
        budget_ms=30_000,
    )
    return scoring.score_receipt(out, s.expect), {
        "status": out.status,
        "fields": out.fields,
        "unreadable": out.unreadable,
        "reason": out.reason,
    }


ADAPTORS: dict[str, Adaptor] = {
    "intake": run_intake,
    "disambiguate.clarify": run_clarify,
    "diagnose.synthesize": run_synthesize,
    "reply.stream": run_stream,
    "escalate.summary": run_summary,
    "query.rewrite": run_rewrite,
    "retrieve.grade": run_grade,
    "diagnose.vision": run_vision,
    "warranty.receipt_ocr": run_receipt,
}
