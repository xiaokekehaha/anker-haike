"""票 43：回放模式与录制包——键稳定、清单不符即 replay_incompatible、命中标 replay、未命中不借用、A1 断网重放。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from haike_contracts.events import parse_event
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from app.health import router as health_router
from app.knowledge.adapter import HINTS, Hit, KnowledgeScope, ToolResult
from app.knowledge.runtime import set_knowledge_adapter
from app.main import app
from app.models.config import load_models_config
from app.models.fake import ScriptExhausted
from app.models.registry import ModelRegistry
from app.models.router import ModelInvokeError, ModelRouter
from app.models.runtime import set_model_router
from app.replay import (
    Recorder,
    RecordingKnowledgeAdapter,
    RecordingRouter,
    ReplayIncompatible,
    ReplayKnowledgeAdapter,
    ReplayRouter,
    knowledge_key,
    load_package,
    model_key,
)
from app.replay import runtime as replay_runtime
from app.rules import RulesService, set_rules_service
from app.sessions import sse
from app.settings import REPO_ROOT
from tests.message_form import message_form
from tests.scripted_model import ScriptedSemanticModel as FakeChatModel
from tests.test_reply_stream import CONFIG as REPLY_CONFIG

RULES = REPO_ROOT / "config" / "rules" / "safety_terms.yaml"
INTAKE_X9 = json.dumps(
    {
        "emotion_level": "calm",
        "product_hints": ["X9 Pro"],
        "symptoms": ["不吸了", "滚刷缠头发"],
        "wants_human": False,
    },
    ensure_ascii=False,
)
SYNTH_HAIR = json.dumps(
    {
        "hypotheses": [
            {
                "plan_id": "rv_suction_hair_wrap",
                "confidence": 0.85,
                "evidence_ids": ["c12"],
                "rationale": "滚刷缠绕毛发",
            }
        ]
    },
    ensure_ascii=False,
)


def make_router(tmp_path, *, fast: list, main: list):
    """与 tests/test_diagnose.make_router 同构：fast / main / backup 三个假模型，脚本为空即任何调用都失败。"""
    p = tmp_path / "models.yaml"
    p.write_text(REPLY_CONFIG, encoding="utf-8")
    fakes = {
        "fast": FakeChatModel(script=list(fast), name_for_trace="fast"),
        "main": FakeChatModel(script=list(main), name_for_trace="main"),
        "backup": FakeChatModel(script=[]),
    }
    router = ModelRouter(
        ModelRegistry(load_models_config(p), env={"K1": "x", "K2": "x"}),
        model_factory=lambda r, _: fakes[r.alias],
    )
    return router, fakes


class ScriptedAdapter:
    def __init__(self, plan: dict[str, list[ToolResult]]):
        self.plan = plan

    async def hybrid_search(self, kb, query, top_k, allow):
        seq = self.plan.get(kb, [])
        r = seq.pop(0) if seq else ToolResult("no_match", hint=HINTS["no_match"], allowed_count=1)
        r.kb, r.query = kb, query
        return r


def _hit(eid: str, snippet: str, score: float = 0.4) -> Hit:
    return Hit(eid, "k-manual", eid, "manual_rv_v1", "2026-09-12.1", "kb_manual", snippet, score)


def OK_HAIR():
    return ToolResult(
        "ok",
        [_hit("c12", "翻转主机取出滚刷，割断缠绕的毛发"), _hit("c15", "取出滤网清洗", 0.2)],
        allowed_count=2,
    )


def NO_MATCH():
    return ToolResult("no_match", hint=HINTS["no_match"], allowed_count=2)


VERSIONS = {"prompt_ver": "p1", "models_ver": "m1", "kb_ver": "k1", "rules_ver": "r1", "actions_version": "a1"}
SCOPE = KnowledgeScope("confirmed_sku", "robot_vacuum", "EUFY-X9-PRO")
PNG_A = b"\x89PNG\r\n\x1a\n" + b"a" * 20
PNG_B = b"\x89PNG\r\n\x1a\n" + b"b" * 20


def _img(data: bytes) -> dict:
    import base64

    return {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64," + base64.b64encode(data).decode()},
    }


class Out(BaseModel):
    answer: str


# ---- 键与清单 ----


def test_model_key_ignores_session_and_depends_on_task_schema_text_and_image_bytes():
    msgs = [("system", "s"), ("human", "你好")]
    assert model_key("intake", "Out", msgs) == model_key("intake", "Out", list(msgs))
    assert model_key("intake", "Out", msgs) != model_key("reply.stream", "Out", msgs)
    assert model_key("intake", "Out", msgs) != model_key("intake", "Other", msgs)
    assert model_key("intake", "Out", msgs) != model_key("intake", "Out", [("human", "你好！")])
    with_a = [{"role": "user", "content": [{"type": "text", "text": "看图"}, _img(PNG_A)]}]
    with_b = [{"role": "user", "content": [{"type": "text", "text": "看图"}, _img(PNG_B)]}]
    assert model_key("diagnose.vision", "Out", with_a) != model_key(
        "diagnose.vision", "Out", with_b
    )
    assert knowledge_key("kb_manual", " X9  不吸 ", SCOPE, 5) == knowledge_key(
        "kb_manual", "X9 不吸", SCOPE, 5
    )
    assert knowledge_key("kb_manual", "X9 不吸", SCOPE, 5) != knowledge_key(
        "kb_tickets", "X9 不吸", SCOPE, 5
    )


def _save(tmp_path: Path, versions=VERSIONS, case_id="demo") -> Path:
    rec = Recorder(case_id, "demo", versions)
    rec.add_model(
        model_key("intake", "Out", [("human", "hi")]),
        {
            "task": "intake",
            "mode": "invoke",
            "schema": "Out",
            "output": {"answer": "ok"},
            "model_used": "p/m",
        },
    )
    rec.add_model(
        model_key("reply.stream", None, [("human", "hi")]),
        {
            "task": "reply.stream",
            "mode": "stream",
            "text": "你好，",
            "chunks": ["你好", "，"],
            "model_used": "p/m",
        },
    )
    rec.add_knowledge(
        knowledge_key("kb_manual", "q", SCOPE, 5),
        {
            "kb": "kb_manual",
            "status": "ok",
            "hits": [
                {
                    "evidence_id": "c12",
                    "knowledge_id": "k1",
                    "chunk_id": "c12",
                    "doc_id": "manual_rv_v1",
                    "doc_version": "1",
                    "source": "kb_manual",
                    "snippet": "s",
                    "score": 0.4,
                }
            ],
            "allowed_count": 2,
        },
    )
    return rec.save(tmp_path)


def test_manifest_mismatch_raises_replay_incompatible_not_silent(tmp_path):
    _save(tmp_path)
    pkg = load_package(tmp_path, "demo")
    assert pkg.describe()["counts"] == {"model": 2, "knowledge": 1}
    pkg.check(VERSIONS)  # 一致：通过
    with pytest.raises(ReplayIncompatible) as ei:
        pkg.check({**VERSIONS, "prompt_ver": "p2"})
    assert "prompt_ver: recorded='p1' current='p2'" in str(
        ei.value
    ) and "replay_incompatible" in str(ei.value)
    with pytest.raises(ReplayIncompatible, match="kb_ver.*current=missing"):
        pkg.check({**VERSIONS, "kb_ver": None})
    # 包缺失 / 损坏同样是不兼容，绝不静默跑到真实模型
    with pytest.raises(ReplayIncompatible, match="manifest not found"):
        load_package(tmp_path, "nope")
    (tmp_path / "demo" / "events.jsonl").write_text("{bad json\n", encoding="utf-8")
    with pytest.raises(ReplayIncompatible, match="line 1 invalid"):
        load_package(tmp_path, "demo")
    with pytest.raises(ReplayIncompatible, match="cannot record without kb_ver"):
        Recorder("x", "x", {**VERSIONS, "kb_ver": None})


# ---- 回放 Router / Adapter ----


async def test_replay_router_hits_and_misses_without_touching_models(tmp_path):
    _save(tmp_path)
    pkg = load_package(tmp_path, "demo")
    real, fakes = make_router(
        tmp_path, fast=[], main=[]
    )  # 脚本为空：任何真实调用都会 ScriptExhausted
    router = ReplayRouter(real.registry, pkg, stream_delay_s=0)
    res = await router.invoke("intake", [("human", "hi")], Out, budget_ms=1000)
    assert res.parsed.answer == "ok" and res.model_used == "p/m" and res.alias == "replay"
    assert [a.outcome for a in res.attempts] == ["ok"]
    with pytest.raises(ModelInvokeError) as ei:
        await router.invoke("intake", [("human", "other")], Out, budget_ms=1000)
    assert ei.value.reason == "replay_miss" and router.misses[0]["task"] == "intake"
    evs = [
        e
        async for e in router.stream(
            "reply.stream", [("human", "hi")], budget_ms=1000, message_id="m1"
        )
    ]
    assert [e.kind for e in evs] == ["start", "delta", "delta", "end"] and "".join(
        e.text for e in evs
    ) == "你好，"
    assert all(len(f.calls) == 0 for f in fakes.values())  # 真实模型零调用


async def test_replay_knowledge_marks_hits_replay_and_miss_is_unavailable(tmp_path):
    _save(tmp_path)
    ad = ReplayKnowledgeAdapter(load_package(tmp_path, "demo"))
    r = await ad.hybrid_search("kb_manual", "q", 5, SCOPE)
    assert r.status == "replay" and r.hits[0].as_evidence_item()["status"] == "replay"
    assert r.allowed_count == 2 and "回放" in (r.hint or "")
    miss = await ad.hybrid_search("kb_tickets", "q", 5, SCOPE)
    assert miss.status == "unavailable" and miss.hits == [] and "replay_miss" in (miss.detail or "")
    assert ad.hits == 1 and len(ad.misses) == 1


# ---- A1 端到端：录制 → 断网回放 ----


async def _run_a1(client, sid):
    events = sse.parse(
        (
            await client.post(
                f"/sessions/{sid}/messages",
                data=await message_form(client, f"/sessions/{sid}/messages", {"text": "eufy X9 Pro 扫地机不吸了，滚刷缠了很多头发"}),
            )
        ).text
    )
    return events


async def test_a1_recorded_then_replayed_offline_with_evidence_status_replay(mem_runtime, tmp_path):
    set_rules_service(RulesService(RULES, hot_reload=False))
    recorder = Recorder("a1", "A1", VERSIONS)
    real, _fakes = make_router(tmp_path, fast=[INTAKE_X9], main=[SYNTH_HAIR])
    set_model_router(RecordingRouter(real, recorder))
    set_knowledge_adapter(
        RecordingKnowledgeAdapter(
            ScriptedAdapter({"kb_manual": [OK_HAIR()], "kb_tickets": [NO_MATCH()]}), recorder
        )
    )
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            sid = (await client.post("/sessions")).json()["session_id"]
            recorded = await _run_a1(client, sid)
    finally:
        set_model_router(None)
        set_knowledge_adapter(None)
    base = recorder.save(tmp_path / "replay")
    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["versions"] == VERSIONS and manifest["counts"]["knowledge"] == 2
    # intake / synthesize 的 invoke 进包；失败的调用（如脚本耗尽的 guide.step）不入包
    assert {"intake", "diagnose.synthesize"} <= {r["task"] for r in recorder.models.values()}
    failed_tasks = [m["task"] for m in recorder.misses]
    assert "guide.step" not in {r["task"] for r in recorder.models.values()}

    pkg = load_package(tmp_path / "replay", "a1")
    pkg.check(VERSIONS)
    offline, offline_fakes = make_router(tmp_path, fast=[], main=[])
    router = ReplayRouter(offline.registry, pkg, stream_delay_s=0)
    adapter = ReplayKnowledgeAdapter(pkg)
    set_model_router(router)
    set_knowledge_adapter(adapter)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            sid2 = (await client.post("/sessions")).json()["session_id"]
            replayed = await _run_a1(client, sid2)
            state = (
                await app.state.session_graph.aget_state({"configurable": {"thread_id": sid2}})
            ).values
    finally:
        set_model_router(None)
        set_knowledge_adapter(None)
        set_rules_service(None)
    for e in replayed:
        parse_event(e)
    # 同一事件类型序列；真实模型零调用；知识两库都命中录制
    assert [e["type"] for e in replayed] == [e["type"] for e in recorded]
    assert all(len(f.calls) == 0 for f in offline_fakes.values())
    assert router.hits == len(pkg.models) and adapter.hits == 2 and adapter.misses == []
    # 回放未命中集合 == 录制时失败集合（如 guide.step）：同样 miss 走降级，不借其他记录
    assert [m["task"] for m in router.misses] == failed_tasks
    ev = next(e for e in replayed if e["type"] == "evidence")
    assert {i["status"] for i in ev["items"]} == {"replay"}
    assert all(v["status"] == "replay" or v["source"] == "approved_plan" for v in state["evidence"].values())
    assert state["knowledge_status"] == "ok"  # 回放命中等价 ok 路径进入 synthesize / guide
    # 票 19：命中计划的排障轮不再自由回复，本轮可见产物是步骤卡
    assert not [e for e in replayed if e["type"] == "message"]
    assert [e for e in replayed if e["type"] == "step_card"]
    # 一轮完整结束，done 原因与录制一致（有 guide 节点时为 awaiting_input + step_card）
    assert replayed[-1]["type"] == "done" and replayed[-1]["reason"] == recorded[-1]["reason"]
    with pytest.raises(ScriptExhausted):  # 佐证：若真去调模型，假模型会立刻抛出
        offline_fakes["fast"]._next([], None, {})


# ---- 进程级开关与 health ----


def test_runtime_loads_package_only_when_case_id_set_and_fails_loudly_on_mismatch(
    tmp_path, monkeypatch
):
    from app.settings import settings

    _save(tmp_path, versions={**VERSIONS})
    monkeypatch.setattr(settings, "replay_dir", str(tmp_path))
    monkeypatch.setattr(replay_runtime, "versions_now", lambda: dict(VERSIONS))
    replay_runtime.set_replay_package(None)
    replay_runtime._built = False
    monkeypatch.setattr(settings, "replay_case_id", "")
    assert replay_runtime.get_replay_package() is None and replay_runtime.describe() is None
    replay_runtime._built = False
    monkeypatch.setattr(settings, "replay_case_id", "demo")
    try:
        assert replay_runtime.get_replay_package().case_id == "demo"
        assert replay_runtime.describe()["status"] == "ok"
        replay_runtime._built = False
        monkeypatch.setattr(replay_runtime, "versions_now", lambda: {**VERSIONS, "rules_ver": "r9"})
        with pytest.raises(ReplayIncompatible, match="rules_ver"):
            replay_runtime.get_replay_package()
        assert replay_runtime.describe()["status"] == "down"
    finally:
        replay_runtime.set_replay_package(None)
        replay_runtime._built = False


async def test_health_exposes_replay_block_only_in_replay_mode(monkeypatch):
    from app.health import checks

    async def _ok(*_a, **_k):
        return checks.ComponentHealth("ok", 1)

    for name in ("check_db", "check_redis", "check_weknora"):
        monkeypatch.setattr(health_router, name, _ok)
    health_router.aggregator._cache = None
    monkeypatch.setattr(replay_runtime, "describe", lambda: None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        assert "replay" not in (await client.get("/health")).json()
        health_router.aggregator._cache = None
        monkeypatch.setattr(
            replay_runtime, "describe", lambda: {"status": "ok", "case_id": "a1", "title": "A1"}
        )
        body = (await client.get("/health")).json()
    health_router.aggregator._cache = None
    assert body["replay"] == {"status": "ok", "case_id": "a1", "title": "A1"}
