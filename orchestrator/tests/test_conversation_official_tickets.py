"""主办方真实工单走完整会话图（模型及知识库均为测试替身）：精确码、症状诊断、质保与交接。"""

import asyncio
import re
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

import app.conversation.interpret as semantic
from app.conversation.interpret import TurnInterpretation
from app.escalation.summary import build_summary, summary_to_text
from app.knowledge.runtime import set_knowledge_adapter
from app.main import app
from app.official.models import OfficialData
from app.official.qa_index import _typed_step, get_qa_index, load_overrides
from app.plans.runtime import get_plan_library
from app.sessions.l3 import NOT_EXECUTABLE_HANDOFF
from tests.conversation_runtime import conversation as conversation_fixture
from tests.fake_qa import QAHitAdapter
from tests.test_conversation_l3 import act, events, interpret_as, said, send, state_of
from tests.test_conversation_l3 import l3_runtime as l3_runtime  # noqa: PLC0414

conversation = conversation_fixture

TICKETS = {t.id: t.body for t in OfficialData().tickets}


@pytest.fixture
def report_intent(monkeypatch):
    async def interpret(router, state, **kwargs):
        return TurnInterpretation(primary_intent="report_problem", device_relation="current"), {"source": "test"}

    monkeypatch.setattr(semantic, "interpret_turn", interpret)


async def _first_turn(ticket: str):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        rows = events(await send(client, sid, TICKETS[ticket]))
        return rows, await state_of(sid)


@pytest.mark.parametrize(
    ("ticket", "sku", "plan_id"),
    [("T18", "T2352", "qa_rv_0147"), ("T11", "T2080", "qa_rv_0481"), ("T16", "T2351", "qa_rv_0056")],
)
async def test_indexed_error_code_gets_the_official_step(l3_runtime, report_intent, ticket, sku, plan_id):
    rows, state = await _first_turn(ticket)
    assert state["product_confirmed"]["sku"] == sku
    card = next(e for e in rows if e["type"] == "step_card")
    assert card["step"]["plan_id"] == plan_id


async def test_hardware_fault_code_goes_straight_to_warranty(l3_runtime, report_intent):
    # T14：4090 墙边传感器，官方 Q&A 判硬件故障 → 不给排障步骤，进入订单 / 凭证收集
    rows, state = await _first_turn("T14")
    assert not [e for e in rows if e["type"] == "step_card"]
    assert state["escalate_reason"] == "R6"


async def test_unindexed_code_is_handed_off_not_guessed(l3_runtime, report_intent):
    # T13：5116 官方未收录 → R5，不套用相近错误码
    rows, state = await _first_turn("T13")
    assert not [e for e in rows if e["type"] == "step_card"]
    assert state["escalate_reason"] == "R5"


async def test_restart_then_warranty_entry_ends_in_the_warranty_flow(l3_runtime, report_intent):
    # T28：2111 滚刷错误，重启后仍未解决才走质保；硬件结论不是第二次操作。
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        rows = events(await send(client, sid, TICKETS["T28"]))
        card = next(e for e in rows if e["type"] == "step_card")
        assert (card["step"]["plan_id"], card["step"]["step_id"]) == ("qa_rv_0256", "s1")
        rows = events(await act(client, sid, "step_feedback", {"feedback": "not_solved"}))
        state = await state_of(sid)
    # 一次真实排障失败后进入订单质保判断；无“对硬件结论反馈失败”的虚假动作。
    assert state["stage"] == "context"
    assert state["counters"]["executed"] == 1
    assert any(t.get("reason") == "handoff_step" for t in state["guide_trace"])
    assert not [e for e in rows if e["type"] == "step_card"]
    assert any(e["type"] == "awaiting_input" for e in rows)


RV_0023_FINE = "The seal ring and tank parts look fine, but the error still shows after reinstalling"
RV_0023_BROKEN = "The seal ring is deformed or broken"
RV_0023_UNCHECKED = "I haven't checked yet"


def test_rv_0023_hardware_conclusion_is_a_confirmation_question():
    # T19：s2「上述检查无异常且重装后仍报错 → 基站硬件问题」改成确认问句，卡片标题来自 qa_overrides.yaml
    plan = get_plan_library().get("qa_rv_0023")
    s1, s2 = plan.step("s1"), plan.step("s2")
    assert s1.kind == "action" and s1.next_on.not_solved == "s2"
    assert s2.kind == "question" and s2.options == [RV_0023_FINE, RV_0023_BROKEN, RV_0023_UNCHECKED]
    assert s2.retry_options == [RV_0023_UNCHECKED]
    assert s2.title == "After checking the clean water tank, which matches what you see?"


@pytest.mark.parametrize("option", [RV_0023_FINE, RV_0023_BROKEN])
async def test_t19_not_solved_asks_which_case_before_the_warranty_check(l3_runtime, report_intent, option):
    # T19：清水箱检查「未解决」不等于检查无异常；先确认是密封圈损坏还是无异常仍报错，再进订单质保判断
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        rows = events(await send(client, sid, TICKETS["T19"]))
        card = next(e for e in rows if e["type"] == "step_card")
        assert (card["step"]["plan_id"], card["step"]["step_id"]) == ("qa_rv_0023", "s1")
        rows = events(await act(client, sid, "step_feedback", {"feedback": "not_solved"}))
        card = next(e for e in rows if e["type"] == "step_card")
        assert card["step"]["step_id"] == "s2" and card["step"]["kind"] == "question"
        assert "hardware problem" not in said(rows) and "warranty" not in said(rows)
        rows = events(await act(client, sid, "step_feedback", {"answer": {"option": option, "text": None, "unavailable": False}}))
        state = await state_of(sid)
    assert state["stage"] == "context"
    assert state["next_action"]["reason"] == "guide_exhausted"
    # 转售后先说为什么（官方排查已走完仍未解决），再索单；不替客户确认在保
    assert "The official troubleshooting for this issue is complete" in said(rows)
    assert "To check the warranty" in said(rows)
    issue = state["issues"][state["active_issue_id"]]
    assert any(option in f["value"] for f in issue["facts"] if f["kind"] == "observation")


@pytest.mark.parametrize("answer", [
    {"option": RV_0023_UNCHECKED, "text": None, "unavailable": False},
    {"option": None, "text": "I do not know. I have not checked the base station seal or reinstalled the tank.", "unavailable": False},
])
async def test_b21_unchecked_answer_resends_the_card_instead_of_concluding(l3_runtime, report_intent, answer):
    # B21：确认题答「还没检查 / 不知道」不能当成检查无异常、说官方排查已完成；带提示重发一次，
    # 再答不上来按原边走，但不算走完的指南（不说 troubleshooting is complete）
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        events(await send(client, sid, TICKETS["T19"]))
        events(await act(client, sid, "step_feedback", {"feedback": "not_solved"}))
        rows = events(await act(client, sid, "step_feedback", {"answer": answer}))
        card = next(e for e in rows if e["type"] == "step_card")["step"]
        assert card["step_id"] == "s2" and "haven't checked this yet" in card["context"]
        assert "troubleshooting for this issue is complete" not in said(rows)
        state = await state_of(sid)
        issue = state["issues"][state["active_issue_id"]]
        assert any(f["polarity"] == "uncertain" for f in issue["facts"] if f["kind"] == "observation")
        rows = events(await act(client, sid, "step_feedback", {"answer": answer}))
        state = await state_of(sid)
    assert "troubleshooting for this issue is complete" not in said(rows)
    assert state["next_action"]["reason"] != "guide_exhausted"


def test_rv_0063_liquid_question_is_split_from_the_foam_check():
    # T26：第 3 段「是否加过第三方清洁液」单独成问句卡；观察泡沫与有泡沫才排水仍是一张操作卡
    plan = get_plan_library().get("qa_rv_0063")
    assert [s.step_id for s in plan.steps] == ["s1", "s2", "s3", "s3b"]
    s3, s3b = plan.step("s3"), plan.step("s3b")
    assert s3.kind == "question" and s3.options == ["Yes", "No", "Not sure"] and s3.next_on.not_solved == "s3b"
    assert s3b.kind == "action" and s3b.title == "Shake the base station's clean water tank and check for foam"
    library = get_plan_library()
    head, tail = library.evidence_snippet(s3.instruction_src), library.evidence_snippet(s3b.instruction_src)
    assert head.startswith("We would like to confirm with you") and "foam" not in head
    assert tail.startswith("After shaking") and tail.endswith("perform the cleaning task.")


@pytest.mark.parametrize(("parts", "message"), [
    ([{}, {"at": "Check the tank"}], "exactly once"),
    ([{}, {"at": "again"}, {"at": "Check the tank. "}], "order"),
    ([{}, {"at": "again", "colour": "red"}], "unknown override keys"),
])
def test_parts_overrides_are_validated(parts, message):
    with pytest.raises(ValueError, match=message):
        _typed_step(1, 1, "Check the tank. Check the tank again.", warranty=False, overrides={1: {"parts": parts}})


def test_parts_rejoin_into_the_original_paragraph():
    # 切出来的文字拼回去就是原段落（只去掉列表符号），不增删原文
    index = get_qa_index()
    for qa_id, entry in load_overrides().items():
        for pos, spec in entry.items():
            if not spec.get("parts"):
                continue
            step = index.guides[qa_id].steps[pos - 1]
            joined = "".join(part.text for part in step.parts)
            assert re.sub(r"[\s-]+", "", joined) == re.sub(r"[\s-]+", "", step.text), (qa_id, pos)


async def test_t26_liquid_answer_is_recorded_before_the_foam_check(l3_runtime, report_intent):
    # T26：未解决两次后先问清洁液使用史（答案写成客户事实），再发泡沫 / 排水操作卡；操作卡未解决才进质保
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        rows = events(await send(client, sid, TICKETS["T26"]))
        cards = [next(e for e in rows if e["type"] == "step_card")["step"]]
        for _ in range(2):
            rows = events(await act(client, sid, "step_feedback", {"feedback": "not_solved"}))
            cards.append(next(e for e in rows if e["type"] == "step_card")["step"])
        assert [(c["step_id"], c["kind"]) for c in cards] == [("s1", "action"), ("s2", "action"), ("s3", "question")]
        rows = events(await act(client, sid, "step_feedback", {"answer": {"option": "Not sure", "text": None, "unavailable": False}}))
        foam = next(e for e in rows if e["type"] == "step_card")["step"]
        assert (foam["step_id"], foam["kind"]) == ("s3b", "action")
        assert foam["instruction"].startswith("After shaking the base station's clean water tank, check for foam.")
        state = await state_of(sid)
        assert state["counters"]["executed"] == 2
        issue = state["issues"][state["active_issue_id"]]
        assert any("Not sure" in f["value"] for f in issue["facts"] if f["kind"] == "observation")
        rows = events(await act(client, sid, "step_feedback", {"feedback": "not_solved"}))
        state = await state_of(sid)
    assert state["stage"] == "context" and state["next_action"]["reason"] == "guide_exhausted"
    assert "To check the warranty" in said(rows)
    # 转人工摘要的排查记录：操作卡记反馈，问句卡记回答
    record = summary_to_text(build_summary(state, reason="R6", lane="domestic"))
    assert "（回答：Not sure）" in record and "Shake the base station's clean water tank and check for foam（已操作，仍有问题）" in record


T36_GONE, T36_CHIRP, T36_OTHER = "The noise is gone", "Still noisy, with a chirping sound", "Still noisy, another kind of sound"


async def _t36_session(client, monkeypatch, conversation):
    symptom = "Tijdens het stofzuigen maakt de stofzuiger enorm veel geluid."
    interpret_as(monkeypatch, {TICKETS["T36"]: TurnInterpretation(
        primary_intent="report_problem", device_relation="current", facts=[{"value": symptom, "quote": symptom}],
    )})
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [
        {"plan_id": "qa_rv_0341", "confidence": 0.9, "evidence_ids": ["chunk-rv-0341"],
         "applicability": "supported", "supported_symptoms": [symptom]},
        {"plan_id": "qa_rv_0316", "confidence": 0.8, "evidence_ids": ["chunk-rv-0316"],
         "applicability": "supported", "supported_symptoms": [symptom]},
    ]}]
    sid = (await client.post("/sessions")).json()["session_id"]
    rows = events(await send(client, sid, TICKETS["T36"]))
    card = next(e for e in rows if e["type"] == "step_card")["step"]
    assert (card["plan_id"], card["step_id"], card["kind"]) == ("qa_rv_0341", "s1", "question")
    return sid


def _answer(option):
    return {"answer": {"option": option, "text": None, "unavailable": False}}


async def test_t36_noise_gone_without_the_brush_goes_to_the_warranty_check(l3_runtime, conversation, report_intent, monkeypatch):
    # T36：rv-0341 诊断树。拆下滚刷后噪音消失 → 官方结论滚刷问题 → 质保判断；没有「未解决」也不换下一条指南
    set_knowledge_adapter(QAHitAdapter("rv-0341", "rv-0316"))
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            sid = await _t36_session(client, monkeypatch, conversation)
            rows = events(await act(client, sid, "step_feedback", _answer(T36_GONE)))
            state = await state_of(sid)
    finally:
        set_knowledge_adapter(None)
    assert not [e for e in rows if e["type"] == "step_card"]
    assert "likely caused by the roller brush" in said(rows)
    assert "We can resolve this by sending" not in said(rows)
    assert state["stage"] == "context" and state["next_action"]["reason"] == "guide_exhausted"


async def test_t36_chirping_tries_mopping_mode_then_goes_to_the_warranty_check(l3_runtime, conversation, report_intent, monkeypatch):
    set_knowledge_adapter(QAHitAdapter("rv-0341", "rv-0316"))
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            sid = await _t36_session(client, monkeypatch, conversation)
            rows = events(await act(client, sid, "step_feedback", _answer(T36_CHIRP)))
            card = next(e for e in rows if e["type"] == "step_card")["step"]
            assert (card["step_id"], card["kind"]) == ("s1d", "action") and "mopping mode" in card["instruction"]
            rows = events(await act(client, sid, "step_feedback", {"feedback": "not_solved"}))
            state = await state_of(sid)
    finally:
        set_knowledge_adapter(None)
    assert "replacement unit" not in said(rows)
    assert state["stage"] == "context" and state["next_action"]["reason"] == "guide_exhausted"


async def test_t36_other_noise_falls_through_to_the_component_guide(l3_runtime, conversation, report_intent, monkeypatch):
    # 其他声音 rv-0341 原文没有覆盖：本指南结束，交给候选里的分部件检查 rv-0316，不直接判换机；
    # rv-0341 不算走完的一条指南，rv-0316 的四项都发完才进质保（不是第一项未解决就停）
    set_knowledge_adapter(QAHitAdapter("rv-0341", "rv-0316"))
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            sid = await _t36_session(client, monkeypatch, conversation)
            rows = events(await act(client, sid, "step_feedback", _answer(T36_OTHER)))
            cards = [next(e for e in rows if e["type"] == "step_card")["step"]]
            rows = await _feedback_until_no_card(client, sid, on_card=cards.append)
            state = await state_of(sid)
    finally:
        set_knowledge_adapter(None)
    assert [(c["plan_id"], c["step_id"]) for c in cards] == [("qa_rv_0316", f"s{i}") for i in range(1, 5)]
    assert state["stage"] == "context" and state["next_action"]["reason"] == "guide_exhausted"


def test_rv_0349_noise_entry_is_split_into_article_question_and_video():
    # B25：rv-0349 一段里是「试文章 + 拆下滚刷后停不停 + 拍视频」，拆成操作卡、问句卡、材料卡；
    # 问句与 rv-0341 第一问标题、选项一致，客户在一条里答过另一条不再问
    plan, library = get_plan_library().get("qa_rv_0349"), get_plan_library()
    assert [(s.step_id, s.kind) for s in plan.steps] == [("s1", "action"), ("s1b", "question"), ("s1c", "material_request")]
    first = get_plan_library().get("qa_rv_0341").step("s1")
    assert (plan.step("s1b").title, plan.step("s1b").options) == (first.title, first.options)
    assert library.evidence_snippet(plan.step("s1b").instruction_src).startswith("Also, please let us know whether the noise stops")


async def test_b26_noise_answer_from_rv_0341_is_not_asked_again_in_rv_0349(l3_runtime, conversation, report_intent, monkeypatch):
    # B26：rv-0341 已答「拆下滚刷仍响、不是吱吱声」，转到 rv-0349 时同一个问题直接沿用，不再发第二遍
    set_knowledge_adapter(QAHitAdapter("rv-0341", "rv-0349"))
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            symptom = "Tijdens het stofzuigen maakt de stofzuiger enorm veel geluid."
            interpret_as(monkeypatch, {TICKETS["T36"]: TurnInterpretation(
                primary_intent="report_problem", device_relation="current", facts=[{"value": symptom, "quote": symptom}])})
            conversation.models["diagnose.synthesize"].script = [{"hypotheses": [
                {"plan_id": "qa_rv_0341", "confidence": 0.9, "evidence_ids": ["chunk-rv-0341"],
                 "applicability": "supported", "supported_symptoms": [symptom]},
                {"plan_id": "qa_rv_0349", "confidence": 0.8, "evidence_ids": ["chunk-rv-0349"],
                 "applicability": "supported", "supported_symptoms": [symptom]},
            ]}]
            sid = (await client.post("/sessions")).json()["session_id"]
            events(await send(client, sid, TICKETS["T36"]))
            rows = events(await act(client, sid, "step_feedback", _answer(T36_OTHER)))
            cards = [next(e for e in rows if e["type"] == "step_card")["step"]]
            assert (cards[0]["plan_id"], cards[0]["step_id"]) == ("qa_rv_0349", "s1")
            rows = events(await act(client, sid, "step_feedback", {"feedback": "not_solved"}))
            card = next((e for e in rows if e["type"] == "step_card"), None)
            state = await state_of(sid)
    finally:
        set_knowledge_adapter(None)
    assert card is not None and (card["step"]["plan_id"], card["step"]["step_id"]) == ("qa_rv_0349", "s1c")
    carried = next(a for a in state["step_attempts"] if a["plan_id"] == "qa_rv_0349" and a["step_id"] == "s1b")
    assert carried["answer"]["option"] == T36_OTHER and carried["answer"]["source"] == "carried"


async def test_b25_free_text_noise_answer_does_not_count_rv_0341_as_walked(l3_runtime, conversation, report_intent, monkeypatch):
    # B25：rv-0341 第一问用文字回答（对不上选项），没走到任何分支：rv-0341 不算走完的指南，rv-0316 四项都发完才进质保
    set_knowledge_adapter(QAHitAdapter("rv-0341", "rv-0316"))
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            sid = await _t36_session(client, monkeypatch, conversation)
            text = "No, the noise does not disappear after removing the roller brush and cover. It is a squeaking sound."
            rows = events(await act(client, sid, "step_feedback", {"answer": {"option": None, "text": text, "unavailable": False}}))
            cards = [next(e for e in rows if e["type"] == "step_card")["step"]]
            rows = await _feedback_until_no_card(client, sid, on_card=cards.append)
            state = await state_of(sid)
    finally:
        set_knowledge_adapter(None)
    assert [(c["plan_id"], c["step_id"]) for c in cards] == [("qa_rv_0316", f"s{i}") for i in range(1, 5)]
    assert state["next_action"]["reason"] == "guide_exhausted"


def test_bp_0114_sixth_paragraph_is_split_and_drops_the_repeated_reset():
    # T53：第 6 段的「Software error → 长按 12 秒重置」与第 2 段重复，不再出卡；出厂按钮损坏先确认再走换机结论
    plan = get_plan_library().get("qa_bp_0114")
    library = get_plan_library()
    ids = [s.step_id for s in plan.steps]
    assert ids[ids.index("s6"):ids.index("s7")] == ["s6", "s6c", "s6d", "s6e"]
    texts = [library.evidence_snippet(plan.step(i).instruction_src) for i in ("s6", "s6c", "s6d", "s6e")]
    assert not any("12 seconds" in t for t in texts)
    assert plan.step("s6").next_on.not_solved == "s6c"
    s6c = plan.step("s6c")
    assert s6c.kind == "question" and s6c.next_on.not_solved == "s6e"
    assert s6c.branches == {"Yes, it was damaged on arrival": "s6d", "No": "s6e"}
    assert plan.step("s6d").kind == "handoff" and plan.step("s6e").kind == "action"


async def _feedback_until_no_card(client, sid, limit=8, on_card=None):
    rows = []
    for _ in range(limit):
        rows = events(await act(client, sid, "step_feedback", {"feedback": "not_solved"}))
        card = next((e["step"] for e in rows if e["type"] == "step_card"), None)
        if card is None:
            break
        if on_card:
            on_card(card)
    return rows


async def test_t55_main_case_troubleshoots_then_checks_order_warranty(l3_runtime, conversation, report_intent, monkeypatch):
    # T55：RMA 表单「S1 Pro Wearable Breast Pump」同名型号由品类词消歧 → 官方 Q&A 排障 → 未解决 → 订单 Anker016 保内 → 收 SOP 证据
    symptom = "It clicks but does not suction."
    interpret_as(monkeypatch, {TICKETS["T55"]: TurnInterpretation(
        primary_intent="report_problem", device_relation="current",
        facts=[{"value": symptom, "quote": symptom}],
    )})
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_bp_0102", "confidence": 0.9, "evidence_ids": ["chunk-bp-0102"],
        "applicability": "supported", "supported_symptoms": [symptom],
    }]}]
    set_knowledge_adapter(QAHitAdapter("bp-0102"))
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            sid = (await client.post("/sessions")).json()["session_id"]
            rows = events(await send(client, sid, TICKETS["T55"]))
            assert not any(e["type"] == "product_card" for e in rows)
            assert next(e for e in rows if e["type"] == "step_card")["step"]["plan_id"] == "qa_bp_0102"
            rows = await _feedback_until_no_card(client, sid)
            state = await state_of(sid)
    finally:
        set_knowledge_adapter(None)
    assert state["product_confirmed"]["sku"] == "T8D04"
    assert state["case_order_no"] == "Anker016" and state["warranty"]["status"] == "in_warranty"
    assert set(state["awaiting_evidence"]) == {"photo_or_video", "serial_number"}


async def test_t29_out_of_warranty_order_is_declined_after_troubleshooting(l3_runtime, conversation, report_intent, monkeypatch):
    symptom = "Water tray will not empty."
    interpret_as(monkeypatch, {TICKETS["T29"]: TurnInterpretation(
        primary_intent="report_problem", device_relation="current",
        facts=[{"value": symptom, "quote": symptom}],
    )})
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_rv_0254", "confidence": 0.9, "evidence_ids": ["chunk-rv-0254"],
        "applicability": "supported", "supported_symptoms": [symptom],
    }]}]
    set_knowledge_adapter(QAHitAdapter("rv-0254"))
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            sid = (await client.post("/sessions")).json()["session_id"]
            first = events(await send(client, sid, TICKETS["T29"]))
            assert next(e for e in first if e["type"] == "step_card")["step"]["plan_id"] == "qa_rv_0254"
            rows = await _feedback_until_no_card(client, sid)
            state = await state_of(sid)
    finally:
        set_knowledge_adapter(None)
    assert state["warranty"]["status"] == "out_of_warranty" and state["stage"] == "done"
    assert "warranty has expired" in said(rows)


@pytest.fixture
def logistics_intent(monkeypatch):
    async def interpret(router, state, **kwargs):
        return TurnInterpretation(primary_intent="logistics_query", device_relation="current"), {"source": "test"}

    monkeypatch.setattr(semantic, "interpret_turn", interpret)


async def test_t2_one_order_with_two_tracking_numbers_is_not_ambiguous(l3_runtime, logistics_intent):
    # T2：一个订单号 + 两个运单号（配件包与主机分开发）是同一订单的两个包裹，不应追问「哪个订单」。
    # 2026-10-09 7.1 复核：客户称 -2 是配件、-3 是主机，与订单记录相反 —— 两条记录照答、告知差异并请客户确认，
    # 不自动互换运单，也不在对象未确认前直接给承运商调查方案。
    rows, _ = await _first_turn("T2")
    text = said(rows)
    assert "Anker002" in text and "Anker1234567-2" in text and "Anker1234567-3" in text
    assert "differs" in text and "confirm" in text.casefold()
    assert not any(e["type"] == "proposal_card" for e in rows)
    assert "which order" not in text.casefold()


async def test_t45_safety_handoff_keeps_dealer_and_serial_facts(l3_runtime, report_intent):
    rows, state = await _first_turn("T45")
    assert state["escalate_reason"] == "R4"
    observations = next(e for e in rows if e["type"] == "escalation_summary")["summary"]["observations"]
    assert "客户填写的 SN：ANKER1234567E" in observations
    assert any("Aeroflow" in o and "authorized dealer" in o for o in observations)


@pytest.mark.parametrize("ticket", ["T42", "T44"])
async def test_physical_damage_skips_troubleshooting(l3_runtime, report_intent, ticket):
    # 部件断裂 / 脱落：排障步骤修不好，直接进质保判断（2026-10-08 Fable 5.1 裁定，63 单回放 T42 先跑了 4 张排障卡）
    rows, state = await _first_turn(ticket)
    assert not [e for e in rows if e["type"] == "step_card"]
    assert state["escalate_reason"] == "R6" or state.get("stage") == "context"


def test_crack_sound_is_not_physical_damage():
    from app.official.damage import physical_damage

    assert physical_damage("When it starts there is a crack sound from the brush") is None
    assert physical_damage("The roller brush came off") is None
    assert physical_damage("The lid of the tank snapped") == "The lid of the tank snapped"


# ---------------------------------------------------------------------------
# P1-3：「从未收到货」不得被读成设备故障（2026-10-09）
#
# 没到手的机器不可能有观察到的故障现象 —— 这是客观约束，不是某一单的补丁。
# 63 单里说「从未收到」的 4 单（T1 T2 T8 T10）金标全部是物流分支，没有一单是排障或质保。
# T1 同一原文实测 8 次有 2 次判成 report_problem，于是回「device troubleshooting → delivery status」。
# ---------------------------------------------------------------------------


def _interpretation(**kw):
    from app.conversation.interpret import TurnInterpretation

    return TurnInterpretation(device_relation="current", **kw)


def test_never_arrived_is_repaired_to_a_logistics_query():
    from app.conversation.interpret import logistics_correction

    text = TICKETS["T1"]
    assert "did not arrive" in text
    fixed = logistics_correction(
        _interpretation(primary_intent="report_problem", secondary_intents=["logistics_query"]), text
    )
    assert fixed.primary_intent == "logistics_query"
    # 次诉求去重：留着会让 tasks.enqueue 发「按顺序处理」的多诉求提示，而这单只有一个诉求
    assert "logistics_query" not in fixed.secondary_intents
    assert "report_problem" not in fixed.secondary_intents


def test_never_arrived_drops_symptom_facts_it_cannot_have():
    """机器没到手，模型顺带抽出来的「故障现象」没有来源，不能进事实库。"""
    from app.conversation.interpret import logistics_correction

    meaning = _interpretation(
        primary_intent="report_problem",
        facts=[
            {"kind": "symptom", "value": "did not arrive", "quote": "The vacuum did not arrive."},
            {"kind": "context", "context_field": "address", "value": "1 Main St",
             "quote": "My address is 1 Main St"},
        ],
    )
    fixed = logistics_correction(meaning, TICKETS["T1"])
    assert [f.kind for f in fixed.facts] == ["context"], "只丢症状，保留地址这类上下文事实"


def test_all_never_arrived_tickets_are_logistics_in_the_gold_set():
    """这条约束在 63 单上零误伤：命中的工单金标必须全是物流分支。

    若将来新增一单「没收到货」却应当走排障，这条用例会先红，提醒重新审视该约束。
    """
    import yaml

    from app.conversation.interpret import NEVER_ARRIVED
    from app.settings import REPO_ROOT

    cases = {c["id"]: c for c in yaml.safe_load(
        (REPO_ROOT / "data/eval/tickets/cases.yaml").read_text(encoding="utf-8"))["cases"]}
    hit = [t.id for t in OfficialData().tickets if NEVER_ARRIVED.search(t.body or "")]
    assert hit, "样例集里应当有「从未收到」的工单"
    assert all(cases[i]["sop"].startswith("logistics") for i in hit), {i: cases[i]["sop"] for i in hit}


def test_a_real_fault_report_is_left_alone():
    """反向用例：真的在报故障时不能被这条约束改判。"""
    from app.conversation.interpret import logistics_correction

    meaning = _interpretation(primary_intent="report_problem")
    assert logistics_correction(meaning, "The vacuum arrived but the roller brush does not spin").primary_intent == "report_problem"
    assert logistics_correction(meaning, TICKETS["T55"]).primary_intent == "report_problem"


def test_replacement_parts_kit_is_not_a_replacement_request():
    """降级路径的同一条约束：T1 的「Only the replacement parts kit」是在描述「收到了什么」。

    关键词表（config/rules/intent_terms.yaml）命中 'replacement' 就判 replacement_request，
    而它在 tasks.PRIORITY 里还高于物流 —— 模型 schema_error 重试耗尽时，这单会去提议换货。
    机器从未到手，没有什么可换。
    """
    from app.conversation.interpret import logistics_correction

    fixed = logistics_correction(
        _interpretation(primary_intent="replacement_request", secondary_intents=["logistics_query"]),
        TICKETS["T1"],
    )
    assert fixed.primary_intent == "logistics_query"
    assert fixed.secondary_intents == []


async def test_the_degraded_path_gets_the_same_repair_as_the_model_path(l3_runtime, monkeypatch):
    """纠正挂在 interpret_turn 的出口上，降级分支不能绕过去。

    模型调用失败恰恰是最容易判错的时候：降级靠关键词凑意图，比模型更容易把
    「没收到货」读成故障或换货 —— T1 的「Only the replacement parts kit」正好命中
    intent_terms 的 'replacement'。这里让模型调用必定失败，走真实降级路径。
    """
    from app.conversation.interpret import interpret_turn
    from app.models.router import ModelInvokeError

    async def always_fails(*a, **kw):
        raise ModelInvokeError("forced", attempts=[])

    class Router:
        invoke = staticmethod(always_fails)

    state = {
        "text": TICKETS["T1"],
        "input_id": "i1",
        "at": "2026-10-09T00:00:00+00:00",
        "history": [{"entry_id": "i1", "session_id": "s1", "run_id": "r1", "kind": "message",
                     "role": "user", "first_seq": 1, "last_seq": 1,
                     "recorded_at": "2026-10-09T00:00:00+00:00", "text": TICKETS["T1"]}],
    }
    meaning, context = await interpret_turn(Router(), state, lane="domestic")
    assert context["source"] == "l3_rules_degraded", "这条用例必须真的走降级路径"
    assert meaning.primary_intent == "logistics_query"
    assert "replacement_request" not in meaning.secondary_intents
    assert "report_problem" not in meaning.secondary_intents


def test_a_genuine_replacement_request_is_left_alone():
    """反向用例：收到了货再要求换货，不受这条约束影响。"""
    from app.conversation.interpret import logistics_correction

    meaning = _interpretation(primary_intent="replacement_request")
    text = "The pump arrived last week but the left side has no suction, I want a replacement."
    assert logistics_correction(meaning, text).primary_intent == "replacement_request"


# ---------------------------------------------------------------------------
# P2：SOP 符合性（2026-10-09）
# ---------------------------------------------------------------------------


def test_overdue_package_states_the_real_reship_reason():
    """P2-3：补发理由要与事实相符。

    T5（Anker005）主机包裹 ETA 9/30 在途逾期，而同一订单的配件包裹 9/15 已送达。
    原来 reship_eligible 固定说「Tracking doesn't show the item as delivered」——
    与「有一包已送达」的事实冲突。理由应当从包裹状态推出来。
    """
    from datetime import date

    from app.backends import logistics

    order = next(o for o in OfficialData().orders if o.order_no == "Anker005")
    text = logistics.sop_text(order, date(2026, 10, 8))
    assert logistics.verdict(order, date(2026, 10, 8)) == "reship_eligible"
    assert "2026-09-30" in text and "estimated delivery date" in text
    assert "doesn't show the item as delivered" not in text, text
    # 退回发件人仍走原来的理由
    returned = next(o for o in OfficialData().orders
                    if any(p.status == "returned" for p in o.packages))
    assert "returned to the sender" in logistics.sop_text(returned, date(2026, 10, 8))


def test_a_replacement_request_with_a_fault_troubleshoots_first():
    """P2-2：主办方 SOP 是「保内**排障无效**可换货」，排障是前置条件。

    T49：吸奶器开不了机 + 想换货，官方 Q&A bp-0123 / bp-0151 有对应条目，
    原行为直接转人工跳过排障。
    """
    from app.sessions.graph import _troubleshoot_before_remedy

    base = {"symptoms": ["can't get them to turn on"]}
    assert _troubleshoot_before_remedy(base, "replacement_request")
    assert _troubleshoot_before_remedy(base, "refund_request")
    # 没有现象可排 / 已排过 / 已在办理中：都不该再绕回排障
    assert not _troubleshoot_before_remedy({}, "replacement_request")
    assert not _troubleshoot_before_remedy({**base, "case_id": "c1"}, "replacement_request")
    assert not _troubleshoot_before_remedy({**base, "requested_remedy": "replace"}, "replacement_request")
    assert not _troubleshoot_before_remedy(
        {**base, "steps_executed": [{"feedback": "not_solved"}]}, "replacement_request")
    # 与排障无关的诉求不受影响
    assert not _troubleshoot_before_remedy(base, "address_update")
    assert not _troubleshoot_before_remedy(base, "order_change")


def test_no_order_number_given_is_not_reported_as_a_failed_lookup():
    """P2-4：客户没给过订单号时不能说「没查到订单」，并且要说明为什么现在谈保修。

    T14 是 App 自动生成的报障表单，通篇没有订单号；官方 Q&A rv-0028 已把 4090 判为硬件故障。
    """
    from app.sessions.l3 import customer_gave_order_no, hardware_basis

    t14 = {"text": TICKETS["T14"], "history": []}
    assert not customer_gave_order_no(t14), "T14 原文没有订单号"
    assert customer_gave_order_no({"text": "My order is Anker001", "history": []})

    basis = hardware_basis({**t14, "diagnose_outcome": {"mode": "warranty", "reason": "hardware_malfunction"}})
    assert basis and "hardware malfunction" in basis and "official guidance" in basis
    # 来路不明时不编理由
    assert hardware_basis({"diagnose_outcome": {"mode": "evidence"}}) is None
    assert hardware_basis({}) is None
    # 官方指南走完仍未解决（T19 / T36）：说明转售后的原因
    assert "troubleshooting for this issue is complete" in hardware_basis({"next_action": {"reason": "guide_exhausted"}})
    assert hardware_basis({"next_action": {"reason": "no_supported_followup"}}) is None


def test_read_only_lookups_do_not_announce_a_processing_order():
    """P2-5：查询类诉求一轮答完，不该先播报「按顺序处理」。

    T7：问物流 + 问订单，都是从同一张订单读字段。
    """
    from app.conversation.tasks import announces_order

    assert not announces_order(["logistics_query", "order_query"])
    assert not announces_order(["logistics_query"])
    # 真的要分轮办的仍然播报
    assert announces_order(["replacement_request", "logistics_query"])
    assert announces_order(["report_problem", "order_query"])


def test_closing_line_does_not_quote_a_truncated_or_question_title():
    """P2-5：结束语不引述被截断的标题或 Q&A 的那句问句（T12 实测引了带省略号的问句）。"""
    from app.sessions.graph import closing_text

    truncated = closing_text({"steps_executed": [
        {"feedback": "solved", "title": 'What Should I do If my T2353 shows clean water insuffic…'}]})
    assert "…" not in truncated and "After following the steps" in truncated

    question = closing_text({"steps_executed": [
        {"feedback": "solved", "title": "Why can't my pump power on?"}]})
    assert "did the trick" not in question

    plain = closing_text({"steps_executed": [
        {"feedback": "solved", "title": "Clean the roller brush"}]})
    assert '"Clean the roller brush" did the trick' in plain


def test_order_change_needs_an_explicit_request():
    """P2-1：order_change 必须有明确的「改订单」原话。

    只靠提示词约束不住：加上这个意图后实测 T1「Was the vacuum shipped?」与
    T9 开头的「inquire about the shipping」都被判成 order_change，一路走到 warranty_replace。
    """
    from app.conversation.interpret import logistics_correction

    def as_change(text):
        return logistics_correction(
            _interpretation(primary_intent="order_change", secondary_intents=["logistics_query"]), text
        )

    # 真的要求别发货的只有 T9
    assert as_change(TICKETS["T9"]).primary_intent == "order_change"
    # 其余只是在问物流，必须退回去
    for tid in ("T1", "T5", "T7", "T2", "T8", "T10"):
        out = as_change(TICKETS[tid])
        assert out.primary_intent == "logistics_query", (tid, out.primary_intent)
        assert "order_change" not in out.secondary_intents
        assert out.secondary_intents == [], (tid, out.secondary_intents)


def test_curly_apostrophes_do_not_defeat_the_text_rules():
    """主办方工单里的撇号多是 ’ 而不是 '（63 单 15 处）。

    T9 的「don’t」曾因此整条漏掉 —— 这不是 T9 的特例，是所有带撇号规则的共同前提。
    """
    from app.conversation.interpret import logistics_correction

    straight = "If you have not shipped, don't and let's talk about your other products."
    curly = straight.replace("'", "\u2019")
    for text in (straight, curly):
        out = logistics_correction(_interpretation(primary_intent="order_change"), text)
        assert out.primary_intent == "order_change", repr(text)


def test_an_unexecutable_request_never_becomes_a_replacement():
    """办不了的诉求没有服务单类型，不能被 requested_type 的兜底悄悄变成换货。

    实测 order_change 曾一路走到 warranty_replace。
    """
    import pytest

    from app.sessions.l3 import NOT_EXECUTABLE_TEXT, requested_type

    assert requested_type({"requested_remedy": "refund"}) == "refund"
    assert requested_type({"requested_remedy": None}) == "replace"  # 排障升级默认换货
    for remedy in ("address_update", "order_change"):
        assert remedy in NOT_EXECUTABLE_TEXT
        with pytest.raises(AssertionError):
            requested_type({"requested_remedy": remedy})


def test_an_explicit_hold_request_is_kept_whatever_the_model_reads():
    """P2-1：T9 的「别发货」不能因为模型只读到后半句就被丢掉。

    T9 原文是「If you have not shipped, don't and let's first talk about your other products」。
    模型稳定地把后半句读成 product_question，于是前半句这个有时效性的诉求整个消失
    （两轮测评都复现：只回了发货日就结束）。明确的要求不该取决于模型挑了哪半句。
    """
    from app.conversation.interpret import logistics_correction

    for primary in ("product_question", "logistics_query"):
        out = logistics_correction(_interpretation(primary_intent=primary), TICKETS["T9"])
        assert "order_change" in out.secondary_intents, primary
        assert out.primary_intent == primary, "不抢主诉求，只把漏掉的诉求补进队列"

    # order_query 会被既有规则纠成 logistics_query（T9 问的是发货），order_change 仍要补上
    out = logistics_correction(_interpretation(primary_intent="order_query"), TICKETS["T9"])
    assert out.primary_intent == "logistics_query"
    assert "order_change" in out.secondary_intents

    # 没有这句明确要求的工单不会被补上
    for tid in ("T1", "T5", "T7", "T55"):
        out = logistics_correction(_interpretation(primary_intent="logistics_query"), TICKETS[tid])
        assert "order_change" not in out.secondary_intents, tid


# ---------------------------------------------------------------------------
# T9：一句话两个诉求 —— 问主机物流 + 「未发货就先别发」（2026-10-09 11:48 复测三次均错）
#
# 实测路径 understand → service_context → commit_issue：不可执行分支说了一句「已转交」就结束，
# 案件仍 open、没有交接记录，排在后面的物流查询永远 pending。话术描述的是一个没发生的动作。
# 根因是 finish() 只在 completed_task_intent 非空时才回任务队列，而主诉求直接进来时它是空的。
# ---------------------------------------------------------------------------


def _t9_intent(monkeypatch, primary, secondary):
    async def interpret(router, state, **kwargs):
        if state.get("entry") == "message" and state.get("text") == TICKETS["T9"]:
            return TurnInterpretation(
                primary_intent=primary, secondary_intents=secondary, device_relation="current",
                request_quotes={"logistics_query": "I am writing to inquire about the shipping of the vacuum I purchased in the 7th."},
            ), {"source": "test"}
        return TurnInterpretation(primary_intent="logistics_query", device_relation="current"), {"source": "test"}

    monkeypatch.setattr(semantic, "interpret_turn", interpret)


async def _case_detail(client, rows):
    case_id = next(e["case_id"] for e in reversed(rows) if e["type"] == "case_changed")
    return (await client.get(f"/admin/api/cases/{case_id}")).json()


@pytest.mark.parametrize(("primary", "secondary"), [("order_change", ["logistics_query"]), ("logistics_query", ["order_change"])])
async def test_t9_hold_request_is_queued_and_the_shipping_question_is_still_answered(l3_runtime, monkeypatch, primary, secondary):
    """无论模型先读到哪半句：暂缓诉求真正进人工队列，物流事实照样答，两者缺一不可。"""
    _t9_intent(monkeypatch, primary, secondary)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        rows = events(await send(client, sid, TICKETS["T9"]))
        text = said(rows)
        # 物流事实：主机预售 10/20 发货、滤网 9/12 已送达
        assert "expected to ship on 2026-10-20" in text and "delivered on 2026-09-12" in text, text
        # 不声称已暂停，不进换货排障
        assert "paused" not in text.casefold() and "on hold" not in text.casefold()
        assert not any(e["type"] in {"proposal_card", "step_card", "product_card"} for e in rows)
        # 案件真的进了人工队列，交接摘要保留客户原话（条件「if you have not shipped」不能丢）
        case = await _case_detail(client, rows)
        assert case["status"] == "awaiting_approval"
        assert [e["payload"]["requested"] for e in case["events"] if e["type"] == "review_requested"] == ["order_change"]
        reason = case["handoff_summary"]["reason"]["text"]
        assert reason.startswith(NOT_EXECUTABLE_HANDOFF["order_change"]) and "If you have not shipped" in reason
        # 任务队列：暂缓等人工，物流已答完，没有悬而未决的 pending
        state = await state_of(sid)
        queue = {t["intent"]: t["status"] for t in state["issues"][state["active_issue_id"]]["task_queue"]}
        assert queue == {"order_change": "waiting_human", "logistics_query": "done"}, queue
        assert state["stage"] == "awaiting_human"


async def test_t9_repeating_the_hold_request_does_not_queue_it_twice(l3_runtime, monkeypatch):
    """同一诉求再说一遍：案件状态、review_requested 与交接摘要都不重复写。"""
    _t9_intent(monkeypatch, "order_change", ["logistics_query"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        first = events(await send(client, sid, TICKETS["T9"]))
        again = events(await send(client, sid, TICKETS["T9"]))
        assert not any(e["type"] == "error" for e in again), again
        case = await _case_detail(client, first)
        kinds = [e["type"] for e in case["events"]]
        # 交接摘要两条：入队时一条、物流查到后补入包裹状态一条（I8）；重复诉求不再多写
        assert kinds.count("review_requested") == 1 and kinds.count("handoff_summary") == 2, kinds
        state = await state_of(sid)
        queue = [(t["intent"], t["status"]) for t in state["issues"][state["active_issue_id"]]["task_queue"]]
        assert queue.count(("order_change", "waiting_human")) == 1, queue


async def test_a_hold_request_alone_is_queued_and_the_turn_ends_cleanly(l3_runtime, monkeypatch):
    """只有暂缓诉求、没有别的任务：交接后不报错、不卡在进行中。"""
    _t9_intent(monkeypatch, "order_change", [])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        rows = events(await send(client, sid, TICKETS["T9"]))
        assert not any(e["type"] == "error" for e in rows), rows
        assert (await _case_detail(client, rows))["status"] == "awaiting_approval"
        snap = (await client.get(f"/sessions/{sid}")).json()
        assert snap["pending_input"] is None and snap["active_run"] is None


# ---------------------------------------------------------------------------
# 2026-10-09 13:15 复核（round3）：交接去重粒度与等人工后的推进规则
#
# 诉求的身份是「类型 + 原话 + 条件」，不是类型；任务能否继续取决于等待原因，不是优先级。
# 上一轮按类型去重、按优先级推进，于是：改口被吞、请人工后排障被推进、
# 人工驳回后任务仍等人工且再提诉求撞非法迁移。存储半途失败的情形与比赛无关，不在此覆盖。
# ---------------------------------------------------------------------------

HOLD = "If you have not shipped Anker008, hold it and tell me its shipping date."
CANCEL = "Actually cancel my whole Anker008 order instead of holding it."


def _order_change_intents(monkeypatch):
    async def interpret(router, state, **kwargs):
        text = state.get("text") or ""
        if state.get("entry") == "message" and text == HOLD:
            return TurnInterpretation(
                primary_intent="order_change", secondary_intents=["logistics_query"], device_relation="current",
                request_quotes={"logistics_query": "tell me its shipping date"},
            ), {"source": "test"}
        if state.get("entry") == "message" and text == CANCEL:
            return TurnInterpretation(primary_intent="order_change", device_relation="current"), {"source": "test"}
        return TurnInterpretation(primary_intent="supplement", device_relation="current"), {"source": "test"}

    monkeypatch.setattr(semantic, "interpret_turn", interpret)


async def _queue_of(sid):
    state = await state_of(sid)
    return [(t["intent"], t["status"], t["quote"]) for t in state["issues"][state["active_issue_id"]]["task_queue"]]


async def _decide(client, sid, decision):
    case = next(c for c in (await client.get("/admin/api/cases/queue")).json()["items"] if c["session_id"] == sid)
    response = await client.post(f"/admin/api/cases/{case['case_id']}/decision", json={
        "decision_id": str(uuid.uuid4()), "expected_revision": case["revision"], "decision": decision, "note": "handled",
    })
    assert response.status_code == 200, response.text
    for _ in range(100):
        if not app.state.run_manager.is_live(response.json()["run_id"]):
            break
        await asyncio.sleep(0.01)
    return case["case_id"]


async def test_a_changed_hold_request_reaches_the_desk_not_the_old_one(l3_runtime, monkeypatch):
    """P1：先要暂停、再改成取消整单 —— 同属 order_change，但不是同一个诉求。人工必须看到最新原话。"""
    _order_change_intents(monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        first = events(await send(client, sid, HOLD))
        rows = events(await send(client, sid, CANCEL))
        assert not any(e["type"] == "error" for e in rows), rows
        case = await _case_detail(client, first)
        assert case["status"] == "awaiting_approval"
        kinds = [e["type"] for e in case["events"]]
        assert kinds.count("review_requested") == 1 and kinds.count("request_changed") == 1, kinds
        assert kinds.count("handoff_summary") == 3  # 暂停入队 + 物流补入 + 改口重写
        assert CANCEL in case["handoff_summary"]["reason"]["text"]
        queue = await _queue_of(sid)
        held = [q for q in queue if q[0] == "order_change"]
        assert held == [("order_change", "waiting_human", CANCEL)], queue


async def test_a_rejected_hold_request_settles_its_task_and_a_new_request_queues_again(l3_runtime, monkeypatch):
    """P2：人工驳回后任务不能仍 waiting_human；客户再提同类诉求要能重新入队，不能撞非法迁移。"""
    _order_change_intents(monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        events(await send(client, sid, HOLD))
        case_id = await _decide(client, sid, "reject")
        state = await state_of(sid)
        assert state["stage"] == "done"
        assert [q[:2] for q in await _queue_of(sid)] == [("order_change", "done"), ("logistics_query", "done")]
        rows = events(await send(client, sid, CANCEL))
        assert not any(e["type"] == "error" for e in rows), [e for e in rows if e["type"] == "error"]
        assert "passed your request" in said(rows)
        case = (await client.get(f"/admin/api/cases/{case_id}")).json()
        assert case["status"] == "awaiting_approval"
        transitions = [e["payload"]["to"] for e in case["events"] if e["type"] == "status_changed"]
        assert transitions == ["awaiting_approval", "rejected", "proposing", "awaiting_approval"], transitions
        assert CANCEL in case["handoff_summary"]["reason"]["text"]
        # 已驳回的旧诉求保持 done，不会被新一句改回等人工；单意图一轮不建新任务，案件本身就是人工队列
        assert [q[:2] for q in await _queue_of(sid)] == [("order_change", "done"), ("logistics_query", "done")]


async def test_asking_for_a_colleague_does_not_start_the_pending_troubleshooting(l3_runtime, monkeypatch):
    """P2：换货单上请人工处理后，排在后面的排障任务不能被自动推进；只有查询类任务可以继续。"""
    text = "左侧吸奶器没有吸力，订单 Anker016，我要换货，顺便帮我排查一下"
    interpret_as(monkeypatch, {
        text: TurnInterpretation(primary_intent="replacement_request", secondary_intents=["report_problem"], device_relation="current"),
        "SN: T8D04121ABCD": TurnInterpretation(primary_intent="supplement", facts=[
            {"kind": "context", "context_field": "serial_number", "value": "T8D04121ABCD", "quote": "SN: T8D04121ABCD"},
        ]),
    })
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        await send(client, sid, text)
        await send(client, sid, "照片", images=1)
        await send(client, sid, "SN: T8D04121ABCD")
        snap = (await client.get(f"/sessions/{sid}")).json()
        assert (snap.get("pending_input") or {}).get("kind") == "confirm_proposal", snap.get("pending_input")
        rows = events(await act(client, sid, "decline_proposal", {"reason": "request_human"}))
        assert "Next up" not in said(rows), said(rows)
        assert not any(e["type"] == "step_card" for e in rows)
        state = await state_of(sid)
        assert state["stage"] == "awaiting_human"
        assert [q[:2] for q in await _queue_of(sid)] == [("replacement_request", "waiting_human"), ("report_problem", "pending")]


async def test_t11_device_prompt_gets_the_official_eb1l_steps(l3_runtime, monkeypatch):
    """T11：推送文案「Click to contact customer service」被模型判成 request_human → 服务端按来源纠正，走 EB1L 官方步骤。"""
    async def interpret(router, state, **kwargs):
        return TurnInterpretation(
            primary_intent="request_human", device_relation="current",
            human_request_quote="Click to contact customer service for assistance",
            facts=[{"value": "error while adding clean water", "quote": "The robot encountered an error while adding clean water"}],
        ), {"source": "test"}

    monkeypatch.setattr(semantic, "interpret_turn", interpret)
    rows, state = await _first_turn("T11")
    assert state["turn_decision"]["escalation_trigger"] is None
    assert not [e for e in rows if e["type"] == "escalation_summary"]
    card = next(e for e in rows if e["type"] == "step_card")
    assert card["step"]["plan_id"] == "qa_rv_0481"


async def test_t11_degraded_path_does_not_read_push_text_as_human_request(l3_runtime):
    """模型不可用时的关键词降级同样不能把设备文案当人工请求（降级词表没有排障意图，只断言不误升级）。"""
    rows, state = await _first_turn("T11")
    assert state["turn_decision"]["escalation_trigger"] is None
    assert state["turn_decision"]["primary_intent"] != "request_human"
    assert not [e for e in rows if e["type"] == "escalation_summary"]


async def test_t63_parts_purchase_is_handed_off_with_the_fault_kept(l3_runtime, monkeypatch):
    """第三批 I8（T63）：买不到刷罩是配件采购诉求，本系统办不了 → 交人工并保留型号未知、刷罩断裂与清洁差三项；
    不能只交接故障而丢掉购买诉求。"""
    async def interpret(router, state, **kwargs):
        return TurnInterpretation(
            primary_intent="parts_purchase", secondary_intents=["report_problem"], device_relation="current",
            facts=[
                {"value": "brush guard snaps off the clips", "quote": "the brush guard just snaps off the clips that hold it in", "subject": "brush guard"},
                {"value": "doesn't clean very well", "quote": "It doesn’t clean very well"},
            ],
        ), {"source": "test"}

    monkeypatch.setattr(semantic, "interpret_turn", interpret)
    rows, state = await _first_turn("T63")
    text = said(rows)
    assert "brush guard" in text.casefold() and "colleague" in text.casefold()
    assert "free" not in text.casefold()
    case = await l3_runtime.cases.store.get(state["case_id"])
    assert case["status"] == "awaiting_approval"
    assert [e["payload"]["requested"] for e in case["events"] if e["type"] == "review_requested"] == ["parts_purchase"]
    summary = [e["payload"] for e in case["events"] if e["type"] == "handoff_summary"][-1]
    assert summary["business"]["kind"] == "parts_purchase"
    assert "brush guard" in summary["business"]["known"].get("part", "").casefold()
    assert "product" in summary["business"]["missing"]
    assert "brush guard snaps off" in summary["problem"]
    queue = {t["intent"]: t["status"] for t in state["task_queue"]}
    assert queue["parts_purchase"] == "waiting_human"


def test_a_parts_purchase_request_is_kept_whatever_the_model_reads():
    """T63 第三批实测：模型只读到刷罩断裂的故障，「can't get a brush guard anywhere」这个采购诉求被丢掉。"""
    from app.conversation.interpret import logistics_correction

    fixed = logistics_correction(TurnInterpretation(primary_intent="report_problem", secondary_intents=["complaint"]), TICKETS["T63"])
    assert "parts_purchase" in fixed.secondary_intents and fixed.primary_intent == "report_problem"
    # 采购原话一并记下：要买什么只从这句取
    assert "brush guard" in fixed.request_quotes["parts_purchase"]
    # 没有采购原话的故障描述不受影响
    plain = TurnInterpretation(primary_intent="report_problem")
    assert logistics_correction(plain, "The brush guard snapped off and it doesn't clean well.") == plain


async def test_t63_purchase_part_comes_from_the_purchase_words_not_the_first_faulty_part(l3_runtime, monkeypatch):
    """2026-10-11 21:45 评测 T63：模型的症状顺序是 detangle elements 在前、brush guard 在后，parts_purchase 没有原话，
    摘要取第一个带部件的症状，交接写成要买 detangle elements。要买的部件只从采购原话里取。"""
    from app.conversation.interpret import logistics_correction

    async def interpret(router, state, **kwargs):
        # 生产路径里模型输出都过 logistics_correction（采购诉求与原话在这里补上）
        return logistics_correction(TurnInterpretation(
            primary_intent="report_problem", secondary_intents=["complaint"], device_relation="current",
            facts=[
                {"value": "detangle elements not working", "quote": "The detangle elements don’t work properly any more", "subject": "detangle elements"},
                {"value": "brush guard snaps off the clips", "quote": "the brush guard just snaps off the clips that hold it in", "subject": "brush guard"},
            ],
        ), state.get("text", "")), {"source": "test"}

    monkeypatch.setattr(semantic, "interpret_turn", interpret)
    rows, state = await _first_turn("T63")
    case = await l3_runtime.cases.store.get(state["case_id"])
    summary = [e["payload"] for e in case["events"] if e["type"] == "handoff_summary"][-1]
    assert summary["business"]["known"]["part"] == "brush guard"
    assert "detangle" not in said(rows).casefold()


def test_purchase_part_unknown_is_left_missing():
    """原话里认不出要买的部件：不猜、不借故障部件，对客文字不点名。"""
    from app.escalation.summary import purchase_object

    assert purchase_object("Why is it I can’t get a brush guard anywhere for this model") == "brush guard"
    assert purchase_object("I want to buy a new filter") == "filter"
    assert purchase_object("Please help") is None


async def test_t23_battery_error_push_gets_the_official_step_not_r4(l3_runtime, monkeypatch):
    """T23（第十轮）：模型把设备推送「E41: Battery abnormal」标成 reported；来源是设备文案、词表未命中，
    不建 R4，按精确错误码下发 rv-0138。"""
    async def interpret(router, state, **kwargs):
        return TurnInterpretation(
            primary_intent="report_problem", device_relation="current",
            facts=[{"value": "Battery abnormal", "quote": "E41: Battery abnormal, task ended."}],
            device_safety_assertion="reported", device_safety_quote="E41: Battery abnormal, task ended.",
        ), {"source": "test"}

    monkeypatch.setattr(semantic, "interpret_turn", interpret)
    rows, state = await _first_turn("T23")
    assert state["risk_cases"] == []
    assert state["escalate_reason"] is None
    card = next(e for e in rows if e["type"] == "step_card")
    assert card["step"]["plan_id"] == "qa_rv_0138"


async def test_t23_no_order_skip_receipt_reaches_the_review_queue(l3_runtime, monkeypatch):
    """T23 走完 rv-0138 两步仍未解决、没有订单号、跳过凭证：质保无法确认 → 真实入人工队列，案件里有交接摘要，
    不再在 summarize 撞 CaseConflict（2026-10-10 复测，约 20 单同路径）。"""
    async def interpret(router, state, **kwargs):
        return TurnInterpretation(
            primary_intent="report_problem", device_relation="current",
            facts=[{"value": "Battery abnormal", "quote": "E41: Battery abnormal, task ended."}],
        ), {"source": "test"}

    monkeypatch.setattr(semantic, "interpret_turn", interpret)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        rows = events(await send(client, sid, TICKETS["T23"]))
        for _ in range(2):
            assert any(e["type"] == "step_card" for e in rows)
            rows = events(await act(client, sid, "step_feedback", {"feedback": "not_solved"}))
        state = await state_of(sid)
        assert (state.get("pending_card") or {}).get("kind") == "upload_receipt"
        rows = events(await act(client, sid, "skip_receipt", {"reason": "none"}))
        state = await state_of(sid)
    assert not [e for e in rows if e["type"] == "error"], [e for e in rows if e["type"] == "error"]
    assert state["stage"] == "awaiting_human" and state["case_status"] == "awaiting_approval"
    assert any(e["type"] == "escalation_summary" and e.get("handoff_status") == "requested" for e in rows)
    case = await l3_runtime.cases.store.get(state["case_id"])
    assert any(e["type"] == "handoff_summary" for e in case["events"])
