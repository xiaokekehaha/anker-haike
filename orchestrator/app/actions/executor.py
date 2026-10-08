import asyncio
import uuid
from dataclasses import dataclass

from haike_contracts.common import SERVICE_ORDER_TYPES, GateResult, Receipt

from app.backends.protocol import BackendError, Logistics, ServiceOrderRequest, Timeout

from .params import missing_params
from .registry import GATE_CHECKS, SUBMITTED_NEXT_STEP, ActionRegistry, ConfigError
from .store import MemoryExecutionStore


class AuthorizationDenied(RuntimeError):
    pass


class OutcomeUnverified(BackendError):
    user_message = "办理结果暂时无法确认，为避免重复办理，已转人工核实。"


@dataclass(frozen=True)
class ExecutionResult:
    execution_id: str
    status: str
    receipt: Receipt
    replayed: bool = False
    recoverable: bool = False
    needs_review: bool = False


class ActionExecutor:
    def __init__(self, backend, store=None, registry=None):
        self.backend = backend
        self.store = store if store is not None else MemoryExecutionStore()
        self.registry = registry if registry is not None else ActionRegistry()

    async def run(
        self,
        kind,
        params,
        *,
        idempotency_key,
        session_id,
        run_id,
        case_id=None,
        issue_id=None,
        gate_result: GateResult | None = None,
        writer=None,
        as_of=None,
        deadline_ms=None,
    ):
        spec = self.registry.spec(kind)
        write = spec["kind"] == "write"
        if write and (
            not case_id
            or not gate_result
            or not gate_result.passed
            or [c.name for c in gate_result.checks] != GATE_CHECKS
            or not all(c.passed for c in gate_result.checks)
        ):
            raise AuthorizationDenied("写操作授权门未通过")
        allowed = set(spec["params"]) | (
            {"service_order_no"} if kind == "logistics.query" else set()
        )
        if set(params) - allowed or missing_params(kind, params):
            raise ConfigError("未知参数或缺少订单号")
        for name, definition in spec["params"].items():
            if definition.get("required") and not params.get(name):
                raise ConfigError("缺少必需参数：" + name)
            if (
                name in params
                and definition.get("type") == "str"
                and not isinstance(params[name], str)
            ):
                raise ConfigError("参数必须为文本：" + name)
        if kind == "service_order.create" and (
            params.get("type") not in SERVICE_ORDER_TYPES
            or not isinstance(params.get("evidence", {}), dict)
        ):
            raise ConfigError("服务单类型或证据格式不合法")
        timeout_ms = min(spec["timeout_ms"], deadline_ms) if deadline_ms else spec["timeout_ms"]
        if timeout_ms <= 0:
            raise Timeout()
        row = {
            "execution_id": str(uuid.uuid4()),
            "case_id": case_id,
            "session_id": session_id,
            "issue_id": issue_id,
            "run_id": run_id,
            "action_kind": kind,
            "idempotency_key": idempotency_key,
            "request": params,
            "gate_result": gate_result.model_dump() if gate_result else None,
            "actions_version": self.registry.version,
        }
        stored, acquired = await self.store.claim(row, spec["timeout_ms"] + 1000)
        if not acquired:
            error = stored.get("error") or {}
            return ExecutionResult(
                stored["execution_id"],
                stored["status"],
                Receipt.model_validate(stored["receipt"]),
                True,
                bool(error.get("recoverable")),
                bool(error.get("needs_review")),
            )
        emit = writer or (lambda _: None)
        emit(
            {
                "type": "tool_call",
                "tool_id": stored["execution_id"],
                "name": kind,
                "status": "started",
                "summary": "正在查询售后工具" if not write else "正在提交服务单",
            }
        )
        try:
            async with asyncio.timeout(timeout_ms / 1000):
                if kind == "logistics.query" and params.get("service_order_no"):
                    value = await self.backend.get_service_order(params["service_order_no"])
                    receipt = Receipt(
                        status=value.status,
                        service_order_no=value.service_order_no,
                        order_no=value.order_no,
                        data=value.model_dump(mode="json"),
                    )
                elif kind == "logistics.query":
                    order = (
                        await self.backend.get_order(params["order_no"])
                        if params.get("order_no")
                        else await self.backend.find_order_by_tracking(params["tracking_no"])
                    )
                    logistics = Logistics(order_no=order.order_no, packages=order.packages, as_of=as_of)
                    receipt = Receipt(
                        status="packages",
                        order_no=order.order_no,
                        tracking_no=params.get("tracking_no"),
                        data=logistics.model_dump(mode="json"),
                    )
                elif kind == "warranty.check":
                    value = await self.backend.get_order(params["order_no"])
                    receipt = Receipt(
                        status="order_found",
                        order_no=value.order_no,
                        data=value.model_dump(mode="json"),
                    )
                else:
                    value = await self._create_once(params, idempotency_key, stored["attempt"])
                    receipt = Receipt(
                        status=value.status,
                        service_order_no=value.service_order_no,
                        order_no=value.order_no,
                        next_step=SUBMITTED_NEXT_STEP,
                        data=value.model_dump(mode="json"),
                    )
        except (BackendError, TimeoutError) as exc:
            error = Timeout() if isinstance(exc, TimeoutError) else exc
            receipt = Receipt(status="failed", next_step=error.user_message)
            needs_review = isinstance(error, OutcomeUnverified)
            await self.store.finish(
                idempotency_key,
                stored["attempt"],
                "failed",
                receipt.model_dump(mode="json"),
                {
                    "code": type(error).__name__,
                    "recoverable": error.recoverable,
                    "message": error.user_message,
                    # A write that timed out may have happened; the next attempt looks it up.
                    "outcome_unknown": write and isinstance(error, Timeout),
                    "needs_review": needs_review,
                },
            )
            emit(
                {
                    "type": "tool_call",
                    "tool_id": stored["execution_id"],
                    "name": kind,
                    "status": "failed",
                    "summary": error.user_message,
                }
            )
            return ExecutionResult(
                stored["execution_id"],
                "failed",
                receipt,
                recoverable=error.recoverable,
                needs_review=needs_review,
            )
        await self.store.finish(
            idempotency_key, stored["attempt"], "succeeded", receipt.model_dump(mode="json"), None
        )
        emit(
            {
                "type": "tool_call",
                "tool_id": stored["execution_id"],
                "name": kind,
                "status": "finished",
                "summary": "售后工具已返回",
            }
        )
        return ExecutionResult(stored["execution_id"], "succeeded", receipt)

    async def _create_once(self, params, client_ref, attempt):
        # An earlier attempt may have created the order and lost the answer. Look it
        # up first; create again only when the backend confirms nothing exists.
        if attempt > 1:
            try:
                found = await self.backend.find_service_order(client_ref)
            except BackendError as exc:
                raise OutcomeUnverified() from exc
            if found:
                return found
        return await self.backend.create_service_order(
            ServiceOrderRequest(**params, client_ref=client_ref)
        )
