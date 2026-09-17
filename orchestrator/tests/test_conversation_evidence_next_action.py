"""Recorded ce6/9db failures through the real decision and HTTP graph seams."""
from types import SimpleNamespace

import pytest

from app.conversation.interpret import SymptomAnswer, TurnInterpretation
from app.conversation.taxonomy import interview_answer, next_interview
from app.diagnose.vision import VisionOutcome
from app.sessions.clarify import decide, fixed_question, make_question
from tests.test_sessions_clarify import _message_text, _send
from tests.test_vision_graph import (  # noqa: F401
    _client,
    _send_with_images,
    _state,
    img_store,
    l3_services,
)


async def test_product_question_cannot_be_replaced_with_symptom_question():
    class WrongQuestionRouter:
        async def invoke(self, *args, **kwargs):
            return SimpleNamespace(parsed=SimpleNamespace(question="请描述具体故障"),
                                   model_used="fake", lane="domestic", attempts=[1])
    out = await make_question(WrongQuestionRouter(), "product", "有点问题",
                              strategy="normal", summary=None, detail={}, session_id="s", lane="domestic")
    assert "品类" in out.text
    assert "描述具体故障" not in out.text


def narrowed_effect_interview():
    interview = next_interview(None, "i", "a", category="robot_vacuum")
    for iid, quote in [("b", "可以"), ("c", "效果不好")]:
        interview, accepted = interview_answer(interview, SymptomAnswer(
            question_id=interview["question"]["question_id"], answer="yes", quote=quote), quote, iid)
        assert accepted
        if iid == "b":
            interview = next_interview(interview, "i", iid, category="robot_vacuum")
    return interview


def test_effect_answer_gets_specific_multi_select_question():
    result = decide({"category": "robot_vacuum", "symptom_interview": narrowed_effect_interview(),
                     "text": "效果不好", "input_id": "c", "active_issue_id": "i"}, abandoned_card=None)
    assert result.outcome == "clarify"
    question = result.detail["discriminator"]
    assert "可多选" in question["question"]
    assert {o["value"] for o in question["options"]} == {"吸力下降", "拖地异常"}


async def test_image_only_then_noise_and_unknown_model_keeps_category(mem_runtime, img_store, monkeypatch):  # noqa: F811
    import app.conversation.interpret as semantic
    original = semantic.interpret_turn

    async def interpret(router, state, **kwargs):
        if state.get("text") == "运行异响":
            return TurnInterpretation(primary_intent="report_problem", device_relation="current",
                facts=[{"quote": "运行异响", "value": "运行异响", "symptom_code": "abnormal_noise"}]), {"source": "recorded"}
        return await original(router, state, **kwargs)

    calls = []
    async def observe(*args, **kwargs):
        calls.append(kwargs["refs"])
        return VisionOutcome("ok", observations=["扫地机器人停在基站旁"],
                             used_image_ids=[r["image_id"] for r in kwargs["refs"]])

    monkeypatch.setattr(semantic, "interpret_turn", interpret)
    monkeypatch.setattr("app.sessions.graph.observe_images", observe)
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        first = await _send_with_images(client, sid, "")
        assert len(calls) == 1
        assert "输入为空" not in _message_text(first)
        assert "确认" in _message_text(first) and "扫地" in _message_text(first)
        assert (await _state(sid))["product_state"] == "unknown"
        # Replay the original user's sequence before answering the corrected
        # question: useful symptom/model evidence must not exhaust its budget.
        await _send_with_images(client, sid, "有点问题")
        await _send(client, sid, "运行异响")
        last = await _send(client, sid, "x00001")
        assert (await _state(sid)).get("escalate_reason") != "R7"
        assert "确认" in _message_text(last)
        await _send(client, sid, "是")
        after_yes = await _state(sid)
        assert after_yes["category"] == "robot_vacuum", {k: after_yes.get(k) for k in ("clarification", "turn_decision", "visual_product", "stage")}
        await _send(client, sid, "运行异响")
        last = await _send(client, sid, "x00001")
        state = await _state(sid)
        assert state["product_state"] == "category_only"
        assert state.get("escalate_reason") != "R7"
        assert len(calls) == 2
        assert not any(e["type"] == "escalation_summary" and e["summary"]["reason"]["rule_id"] == "R7" for e in last)


WRAPPED_BRUSH = {
    "image_quality": {"usable": True, "reasons": []},
    "model_hint": None,
    "model_hint_verified": False,
    "conflicts_with_text": [],
    "findings": [{"part": "滚刷", "phenomenon": "缠绕", "evidence": "刷体缠绕大量毛发", "cell": "中心"}],
}


def _noise_interpreter(original):
    async def interpret(router, state, **kwargs):
        if state.get("text") == "运行异响":
            return TurnInterpretation(primary_intent="report_problem", device_relation="current",
                facts=[{"quote": "运行异响", "value": "运行异响", "symptom_code": "abnormal_noise"}]), {"source": "recorded"}
        return await original(router, state, **kwargs)
    return interpret


def _signature_facts(state):
    return [f for f in state["issues"][state["active_issue_id"]]["facts"] if f.get("source_kind") == "image_signature"]


async def test_photo_signature_joins_candidates_beside_text_symptom(mem_runtime, img_store, monkeypatch):  # noqa: F811
    """9db 重放（2026-09-17，会话 10c5eeaf）：滚刷缠绕照片 + 文字「运行异响」。

    改动前照片只写观察事实，candidates 被 abnormal_noise 过滤成单一停机计划；现在照片签名写成症状事实，
    hair_wrap 与 motor_fault 同在候选集。部件「滚刷」同时推出待确认的品类线索，仍要用户说「是」。"""
    import app.conversation.interpret as semantic
    monkeypatch.setattr(semantic, "interpret_turn", _noise_interpreter(semantic.interpret_turn))

    async def observe(*args, **kwargs):
        return VisionOutcome("ok", fault_localization=WRAPPED_BRUSH, observations=["滚刷缠绕大量毛发"],
                             used_image_ids=[r["image_id"] for r in kwargs["refs"]])
    monkeypatch.setattr("app.sessions.graph.observe_images", observe)
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        first = await _send_with_images(client, sid, "")
        # 观察句里没有整机词，只靠部件「滚刷」→ 问「是扫地机器人吗」，不静默锁定
        assert "扫地机器人" in _message_text(first) and "确认" in _message_text(first), _message_text(first)
        state = await _state(sid)
        assert state["visual_product"]["category"] == "robot_vacuum" and state["product_state"] == "unknown"
        assert [(f["kind"], f["quote"], f["symptom_codes"], f["plan_ids"]) for f in _signature_facts(state)] == [
            ("symptom", "滚刷缠绕", ["suction_low"], ["rv_suction_hair_wrap"]),
        ]
        # 同一张图重传：读两次，症状事实只有一条
        await _send_with_images(client, sid, "有点问题")
        assert len(_signature_facts(await _state(sid))) == 1
        await _send(client, sid, "运行异响")
        last = await _send(client, sid, "是")
        state = await _state(sid)
        assert state["category"] == "robot_vacuum" and state["product_state"] == "category_only"
        assert set(state["symptom_codes"]) == {"abnormal_noise", "suction_low"}
        ranked = [p["plan_id"] for p in state["plans_ranked"]]
        assert {"rv_suction_hair_wrap", "rv_suction_motor_fault"} <= set(ranked), ranked
        assert last[-1]["reason"] == "awaiting_input", [e["type"] for e in last]


@pytest.mark.usefixtures("img_store")
async def test_generic_parts_do_not_hint_a_category_or_symptom(monkeypatch):
    from app.sessions.graph import vision
    localization = {**WRAPPED_BRUSH, "findings": [{"part": "传感器", "phenomenon": "污渍", "evidence": "有灰"}]}

    async def observe(*args, **kwargs):
        return VisionOutcome("ok", fault_localization=localization, observations=["传感器有灰"], used_image_ids=["pic"])
    monkeypatch.setattr("app.sessions.graph.observe_images", observe)
    monkeypatch.setattr("app.sessions.graph.get_stream_writer", lambda: lambda event: None)
    state = {"session_id": "s", "run_id": "r", "input_id": "in1", "at": "2026-09-17T00:00:00Z",
             "active_issue_id": "i", "product_state": "unknown",
             "issues": {"i": {"issue_revision": 0, "device_ref": {"device_ref_id": "d"}}},
             "image_refs": [{"image_id": "pic", "run_id": "r", "issue_id": "i"}]}
    update = await vision(state)
    assert "visual_product" not in update
    facts = update["issues"]["i"]["facts"]
    assert [f["kind"] for f in facts] == ["observation"] and not _signature_facts({**state, **update})


def test_unread_images_belong_to_issue_and_survive_turn_boundary():
    from app.sessions.graph import _new_fault_images
    refs = [{"image_id": "old", "run_id": "r1", "issue_id": "i"},
            {"image_id": "other", "run_id": "r2", "issue_id": "j"}]
    state = {"image_refs": refs, "run_id": "r3", "active_issue_id": "i"}
    assert [r["image_id"] for r in _new_fault_images(state)] == ["old"]
    state["processed_fault_image_ids"] = ["old"]
    assert _new_fault_images(state) == []


@pytest.mark.parametrize("answer,codes", [("1", {"suction_low"}), ("2", {"mop_failure"}),
                                         ("两者都有", {"suction_low", "mop_failure"})])
async def test_effect_question_accepts_single_and_multiple_answers(mem_runtime, monkeypatch, answer, codes):
    import app.conversation.interpret as semantic
    original = semantic.interpret_turn

    async def interpret(router, state, **kwargs):
        if state.get("text") == "eufy X10 Pro Omni":
            return TurnInterpretation(primary_intent="report_problem", device_relation="current",
                                      product_hints=["eufy X10 Pro Omni"]), {"source": "recorded"}
        if state.get("text") == "效果不好":
            return TurnInterpretation(primary_intent="answer_pending", device_relation="current",
                symptom_answer={"question_id": state["symptom_interview"]["question"]["question_id"],
                                "answer": "yes", "quote": "效果不好"}), {"source": "recorded"}
        return await original(router, state, **kwargs)

    monkeypatch.setattr(semantic, "interpret_turn", interpret)
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        await _send(client, sid, "eufy X10 Pro Omni")
        assert (await _state(sid))["symptom_interview"]["question"]["question"] == "设备按电源后能正常启动吗？"
        await _send(client, sid, "可以")
        assert len((await _state(sid))["symptom_interview"]["candidates"]) == 6, (await _state(sid))["symptom_interview"]
        rows = await _send(client, sid, "效果不好")
        assert "可多选" in _message_text(rows)
        assert not any(e["type"] == "escalation_summary" for e in rows)
        await _send(client, sid, answer)
        state = await _state(sid)
        assert set(state["symptom_codes"]) == codes
        assert state.get("escalate_reason") != "R7"


def test_unavailable_answer_remains_bounded_and_summary_preserves_answers():
    from app.conversation.l3_intents import symptom_question_answer
    from app.escalation.summary import build_summary
    state = {"category": "robot_vacuum", "symptom_interview": narrowed_effect_interview(), "active_issue_id": "i"}
    for iid in ["d", "e"]:
        decision = decide(state, abandoned_card=None)
        assert decision.outcome == "clarify"
        state["symptom_interview"] = decision.detail["symptom_interview"]
        state.update(text="不知道", input_id=iid)
        answer = symptom_question_answer(state).symptom_answer
        state["symptom_interview"], accepted = interview_answer(state["symptom_interview"], answer, state["text"], iid)
        assert accepted
    decision = decide(state, abandoned_card=None)
    assert decision.outcome == "escalate"
    summary = build_summary({**state, **decision.update}, reason="R7", lane="domestic")
    assert "效果不好" in summary.problem and "尚未" not in summary.problem
    assert "暂时无法确认" in summary.reason.text


async def test_unverified_ocr_cannot_confirm_catalog_product(monkeypatch):
    from app.sessions.graph import vision
    localization = {"model_hint": "X10", "model_hint_verified": False,
                    "image_quality": {"usable": True}, "findings": []}
    async def observe(*args, **kwargs):
        return VisionOutcome("ok", fault_localization=localization, observations=[], used_image_ids=["pic"])
    monkeypatch.setattr("app.sessions.graph.observe_images", observe)
    monkeypatch.setattr("app.sessions.graph.get_stream_writer", lambda: lambda event: None)
    state = {"session_id": "s", "run_id": "r", "active_issue_id": "i", "product_state": "unknown",
             "issues": {"i": {"issue_revision": 0, "device_ref": {"device_ref_id": "d"}}},
             "image_refs": [{"image_id": "pic", "run_id": "r", "issue_id": "i"}]}
    update = await vision(state)
    result = decide({**state, **update}, abandoned_card=None)
    assert result.outcome == "clarify"
    assert not result.update.get("product_confirmed")


def test_old_product_counter_does_not_prove_question_was_asked():
    state = {"text": "x00001", "product_hints": ["x00001"],
             "clarification": {"reason": "product", "attempts": 2}}
    result = decide(state, abandoned_card=None)
    assert result.outcome == "clarify"
    assert "未匹配" in fixed_question("product", result.detail)


@pytest.mark.usefixtures("img_store", "l3_services")
async def test_unknown_product_low_resolution_photo_allows_text_category(mem_runtime, monkeypatch):
    async def observe(*args, **kwargs):
        return VisionOutcome("unusable", fault_localization={"image_quality": {"usable": False, "reasons": ["too_far"]}})
    monkeypatch.setattr("app.sessions.graph.observe_images", observe)
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        rows = await _send_with_images(client, sid, "")
        assert not any(e["type"] in {"retake_card", "escalation_summary"} for e in rows)
        assert "品类" in _message_text(rows)


def test_uncertain_selection_cannot_create_a_confirmed_symptom():
    question_state = next_interview(narrowed_effect_interview(), "i", "c")
    answer = SymptomAnswer(question_id=question_state["question"]["question_id"],
                          answer="unknown", selected_families=["吸力下降"], quote="不知道")
    unchanged, accepted = interview_answer(question_state, answer, "不知道", "d")
    assert not accepted and unchanged == question_state


def test_product_answer_binding_preserves_explicit_business_switches():
    from app.conversation.l3_intents import product_question_answer
    state = {"clarification": {"reason": "product", "question": "请告诉我设备品类或型号。"}}
    for text in ["x00001", "00001", "扫地机器人"]:
        answer = product_question_answer({**state, "text": text})
        assert answer.primary_intent == "supplement"
    assert product_question_answer({**state, "text": "查一下订单 x00001"}) is None
    state["history"] = [{"role": "assistant", "kind": "message", "text": "请提供订单号。"}]
    assert product_question_answer({**state, "text": "00001"}) is None
    from app.sessions.graph import route_entry
    assert route_entry({"consult_intent": "order_query", "turn_decision": {
        "primary_intent": "supplement", "product_answered": True,
    }}) == "disambiguate"


async def test_approved_noise_stop_notice_is_publishable_without_creating_risk():
    from app.guide import prepare_step
    from app.rules import RulesService
    from app.sessions.cards import get_plans
    from app.settings import REPO_ROOT

    library = get_plans()
    rules = RulesService(REPO_ROOT / "config/rules/safety_terms.yaml", hot_reload=False)
    result = await prepare_step(state={"plan_cursor": {"plan_id": "rv_suction_motor_fault", "step_id": "s1"}},
                                library=library, rules=rules, router=None, lane="domestic", session_id="noise")
    assert result.outcome == "ready", result.dropped
    assert result.step["instruction"] == library.evidence_snippet("evidence:manual_rv_v1#c30")
    assert "若运行时出现持续异响" in result.step["instruction"]
    assert rules.check_in(text="设备出现焦味", session_id="risk").escalate
    dangerous = rules.pre_step.high_risk_actions[0]
    assert rules.check_pre_step(instruction=dangerous, caution=None, conditional_notice=True).action == "drop"
