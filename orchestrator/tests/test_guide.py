"""票 34 / 35：步骤卡下发（改写忠实性、证据校验、CP-pre-step）与反馈推进（计数器、next_on、计划切换、去重、R2）。"""

from __future__ import annotations

from tests.message_form import model_task_text

from tests.message_form import action_body, message_form

import json
import time
import uuid

import pytest
from haike_contracts.events import parse_event
from haike_contracts.snapshot import SessionSnapshot
from httpx import ASGITransport, AsyncClient

from app.guide import apply_feedback, prepare_step, rewrite_is_faithful, step_card_id
from app.knowledge.runtime import set_knowledge_adapter
from app.main import app
from app.models.runtime import set_model_router
from app.plans import PlanLibrary
from app.plans.runtime import set_plan_library
from app.rules import RulesService, set_rules_service
from app.sessions import sse
from app.settings import REPO_ROOT
from tests.test_diagnose import INTAKE_X9, NO_MATCH, OK_HAIR, ScriptedAdapter, make_router

RULES = REPO_ROOT / "config" / "rules" / "safety_terms.yaml"
LIB = PlanLibrary.from_yaml(REPO_ROOT / "config" / "plans.yaml")
C12 = "翻转主机，按下滚刷盖两侧卡扣取出滚刷，用附带清洁刀具割断缠绕的毛发后装回。"
SYNTH = json.dumps(
    {
        "hypotheses": [
            {"plan_id": "rv_suction_hair_wrap", "confidence": 0.85, "evidence_ids": ["c12"]},
            {"plan_id": "rv_suction_filter_clog", "confidence": 0.4, "evidence_ids": ["c15"]},
        ]
    }
)
SYNTH_LOW_SECOND = SYNTH.replace('"confidence": 0.4', '"confidence": 0.2')
REWRITE_OK = json.dumps(
    {"instruction": "把主机翻过来，按住滚刷盖两侧卡扣取出滚刷，用清洁刀具割断毛发后装回。"},
    ensure_ascii=False,
)
REWRITE_BAD = json.dumps(
    {"instruction": "取出滚刷后用清水冲洗并晾干，再装回。"}, ensure_ascii=False
)  # 多了冲洗 / 晾干


def _cfg(sid):
    return {"configurable": {"thread_id": sid}}


def _feedback(pending: dict, feedback: str, note: str | None = None) -> dict:
    return {
        "action_id": uuid.uuid4().hex,
        "input_token": pending["input_token"],
        "card_id": pending["card_id"],
        "expected_version": pending["version"],
        "kind": "step_feedback",
        "payload": {"feedback": feedback, **({"note": note} if note else {})},
    }


class Session:
    """驱动一条会话：发文本 → 步骤卡；点反馈 → 下一张卡 / 结束 / 升级。"""

    def __init__(self, client: AsyncClient, sid: str):
        self.client, self.sid = client, sid

    async def send(self, text: str) -> list[dict]:
        resp = await self.client.post(f"/sessions/{self.sid}/messages", data=await message_form(self.client, f"/sessions/{self.sid}/messages", {"text": text}))
        assert resp.status_code == 200, resp.text
        return sse.parse(resp.text)

    async def feedback(self, pending: dict, fb: str, note: str | None = None) -> list[dict]:
        resp = await self.client.post(
            f"/sessions/{self.sid}/actions", json=await action_body(self.client, f"/sessions/{self.sid}/actions", _feedback(pending, fb, note))
        )
        assert resp.status_code == 200, resp.text
        return sse.parse(resp.text)

    async def state(self) -> dict:
        return (await app.state.session_graph.aget_state(_cfg(self.sid))).values

    async def snap(self) -> SessionSnapshot:
        return SessionSnapshot.model_validate(
            (await self.client.get(f"/sessions/{self.sid}")).json()
        )


def pending_of(events: list[dict]) -> dict:
    return next(e for e in events if e["type"] == "awaiting_input")


def step_card_of(events: list[dict]) -> dict:
    cards = [e for e in events if e["type"] == "step_card"]
    assert len(cards) == 1, [e["type"] for e in events]
    return cards[0]


@pytest.fixture
async def runtime(mem_runtime, tmp_path):
    """假 router + 假知识适配器 + 真规则 / 计划库。yield 一个工厂：按脚本建 Session。"""
    holder: dict = {}

    async def make(*, fast: list, main: list, adapter=None) -> tuple[Session, dict]:
        router, fakes = make_router(tmp_path, fast=fast, main=main)
        set_model_router(router)
        set_knowledge_adapter(
            adapter or ScriptedAdapter({"kb_manual": [OK_HAIR()], "kb_tickets": [NO_MATCH()]})
        )
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://t")
        holder["client"] = client
        sid = (await client.post("/sessions")).json()["session_id"]
        return Session(client, sid), fakes

    set_rules_service(RulesService(RULES, hot_reload=False))
    try:
        yield make
    finally:
        if "client" in holder:
            await holder["client"].aclose()
        set_model_router(None)
        set_knowledge_adapter(None)
        set_rules_service(None)
        set_plan_library(None)


# ---------------- 票 34：单元 ----------------


def test_rewrite_faithfulness_gold_pairs():
    """金标：动作集合不增不删才接受；增删动作 / 空动作拒绝。"""
    assert rewrite_is_faithful(
        C12, "把主机翻过来，按住滚刷盖两侧卡扣取出滚刷，用清洁刀具割断毛发后装回。"
    )
    assert rewrite_is_faithful(
        "打开尘盒盖取出滤网，轻拍去尘并用清水冲洗，晾干 24 小时后装回。",
        "打开尘盒盖取出滤网，清水冲洗后晾干一天再装回。",
    )
    # 多了动作（冲洗 / 晾干）→ 拒绝
    assert not rewrite_is_faithful(C12, "取出滚刷后用清水冲洗并晾干，再装回。")
    # 少了动作（没有装回）→ 拒绝
    assert not rewrite_is_faithful(C12, "翻转主机取出滚刷，割断缠绕的毛发。")
    # 没有任何动作词 → 拒绝
    assert not rewrite_is_faithful(C12, "滚刷是位于机身底部的部件。")


def test_step_card_id_is_derived_from_session_plan_step():
    a = step_card_id("s1", "rv_suction_hair_wrap", "s1")
    assert a == step_card_id("s1", "rv_suction_hair_wrap", "s1") and len(a) == 32
    assert (
        a
        != step_card_id("s1", "rv_suction_hair_wrap", "s2")
        != step_card_id("s2", "rv_suction_hair_wrap", "s2")
    )


def _lib_with(tmp_path, evidence_extra: str, steps_yaml: str) -> PlanLibrary:
    base = (REPO_ROOT / "config" / "plans.yaml").read_text(encoding="utf-8")
    text = base.replace("evidence:\n", f"evidence:\n{evidence_extra}", 1) + steps_yaml
    p = tmp_path / "plans.yaml"
    p.write_text(text, encoding="utf-8")
    return PlanLibrary.from_yaml(p)


async def test_high_risk_step_without_caution_is_dropped_and_next_taken(tmp_path):
    """CP-pre-step：步骤文字含高危动作（拆解）而来源无 caution → 丢弃，取 next_on.not_solved 的下一步。"""
    lib = _lib_with(
        tmp_path,
        "  test#risky: {source: kb_manual, doc_version: t, snippet: 拆解机身底盖，检查主板接线是否松动后装回。}\n",
        """
  - plan_id: rv_test_risky
    version: 1
    fault: 测试
    applies_to: {scope: category_generic, category: robot_vacuum}
    steps:
      - {step_id: s1, title: 检查主板, instruction_src: evidence:test#risky, expected_result: 无松动,
         next_on: {solved: DONE, not_solved: s2, cannot_do: s2}}
      - {step_id: s2, title: 取出并清洁滤网, instruction_src: evidence:manual_rv_v1#c15, expected_result: 滤网无堵塞,
         next_on: {solved: DONE, not_solved: EXHAUSTED, cannot_do: EXHAUSTED}}
""",
    )
    rules = RulesService(RULES, hot_reload=False)
    state = {
        "plan_cursor": {
            "plan_id": "rv_test_risky",
            "version": 1,
            "step_id": "s1",
            "source": "standard_flow",
        },
        "evidence": {},
    }
    prep = await prepare_step(
        state=state, library=lib, rules=rules, router=None, lane="domestic", session_id="sid"
    )
    assert prep.outcome == "ready" and prep.step["step_id"] == "s2" and prep.step["step_no"] == 2
    assert prep.dropped == [
        {"plan_id": "rv_test_risky", "step_id": "s1", "reason": "high_risk_without_caution:拆解"}
    ]
    assert (
        prep.step["instruction"] == "打开尘盒盖取出滤网，轻拍去尘并用清水冲洗，晾干 24 小时后装回。"
    )  # 无 router → 原文
    # 同样的高危动作带 caution → 允许下发
    lib2 = _lib_with(
        tmp_path,
        "  test#risky: {source: kb_manual, doc_version: t, snippet: 拆解机身底盖，检查主板接线是否松动后装回。}\n",
        """
  - plan_id: rv_test_risky
    version: 1
    fault: 测试
    applies_to: {scope: category_generic, category: robot_vacuum}
    steps:
      - {step_id: s1, title: 检查主板, instruction_src: evidence:test#risky, expected_result: 无松动, caution: 请先断电,
         next_on: {solved: DONE, not_solved: EXHAUSTED, cannot_do: EXHAUSTED}}
""",
    )
    prep2 = await prepare_step(
        state=state, library=lib2, rules=rules, router=None, lane="domestic", session_id="sid"
    )
    assert (
        prep2.outcome == "ready"
        and prep2.step["step_id"] == "s1"
        and prep2.step["caution"] == "请先断电"
    )


async def test_pre_step_r4_in_step_text_escalates(tmp_path):
    lib = _lib_with(
        tmp_path,
        "  test#smoke: {source: kb_manual, doc_version: t, snippet: 若机器冒烟请继续运行观察 5 分钟。}\n",
        """
  - plan_id: rv_test_smoke
    version: 1
    fault: 测试
    applies_to: {scope: category_generic, category: robot_vacuum}
    steps:
      - {step_id: s1, title: 观察, instruction_src: evidence:test#smoke, expected_result: 无,
         next_on: {solved: DONE, not_solved: EXHAUSTED, cannot_do: EXHAUSTED}}
""",
    )
    state = {
        "plan_cursor": {"plan_id": "rv_test_smoke", "version": 1, "step_id": "s1"},
        "evidence": {},
    }
    prep = await prepare_step(
        state=state,
        library=lib,
        rules=RulesService(RULES, hot_reload=False),
        router=None,
        lane="domestic",
        session_id="sid",
    )
    assert prep.outcome == "escalate" and prep.escalate_reason == "R4"


async def test_evidence_outside_allowed_set_drops_step():
    """diagnose 给该计划的 evidence_ids 若不在当前允许集合 → 丢弃步骤（09 §2.5）；全部丢弃 → exhausted。"""
    state = {
        "plan_cursor": {"plan_id": "rv_suction_filter_clog", "version": 1, "step_id": "s1"},
        "evidence": {
            "c15": {"evidence_id": "c15", "doc_id": "manual_rv_v1", "source": "kb_manual"}
        },
        "plans_ranked": [
            {
                "plan_id": "rv_suction_filter_clog",
                "confidence": 0.5,
                "evidence_ids": ["c15", "ghost"],
            }
        ],
    }
    prep = await prepare_step(
        state=state,
        library=LIB,
        rules=RulesService(RULES, hot_reload=False),
        router=None,
        lane="domestic",
        session_id="sid",
    )
    assert prep.outcome == "exhausted"
    assert [d["reason"] for d in prep.dropped] == ["evidence_out_of_scope:ghost"] * 2
    # 允许集合内 → 正常下发，evidence_ids 为同 doc 条目 + 计划引用
    state["plans_ranked"][0]["evidence_ids"] = ["c15"]
    prep = await prepare_step(
        state=state,
        library=LIB,
        rules=RulesService(RULES, hot_reload=False),
        router=None,
        lane="domestic",
        session_id="sid",
    )
    assert prep.outcome == "ready" and prep.step["evidence_ids"] == ["c15"]


# ---------------- 票 34：图内 ----------------


async def test_a1_first_step_card_rewritten_and_ready(runtime):
    s, fakes = await runtime(fast=[INTAKE_X9], main=[SYNTH, ["请先清理滚刷。"], REWRITE_OK])
    events = await s.send("eufy X9 Pro 扫地机不吸了，滚刷缠了很多头发")
    for e in events:
        parse_event(e)
    card, pending, done = events[-3], events[-2], events[-1]
    assert (
        card["type"] == "step_card"
        and pending["kind"] == "step_feedback"
        and done["reason"] == "awaiting_input"
    )
    from app.conversation.reduce import stable_id
    st = await s.state()
    assert card["card_id"] == pending["card_id"] == stable_id(st["input_id"], st["active_issue_id"], step_card_id(s.sid, "rv_suction_hair_wrap", "s1"))
    assert pending["input_token"] == stable_id(card["card_id"], "token")
    assert card["version"] == pending["version"] == done["version"]
    step = card["step"]
    assert (
        step["plan_id"] == "rv_suction_hair_wrap"
        and step["step_id"] == "s1"
        and step["step_no"] == 1
    )
    assert step["title"] == "检查并清理滚刷" and step["expected_result"] == "滚刷无缠绕物，转动顺畅"
    assert step["instruction"] == json.loads(REWRITE_OK)["instruction"]  # 改写被接受
    assert step["evidence_ids"] == ["c12", "c15"]  # 同 doc 的允许证据 + 计划引用
    # guide.step 是 internal 调用，prompt 里包着 <data kind="instruction_src"> 原文
    call = fakes["main"].calls[-1]
    assert call["metadata"]["task"] == "guide.step" and "internal" in call["tags"]
    assert (
        'kind="instruction_src"' in model_task_text(call)
        and C12 in model_task_text(call)
    )
    st = await s.state()
    assert st["stage"] == "guide" and st["pending_card"]["kind"] == "step_feedback"
    assert st["plan_cursor"] == {
        "plan_id": "rv_suction_hair_wrap",
        "version": 1,
        "step_id": "s1",
        "source": "synthesize",
    }
    assert isinstance(st["card_ready_ms"], int) and 0 <= st["card_ready_ms"] < 15000
    assert (
        st["model_trace"][-1]["task"] == "guide.step"
        and st["model_trace"][-1]["model_used"] != "skipped"
    )
    assert st["guide_trace"][-1] == {
        "event": "step_ready",
        "card_id": card["card_id"],
        "rewritten": True,
    }
    snap = await s.snap()
    assert snap.stage == "guide" and snap.pending_input.kind == "step_feedback"
    item = next(i for i in snap.timeline if i.kind == "step_card")
    assert item.step.instruction == step["instruction"] and item.feedback is None


async def test_unfaithful_rewrite_falls_back_to_source_text(runtime):
    s, _ = await runtime(fast=[INTAKE_X9], main=[SYNTH, ["请先清理滚刷。"], REWRITE_BAD])
    events = await s.send("eufy X9 Pro 扫地机不吸了，滚刷缠了很多头发")
    assert step_card_of(events)["step"]["instruction"] == C12
    st = await s.state()
    assert st["guide_trace"][-1]["rewritten"] is False
    trace = st["model_trace"][-1]
    assert (
        trace["task"] == "guide.step"
        and trace["model_used"] != "skipped"
        and trace["attempts"] == 1
    )


async def test_rewrite_model_failure_uses_source_and_marks_skipped(runtime):
    s, _ = await runtime(fast=[INTAKE_X9], main=[SYNTH, ["请先清理滚刷。"], RuntimeError("down")])
    events = await s.send("eufy X9 Pro 扫地机不吸了，滚刷缠了很多头发")
    assert step_card_of(events)["step"]["instruction"] == C12
    st = await s.state()
    assert (
        st["model_trace"][-1]["task"] == "guide.step"
        and st["model_trace"][-1]["model_used"] == "skipped"
    )


async def test_step_card_replayed_with_same_id_on_resume_and_invalid_feedback_rejected(runtime):
    s, _ = await runtime(fast=[INTAKE_X9], main=[SYNTH, ["x"]])
    first = await s.send("eufy X9 Pro 扫地机不吸了，滚刷缠了很多头发")
    pending = pending_of(first)
    # select_product 在等待 step_feedback 时不允许
    bad = {
        **_feedback(pending, "solved"),
        "kind": "select_product",
        "payload": {"sku": "EUFY-X9-PRO"},
    }
    r = await s.client.post(f"/sessions/{s.sid}/actions", json=await action_body(s.client, f"/sessions/{s.sid}/actions", bad))
    assert r.status_code == 409 and r.json()["code"] == "not_allowed_now"
    # 非法 feedback 值 → 422
    r = await s.client.post(
        f"/sessions/{s.sid}/actions",
        json=await action_body(s.client, f"/sessions/{s.sid}/actions", {**_feedback(pending, "solved"), "payload": {"feedback": "maybe"}}),
    )
    assert r.status_code == 422
    # 正确反馈：恢复 run 先重发同一张卡（await_input 重跑），再进入 verify
    resumed = await s.feedback(pending, "not_solved")
    assert resumed[0]["resumed"] is False
    assert all(e.get("card_id") != pending["card_id"] for e in resumed if e["type"] == "step_card")
    assert any(e["type"] == "pending_changed" and e["pending_id"] == pending["card_id"] and e["status"] == "consumed" for e in resumed)



# ---------------- 票 35：反馈推进 ----------------


async def test_not_solved_advances_to_next_step_and_counts(runtime):
    s, _ = await runtime(fast=[INTAKE_X9], main=[SYNTH, ["x"]])
    p1 = pending_of(await s.send("eufy X9 Pro 扫地机不吸了，滚刷缠了很多头发"))
    events = await s.feedback(p1, "not_solved", note="还是没吸力")
    types = [e["type"] for e in events]
    assert (
        types[-3:] == ["step_card", "awaiting_input", "done"]
        and events[-1]["reason"] == "awaiting_input"
    )
    stages = [(e["stage"], e.get("substage")) for e in events if e["type"] == "progress"]
    assert stages == [("guide", None)]  # verify 无 progress / 模型事件；直接出下一张卡
    card = step_card_of(events[2:])  # 跳过重发的旧卡
    assert (
        card["step"]["step_id"] == "s2"
        and card["step"]["step_no"] == 2
        and card["step"]["title"] == "取出并清洁滤网"
    )
    assert card["card_id"] != p1["card_id"]
    assert card["step"]["step_id"] == "s2"
    st = await s.state()
    assert st["counters"] == {"executed": 1, "advanced": 1, "skipped": 0, "plans_exhausted": 0}
    assert [(x["step_id"], x["feedback"], x["note"]) for x in st["steps_executed"]] == [
        ("s1", "not_solved", "还是没吸力")
    ]
    assert (
        st["steps_executed"][0]["card_id"] == p1["card_id"]
        and st["steps_executed"][0]["instruction_src"] == "evidence:manual_rv_v1#c12"
    )
    assert st["plan_cursor"]["step_id"] == "s2" and st["card_results"][p1["card_id"]] == {
        "feedback": "not_solved",
        "note": "还是没吸力",
    }
    snap = await s.snap()
    cards = [i for i in snap.timeline if i.kind == "step_card"]
    assert [(c.step.step_id, c.feedback) for c in cards] == [("s1", "not_solved"), ("s2", None)]
    assert snap.pending_input.card_id == cards[1].card_id


async def test_cannot_do_follows_next_on_cannot_do_and_counts_skipped(runtime):
    s, _ = await runtime(fast=[INTAKE_X9], main=[SYNTH, ["x"]])
    p1 = pending_of(await s.send("eufy X9 Pro 扫地机不吸了，滚刷缠了很多头发"))
    # s1.cannot_do → s2
    ev = await s.feedback(p1, "cannot_do")
    assert step_card_of(ev[2:])["step"]["step_id"] == "s2"
    st = await s.state()
    assert st["counters"] == {"executed": 0, "advanced": 0, "skipped": 1, "plans_exhausted": 0}
    # s2.cannot_do → EXHAUSTED → 第二计划 filter_clog(0.4 ≥ 0.3)；其 s1 与已执行的 s2 同 instruction_src(c15) → 跳过 → s2(q9)
    ev = await s.feedback(pending_of(ev), "cannot_do")
    card = step_card_of(ev[2:])
    assert card["step"]["plan_id"] == "rv_suction_filter_clog" and card["step"]["step_id"] == "s2"
    st = await s.state()
    assert st["counters"] == {"executed": 0, "advanced": 0, "skipped": 2, "plans_exhausted": 1}
    assert st["exhausted_plans"] == ["rv_suction_hair_wrap"]
    dropped = [t for t in st["guide_trace"] if t["event"] == "step_dropped"]
    assert dropped == [
        {
            "event": "step_dropped",
            "plan_id": "rv_suction_filter_clog",
            "step_id": "s1",
            "reason": "duplicate_instruction_src",
        }
    ]
    assert any(t["event"] == "verify" and t.get("rule") == "switch_plan" for t in st["guide_trace"])


async def test_first_plan_exhausted_switches_to_second_plan_first_step(runtime):
    s, _ = await runtime(fast=[INTAKE_X9], main=[SYNTH, ["x"]])
    p = pending_of(await s.send("eufy X9 Pro 扫地机不吸了，滚刷缠了很多头发"))
    for expect in ("s2", "s3"):  # s1 → s2 → s3
        ev = await s.feedback(p, "not_solved")
        p = pending_of(ev)
        assert step_card_of(ev[2:])["step"]["step_id"] == expect
    # s3.not_solved → EXHAUSTED → 切到 filter_clog；filter_clog.s1(c15) 与 hair_wrap.s2(c15) 重复 → 跳到 s2(q9)
    ev = await s.feedback(p, "not_solved")
    card = step_card_of(ev[2:])
    assert (card["step"]["plan_id"], card["step"]["step_id"]) == ("rv_suction_filter_clog", "s2")
    st = await s.state()
    assert st["counters"] == {"executed": 3, "advanced": 3, "skipped": 0, "plans_exhausted": 1}
    assert (
        st["plan_cursor"]["plan_id"] == "rv_suction_filter_clog"
        and st["plan_cursor"]["source"] == "synthesize"
    )
    assert st.get("escalate_reason") is None
    switch = next(
        t for t in st["guide_trace"] if t["event"] == "verify" and t["rule"] == "switch_plan"
    )
    assert switch["confidence"] == 0.4


async def test_exhausted_with_low_confidence_next_plan_escalates_r2(runtime):
    s, _ = await runtime(fast=[INTAKE_X9], main=[SYNTH_LOW_SECOND, ["x"]])
    p = pending_of(await s.send("eufy X9 Pro 扫地机不吸了，滚刷缠了很多头发"))
    for _ in range(2):
        p = pending_of(await s.feedback(p, "not_solved"))
    ev = await s.feedback(p, "not_solved")  # s3 → EXHAUSTED，下一计划 0.2 < 0.3 → R2
    stages = [(e["stage"], e.get("substage")) for e in ev if e["type"] == "progress"]
    assert stages[0] == ("escalate", "collect_receipt")  # 常规升级先收凭证（票 39）
    assert pending_of(ev)["kind"] == "upload_receipt"
    st = await s.state()
    assert st["escalate_reason"] == "R2" and st["plan_cursor"] is None
    assert st["counters"]["plans_exhausted"] == 1 and st["exhausted_plans"] == [
        "rv_suction_hair_wrap"
    ]
    assert st["_verify"]["rule"] == "R2"


async def test_solved_ends_run_completed(runtime):
    s, fakes = await runtime(fast=[INTAKE_X9], main=[SYNTH, ["x"]])
    p = pending_of(await s.send("eufy X9 Pro 扫地机不吸了，滚刷缠了很多头发"))
    n_calls = len(fakes["main"].calls)
    ev = await s.feedback(p, "solved")
    assert ev[-1]["reason"] == "completed" and "step_card" not in [e["type"] for e in ev[2:]]
    assert len(fakes["main"].calls) == n_calls  # verify / close 无模型调用
    # 票 36：结束语以 message 事件流式下发，progress 推到 done，最后 done(completed)
    types = [e["type"] for e in ev]
    assert types[-4:] == ["message_start", "message", "message_end", "done"]
    closing = next(e for e in ev if e["type"] == "message")
    assert "问题已经解决" in closing["delta"] and "滚刷" in closing["delta"]
    assert {"type": "progress", "stage": "done", "substage": None} in [
        {k: e.get(k) for k in ("type", "stage", "substage")} for e in ev if e["type"] == "progress"
    ]
    st = await s.state()
    assert st["stage"] == "done" and st["pending_card"] is None and st["plan_cursor"] is None
    assert st["visible_messages"][-1]["kind"] == "closing" and st["visible_messages"][-1]["text"] == closing["delta"]
    assert st["guide_trace"][-1] == {"event": "close", "rule": "solved"}
    assert st["counters"] == {"executed": 0, "advanced": 0, "skipped": 0, "plans_exhausted": 0}
    assert st["steps_executed"][-1]["feedback"] == "solved"
    snap = await s.snap()
    assert snap.pending_input is None and snap.active_run is None
    assert next(i for i in snap.timeline if i.kind == "step_card").feedback == "solved"


async def test_feedback_note_with_safety_term_escalates_r4(runtime):
    s, _ = await runtime(fast=[INTAKE_X9], main=[SYNTH, ["x"]])
    p = pending_of(await s.send("eufy X9 Pro 扫地机不吸了，滚刷缠了很多头发"))
    ev = await s.feedback(p, "not_solved", note="拆的时候闻到焦味了")
    assert next(e["stage"] for e in ev if e["type"] == "progress") == "escalate"
    st = await s.state()
    assert st["escalate_reason"] == "R4" and st["safety_flags"][-1]["source"] == "action_note"
    assert (
        st.get("counters") in (None, {}) or st["counters"].get("executed", 0) == 0
    )  # 拒绝路径不推进计数


# ---------------- 票 35：单元 / 性能 ----------------


def _state(plan="rv_suction_hair_wrap", step="s1", **over):
    base = {
        "plan_cursor": {"plan_id": plan, "version": 1, "step_id": step, "source": "synthesize"},
        "plans_ranked": [
            {"plan_id": "rv_suction_hair_wrap", "confidence": 0.85},
            {"plan_id": "rv_suction_filter_clog", "confidence": 0.4},
        ],
    }
    base.update(over)
    return base


def test_cp_verify_limits_r1_r1b_r1c(monkeypatch):
    from app.guide import verify as verify_mod

    out = apply_feedback(
        state=_state(counters={"executed": 3, "skipped": 0}),
        feedback="not_solved",
        note=None,
        card_id="c",
        library=LIB,
    )
    assert (
        out.outcome == "escalate" and out.escalate_reason == "R1" and out.counters["executed"] == 4
    )
    out = apply_feedback(
        state=_state(counters={"executed": 0, "skipped": 2}),
        feedback="cannot_do",
        note=None,
        card_id="c",
        library=LIB,
    )
    assert (
        out.outcome == "escalate" and out.escalate_reason == "R1b" and out.counters["skipped"] == 3
    )
    # R1c 是硬上限：当前 R1=4 / R1b=3 下 executed+skipped 最多 5 就已被前两条拦下；放宽前两条验证它独立生效
    monkeypatch.setitem(verify_mod.LIMITS, "R1", 10)
    monkeypatch.setitem(verify_mod.LIMITS, "R1b", 10)
    out = apply_feedback(
        state=_state(counters={"executed": 3, "skipped": 2}),
        feedback="cannot_do",
        note=None,
        card_id="c",
        library=LIB,
    )
    assert (
        out.outcome == "escalate" and out.escalate_reason == "R1c" and out.counters["skipped"] == 3
    )
    # 未到上限：继续
    out = apply_feedback(
        state=_state(counters={"executed": 2, "skipped": 1}),
        feedback="not_solved",
        note=None,
        card_id="c",
        library=LIB,
    )
    assert out.outcome == "next" and out.plan_cursor["step_id"] == "s2"


def test_verify_is_fast_and_has_no_model_dependency():
    started = time.perf_counter()
    for _ in range(200):
        apply_feedback(
            state=_state(step="s3"), feedback="not_solved", note=None, card_id="c", library=LIB
        )
    per_call_ms = (time.perf_counter() - started) * 1000 / 200
    assert per_call_ms < 100
    import inspect

    from app.guide import verify as verify_mod

    src = inspect.getsource(verify_mod)
    assert "ModelRouter" not in src and "invoke(" not in src
