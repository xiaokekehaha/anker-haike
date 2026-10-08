import asyncio
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta

import pytest
from haike_contracts.common import WarrantyDecision

from app.actions.executor import ActionExecutor, AuthorizationDenied
from app.actions.gate import AuthorizationGate
from app.actions.registry import SUBMITTED_NEXT_STEP, ActionRegistry, ConfigError
from app.actions.store import ExecutionBusy, ExecutionNeedsReview, IdempotencyConflict
from app.backends.protocol import Conflict, NotFound, ServiceOrderRequest, Timeout, Unavailable
from app.backends.service import MemoryBackend

FULL_EVIDENCE = {
    "order_or_receipt": "order:Anker016",
    "address": "order:AnkerDirect",
    "photo_or_video": "images:img-1",
    "serial_number": "customer:T8D04121",
}


def in_warranty():
    return WarrantyDecision(
        status="in_warranty", basis="order", warranty_end=date(2027, 4, 1), as_of=date(2026, 10, 8),
        order_no="Anker016", reason="订单 Anker016 质保至 2027-04-01",
    )


def gate(**overrides):
    values = {
        "kind": "replace",
        "warranty": in_warranty(),
        "logistics_ok": False,
        "evidence": FULL_EVIDENCE,
        "risk_cases": [],
        "allowed_operations": True,
        "user_confirmed": True,
        "case_status": "awaiting_confirmation",
    }
    return AuthorizationGate().check(**(values | overrides))


def request(**overrides):
    return ServiceOrderRequest(
        **{"type": "replace", "order_no": "Anker016", "sku": "T8D04121", "reason": "左侧无吸力",
           "client_ref": "case:service_order.create:replace"} | overrides
    )


async def test_order_book_reads_official_orders_and_tracking():
    backend = MemoryBackend()
    order = await backend.get_order("anker016")
    assert order.order_no == "Anker016" and order.main_line.sku == "T8D04121"
    assert (await backend.find_order_by_tracking("Anker 1234567-3")).order_no == "Anker002"
    for fn in (
        lambda: backend.get_order("missing"),
        lambda: backend.find_order_by_tracking("missing"),
        lambda: backend.get_service_order("missing"),
        lambda: backend.create_service_order(request(order_no="missing")),
    ):
        with pytest.raises(NotFound):
            await fn()


async def test_service_order_is_submitted_once_per_client_ref():
    backend = MemoryBackend()
    first, second = await asyncio.gather(
        backend.create_service_order(request()), backend.create_service_order(request())
    )
    assert first == second == await backend.get_service_order(first.service_order_no)
    assert first.status == "submitted" and backend.create_calls == 1


async def test_dealer_path_service_order_has_no_order_number():
    backend = MemoryBackend()
    created = await backend.create_service_order(request(order_no=None, sku=None, client_ref="dealer-case"))
    assert created.order_no is None and created.type == "replace"


async def test_service_order_rejects_sku_not_on_order():
    with pytest.raises(Conflict):
        await MemoryBackend().create_service_order(request(sku="T2351111"))


@pytest.mark.parametrize("mode,error", [("timeout", Timeout), ("unavailable", Unavailable), ("conflict", Conflict)])
async def test_fault_injection(mode, error):
    backend = MemoryBackend(faults=[{"op": "create_service_order", "key": "Anker016", "mode": mode}])
    with pytest.raises(error):
        await backend.create_service_order(request())


@pytest.mark.parametrize(
    "override",
    [
        {"user_confirmed": False},
        {"warranty": None},
        {"warranty": in_warranty().model_copy(update={"status": "out_of_warranty"})},
        {"warranty": in_warranty().model_copy(update={"status": "unauthorized_dealer"})},
        {"evidence": {k: v for k, v in FULL_EVIDENCE.items() if k != "serial_number"}},
        {"evidence": {k: v for k, v in FULL_EVIDENCE.items() if k != "photo_or_video"}},
        {"risk_cases": [{"rule_id": "R4", "status": "reported"}]},
        {"allowed_operations": False},
        {"execution_status": "running"},
        {"execution_status": "succeeded"},
        {"case_status": "closed"},
        {"kind": "reship", "logistics_ok": False},
    ],
)
def test_gate_denies_each_constraint(override):
    result = gate(**override)
    assert not result.passed and result.fallback == "await_human"
    assert [c.name for c in result.checks] == ["eligibility", "evidence", "safety", "idempotency"]


def test_gate_names_missing_sop_evidence():
    result = gate(evidence={"order_or_receipt": "order:Anker016"})
    detail = next(c for c in result.checks if c.name == "evidence").detail
    assert "收货地址" in detail and "故障照片或视频" in detail and "产品 SN" in detail


def test_reship_needs_only_order_and_logistics():
    assert gate(kind="reship", warranty=None, logistics_ok=True, evidence={"order_or_receipt": "order:Anker007"}).passed
    assert gate().passed


@pytest.mark.parametrize("mutation", ["requires", "idempotency", "loosened", "read"])
def test_registry_fails_closed(mutation):
    registry = ActionRegistry()
    config = {"version": registry.version, "actions": deepcopy(registry.actions)}
    spec = config["actions"]["service_order.create"]
    if mutation in {"requires", "idempotency"}:
        spec.pop(mutation)
    elif mutation == "loosened":
        spec["requires"]["checks"] = ["safety"]
    else:
        spec["kind"] = "read"
    with pytest.raises(ConfigError):
        ActionRegistry(config)


WRITE_ARGS = {
    "idempotency_key": "case:service_order.create:replace",
    "session_id": "s",
    "run_id": "r",
    "case_id": "e3d41a46-6c8d-4511-8023-06989b90bc5f",
}


def params(**overrides):
    return request(**overrides).model_dump(exclude={"client_ref"}, exclude_none=True)


async def test_executor_gate_and_idempotency():
    backend = MemoryBackend()
    executor = ActionExecutor(backend)
    with pytest.raises(AuthorizationDenied):
        await executor.run("service_order.create", params(), **WRITE_ARGS)
    assert backend.create_calls == 0
    events = []
    first = await executor.run("service_order.create", params(), **WRITE_ARGS, gate_result=gate(), writer=events.append)
    second = await executor.run("service_order.create", params(), **WRITE_ARGS, gate_result=gate())
    assert first.receipt == second.receipt and second.replayed
    assert first.receipt.next_step == SUBMITTED_NEXT_STEP and "工作日" not in first.receipt.next_step
    assert backend.create_calls == 1
    assert [e["status"] for e in events] == ["started", "finished"]
    with pytest.raises(IdempotencyConflict):
        await executor.run("service_order.create", params(order_no="Anker013"), **WRITE_ARGS, gate_result=gate())


async def test_executor_rejects_unknown_service_type():
    with pytest.raises(ConfigError):
        await ActionExecutor(MemoryBackend()).run(
            "service_order.create", params() | {"type": "paid_repair"}, **WRITE_ARGS, gate_result=gate()
        )


async def test_logistics_query_returns_all_packages():
    result = await ActionExecutor(MemoryBackend()).run(
        "logistics.query", {"order_no": "Anker001"}, idempotency_key="k", session_id="s", run_id="r",
        as_of=date(2026, 10, 8),
    )
    assert result.status == "succeeded"
    assert [p["tracking_no"] for p in result.receipt.data["packages"]] == ["Anker1234567", "Anker1234567-1"]


async def test_lease_fencing_and_one_stale_recovery():
    executor = ActionExecutor(MemoryBackend())
    row = {"execution_id": "e", "idempotency_key": "key", "action_kind": "service_order.create",
           "request": {}, "case_id": "c", "session_id": "s"}
    first, _ = await executor.store.claim(row, 100)
    with pytest.raises(ExecutionBusy):
        await executor.store.claim(row, 100)
    executor.store.rows["key"]["started_at"] = datetime.now(UTC) - timedelta(seconds=1)
    second, acquired = await executor.store.claim(row, 100)
    assert acquired and second["attempt"] == 2
    with pytest.raises(ExecutionBusy):
        await executor.store.finish("key", first["attempt"], "succeeded", {}, None)
    executor.store.rows["key"]["started_at"] = datetime.now(UTC) - timedelta(seconds=1)
    with pytest.raises(ExecutionNeedsReview):
        await executor.store.claim(row, 100)


def spy_creates(backend):
    """Record every create request, including ones the backend dedupes by client_ref."""
    calls = []
    create = backend.create_service_order

    async def counted(req):
        calls.append(req.client_ref)
        return await create(req)

    backend.create_service_order = counted
    return calls


def ambiguous(backend, mode="created_then_timeout"):
    backend.faults.append({"op": "create_service_order", "key": "Anker016", "mode": mode})


async def test_created_then_timeout_leaves_an_order_found_by_client_ref():
    backend = MemoryBackend()
    ambiguous(backend)
    with pytest.raises(Timeout):
        await backend.create_service_order(request(client_ref="ref-1"))
    found = await backend.find_service_order("ref-1")
    assert found and found.order_no == "Anker016" and backend.create_calls == 1
    assert await backend.find_service_order("other") is None


async def test_retry_after_ambiguous_timeout_reuses_the_created_order():
    backend = MemoryBackend()
    calls = spy_creates(backend)
    executor = ActionExecutor(backend)
    ambiguous(backend)
    first = await executor.run("service_order.create", params(), **WRITE_ARGS, gate_result=gate())
    assert first.status == "failed" and first.recoverable and not first.needs_review
    assert (await executor.store.get(WRITE_ARGS["idempotency_key"]))["error"]["outcome_unknown"]
    backend.faults.clear()
    second = await executor.run("service_order.create", params(), **WRITE_ARGS, gate_result=gate())
    assert second.status == "succeeded"
    assert calls == [WRITE_ARGS["idempotency_key"]]
    found = await backend.find_service_order(WRITE_ARGS["idempotency_key"])
    assert second.receipt.service_order_no == found.service_order_no


async def test_retry_after_timeout_before_commit_creates_once():
    backend = MemoryBackend()
    calls = spy_creates(backend)
    executor = ActionExecutor(backend)
    ambiguous(backend, "timeout")
    first = await executor.run("service_order.create", params(), **WRITE_ARGS, gate_result=gate())
    assert first.status == "failed" and backend.create_calls == 0
    backend.faults.clear()
    second = await executor.run("service_order.create", params(), **WRITE_ARGS, gate_result=gate())
    assert second.status == "succeeded" and backend.create_calls == 1
    assert calls == [WRITE_ARGS["idempotency_key"]] * 2


async def test_unverifiable_previous_attempt_goes_to_review_without_creating():
    backend = MemoryBackend()
    calls = spy_creates(backend)
    executor = ActionExecutor(backend)
    ambiguous(backend)
    await executor.run("service_order.create", params(), **WRITE_ARGS, gate_result=gate())
    backend.faults.clear()

    async def lookup_down(client_ref):
        raise Unavailable()

    backend.find_service_order = lookup_down
    result = await executor.run("service_order.create", params(), **WRITE_ARGS, gate_result=gate())
    assert result.status == "failed" and not result.recoverable and result.needs_review
    assert "人工核实" in result.receipt.next_step
    assert calls == [WRITE_ARGS["idempotency_key"]]


@pytest.mark.parametrize("mode,recoverable", [("timeout", True), ("unavailable", True), ("conflict", False)])
async def test_executor_errors_are_classified(mode, recoverable):
    executor = ActionExecutor(MemoryBackend(faults=[{"op": "get_order", "key": "Anker016", "mode": mode}]))
    result = await executor.run(
        "warranty.check", {"order_no": "Anker016"}, idempotency_key="key", session_id="s", run_id="r"
    )
    assert result.status == "failed" and result.recoverable == recoverable
