import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from app.actions.executor import ActionExecutor, AuthorizationDenied
from app.actions.gate import AuthorizationGate
from app.actions.registry import ActionRegistry, ConfigError
from app.actions.store import ExecutionBusy, ExecutionNeedsReview, IdempotencyConflict
from app.backends.mock import MemoryBackend
from app.backends.protocol import Conflict, NotFound, ServiceOrderRequest, Timeout, Unavailable
from app.policy import PolicyEngine, PolicyInput


def gate(**overrides):
    decision = PolicyEngine().decide(
        PolicyInput(
            sku="EUFY-X10-PRO-OMNI",
            region_purchase="US",
            region_use="US",
            channel="official_store",
            purchase_date="2026-02-26",
            today="2026-09-14",
            fault_class="quality",
        )
    )
    values = {
        "decision": decision,
        "option": {"remedy": "replace"},
        "receipt": {"status": "order_verified"},
        "product_state": "confirmed_sku",
        "risk_cases": [],
        "allowed_operations": True,
        "user_confirmed": True,
        "case_status": "awaiting_confirmation",
    }
    return AuthorizationGate().check(**(values | overrides))


def request():
    return ServiceOrderRequest(
        order_no="DEMO-X10-001", sku="EUFY-X10-PRO-OMNI", reason_code="quality"
    )


@pytest.mark.parametrize("approved", [False, True])
def test_order_binding_cannot_be_overridden_by_consent_or_approval(approved):
    result = gate(
        case_order_no="order-a",
        human_approved=approved,
        receipt={"status": "order_verified", "fields": {"order_no": "order-b"}},
    )
    assert not result.passed
    assert not next(c for c in result.checks if c.name == "evidence_and_consent").passed
    assert gate(
        case_order_no="order-a",
        receipt={"status": "order_verified", "fields": {"order_no": "order-a"}},
    ).passed


async def test_backend_normal_not_found_and_business_idempotency():
    backend = MemoryBackend()
    assert (await backend.get_order("DEMO-X10-001")).sku == request().sku
    shipment = await backend.get_shipment(order_no="DEMO-X10-001")
    assert await backend.get_shipment(tracking_no=shipment.tracking_no) == shipment
    first, second = await asyncio.gather(
        backend.create_service_order(request()), backend.create_service_order(request())
    )
    assert first == second == await backend.get_service_order(first.service_order_no)
    assert backend.create_calls == 1
    for fn in (
        lambda: backend.get_order("missing"),
        lambda: backend.get_shipment(order_no="missing"),
        lambda: backend.get_service_order("missing"),
        lambda: backend.create_service_order(request().model_copy(update={"order_no": "missing"})),
    ):
        with pytest.raises(NotFound):
            await fn()


@pytest.mark.parametrize("number,error", [(1, Timeout), (2, Unavailable), (3, Conflict)])
async def test_fault_injection(number, error):
    backend = MemoryBackend()
    with pytest.raises(error):
        await backend.create_service_order(
            request().model_copy(update={"order_no": f"DEMO-FAIL-{number:03}"})
        )


@pytest.mark.parametrize(
    "override",
    [
        {"user_confirmed": False},
        {"receipt": {"status": "insufficient"}},
        {"product_state": "unknown"},
        {"risk_cases": [{"rule_id": "R4", "status": "reported"}]},
        {"allowed_operations": False},
        {"execution_status": "running"},
        {"execution_status": "succeeded"},
        {"case_status": "closed"},
        {"option": {"remedy": "refund"}},
    ],
)
def test_gate_denies_each_constraint(override):
    result = gate(**override)
    assert not result.passed and result.fallback == "await_human"
    assert len(result.model_dump()["checks"]) == 4


def test_human_policy_override_cannot_bypass_safety_or_consent():
    assert not gate(human_approved=True, allowed_operations=False).passed
    assert not gate(human_approved=True, user_confirmed=False).passed
    assert gate().passed


@pytest.mark.parametrize("mutation", ["requires", "idempotency", "state", "read", "estimate"])
def test_registry_fails_closed(mutation):
    registry = ActionRegistry()
    config = {"version": registry.version, "actions": deepcopy(registry.actions)}
    spec = config["actions"]["replacement.create"]
    if mutation in {"requires", "idempotency"}:
        spec.pop(mutation)
    elif mutation == "state":
        spec["params"]["sku"]["from_state"] = "untrusted.value"
    elif mutation == "estimate":
        spec["estimated_dispatch_working_days"] = 0
    else:
        spec["kind"] = "read"
    with pytest.raises(ConfigError):
        ActionRegistry(config)


async def test_executor_gate_and_idempotency():
    backend = MemoryBackend()
    executor = ActionExecutor(backend)
    args = {
        "idempotency_key": "case:replace:v1",
        "session_id": "s",
        "run_id": "r",
        "case_id": "e3d41a46-6c8d-4511-8023-06989b90bc5f",
    }
    params = request().model_dump(exclude={"type", "client_ref"})
    with pytest.raises(AuthorizationDenied):
        await executor.run("replacement.create", params, **args)
    assert backend.create_calls == 0
    events = []
    first = await executor.run(
        "replacement.create", params, **args, gate_result=gate(), writer=events.append
    )
    second = await executor.run("replacement.create", params, **args, gate_result=gate())
    assert first.receipt == second.receipt and second.replayed
    assert backend.create_calls == 1
    assert [e["status"] for e in events] == ["started", "finished"]
    assert "DEMO-X10-001" not in str(events)
    with pytest.raises(IdempotencyConflict):
        await executor.run(
            "replacement.create", params | {"order_no": "DEMO-S1-002"}, **args, gate_result=gate()
        )


async def test_lease_fencing_and_one_stale_recovery():
    executor = ActionExecutor(MemoryBackend())
    row = {
        "execution_id": "e",
        "idempotency_key": "key",
        "action_kind": "replacement.create",
        "request": {},
        "case_id": "c",
        "session_id": "s",
    }
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
    """Record every create request, including ones the backend dedupes by business key."""
    calls = []
    create = backend.create_service_order

    async def counted(req):
        calls.append(req.client_ref)
        return await create(req)

    backend.create_service_order = counted
    return calls


WRITE_ARGS = {
    "idempotency_key": "case:replacement.create:replace",
    "session_id": "s",
    "run_id": "r",
    "case_id": "e3d41a46-6c8d-4511-8023-06989b90bc5f",
}


def ambiguous(backend, mode="created_then_timeout"):
    backend.faults.append({"op": "create_service_order", "order_no": "DEMO-X10-001", "mode": mode})


async def test_created_then_timeout_leaves_an_order_found_by_client_ref():
    backend = MemoryBackend()
    ambiguous(backend)
    with pytest.raises(Timeout):
        await backend.create_service_order(request().model_copy(update={"client_ref": "ref-1"}))
    found = await backend.find_service_order("ref-1")
    assert found and found.order_no == "DEMO-X10-001" and backend.create_calls == 1
    assert await backend.find_service_order("other") is None


async def test_retry_after_ambiguous_timeout_reuses_the_created_order():
    backend = MemoryBackend()
    calls = spy_creates(backend)
    executor = ActionExecutor(backend)
    params = request().model_dump(exclude={"type", "client_ref"})
    ambiguous(backend)
    first = await executor.run("replacement.create", params, **WRITE_ARGS, gate_result=gate())
    assert first.status == "failed" and first.recoverable and not first.needs_review
    stored = await executor.store.get(WRITE_ARGS["idempotency_key"])
    assert stored["error"]["outcome_unknown"]
    backend.faults.clear()
    second = await executor.run("replacement.create", params, **WRITE_ARGS, gate_result=gate())
    assert second.status == "succeeded"
    assert calls == [WRITE_ARGS["idempotency_key"]]
    found = await backend.find_service_order(WRITE_ARGS["idempotency_key"])
    assert second.receipt.service_order_no == found.service_order_no


async def test_retry_after_timeout_before_commit_creates_once():
    backend = MemoryBackend()
    calls = spy_creates(backend)
    executor = ActionExecutor(backend)
    params = request().model_dump(exclude={"type", "client_ref"})
    ambiguous(backend, "timeout")
    first = await executor.run("replacement.create", params, **WRITE_ARGS, gate_result=gate())
    assert first.status == "failed" and backend.create_calls == 0
    backend.faults.clear()
    second = await executor.run("replacement.create", params, **WRITE_ARGS, gate_result=gate())
    assert second.status == "succeeded" and backend.create_calls == 1
    assert calls == [WRITE_ARGS["idempotency_key"]] * 2


async def test_unverifiable_previous_attempt_goes_to_review_without_creating():
    backend = MemoryBackend()
    calls = spy_creates(backend)
    executor = ActionExecutor(backend)
    params = request().model_dump(exclude={"type", "client_ref"})
    ambiguous(backend)
    await executor.run("replacement.create", params, **WRITE_ARGS, gate_result=gate())
    backend.faults.clear()

    async def lookup_down(client_ref):
        raise Unavailable()

    backend.find_service_order = lookup_down
    result = await executor.run("replacement.create", params, **WRITE_ARGS, gate_result=gate())
    assert result.status == "failed" and not result.recoverable and result.needs_review
    assert "人工核实" in result.receipt.next_step
    assert calls == [WRITE_ARGS["idempotency_key"]]


@pytest.mark.parametrize("number,recoverable", [(1, True), (2, True), (3, False)])
async def test_executor_errors_are_classified(number, recoverable):
    executor = ActionExecutor(MemoryBackend())
    result = await executor.run(
        "warranty.check",
        {"order_no": f"DEMO-FAIL-{number:03}"},
        idempotency_key="key",
        session_id="s",
        run_id="r",
    )
    assert result.status == "failed" and result.recoverable == recoverable
