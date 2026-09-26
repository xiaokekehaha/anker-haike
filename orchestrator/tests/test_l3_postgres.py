"""Exercise real SQL in an isolated schema of the configured project database."""

import importlib.util
import uuid

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.actions.executor import ActionExecutor
from app.actions.store import PostgresExecutionStore
from app.backends.mock import MockBackend
from app.backends.protocol import ServiceOrderRequest
from app.backends.seed import seed_backends
from app.cases.service import CaseService
from app.cases.store import CaseConflict, PostgresCaseStore
from app.settings import REPO_ROOT, settings


@pytest.fixture
async def l3_pool():
    try:
        connection = await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True, connect_timeout=1
        )
    except psycopg.OperationalError:
        pytest.skip("project Postgres unavailable")
    schema = "l3_test_" + uuid.uuid4().hex
    await connection.execute(f"create schema {schema}")
    pool = AsyncConnectionPool(
        settings.database_url,
        open=False,
        min_size=1,
        max_size=4,
        kwargs={"autocommit": True, "row_factory": dict_row, "options": f"-c search_path={schema}"},
    )
    await pool.open(wait=True)
    try:
        async with pool.connection() as conn:
            await conn.execute(
                "create table orders_mock(order_no text primary key,sku text not null,channel text not null,purchase_date date not null)"
            )
            path = REPO_ROOT / "orchestrator/migrations/versions/0006_l3_closed_loop.py"
            spec = importlib.util.spec_from_file_location("l3_migration", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            for statement in module.STATEMENTS:
                await conn.execute(statement)
            from types import SimpleNamespace
            for name in ("0007_l3_metrics", "0008_service_order_client_ref"):
                path = REPO_ROOT / f"orchestrator/migrations/versions/{name}.py"
                spec = importlib.util.spec_from_file_location(name, path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                statements = []
                module.op = SimpleNamespace(execute=statements.append)
                module.upgrade()
                for statement in statements:
                    await conn.execute(statement)
        yield pool
    finally:
        await pool.close()
        await connection.execute(f"drop schema {schema} cascade")
        await connection.close()


async def test_seed_sql_and_backend_idempotency(l3_pool):
    import asyncio

    path = REPO_ROOT / "config/backends_mock.yaml"
    assert await seed_backends(l3_pool, path) == await seed_backends(l3_pool, path)
    backend = MockBackend(l3_pool)
    order = await backend.get_order("DEMO-X10-001")
    assert order.region_purchase == "US"
    shipment = await backend.get_shipment(order_no=order.order_no)
    assert await backend.get_shipment(tracking_no=shipment.tracking_no) == shipment
    req = ServiceOrderRequest(
        order_no=order.order_no, sku=order.sku, reason_code="quality", client_ref="case:replace"
    )
    results = await asyncio.gather(*[backend.create_service_order(req) for _ in range(5)])
    assert all(r == results[0] for r in results)
    assert await backend.get_service_order(results[0].service_order_no) == results[0]
    assert await backend.find_service_order("case:replace") == results[0]
    assert await backend.find_service_order("other") is None


async def test_durable_executor_and_case_transactions(l3_pool):
    import asyncio

    from tests.test_l3_backends_actions import gate

    await seed_backends(l3_pool, REPO_ROOT / "config/backends_mock.yaml")
    cases = CaseService(PostgresCaseStore(l3_pool))
    case = await cases.open("s", "i", {"sku": "EUFY-X10-PRO-OMNI", "category": "robot_vacuum"})
    case = await cases.bind_order(case["case_id"], "DEMO-X10-001")
    with pytest.raises(CaseConflict, match="其他订单"):
        await cases.bind_order(case["case_id"], "DEMO-CN-003")
    assert (await cases.store.get(case["case_id"]))["external_refs"]["order_no"] == "DEMO-X10-001"
    case = await cases.transition(case["case_id"], "proposing", "test")
    option = {
        "option_id": "replace",
        "remedy": "replace",
        "title": "申请换货",
        "auto_allowed": False,
    }
    case = await cases.transition(
        case["case_id"],
        "awaiting_approval",
        "cross region",
        proposal={"options": [option]},
        policy_decision={"needs_human": True},
    )
    args = {
        "decision": "approve",
        "actor": "agent:test",
        "expected_revision": case["revision"],
        "note": "approved",
        "option_id": "replace",
        "override_reason": "demo override",
    }
    ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    results = await asyncio.gather(
        *[cases.decide(case["case_id"], decision_id=d, **args) for d in ids], return_exceptions=True
    )
    assert sum(isinstance(r, CaseConflict) for r in results) == 1
    row = await cases.store.get(case["case_id"])
    assert len(row["decisions"]) == 1 and row["status"] == "approved"
    decision = row["decisions"][0]
    assert (await cases.decide(case["case_id"], decision_id=decision["decision_id"], **args))[
        "revision"
    ] == row["revision"]
    await cases.consume_decision(case["case_id"], decision["decision_id"], "input1")
    await cases.transition(case["case_id"], "executing", "test")
    backend = MockBackend(l3_pool)
    executor = ActionExecutor(backend, PostgresExecutionStore(l3_pool))
    params = {
        "order_no": "DEMO-X10-001",
        "sku": "EUFY-X10-PRO-OMNI",
        "reason_code": "quality",
        "evidence_ids": [],
    }
    args = {
        "idempotency_key": "case:replace",
        "case_id": case["case_id"],
        "session_id": "s",
        "issue_id": "i",
        "run_id": "r",
        "gate_result": gate(),
    }
    first = await executor.run("replacement.create", params, **args)
    # A fresh service instance simulates process restart.
    second = await ActionExecutor(backend, PostgresExecutionStore(l3_pool)).run(
        "replacement.create", params, **args
    )
    assert second.replayed and second.receipt == first.receipt
    await cases.attach_execution(case["case_id"], first.receipt.model_dump())
    with pytest.raises(CaseConflict):
        await cases.close(case["case_id"], user_confirmed=True, external_status="created")
    row = await cases.close(case["case_id"], user_confirmed=True, external_status="shipped")
    assert row["status"] == "closed"
    assert (await cases.reopen(case["case_id"]))["reopened_count"] == 1
    await cases.rate("s", "i", 5, case_id=case["case_id"])
    await cases.rate("s", "i", 4, case_id=case["case_id"])
    async with l3_pool.connection() as conn:
        row = await (
            await conn.execute("select count(*) as n from satisfaction_ratings")
        ).fetchone()
        assert row["n"] == 1


async def test_metric_sql_observes_manual_close(l3_pool):
    from datetime import UTC, datetime, timedelta

    from app.analytics.l3 import episode, metrics
    service = CaseService(PostgresCaseStore(l3_pool))
    row = await service.open("metric-session", "issue", {})
    value = {"session_id": "metric-session", "active_issue_id": "issue", "case_id": row["case_id"], "stage": "track"}
    await service.store.record_episode(episode(value, row))
    await service.rate("metric-session", "issue", 5, case_id=row["case_id"])
    rows = await service.store.metric_rows(datetime.now(UTC)-timedelta(days=1))
    assert metrics(rows)["terminal"] == 0 and metrics(rows)["nss"] == 1
    await service.close(row["case_id"], actor="agent:test")
    rows = await service.store.metric_rows(datetime.now(UTC)-timedelta(days=1))
    assert rows[0]["outcome"] == "human_executed"
    assert metrics(rows)["managed_rate"] == 0


async def test_retention_keeps_open_case_and_explicit_delete_erases_raw(l3_pool):
    from datetime import UTC, datetime, timedelta

    from app.analytics.l3 import episode
    from app.retention import delete_session_data
    async with l3_pool.connection() as conn:
        await conn.execute("create table sessions(session_id text primary key, active_run_id text, updated_at timestamptz)")
        await conn.execute("insert into sessions values ('retention-session',null,now()-interval '2 days')")
    service=CaseService(PostgresCaseStore(l3_pool))
    row=await service.open('retention-session','issue',{})
    await service.record_commitment(row['case_id'],'模拟时效承诺','clause')
    await service.store.record_episode(episode({'session_id':'retention-session','active_issue_id':'issue','case_id':row['case_id'],'stage':'track'},row))
    await service.rate('retention-session','issue',4,'客户原文',row['case_id'])
    assert await delete_session_data(l3_pool,'retention-session',expired_before=datetime.now(UTC)-timedelta(days=1)) == {}
    # A manual close happens after the last conversation episode was recorded.
    await service.close(row['case_id'], actor='agent:reviewer')
    since = datetime.now(UTC)-timedelta(days=1)
    before = (await service.store.metric_rows(since))[0]
    assert before['outcome'] == 'human_executed' and before['human_involved']
    await delete_session_data(l3_pool,'retention-session')
    result=await service.store.get(row['case_id'])
    assert result['session_id'] is None and all(e['payload']=={} for e in result['events'])
    async with l3_pool.connection() as conn:
        metric=await (await conn.execute('select * from service_episodes')).fetchone()
        assert metric['session_id'] is None and metric['rating']==4
        assert metric['outcome'] == 'human_executed' and metric['human_involved']
    after = (await service.store.metric_rows(since))[0]
    assert {k: after[k] for k in ('outcome', 'human_involved', 'rating', 'intent_correct')} == {k: before[k] for k in ('outcome', 'human_involved', 'rating', 'intent_correct')}
