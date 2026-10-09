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


async def test_three_product_states_written_and_in_summary(mem_runtime):
    async with _client() as client:
        # confirmed_sku：单命中直接确认
        a = (await client.post("/sessions")).json()["session_id"]
        await _send(client, a, "扫地机 X10 报错 6025")
        sa = await _state(a)
        assert sa["product_state"] == "confirmed_sku" and sa["product_confirmed"]["sku"] == (
            "T2351"
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
        detail={"category": "robot_vacuum"},
        session_id="s",
        lane="domestic",
    )
    assert out.text == FIXED_QUESTIONS["symptom"] and out.model_used == "fixed"
    assert fixed_question("conflict", {"confirmed": "A", "mentioned": "B"}) == (
        "Earlier we confirmed A, and now you mentioned B. Which one should we look at?"
    )


async def test_deictic_without_context_asks_but_with_context_continues(mem_runtime):
    """「这个又不行了」无上下文 → 问一个具体问题；明确上文（已确认产品与故障）→ 承接，不再追问（验收项 5）。"""
    async with _client() as client:
        a = (await client.post("/sessions")).json()["session_id"]
        ev = await _send(client, a, "这个又不行了")
        assert _message_text(ev) == FIXED_QUESTIONS["product"]
        assert (await _state(a))["clarification"]["reason"] == "product"

        b = (await client.post("/sessions")).json()["session_id"]
        await _send(client, b, "扫地机 X10 报错 6025")
        ev2 = await _send(client, b, "这个又不行了")
    assert "message_start" not in [e["type"] for e in ev2] or _message_text(ev2) not in (
        FIXED_QUESTIONS.values()
    )
    # 上文已定且事实没变：直接依据已有候选继续（重新出步骤卡），不重复检索也不追问
    assert "diagnose" in _stages(ev2) or any(e["type"] == "step_card" for e in ev2)
    sb = await _state(b)
    assert sb["product_confirmed"]["sku"] == "T2351" and sb["clarification"] is None


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
            # 没有现象：问一句开放问题（可贴错误码），模型改写的问题保持同一目标
            assert _message_text(ev1) in (FIXED_QUESTIONS["symptom"], "请问 X10 是吸力变弱、无法启动，还是有异响？")
            s1 = await _state(sid)
            assert s1["product_state"] == "confirmed_sku"  # 产品已定，只问症状
            assert {k: s1["clarification"][k] for k in ("reason", "attempts", "asked_run_id")} == {
                "reason": "symptom",
                "attempts": 1,
                "asked_run_id": ev1[0]["run_id"],
            }
            set_model_router(None)  # 第二轮不再需要模型
            ev2 = await _send(client, sid, "吸力变弱了，地上的灰尘和碎屑都吸不干净")
        assert "diagnose" in _stages(ev2)
        s2 = await _state(sid)
        assert s2["clarification"] is None and s2["product_confirmed"]["sku"] == "T2351"
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
        first = await _send(client, sid, "我的 S1 Pro 报错 E23")
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
                "payload": {"sku": "T2080"},
            }),
        )
        assert response.status_code == 200
        assert (await _state(sid))["product_confirmed"]["sku"] == "T2080"


async def test_product_correction_and_category_conflict(mem_runtime):
    """已确认 X10 后：单命中的另一型号 → 型号纠正（旧证据失效）；只提到另一品类 → conflict 澄清。"""
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        await _send(client, sid, "扫地机 X10 报错 6025")
        ev = await _send(client, sid, "说错了，是 E28 报错 3212")
        s = await _state(sid)
        # 型号纠正：X10 的旧证据作废，按 E28 的官方 Q&A 重新命中
        assert s["product_confirmed"]["sku"] == "T2352" and all("rv-0236" not in k for k in s["evidence"])
        assert "diagnose" in _stages(ev)

        ev2 = await _send(client, sid, "吸奶器也坏了")
    assert _message_text(ev2) == (
        "Earlier we confirmed eufy Robot Vacuum Omni E28, and now you mentioned 吸奶器. Which one should we look at?"
    )
    s2 = await _state(sid)
    assert s2["clarification"]["reason"] == "conflict" and s2["product_confirmed"]["sku"] == "T2352"


def test_fake_router_helper_shape():
    fake = FakeChatModel(script=[json.dumps({"question": "q"})])
    assert fake.script and fake.calls == []


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


async def test_unknown_model_is_rejected_on_cross_category_card(mem_runtime):
    """目录多命中的卡（T0）品类未定，没有可退回的品类：sku=null 不合法，卡片保持待选。"""
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        events = await _send(client, sid, "我的 S1 Pro 报错 E23")
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
        response = await _select(client, sid, events, "T2080")
        assert response.status_code == 200, response.text
        rows = sse.parse(response.text)
    assert not any(e["type"] == "step_card" for e in rows)
    assert _message_text(rows) == FIXED_QUESTIONS["symptom"]
    state = await _state(sid)
    assert state["product_confirmed"]["sku"] == "T2080"
    assert state["clarification"]["reason"] == "symptom" and state["clarification"]["attempts"] == 1

def test_confirmed_product_survives_a_turn_with_no_model_in_it():
    """P1-2：产品已确认后，一句不含型号的补充不得让产品卡再弹一次。

    复现路径（T55 实测弹两次，journey run 5 与 run 7）：首封含「S1 Pro」→ product_hints 记下它；
    该别名同时命中扫地机 T2080 与吸奶器 T8D04。排障走到一半客户回
    「Here are photos of the problem.」，本轮原话没有任何型号，旧 hint 被重新查成两个候选，
    已确认的 T8D04 被判成「提到了别的型号」而作废（clarify.decide 的 len(cands)>1 分支）。
    已确认的产品是更强的证据，推翻它要靠本轮原话里真的出现别的型号，不是一条只增不减的旧线索。

    直接驱动 decide：这条取决于 product_hints 的内容，而默认 HAIKE_LLM=off 时 intake 降级，
    走 HTTP 根本填不出 hints，端到端反而测不到这条路径。
    """
    from app.sessions.clarify import decide

    confirmed = {"sku": "T8D04", "name": "eufy Wearable Breast Pump S1 Pro",
                 "category": "breast_pump", "in_scope": True}
    state = {
        "text": "Here are photos of the problem.",
        "product_hints": ["S1 Pro"],  # 首封留下的旧线索，同名跨品类
        "product_confirmed": confirmed,
        "product_state": "confirmed_sku",
        "symptoms": ["no suction"],
    }
    decision = decide(state, abandoned_card=None)
    assert decision.update.get("product_state") != "unknown", "不该把已确认的产品打回未知"
    assert not decision.update.get("product_candidates"), "不该重新出产品卡"
    assert decision.update.get("product_confirmed", confirmed)["sku"] == "T8D04"


async def test_a_real_model_change_in_this_turn_still_switches_the_product(mem_runtime):
    """反向用例：本轮原话里真的出现了另一台设备，仍然要改产品 —— 上一条修复不能把纠错也堵掉。"""
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        await _send(client, sid, "我的 S1 Pro Wearable Breast Pump 不吸了")
        assert (await _state(sid))["product_confirmed"]["sku"] == "T8D04"
        await _send(client, sid, "说错了，是 X10 Pro Omni 不吸了")
    state = await _state(sid)
    assert state["product_confirmed"]["sku"] == "T2351"


async def test_category_word_locates_a_shared_alias_even_after_confirmation():
    """同名别名的品类消歧对「已确认」分支同样生效，不是只在首次确认时才有。

    「S1 Pro」同时是扫地机 T2080 与吸奶器 T8D04。客户已确认吸奶器后说
    「my S1 Pro vacuum broke」——原话两个候选都命中，但品类词 vacuum 已经说明是哪一台。
    修复前这段收窄只写在 `not confirmed` 分支里，已确认时反而失去定位能力，
    只能作废产品再弹一次卡；正确行为是识别为换了设备并切到扫地机。
    """
    from app.sessions.clarify import decide

    state = {
        "text": "my S1 Pro vacuum broke",
        "product_hints": ["S1 Pro"],
        "product_confirmed": {"sku": "T8D04", "name": "eufy Wearable Breast Pump S1 Pro",
                              "category": "breast_pump", "in_scope": True},
        "product_state": "confirmed_sku",
        "symptoms": ["broke"],
    }
    decision = decide(state, abandoned_card=None)
    assert decision.update.get("product_state") != "unknown", "品类词已定位，不该退回出卡"
    assert not decision.update.get("product_candidates")
    assert decision.update["product_confirmed"]["sku"] == "T2080"
