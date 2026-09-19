"""票 24：product_state 三分、澄清（product / symptom / conflict）与追问上限 R7。

默认 HAIKE_LLM=off：intake 抽取降级（symptoms 为空 → 回退原文判断），追问用固定文案；
需要模型输出的用例用 tests.test_intake.fake_router 注入假 ModelRouter。
"""

from __future__ import annotations

import json

from haike_contracts.snapshot import SessionSnapshot
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.fake import FakeChatModel
from app.models.runtime import set_model_router
from app.sessions import sse
from app.sessions.clarify import (
    FIXED_QUESTIONS,
    MAX_CLARIFICATIONS,
    REPEAT_LEAD,
    fixed_question,
    make_question,
)
from tests.message_form import action_body, message_form
from tests.test_intake import fake_router


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def _send(client, sid: str, text: str) -> list[dict]:
    resp = await client.post(f"/sessions/{sid}/messages", data=await message_form(client, f"/sessions/{sid}/messages", {"text": text}))
    assert resp.status_code == 200, resp.text
    return sse.parse(resp.text)


def _stages(events):
    return [e["stage"] for e in events if e["type"] == "progress"]


def _message_text(events) -> str:
    return "".join(e["delta"] for e in events if e["type"] == "message")


async def _state(sid: str) -> dict:
    return (await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})).values


async def test_unknown_category_two_clarifications_then_r7(mem_runtime):
    """「机器不吸了」→ 追问 → 回答仍不明 → 第二次追问 → 第二次回答仍不明 → R7 升级摘要（验收项 1、6）。"""
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        ev1 = await _send(client, sid, "机器不吸了")
        assert _stages(ev1) == ["intake", "disambiguate"]  # 不进入 diagnose、不检索、不发卡
        assert any(e["type"] == "input_received" for e in ev1)
        assert [e["type"] for e in ev1 if e["type"] not in {"progress", "input_received", "issue_changed"}] == [
            "run_started",
            "message_start",
            "message",
            "message_end",
            "done",
        ]
        assert _message_text(ev1) == FIXED_QUESTIONS["product"]
        assert ev1[-1]["reason"] == "completed"  # 只结束本 run，会话未 solved
        s1 = await _state(sid)
        assert s1["product_state"] == "unknown" and s1["pending_card"] is None
        assert {k: s1["clarification"][k] for k in ("reason", "attempts", "asked_run_id")} == {
            "reason": "product",
            "attempts": 1,
            "asked_run_id": ev1[0]["run_id"],
        }
        # 仅等待用户，不升级：快照 idle、无 pending
        snap = SessionSnapshot.model_validate((await client.get(f"/sessions/{sid}")).json())
        assert snap.active_run is None and snap.pending_input is None
        assert [i.kind for i in snap.timeline] == ["user_message", "assistant_message"]

        ev2 = await _send(client, sid, "就是那个机器啊")  # 第一次回答仍不明 → 第二次追问
        # 同一句再问一次时先承接，不一字不差地复读；问题本身原样保留
        assert _message_text(ev2) == REPEAT_LEAD + FIXED_QUESTIONS["product"]
        s2 = await _state(sid)
        assert s2["clarification"]["attempts"] == 2  # 跨 run 保留并累加
        assert "escalation_summary" not in [e["type"] for e in ev2]

        ev3 = await _send(client, sid, "不知道啊")  # 第二次回答仍不明 → R7
        types = [e["type"] for e in ev3]
        assert "escalation_summary" in types and _stages(ev3)[-1] == "escalate"
        summary = next(e for e in ev3 if e["type"] == "escalation_summary")["summary"]
    assert summary["reason"]["rule_id"] == "R7"
    assert summary["product"] == "未确认"  # product_state=unknown 出现在摘要
    assert any("R7" in o and "2 次澄清" in o for o in summary["observations"])
    s3 = await _state(sid)
    assert s3["escalate_reason"] == "R7" and s3["product_state"] == "unknown"
    assert s3["clarification"]["attempts"] == MAX_CLARIFICATIONS


async def test_out_of_scope_product_stays_out_of_scope_until_user_switches(mem_runtime):
    """2026-09-17 会话 cd45df：范围外产品被 out_of_scope 节点写成 product_confirmed 占位后，
    下一轮不能掉进症状问诊去问一台储能设备「按电源后能正常启动吗」；用户改说范围内品类才切换。
    （原案是移动电源；多品类后移动电源已在范围内，这里用仍在范围外的家用储能复现同一条路。）"""
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        first = await _send(client, sid, "我家的阳台光储出问题了")
        assert _stages(first)[-2:] == ["out_of_scope", "escalate"]
        s1 = await _state(sid)
        assert s1["category"] == "home_storage" and s1["product_confirmed"]["in_scope"] is False
        # 没提到任何品类：仍是范围外，再说明一次，不问症状
        second = await _send(client, sid, "有问题")
        assert "out_of_scope" in _stages(second) and "clarify" not in _stages(second)
        assert "启动" not in _message_text(second) and "暂不在支持范围内" in _message_text(second)
        # 改说机器人：切到范围内品类，占位产品作废
        third = await _send(client, sid, "我的机器人有问题")
        s3 = await _state(sid)
        assert s3["product_state"] == "category_only" and s3["category"] == "robot_vacuum"
        assert s3["product_confirmed"] is None and s3["out_of_scope"] is False
        assert "out_of_scope" not in _stages(third)
        assert not any(e["type"] == "escalation_summary" for e in third)


async def test_category_word_without_model_goes_category_only(mem_runtime):
    """「扫地机不吸了，不知道型号」→ category_only → 进入 diagnose（验收项 2、7）。"""
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        events = await _send(client, sid, "扫地机不吸了，不知道型号")
    types = [e["type"] for e in events]
    assert "product_card" not in types and "message_start" not in types  # 不追问、不出卡
    assert _stages(events)[:3] == ["intake", "disambiguate", "diagnose"]
    state = await _state(sid)
    assert state["product_state"] == "category_only" and state["category"] == "robot_vacuum"
    assert state["product_confirmed"] is None and state["clarification"] is None
    assert events[-1]["reason"] == "awaiting_input"  # 票 34：品类通用计划的步骤卡


async def test_three_product_states_written_and_in_summary(mem_runtime):
    async with _client() as client:
        # confirmed_sku：单命中直接确认
        a = (await client.post("/sessions")).json()["session_id"]
        await _send(client, a, "扫地机 X10 不吸了")
        sa = await _state(a)
        assert sa["product_state"] == "confirmed_sku" and sa["product_confirmed"]["sku"] == (
            "EUFY-X10-PRO-OMNI"
        )
        # category_only
        b = (await client.post("/sessions")).json()["session_id"]
        await _send(client, b, "扫地机器人不回充")
        assert (await _state(b))["product_state"] == "category_only"
        # unknown → 两次追问后 R7，摘要 product 带线索为空 → 「未确认」
        c = (await client.post("/sessions")).json()["session_id"]
        await _send(client, c, "它坏了")
        await _send(client, c, "就是坏了")
        ev = await _send(client, c, "不清楚")
        summary = next(e for e in ev if e["type"] == "escalation_summary")["summary"]
    assert (await _state(c))["product_state"] == "unknown"
    assert summary["product"] == "未确认" and summary["reason"]["rule_id"] == "R7"


async def test_clarify_question_preserves_target_without_model_rewrite(mem_runtime, tmp_path):
    """Question selection and wording share one authority; intake still uses the model."""
    intake_out = {
        "emotion_level": "calm",
        "product_hints": [],
        "symptoms": ["不吸了"],
        "wants_human": False,
    }
    router, fake = fake_router(tmp_path, [intake_out, {"question": "请问是哪一款设备不吸了？"}])
    set_model_router(router)
    try:
        async with _client() as client:
            sid = (await client.post("/sessions")).json()["session_id"]
            events = await _send(client, sid, "机器不吸了")
        assert _message_text(events) == FIXED_QUESTIONS["product"]
        assert all(call["metadata"]["task"] != "disambiguate.clarify" for call in fake.calls)
        state = await _state(sid)
        assert state["clarification"]["question"] == _message_text(events)
    finally:
        set_model_router(None)

    # 模型失败 → 固定文案
    router2, _ = fake_router(tmp_path, [RuntimeError("boom")] * 6)
    out = await make_question(
        router2,
        "symptom",
        "这个又不行了",
        strategy="normal",
        summary=None,
        detail={"category": "robot_vacuum"},  # 判别题按品类选：decide 把品类放进 detail
        session_id="s",
        lane="domestic",
    )
    assert out.text == "设备按电源后能正常启动吗？" and out.model_used == "fixed"
    assert fixed_question("conflict", {"confirmed": "A", "mentioned": "B"}) == (
        "您之前确认的是 A，这次提到的是 B，请问需要排查的是哪一台？"
    )


async def test_deictic_without_context_asks_but_with_context_continues(mem_runtime):
    """「这个又不行了」无上下文 → 问一个具体问题；明确上文（已确认产品与故障）→ 承接，不再追问（验收项 5）。"""
    async with _client() as client:
        a = (await client.post("/sessions")).json()["session_id"]
        ev = await _send(client, a, "这个又不行了")
        assert _message_text(ev) == FIXED_QUESTIONS["product"]
        assert (await _state(a))["clarification"]["reason"] == "product"

        b = (await client.post("/sessions")).json()["session_id"]
        await _send(client, b, "扫地机 X9 吸力变小了")
        ev2 = await _send(client, b, "这个又不行了")
    assert "message_start" not in [e["type"] for e in ev2] or _message_text(ev2) not in (
        FIXED_QUESTIONS.values()
    )
    assert "diagnose" in _stages(ev2)
    sb = await _state(b)
    assert sb["product_confirmed"]["sku"] == "EUFY-X9-PRO" and sb["clarification"] is None


async def test_symptom_clarification_when_product_known_but_no_symptom(mem_runtime, tmp_path):
    """品类 / 产品已知但症状不明 → symptom 澄清；补充症状后继续并清零（验收项 7、6）。"""
    router, _ = fake_router(
        tmp_path,
        [
            {
                "emotion_level": "calm",
                "product_hints": ["X10"],
                "symptoms": [],
                "wants_human": False,
            },
            {"question": "请问 X10 是吸力变弱、无法启动，还是有异响？"},
        ],
    )
    set_model_router(router)
    try:
        async with _client() as client:
            sid = (await client.post("/sessions")).json()["session_id"]
            ev1 = await _send(client, sid, "X10 这个又不行了")
            # The model's different question cannot change the stored yes/no split.
            assert _message_text(ev1) == "设备按电源后能正常启动吗？"
            s1 = await _state(sid)
            assert s1["product_state"] == "confirmed_sku"  # 产品已定，只问症状
            assert {k: s1["clarification"][k] for k in ("reason", "attempts", "asked_run_id")} == {
                "reason": "symptom",
                "attempts": 1,
                "asked_run_id": ev1[0]["run_id"],
            }
            set_model_router(None)  # 第二轮不再需要模型
            ev2 = await _send(client, sid, "吸力变弱了")
        assert "diagnose" in _stages(ev2)
        s2 = await _state(sid)
        assert s2["clarification"] is None and s2["product_confirmed"]["sku"] == "EUFY-X10-PRO-OMNI"
    finally:
        set_model_router(None)


async def test_uncertain_text_preserves_product_card_until_valid_selection(mem_runtime, monkeypatch):
    """A conversational detour cannot consume a product choice or fabricate failed actions."""
    import app.conversation.interpret as semantic

    original = semantic.interpret_turn

    async def uncertain_turn(router, state, **kwargs):
        if state.get("entry") == "message" and state.get("active_issue_id"):
            return semantic.TurnInterpretation(
                primary_intent="unknown", clarification="请查看设备标签，确认设备品类。"
            ), {"source": "uncertain-input-fixture"}
        return await original(router, state, **kwargs)

    monkeypatch.setattr(semantic, "interpret_turn", uncertain_turn)
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        first = await _send(client, sid, "我的 S1 Pro 不吸了")
        pending = next(e for e in first if e["type"] == "awaiting_input")
        before = await _state(sid)
        for text in ("不知道是哪个", "还是不知道"):
            events = await _send(client, sid, text)
            snap = SessionSnapshot.model_validate((await client.get(f"/sessions/{sid}")).json())
            assert snap.pending_input.card_id == pending["card_id"]
            assert snap.pending_input.input_token == pending["input_token"]
            assert not any(e["type"] == "escalation_summary" for e in events)
            state = await _state(sid)
            assert state["clarification"]["attempts"] == before["clarification"]["attempts"]
        response = await client.post(
            f"/sessions/{sid}/actions",
            json=await action_body(client, f"/sessions/{sid}/actions", {
                "action_id": "selected-after-detour",
                "input_token": pending["input_token"],
                "card_id": pending["card_id"],
                "expected_version": snap.version,
                "kind": "select_product",
                "payload": {"sku": "EUFY-S1-PRO"},
            }),
        )
        assert response.status_code == 200
        assert (await _state(sid))["product_confirmed"]["sku"] == "EUFY-S1-PRO"


async def test_product_correction_and_category_conflict(mem_runtime):
    """已确认 X10 后：单命中的另一型号 → 型号纠正（旧证据失效）；只提到另一品类 → conflict 澄清。"""
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        await _send(client, sid, "扫地机 X10 不吸了")
        ev = await _send(client, sid, "说错了，是 X9 不吸")
        s = await _state(sid)
        assert s["product_confirmed"]["sku"] == "EUFY-X9-PRO" and all(e["source"] == "approved_plan" for e in s["evidence"].values())
        assert "diagnose" in _stages(ev)

        ev2 = await _send(client, sid, "吸奶器也坏了")
    assert _message_text(ev2) == (
        "您之前确认的是 eufy X9 Pro，这次提到的是 吸奶器，请问需要排查的是哪一台？"
    )
    s2 = await _state(sid)
    assert s2["clarification"]["reason"] == "conflict" and s2["product_confirmed"]["sku"] == (
        "EUFY-X9-PRO"
    )


def test_fake_router_helper_shape():
    fake = FakeChatModel(script=[json.dumps({"question": "q"})])
    assert fake.script and fake.calls == []


async def test_differentiated_category_asks_model_once_then_uses_sku_plan(mem_runtime):
    """spec 2026-09-19-0810 A（T1）：品类已知、知识按型号分化 → 出一次型号卡；选中后走型号专属计划。
    今天头戴耳机没有通用卡，不问型号只能 R5。"""
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        events = await _send(client, sid, "我的头戴耳机一边没声音")
        card = next(e for e in events if e["type"] == "product_card")
        assert {c["sku"] for c in card["candidates"]} == {"SOUNDCORE-A3035", "SOUNDCORE-A3040"}
        assert not any(e["type"] == "escalation_summary" for e in events)
        state = await _state(sid)
        assert state["product_state"] == "category_only" and state["category"] == "headphones"
        pending = next(e for e in events if e["type"] == "awaiting_input")
        snap = SessionSnapshot.model_validate((await client.get(f"/sessions/{sid}")).json())
        response = await client.post(
            f"/sessions/{sid}/actions",
            json=await action_body(client, f"/sessions/{sid}/actions", {
                "action_id": "pick-q45",
                "input_token": pending["input_token"],
                "card_id": pending["card_id"],
                "expected_version": snap.version,
                "kind": "select_product",
                "payload": {"sku": "SOUNDCORE-A3040"},
            }),
        )
        assert response.status_code == 200, response.text
        rows = sse.parse(response.text)
    step = next(e for e in rows if e["type"] == "step_card")["step"]
    assert step["plan_id"] == "hd_q45_one_side"
    final = await _state(sid)
    assert final["product_state"] == "confirmed_sku" and final["product_confirmed"]["sku"] == "SOUNDCORE-A3040"


async def test_generic_only_category_skips_model_card_and_asks_selection(mem_runtime):
    """spec 2026-09-19-0810 A（T2）+ C：吸奶器两款型号知识相同 → 不问型号；没有症状时首问是多选题（会话 934ad）。"""
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        events = await _send(client, sid, "我的吸奶器出问题了：")
    types = [e["type"] for e in events]
    assert "product_card" not in types
    text = _message_text(events)
    assert text.startswith("具体有哪些现象（可多选）？") and "吸力不足" in text and "App 连接" in text
    state = await _state(sid)
    assert state["product_state"] == "category_only" and state["category"] == "breast_pump"
    assert state["symptom_interview"]["question"]["kind"] == "symptom_selection"


def test_model_card_is_skipped_when_it_would_not_change_the_next_step():
    """T1 不出卡的三种情况：本会话已出过卡、用户已声明不知道型号、分化候选不足两个。"""
    from app.sessions.cards import get_catalog
    from app.sessions.clarify import differentiated_candidates

    catalog = get_catalog()
    base = {"text": "扫地机地图丢了", "prepare_card_calls": 0}
    assert {c["sku"] for c in differentiated_candidates(catalog, "robot_vacuum", base)} == {
        "EUFY-X10-PRO-OMNI", "EUFY-X9-PRO",
    }
    assert differentiated_candidates(catalog, "robot_vacuum", {**base, "prepare_card_calls": 1}) == []
    assert differentiated_candidates(catalog, "robot_vacuum", {**base, "text": "扫地机地图丢了，不知道型号"}) == []
    assert differentiated_candidates(catalog, "robot_vacuum", {**base, "text": "扫地机型号不清楚，地图丢了"}) == []
    # 异响只有 X10 一个分化型号：卡片带「其他型号 / 不确定」出口，单候选也问
    assert [c["sku"] for c in differentiated_candidates(catalog, "robot_vacuum", {**base, "text": "扫地机有异响"})] == ["EUFY-X10-PRO-OMNI"]
    # 问诊已经开始就不再插入型号问题
    assert differentiated_candidates(catalog, "robot_vacuum", {**base, "symptom_interview": {"answers": []}}) == []
    assert differentiated_candidates(catalog, "breast_pump", {**base, "text": "吸奶器不吸了"}) == []


async def _select(client, sid, events, sku):
    pending = next(e for e in events if e["type"] == "awaiting_input")
    snap = SessionSnapshot.model_validate((await client.get(f"/sessions/{sid}")).json())
    response = await client.post(
        f"/sessions/{sid}/actions",
        json=await action_body(client, f"/sessions/{sid}/actions", {
            "action_id": f"pick-{sku or 'unknown'}",
            "input_token": pending["input_token"],
            "card_id": pending["card_id"],
            "expected_version": snap.version,
            "kind": "select_product",
            "payload": {"sku": sku},
        }),
    )
    return response


async def test_unknown_model_falls_back_to_category_generic_plan(mem_runtime):
    """spec 2026-09-19-0810 B：型号卡带「其他型号 / 不确定」出口；选它退回 category_only，按品类通用计划继续。"""
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        events = await _send(client, sid, "扫地机运行时有异响")
        card = next(e for e in events if e["type"] == "product_card")
        assert [c["sku"] for c in card["candidates"]] == ["EUFY-X10-PRO-OMNI"]
        assert card["allow_unknown"] is True and card["note"] == "不同型号的排查方法不同"
        response = await _select(client, sid, events, None)
        assert response.status_code == 200, response.text
        rows = sse.parse(response.text)
        snap = SessionSnapshot.model_validate((await client.get(f"/sessions/{sid}")).json())
    step = next(e for e in rows if e["type"] == "step_card")["step"]
    from app.sessions.cards import get_plans
    plan = get_plans().get(step["plan_id"])
    assert plan.applies_to.scope == "category_generic" and "abnormal_noise" in plan.symptom_codes
    state = await _state(sid)
    assert state["product_state"] == "category_only" and state["category"] == "robot_vacuum"
    assert state["product_confirmed"] is None and state["clarification"] is None
    item = next(t for t in snap.timeline if t.kind == "product_card")
    assert item.selected_unknown is True and item.selected_sku is None and item.allow_unknown is True


async def test_unknown_model_without_generic_knowledge_ends_honestly(mem_runtime):
    """头戴耳机没有品类通用计划：选「不确定」后按 R5 结束，摘要写明问过型号。"""
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        events = await _send(client, sid, "我的头戴耳机一边没声音")
        response = await _select(client, sid, events, None)
        assert response.status_code == 200, response.text
        rows = sse.parse(response.text)
    summary = next(e for e in rows if e["type"] == "escalation_summary")["summary"]
    assert summary["reason"]["rule_id"] == "R5"
    assert any("已询问型号，用户不确定" in o for o in summary["observations"])


async def test_unknown_model_is_rejected_on_cross_category_card(mem_runtime):
    """目录多命中的卡（T0）品类未定，没有可退回的品类：sku=null 不合法，卡片保持待选。"""
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        events = await _send(client, sid, "我的 S1 Pro 不吸了")
        card = next(e for e in events if e["type"] == "product_card")
        assert card["allow_unknown"] is False
        response = await _select(client, sid, events, None)
        assert response.status_code == 409, response.text
        snap = SessionSnapshot.model_validate((await client.get(f"/sessions/{sid}")).json())
        assert snap.pending_input is not None and snap.pending_input.kind == "select_product"


async def test_product_selection_without_symptom_asks_before_any_step(mem_runtime):
    """选完型号还没有任何现象：先问症状，不能直接下发第一条计划的步骤（T0 与 T1 同一套判定）。"""
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        events = await _send(client, sid, "我的 S1 Pro 出问题了：")
        response = await _select(client, sid, events, "EUFY-S1-PRO")
        assert response.status_code == 200, response.text
        rows = sse.parse(response.text)
    assert not any(e["type"] == "step_card" for e in rows)
    assert _message_text(rows) == "设备按电源后能正常启动吗？"
    state = await _state(sid)
    assert state["product_confirmed"]["sku"] == "EUFY-S1-PRO"
    assert state["clarification"]["reason"] == "symptom" and state["clarification"]["attempts"] == 1
    assert state["symptom_interview"]["question"]["question"] == "设备按电源后能正常启动吗？"


def _interview_driven_interpret():
    """按待答问诊题作答的 intake 替身：是非题按原话判 yes/no，多选题按序号选族；不依赖模型。"""
    import app.conversation.interpret as semantic

    async def interpret(router, state, **kwargs):
        text = state.get("text", "") or ""
        question = (state.get("symptom_interview") or {}).get("question") or {}
        answer = None
        if question.get("kind") == "symptom_selection":
            family = question["options"][int(text) - 1]["value"]
            answer = semantic.SymptomAnswer(
                question_id=question["question_id"], answer="selection", selected_families=[family], quote=text,
            )
        elif question:
            answer = semantic.SymptomAnswer(
                question_id=question["question_id"], answer="no" if text.startswith(("不", "没")) else "yes", quote=text,
            )
        return semantic.TurnInterpretation(
            primary_intent="answer_pending" if answer else "report_problem",
            device_relation="current", symptom_answer=answer,
        ), {"source": "interview-fixture"}

    return semantic, interpret


async def _interview_to_mop_selection(client, monkeypatch):
    """复现会话 e84456 的前三轮：品类扫地机（分化型号超过卡片上限，首轮不问型号）→ 能启动 → 效果不好 → 选「2」拖地异常。"""
    from app.knowledge import adapter

    # 线上知识索引里 manual_rv_v2 按 L/G 六款分化，加上 X10 / X9 / S1 Pro 共 9 个型号，超过 MAX_MODEL_CARD；单测无索引，这里补上
    monkeypatch.setattr(adapter, "sku_scoped_skus", lambda entries, category, skus: {
        "EUFY-L60-HYBRID", "EUFY-L50-SES", "EUFY-G50-HYBRID", "EUFY-G40-HYBRID", "EUFY-G30-VERGE", "EUFY-G20-HYBRID", "EUFY-S1-PRO",
    })
    sid = (await client.post("/sessions")).json()["session_id"]
    events = await _send(client, sid, "我的扫地机器人出问题了：")
    assert "product_card" not in {e["type"] for e in events}
    assert _message_text(events) == "设备按电源后能正常启动吗？"
    events = await _send(client, sid, "能")
    assert _message_text(events) == "是清扫或拖地的效果不好吗？"
    events = await _send(client, sid, "效果不好")
    text = _message_text(events)
    assert text.startswith("具体有哪些现象（可多选）？") and "2．拖地后仍有污渍或拖布异常" in text
    return sid, await _send(client, sid, "2")


async def test_selected_symptom_without_generic_plan_asks_model_before_r5(mem_runtime, monkeypatch):
    """会话 e84456：用户选「2」（拖地异常）被正确记为 mop_failure，但品类通用计划无一覆盖拖地，唯一的拖地计划锁在
    X10 上。此时应补问一次型号，选中 X10 后走 rv_x10_mop_no_water，而不是直接 R5 转人工。"""
    semantic, interpret = _interview_driven_interpret()
    monkeypatch.setattr(semantic, "interpret_turn", interpret)
    async with _client() as client:
        sid, events = await _interview_to_mop_selection(client, monkeypatch)
        assert not any(e["type"] == "escalation_summary" for e in events)
        card = next(e for e in events if e["type"] == "product_card")
        assert [c["sku"] for c in card["candidates"]] == ["EUFY-X10-PRO-OMNI"] and card["allow_unknown"] is True
        state = await _state(sid)
        assert state["symptom_codes"] == ["mop_failure"] and state["product_state"] == "category_only"
        response = await _select(client, sid, events, "EUFY-X10-PRO-OMNI")
        assert response.status_code == 200, response.text
        rows = sse.parse(response.text)
    step = next(e for e in rows if e["type"] == "step_card")["step"]
    assert step["plan_id"] == "rv_x10_mop_no_water"
    final = await _state(sid)
    assert final["product_confirmed"]["sku"] == "EUFY-X10-PRO-OMNI"
    assert [p["plan_id"] for p in final["plans_ranked"]] == ["rv_x10_mop_no_water"]


async def test_selected_symptom_unknown_model_ends_r5_without_unrelated_steps(mem_runtime, monkeypatch):
    """同一路径选「其他型号 / 不确定」：通用计划全是吸力 / 供电 / 异响，不能拿它们冒充拖地排查（原会话下发了
    四步吸力排查后 R1），按 R5 如实结束，摘要写明问过型号。"""
    semantic, interpret = _interview_driven_interpret()
    monkeypatch.setattr(semantic, "interpret_turn", interpret)
    async with _client() as client:
        sid, events = await _interview_to_mop_selection(client, monkeypatch)
        response = await _select(client, sid, events, None)
        assert response.status_code == 200, response.text
        rows = sse.parse(response.text)
    assert not any(e["type"] == "step_card" for e in rows)
    summary = next(e for e in rows if e["type"] == "escalation_summary")["summary"]
    assert summary["reason"]["rule_id"] == "R5"
    assert any("已询问型号，用户不确定" in o for o in summary["observations"])
    state = await _state(sid)
    assert state["plans_ranked"] == [] and state["product_state"] == "category_only"
