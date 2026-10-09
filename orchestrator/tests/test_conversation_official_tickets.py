"""主办方真实工单首封消息走完整会话图（无模型、无知识库）：错误码精确命中官方 Q&A、硬件故障直进质保、未收录码转人工。"""

import pytest
from httpx import ASGITransport, AsyncClient

import app.conversation.interpret as semantic
from app.conversation.interpret import TurnInterpretation
from app.knowledge.runtime import set_knowledge_adapter
from app.main import app
from app.official.models import OfficialData
from tests.fake_qa import QAHitAdapter
from tests.test_conversation_l3 import act, events, said, send, state_of
from tests.test_conversation_l3 import l3_runtime as l3_runtime  # noqa: PLC0414

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
    # T28：2111 滚刷错误，官方 Q&A 先让重启，仍未解决才走质保（rv-0256 拆成两步）
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        rows = events(await send(client, sid, TICKETS["T28"]))
        card = next(e for e in rows if e["type"] == "step_card")
        assert (card["step"]["plan_id"], card["step"]["step_id"]) == ("qa_rv_0256", "s1")
        rows = events(await act(client, sid, "step_feedback", {"feedback": "not_solved"}))
        second = next(e for e in rows if e["type"] == "step_card")
        assert second["step"]["step_id"] == "s2" and "engineering team" in second["step"]["instruction"]
        rows = events(await act(client, sid, "step_feedback", {"feedback": "not_solved"}))
        state = await state_of(sid)
    # 质保步仍未解决 → 计划用尽，按 SOP 进入订单质保判断（先收订单 / 凭证），不再出操作步骤
    assert state["escalate_reason"] == "R6" and state["stage"] == "context"
    assert not [e for e in rows if e["type"] == "step_card"]
    assert any(e["type"] == "awaiting_input" for e in rows)


async def _feedback_until_no_card(client, sid, limit=8):
    rows = []
    for _ in range(limit):
        rows = events(await act(client, sid, "step_feedback", {"feedback": "not_solved"}))
        if not any(e["type"] == "step_card" for e in rows):
            break
    return rows


async def test_t55_main_case_troubleshoots_then_checks_order_warranty(l3_runtime, report_intent):
    # T55：RMA 表单「S1 Pro Wearable Breast Pump」同名型号由品类词消歧 → 官方 Q&A 排障 → 未解决 → 订单 Anker016 保内 → 收 SOP 证据
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


async def test_t29_out_of_warranty_order_is_declined_after_troubleshooting(l3_runtime, report_intent):
    set_knowledge_adapter(QAHitAdapter("rv-0236"))
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            sid = (await client.post("/sessions")).json()["session_id"]
            events(await send(client, sid, TICKETS["T29"]))
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
    # T2：一个订单号 + 两个运单号（配件包与主机分开发）是同一订单的两个包裹，不应追问「哪个订单」
    rows, state = await _first_turn("T2")
    assert state["case_order_no"] == "Anker002"
    card = next(e for e in rows if e["type"] == "proposal_card")
    assert [o["type"] for o in card["options"]] == ["carrier_investigation"]


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
            return TurnInterpretation(primary_intent=primary, secondary_intents=secondary, device_relation="current"), {"source": "test"}
        return TurnInterpretation(primary_intent="logistics_query", device_relation="current"), {"source": "test"}

    monkeypatch.setattr(semantic, "interpret_turn", interpret)


async def _case_detail(client, rows):
    case_id = next(e["case_id"] for e in reversed(rows) if e["type"] == "case_changed")
    return (await client.get(f"/admin/api/cases/{case_id}")).json()


@pytest.mark.parametrize(("primary", "secondary"), [("order_change", ["logistics_query"]), ("logistics_query", ["order_change"])])
async def test_t9_hold_request_is_queued_and_the_shipping_question_is_still_answered(l3_runtime, monkeypatch, primary, secondary):
    """无论模型先读到哪半句：暂缓诉求真正进人工队列，物流事实照样答，两者缺一不可。"""
    from app.sessions.l3 import NOT_EXECUTABLE_HANDOFF

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
        assert kinds.count("review_requested") == 1 and kinds.count("handoff_summary") == 1, kinds
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
