"""Replay eb218762: category → symptom → unknown model must retain device context."""

from tests.conversation_runtime import conversation as conversation  # noqa: PLC0414


async def test_unknown_model_after_category_and_symptom_reaches_retrieval(conversation):
    session = conversation
    question = "请问您的扫地机器人具体是什么型号？"
    session.models["disambiguate.clarify"].script = [{"question": question}] * 2
    await session.send(
        "我的扫地机器人出问题了：",
        {
            "primary_intent": "report_problem",
            "device_relation": "current",
            "device_category": "扫地机器人",
            "facts": [{"kind": "symptom", "value": "出问题了", "quote": "我的扫地机器人出问题了"}],
            "clarification": "请具体描述一下扫地机器人出现了什么问题（例如：无法启动、不充电、报错代码等），以便我为您排查。",
        },
    )
    await session.send(
        "不启动",
        {"primary_intent": "supplement", "facts": [{"value": "不启动", "quote": "不启动"}]},
    )
    await session.send(
        "00001",
        {
            "primary_intent": "supplement",
            "device_category": "扫地机器人",
            "product_hints": ["00001"],
            "facts": [{"kind": "observation", "value": "型号为00001", "quote": "00001"}],
        },
    )
    snap = await session.snapshot()
    replies = [e["text"] for e in snap["timeline"] if e["kind"] == "assistant_message"]
    assert replies.count(question) < 2, "用户提供 00001 后重复询问型号"
    assert session.knowledge.calls, "已知扫地机器人与不启动，仍未进入品类通用检索"
    state = await session.state()
    assert state["product_state"] == "category_only"
    assert state["category"] == "robot_vacuum"
    assert state.get("product_confirmed") is None  # Unknown model must not become a made-up SKU.
    assert "00001" in state["product_hints"]
    assert state.get("escalate_reason") != "R7"


def test_saved_category_is_issue_scoped_and_current_category_takes_priority():
    from app.sessions.clarify import decide

    base = {
        "text": "00001",
        "product_hints": ["00001"],
        "symptoms": ["不吸了"],
        "active_issue_id": "current",
        "issues": {"old": {"device_ref": {"category": "扫地机器人"}}, "current": {}},
    }
    missing = decide(base, abandoned_card=None)
    assert missing.outcome == "clarify"  # Another issue must not supply this device's category.
    for category in ("扫地机器人", "robot_vacuum"):
        state = {**base, "issues": {"current": {"device_ref": {"category": category}}}}
        result = decide(state, abandoned_card=None)
        assert result.outcome == "continue"
        assert result.update["category"] == "robot_vacuum"
        assert result.update["product_state"] == "category_only"
        changed = decide({**state, "text": "充电宝 00001"}, abandoned_card=None)
        assert changed.update["category"] == "power_bank"
        assert changed.update["out_of_scope"] is True
    cached = decide({**base, "category": "robot_vacuum"}, abandoned_card=None)
    assert cached.outcome == "continue"
    assert cached.update["category"] == "robot_vacuum"


async def test_unmatched_model_fallback_acknowledges_answer():
    from app.sessions.clarify import build_messages, decide, make_question

    result = decide({"text": "00001", "product_hints": ["00001"]}, abandoned_card=None)
    assert result.outcome == "clarify"
    messages = build_messages(
        "product",
        "00001",
        strategy="normal",
        summary=None,
        detail=result.detail,
    )
    assert "用户没有说明设备的品类或型号" not in str(messages)
    assert "unmatched_product_hints" in str(messages)
    question = await make_question(
        None,
        "product",
        "00001",
        strategy="normal",
        summary=None,
        detail=result.detail,
        session_id=None,
        lane="domestic",
    )
    assert "您提供的型号" in question.text
    assert "未匹配" in question.text
    assert "品类" in question.text and "标签" in question.text
