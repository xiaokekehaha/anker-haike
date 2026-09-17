import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.actions.runtime import configure
from app.conversation.interpret import TurnInterpretation
from app.main import app


@pytest.fixture
async def l3_runtime(mem_runtime, monkeypatch):
    monkeypatch.setenv("HAIKE_LLM", "off")
    services = configure(memory=True)
    app.state.l3_services = services
    yield services
    await app.state.run_manager.shutdown()
    configure()
    app.state.l3_services = None


def events(response):
    import json

    return [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
    ]


async def send(client, sid, text):
    snap = (await client.get(f"/sessions/{sid}")).json()
    return await client.post(
        f"/sessions/{sid}/messages",
        data={"input_id": str(uuid.uuid4()), "expected_version": snap["version"], "text": text},
    )


async def act(client, sid, kind, payload):
    snap = (await client.get(f"/sessions/{sid}")).json()
    pending = snap["pending_input"]
    return await client.post(
        f"/sessions/{sid}/actions",
        json={
            "action_id": str(uuid.uuid4()),
            "expected_version": snap["version"],
            "target_issue_id": snap["active_issue_id"],
            "card_id": pending["card_id"],
            "input_token": pending["input_token"],
            "kind": kind,
            "payload": payload,
        },
    )


async def test_a4_consult_fast_path_and_missing_param(l3_runtime):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        response = await send(client, sid, "我的换货单 DEMO-X10-001 到哪了")
        rows = events(response)
        assert any(
            e["type"] == "tool_call"
            and e["name"] == "logistics.query"
            and e["status"] == "finished"
            for e in rows
        )
        assert not any(e.get("stage") in {"disambiguate", "diagnose"} for e in rows)
        text = "".join(e.get("delta", "") for e in rows)
        assert "shipped" in text and "模拟" in text
        sid = (await client.post("/sessions")).json()["session_id"]
        assert "请提供订单号" in "".join(
            e.get("delta", "") for e in events(await send(client, sid, "查物流"))
        )
        assert "shipped" in "".join(
            e.get("delta", "") for e in events(await send(client, sid, "DEMO-X10-001"))
        )


@pytest.mark.parametrize("answer", ["no", "unknown"])
async def test_symptom_interview_stops_when_actions_are_known_or_answers_unavailable(l3_runtime, monkeypatch, answer):
    import app.conversation.interpret as semantic

    async def interpretation(router, state, **kwargs):
        question = (state.get("symptom_interview") or {}).get("question")
        if question:
            return TurnInterpretation(primary_intent="answer_pending", symptom_answer={"question_id": question["question_id"], "answer": answer, "quote": state["text"]}), {"source": "test"}
        return TurnInterpretation(primary_intent="report_problem", device_relation="current", product_hints=["eufy X10 Pro Omni"]), {"source": "test"}

    monkeypatch.setattr(semantic, "interpret_turn", interpretation)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        first = events(await send(client, sid, "eufy X10 Pro Omni 坏了"))
        assert "能正常启动" in "".join(e.get("delta", "") for e in first)
        second = events(await send(client, sid, "不能" if answer == "no" else "不知道"))
        state = (await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})).values
        assert len(state["symptom_interview"]["candidates"]) == (2 if answer == "no" else 8)
        if answer == "no":
            assert set(state["symptom_codes"]) == {"power_failure", "charging_failure"}
            assert state["diagnostic_decision"]["reason"] == "same_applicable_plans"
            assert any(e["type"] == "step_card" and e["step"]["plan_id"] == "rv_power_supply" for e in second)
            assert not any(e["type"] == "escalation_summary" for e in second)
        else:
            assert state["clarification"]["attempts"] == 2
            last = events(await send(client, sid, "还是不知道"))
            state = (await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})).values
            assert state["symptom_interview"]["status"] == "insufficient"
            assert any(e["type"] == "escalation_summary" and e["summary"]["reason"]["rule_id"] == "R7" for e in last)



async def test_manual_close_reopen_syncs_case_snapshot_and_invalidates_consent(l3_runtime, monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = await seed_issue(client, monkeypatch)
        await send(client, sid, "我要换货")
        before = (await client.get(f"/sessions/{sid}")).json()
        state = (await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})).values
        row = await l3_runtime.cases.store.get(state["case_id"])
        path = f"/admin/api/cases/{row['case_id']}"
        body = {"expected_revision": row["revision"]}
        closed = await client.post(path + "/close", json=body)
        assert closed.status_code == 200, closed.text
        assert closed.json()["status"] == "closed"
        replay = await client.post(path + "/close", json=body)
        assert replay.status_code == 200 and replay.json()["revision"] == closed.json()["revision"]
        snap = (await client.get(f"/sessions/{sid}")).json()
        assert snap["pending_input"] is None
        assert any(e["kind"] == "case_changed" and e["status"] == "closed" for e in snap["timeline"])
        old = before["pending_input"]
        stale_card = await client.post(f"/sessions/{sid}/actions", json={
            "action_id": str(uuid.uuid4()), "expected_version": snap["version"],
            "target_issue_id": before["active_issue_id"], "card_id": old["card_id"],
            "input_token": old["input_token"], "kind": "confirm_proposal", "payload": {"option_id": "replace"},
        })
        assert stale_card.status_code == 409
        assert (await client.post(path + "/reopen", json=body)).status_code == 409
        reopened = await client.post(path + "/reopen", json={"expected_revision": closed.json()["revision"]})
        assert reopened.status_code == 200, reopened.text
        assert reopened.json()["status"] == "reopened" and reopened.json()["reopened_count"] == 1
        snap = (await client.get(f"/sessions/{sid}")).json()
        assert any(e["kind"] == "case_changed" and e["status"] == "reopened" for e in snap["timeline"])
        assert snap["pending_input"] is None and l3_runtime.backend.create_calls == 0
        state = (await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})).values
        assert not state["proposal"]["user_confirmed"] and state["requested_remedy"] is None


@pytest.mark.parametrize("report", ["outcome", "symptom"])
async def test_unresolved_report_reopens_original_case_and_requires_fresh_confirmation(l3_runtime, monkeypatch, report):
    import app.conversation.interpret as semantic

    original = semantic.interpret_turn
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = await seed_issue(client, monkeypatch)
        await send(client, sid, "我要换货")
        state = (await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})).values
        case_id, issue_id = state["case_id"], state["active_issue_id"]
        case = await l3_runtime.cases.store.get(case_id)
        assert (await client.post(f"/admin/api/cases/{case_id}/close", json={"expected_revision": case["revision"]})).status_code == 200

        async def interpretation(router, state, **kwargs):
            if state.get("text") == "原来那台仍然不吸了":
                return TurnInterpretation(primary_intent="report_problem", device_relation="current", facts=[{"kind": "symptom", "value": "不吸了", "quote": "仍然不吸了"}]), {"source": "test"}
            if state.get("text") == "这个问题还没有解决":
                return TurnInterpretation(primary_intent="step_feedback", device_relation="current", feedback="not_solved", feedback_quote="还没有解决", unresolved_quote="还没有解决"), {"source": "test"}
            if state.get("text") == "原售后案件的问题还没有解决":
                return TurnInterpretation(primary_intent="report_problem", device_relation="current", unresolved_quote="问题还没有解决", business_reference={"relation": "case", "quote": "原售后案件"}), {"source": "test"}
            return await original(router, state, **kwargs)

        monkeypatch.setattr(semantic, "interpret_turn", interpretation)
        await send(client, sid, "查物流 DEMO-X10-001")
        assert (await l3_runtime.cases.store.get(case_id))["status"] == "closed"
        if report == "outcome":
            await send(client, sid, "查物流 DEMO-CN-003")
            ambiguous = events(await send(client, sid, "这个问题还没有解决"))
            assert (await l3_runtime.cases.store.get(case_id))["status"] == "closed"
            assert "请确认" in "".join(e.get("delta", "") for e in ambiguous)
        rows = events(await send(client, sid, "原售后案件的问题还没有解决" if report == "outcome" else "原来那台仍然不吸了"))
        assert not any(e["type"] == "error" for e in rows), rows
        assert any(e["type"] == "case_changed" and e["status"] == "reopened" for e in rows)
        final = (await client.get(f"/sessions/{sid}")).json()
        assert final["active_issue_id"] == issue_id
        assert final["pending_input"]["kind"] == "confirm_proposal"
        case = await l3_runtime.cases.store.get(case_id)
        assert case["reopened_count"] == 1 and case["external_refs"]["order_no"] == "DEMO-X10-001"
        assert not case["proposal"]["user_confirmed"] and l3_runtime.backend.create_calls == 0


async def seed_issue(client, monkeypatch, region="US", order="DEMO-X10-001"):
    import app.conversation.interpret as semantic

    async def interpretation(router, state, **kwargs):
        if state.get("entry") == "action":
            return await original(router, state, **kwargs)
        return TurnInterpretation(
            primary_intent="replacement_request", device_relation="current"
        ), {"source": "test"}

    original = semantic.interpret_turn
    monkeypatch.setattr(semantic, "interpret_turn", interpretation)
    sid = (await client.post("/sessions")).json()["session_id"]
    # First create a legitimate issue, then seed diagnostic evidence as an exhausted A1 state.
    await send(client, sid, "我要换货")
    snap = (await client.get(f"/sessions/{sid}")).json()
    graph = app.state.session_graph
    state = await graph.aget_state({"configurable": {"thread_id": sid}})
    iid = snap["active_issue_id"]
    patch = {
        "business_context": None,  # An old diagnostic checkpoint: exercise one-time migration.
        "product_state": "confirmed_sku",
        "product_confirmed": {
            "sku": "EUFY-X10-PRO-OMNI",
            "name": "eufy X10 Pro Omni",
            "category": "robot_vacuum",
            "in_scope": True,
        },
        "category": "robot_vacuum",
        "diagnose_outcome": {"mode": "evidence", "plan_id": "rv_suction_hair_wrap"},
        "service_context": {"region_use": region},
        "context_sources": {"region_use": "user"},
        "receipt": {
            "status": "order_verified",
            "fields": {"order_no": order},
            "verified_facts": {"purchase_date": "2026-02-26"},
        },
        "pending_card": None,
    }
    issues = state.values["issues"]
    issues[iid].update(patch)
    config = await graph.aupdate_state(
        {"configurable": {"thread_id": sid}}, patch | {"issues": issues}, as_node="commit_issue"
    )
    # Publish the seeded checkpoint in the in-memory projection used by API consistency checks.
    store = app.state.session_store
    await store.upsert_projection(
        sid,
        version=snap["version"],
        stage="guide",
        active_run_id=None,
        pending_input=None,
        published_checkpoint_id=config["configurable"]["checkpoint_id"],
    )
    return sid


async def test_a5_proposal_execute_snapshot_rating(l3_runtime, monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = await seed_issue(client, monkeypatch)
        rows = events(await send(client, sid, "我要换货"))
        assert any(e["type"] == "proposal_card" for e in rows), rows
        card = next(e for e in rows if e["type"] == "proposal_card")
        replacement = next(o for o in card["options"] if o["remedy"] == "replace")
        assert replacement["dispatch_estimate"] == {"working_days": 3, "action": "replacement.create", "actions_version": l3_runtime.executor.registry.version}
        snap = (await client.get(f"/sessions/{sid}")).json()
        assert snap["pending_input"]["kind"] == "confirm_proposal"
        rows = events(await act(client, sid, "confirm_proposal", {"option_id": "replace"}))
        assert any(e["type"] == "execution_card" and e["status"] == "succeeded" for e in rows), rows
        assert l3_runtime.backend.create_calls == 1
        snap = (await client.get(f"/sessions/{sid}")).json()
        assert snap["pending_input"]["kind"] == "rate_satisfaction"
        assert any(e["kind"] == "execution_card" for e in snap["timeline"])
        await act(client, sid, "rate_satisfaction", {"score": 5})
        assert len(l3_runtime.cases.store.ratings) == 1


@pytest.mark.parametrize("edit_cost", [False, True])
async def test_a6_approval_restores_graph(l3_runtime, monkeypatch, edit_cost):
    import asyncio

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 美国买、德国用：政策命中但跨区域，需要人工特批。用 UK 订单已经不行了 ——
        # 非 US 购买地没有可引用的政策，连候选方案都出不来，人工也没得批。
        sid = await seed_issue(client, monkeypatch, region="DE", order="DEMO-X10-001")
        rows = events(await send(client, sid, "我要换货"))
        assert any(
            e["type"] == "case_changed" and e["status"] == "awaiting_approval" for e in rows
        ), rows
        assert l3_runtime.backend.create_calls == 0
        queue = (await client.get("/admin/api/cases/queue")).json()["items"]
        case = next(c for c in queue if c["session_id"] == sid)
        response = await client.post(
            f"/admin/api/cases/{case['case_id']}/decision",
            json={
                "decision_id": str(uuid.uuid4()),
                "expected_revision": case["revision"],
                "decision": "approve",
                "option_id": "replace",
                "override_reason": "演示跨区域特批",
                "note": "同意按换货方案办理",
                "edited_option": {**next(o for o in case["proposal"]["options"] if o["option_id"] == "replace"), "cost_bearer": "shared"} if edit_cost else None,
            },
        )
        assert response.status_code == 200, response.text
        run_id = response.json()["run_id"]
        for _ in range(100):
            if not app.state.run_manager.is_live(run_id):
                break
            await asyncio.sleep(0.01)
        snap = (await client.get(f"/sessions/{sid}")).json()
        if edit_cost:
            assert l3_runtime.backend.create_calls == 0
            assert snap["pending_input"]["kind"] == "confirm_proposal"
            offered = next(e for e in reversed(snap["timeline"]) if e["kind"] == "proposal_card")
            assert offered["options"][0]["cost_bearer"] == "shared"
            await act(client, sid, "confirm_proposal", {"option_id": "replace"})
            snap = (await client.get(f"/sessions/{sid}")).json()
        assert any(
            e["kind"] == "execution_card" and e["status"] == "succeeded" for e in snap["timeline"]
        ), snap
        assert l3_runtime.backend.create_calls == 1


@pytest.mark.parametrize("query_order", ["DEMO-X10-001", "DEMO-CN-003"])
async def test_inline_consult_keeps_proposal_card_and_token(l3_runtime, monkeypatch, query_order):
    import app.conversation.interpret as semantic

    original = semantic.interpret_turn
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = await seed_issue(client, monkeypatch)
        await send(client, sid, "我要换货")
        before = (await client.get(f"/sessions/{sid}")).json()
        monkeypatch.setattr(semantic, "interpret_turn", original)
        rows = events(await send(client, sid, f"查物流 {query_order}"))
        assert any(e["type"] == "tool_call" and e["name"] == "logistics.query" for e in rows)
        after = (await client.get(f"/sessions/{sid}")).json()
        assert after["pending_input"]["card_id"] == before["pending_input"]["card_id"]
        assert after["pending_input"]["input_token"] == before["pending_input"]["input_token"]
        assert not any(e["type"] == "execution_card" for e in rows)
        rows = events(await act(client, sid, "confirm_proposal", {"option_id": "replace"}))
        assert any(e["type"] == "execution_card" and e["status"] == "succeeded" for e in rows)
        assert not any(e["type"] == "error" for e in rows), rows
        state = (await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})).values
        assert state["execution"]["status"] == "succeeded"
        assert state["execution"]["receipt"]["order_no"] == "DEMO-X10-001"
        from app.conversation.business import BusinessContext

        assert BusinessContext.restore(state).bind("warranty.check").params["order_no"] == query_order


@pytest.mark.parametrize("indirect", [False, True])
@pytest.mark.parametrize("completed", [False, True])
async def test_new_order_remedy_gets_its_own_issue_and_case(l3_runtime, monkeypatch, indirect, completed):
    import app.conversation.interpret as semantic

    original = semantic.interpret_turn
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = await seed_issue(client, monkeypatch)
        await send(client, sid, "我要换货")
        if completed:
            await act(client, sid, "confirm_proposal", {"option_id": "replace"})
        before = (await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})).values
        case_before = await l3_runtime.cases.store.get(before["case_id"])
        monkeypatch.setattr(semantic, "interpret_turn", original)
        if indirect:
            await send(client, sid, "查物流 DEMO-CN-003")
        rows = events(await send(client, sid, "我要退款" if indirect else "我要退款 DEMO-CN-003"))
        assert not any(e["type"] == "error" for e in rows), rows
        after = (await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})).values
        assert after["active_issue_id"] != before["active_issue_id"]
        assert after["case_id"] != before["case_id"]
        assert after["receipt"]["fields"]["order_no"] == "DEMO-CN-003"
        assert after["requested_remedy"] == "refund"
        assert after.get("execution") is None and after.get("execution_key") is None
        assert after.get("human_decision_id") is None
        assert after.get("policy_decision") is None
        assert after["service_context"].get("region_use") is None
        assert await l3_runtime.cases.store.get(before["case_id"]) == case_before
        assert l3_runtime.backend.create_calls == int(completed)
        # An explicit return reuses the original issue/case, not the new order's state.
        await send(client, sid, "我要换货 DEMO-X10-001")
        resumed = (await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})).values
        assert resumed["active_issue_id"] == before["active_issue_id"]
        assert resumed["case_id"] == before["case_id"]
        assert resumed["receipt"]["fields"]["order_no"] == "DEMO-X10-001"


async def test_other_order_without_id_collects_receipt_in_a_new_case(l3_runtime, monkeypatch):
    import app.conversation.interpret as semantic

    original = semantic.interpret_turn
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = await seed_issue(client, monkeypatch)
        await send(client, sid, "我要换货")
        before = (await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})).values
        monkeypatch.setattr(semantic, "interpret_turn", original)
        rows = events(await send(client, sid, "另一笔订单想退款"))
        assert not any(e["type"] == "error" for e in rows)
        waiting = (await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})).values
        assert waiting["active_issue_id"] != before["active_issue_id"]
        assert waiting["case_id"] != before["case_id"]
        assert waiting["pending_card"]["kind"] == "upload_receipt"
        assert not ((waiting.get("receipt") or {}).get("fields") or {}).get("order_no")
        rows = events(await send(client, sid, "DEMO-CN-003"))
        assert not any(e["type"] == "error" for e in rows)
        after = (await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})).values
        assert after["case_id"] == waiting["case_id"]
        assert after["receipt"]["fields"]["order_no"] == "DEMO-CN-003"
        assert after["requested_remedy"] == "refund"


@pytest.mark.parametrize("resume_explicitly", [False, True])
async def test_a7_diagnostic_then_queued_logistics(l3_runtime, monkeypatch, resume_explicitly):
    import app.conversation.interpret as semantic
    from app.conversation.business import BusinessContext
    from app.knowledge.runtime import set_knowledge_adapter
    from app.models.runtime import set_model_router

    set_model_router(None)
    set_knowledge_adapter(None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        rows = events(
            await send(client, sid, "eufy X10 Pro Omni 不吸了，另外换货单 DEMO-X10-001 发出去了吗")
        )
        snap = (await client.get(f"/sessions/{sid}")).json()
        assert "设备排障 → 物流查询" in "".join(e.get("delta", "") for e in rows), rows
        assert snap["pending_input"]["kind"] == "step_feedback", snap
        card_id = snap["pending_input"]["card_id"]
        await send(client, sid, "查订单 DEMO-CN-003")
        await send(client, sid, "查物流 DEMO-CN-003")
        interrupted = (await client.get(f"/sessions/{sid}")).json()
        queued = next(t for t in interrupted["issues"][0]["task_queue"] if t["intent"] == "logistics_query")
        assert queued["status"] == "pending"
        assert interrupted["pending_input"]["card_id"] == card_id
        if resume_explicitly:
            original = semantic.interpret_turn
            async def resume(router, state, **kwargs):
                if state.get("text") == "先处理之前排队的物流查询":
                    return TurnInterpretation(primary_intent="resume_task", target_task_id=queued["task_id"]), {"source": "test"}
                return await original(router, state, **kwargs)
            monkeypatch.setattr(semantic, "interpret_turn", resume)
            rows = events(await send(client, sid, "先处理之前排队的物流查询"))
            assert "DEMO-X10-001" in "".join(e.get("delta", "") for e in rows)
            assert (await client.get(f"/sessions/{sid}")).json()["pending_input"]["card_id"] == card_id
        rows = events(await act(client, sid, "step_feedback", {"feedback": "solved"}))
        assert not any(e["type"] == "error" for e in rows), rows
        if not resume_explicitly:
            assert any(e["type"] == "tool_call" and e["name"] == "logistics.query" for e in rows), rows
            assert "DEMO-X10-001" in "".join(e.get("delta", "") for e in rows)
        state = (await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})).values
        assert BusinessContext.restore(state).bind("warranty.check").params["order_no"] == "DEMO-X10-001"
        final = (await client.get(f"/sessions/{sid}")).json()
        assert all(t["status"] == "done" for t in final["issues"][0]["task_queue"])


async def test_a8_complaint_marks_existing_case_priority(l3_runtime, monkeypatch):
    import app.conversation.interpret as semantic

    original = semantic.interpret_turn
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = await seed_issue(client, monkeypatch)
        await send(client, sid, "我要换货")
        monkeypatch.setattr(semantic, "interpret_turn", original)
        rows = events(await send(client, sid, "我要投诉，太烂了"))
        row = next(r for r in await l3_runtime.cases.store.queue() if r["session_id"] == sid)
        assert row["complaint_risk"] and row["priority"] == "high"
        assert "人工协助" in "".join(e.get("delta", "") for e in rows)
        assert l3_runtime.backend.create_calls == 0


async def test_consult_order_reference_is_issue_scoped(l3_runtime):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        await send(client, sid, "查物流 DEMO-X10-001")
        rows = events(await send(client, sid, "这个订单还在保修期吗"))
        assert any(
            e["type"] == "tool_call" and e["name"] == "warranty.check" and e["status"] == "finished"
            for e in rows
        ), rows
        assert "保修截止" in "".join(e.get("delta", "") for e in rows)
        rows = events(await send(client, sid, "查另一个订单保修"))
        assert not any(e["type"] == "tool_call" for e in rows)
        rows = events(await send(client, sid, "保修状态"))
        assert not any(e["type"] == "tool_call" for e in rows)


@pytest.mark.parametrize(
    "followup,tool",
    [
        ("物流状态", "logistics.query"),
        ("保修状态", "warranty.check"),
        ("订单状态", "warranty.check"),
    ],
)
async def test_consult_short_followup_reuses_current_order(l3_runtime, followup, tool):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        await send(client, sid, "查物流 DEMO-X10-001")
        rows = events(await send(client, sid, followup))
        assert any(
            e["type"] == "tool_call" and e["name"] == tool and e["status"] == "finished"
            for e in rows
        ), rows
        assert "请提供订单号" not in "".join(e.get("delta", "") for e in rows)


async def test_logistics_id_after_multiple_turns(l3_runtime):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        await send(client, sid, "查物流 DEMO-X10-001")
        for _ in range(10):
            await send(client, sid, "谢谢，我再考虑一下")
        rows = events(await send(client, sid, "物流id呢"))
        shipment = await l3_runtime.backend.get_shipment(order_no="DEMO-X10-001")
        assert shipment.tracking_no in "".join(e.get("delta", "") for e in rows)


async def test_refund_after_logistics_does_not_ask_known_order_again(l3_runtime, monkeypatch):
    import app.conversation.interpret as semantic

    original = semantic.interpret_turn

    async def captured_meaning(router, state, **kwargs):
        if state.get("text") == "我想退货怎么办":
            return TurnInterpretation(
                primary_intent="refund_request", clarification="请提供需要退货的订单号或商品链接。"
            ), {"source": "captured_model"}
        return await original(router, state, **kwargs)

    monkeypatch.setattr(semantic, "interpret_turn", captured_meaning)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        await send(client, sid, "查物流 DEMO-X10-001")
        rows = events(await send(client, sid, "我想退货怎么办"))
        assert any(e["type"] == "context_card" for e in rows), rows
        assert "请提供需要退货的订单号" not in "".join(e.get("delta", "") for e in rows)
        state = await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})
        assert state.values["receipt"]["fields"]["order_no"] == "DEMO-X10-001"
        assert state.values["product_confirmed"]["sku"] == "EUFY-X10-PRO-OMNI"
        assert l3_runtime.backend.create_calls == 0


async def test_business_missing_order_then_text_supplement(l3_runtime):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        await send(client, sid, "我要申请换货")
        rows = events(await send(client, sid, "DEMO-X10-001"))
        assert any(e["type"] == "context_card" for e in rows), rows
        state = await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})
        case = await l3_runtime.cases.store.get(state.values["case_id"])
        assert case["sku"] == "EUFY-X10-PRO-OMNI"


async def test_two_orders_do_not_execute_a_random_query(l3_runtime):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        rows = events(await send(client, sid, "查 DEMO-X10-001 和 DEMO-UK-005 的物流"))
        assert not any(e["type"] == "tool_call" for e in rows)
        assert "多个订单" in "".join(e.get("delta", "") for e in rows)
        rows = events(await send(client, sid, "DEMO-X10-001"))
        assert any(e["type"] == "tool_call" and e["status"] == "finished" for e in rows)


async def test_switching_issues_restores_each_business_subject(l3_runtime, monkeypatch):
    import app.conversation.interpret as semantic
    original = semantic.interpret_turn
    first_issue = None

    async def meaning(router, state, **kwargs):
        if state.get("text") == "开始新问题":
            return TurnInterpretation(primary_intent="new_issue"), {"source": "test"}
        if state.get("text") == "回到原问题":
            return TurnInterpretation(primary_intent="resume_issue", target_issue_id=first_issue), {"source": "test"}
        return await original(router, state, **kwargs)

    monkeypatch.setattr(semantic, "interpret_turn", meaning)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        await send(client, sid, "查物流 DEMO-X10-001")
        first_issue = (await client.get(f"/sessions/{sid}")).json()["active_issue_id"]
        await send(client, sid, "开始新问题")
        rows = events(await send(client, sid, "查物流"))
        assert not any(e["type"] == "tool_call" for e in rows)
        await send(client, sid, "回到原问题")
        rows = events(await send(client, sid, "物流id呢"))
        assert "DEMO-TRACK-001" in "".join(e.get("delta", "") for e in rows)


async def test_transient_execution_failure_retries_original_case_after_inline_query(l3_runtime, monkeypatch):
    import app.conversation.interpret as semantic

    original = semantic.interpret_turn
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = await seed_issue(client, monkeypatch)
        await send(client, sid, "我要换货")
        l3_runtime.backend.faults.append({"op": "create_service_order", "order_no": "DEMO-X10-001", "mode": "timeout"})
        failed = events(await act(client, sid, "confirm_proposal", {"option_id": "replace"}))
        assert any(e["type"] == "case_changed" and e["status"] == "executing_failed" for e in failed)
        retry = next(e for e in failed if e["type"] == "proposal_card")
        assert retry["retry"] and [o["option_id"] for o in retry["options"]] == ["replace"]
        first_receipt = next(e for e in failed if e["type"] == "execution_card")
        assert l3_runtime.backend.create_calls == 0
        monkeypatch.setattr(semantic, "interpret_turn", original)
        await send(client, sid, "查物流 DEMO-CN-003")
        snapshot = (await client.get(f"/sessions/{sid}")).json()
        assert snapshot["pending_input"]["card_id"] == retry["card_id"]
        assert next(c for c in snapshot["timeline"] if c.get("card_id") == retry["card_id"])["retry"]
        l3_runtime.backend.faults.clear()
        succeeded = events(await act(client, sid, "confirm_proposal", {"option_id": "replace"}))
        last_receipt = next(e for e in succeeded if e["type"] == "execution_card")
        assert last_receipt["status"] == "succeeded"
        assert last_receipt["idempotency_key"] == first_receipt["idempotency_key"]
        assert last_receipt["receipt"]["order_no"] == "DEMO-X10-001"
        assert l3_runtime.backend.create_calls == 1
        execution = await l3_runtime.executor.store.get(last_receipt["idempotency_key"])
        assert execution["attempt"] == 2
        assert not any(e["type"] == "error" for e in [*failed, *succeeded])


async def test_retry_rechecks_changed_service_context(l3_runtime, monkeypatch):
    import app.conversation.interpret as semantic

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = await seed_issue(client, monkeypatch)
        await send(client, sid, "我要换货")
        l3_runtime.backend.faults.append({"op": "create_service_order", "order_no": "DEMO-X10-001", "mode": "timeout"})
        await act(client, sid, "confirm_proposal", {"option_id": "replace"})
        original = semantic.interpret_turn

        async def supplement(router, state, **kwargs):
            if state.get("entry") == "action":
                return await original(router, state, **kwargs)
            return TurnInterpretation(primary_intent="supplement", facts=[{"kind": "context", "context_field": "region_use", "value": "DE", "quote": "德国"}]), {"source": "test"}

        monkeypatch.setattr(semantic, "interpret_turn", supplement)
        await send(client, sid, "实际在德国使用")
        l3_runtime.backend.faults.clear()
        rows = events(await act(client, sid, "confirm_proposal", {"option_id": "replace"}))
        assert l3_runtime.backend.create_calls == 0
        assert "办理依据已发生变化" in "".join(e.get("delta", "") for e in rows)
        assert any(e["type"] == "case_changed" and e["status"] == "awaiting_approval" for e in rows)
        assert not any(e["type"] == "error" for e in rows)


async def test_confirm_context_command_is_applied_before_intent_routing(l3_runtime):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        rows = events(await send(client, sid, "我要退款 DEMO-CN-003"))
        card = next(e for e in rows if e["type"] == "context_card")
        assert card["fields"] == ["region_use"] and "DE" in card["choices"]["region_use"]
        rows = events(await act(client, sid, "confirm_context", {**card["prefilled"], "region_use": "DE"}))
        assert not any(e["type"] in {"context_card", "error"} for e in rows)
        assert any(e["type"] == "case_changed" and e["status"] == "awaiting_approval" for e in rows)
        state = (await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})).values
        assert state["service_context"]["region_use"] == "DE"
        assert state["card_results"][card["card_id"]]["confirmed_fields"]["region_use"] == "DE"
