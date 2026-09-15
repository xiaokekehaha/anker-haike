import asyncio
import uuid
from dataclasses import dataclass

from haike_contracts.common import GateResult, Receipt

from app.backends.protocol import BackendError, ServiceOrderRequest, Timeout

from .params import missing_params
from .registry import ActionRegistry, ConfigError
from .store import MemoryExecutionStore


class AuthorizationDenied(RuntimeError):
    pass


@dataclass(frozen=True)
class ExecutionResult:
    execution_id: str
    status: str
    receipt: Receipt
    replayed: bool = False
    recoverable: bool = False


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
        policy_version=None,
        writer=None,
        deadline_ms=None,
    ):
        spec = self.registry.spec(kind)
        write = spec["kind"] == "write"
        if write and (
            not case_id
            or not gate_result
            or not gate_result.passed
            or {c.name for c in gate_result.checks}
            != {"policy", "evidence_and_consent", "safety", "idempotency"}
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
        if "evidence_ids" in params and (
            not isinstance(params["evidence_ids"], list)
            or any(not isinstance(v, str) for v in params["evidence_ids"])
        ):
            raise ConfigError("evidence_ids 必须为字符串列表")
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
            "policy_version": policy_version,
            "actions_version": self.registry.version,
        }
        stored, acquired = await self.store.claim(row, spec["timeout_ms"] + 1000)
        if not acquired:
            return ExecutionResult(
                stored["execution_id"],
                stored["status"],
                Receipt.model_validate(stored["receipt"]),
                True,
                bool((stored.get("error") or {}).get("recoverable")),
            )
        emit = writer or (lambda _: None)
        emit(
            {
                "type": "tool_call",
                "tool_id": stored["execution_id"],
                "name": kind,
                "status": "started",
                "summary": "正在调用模拟业务系统",
            }
        )
        try:
            async with asyncio.timeout(timeout_ms / 1000):
                if kind == "logistics.query":
                    value = (
                        await self.backend.get_service_order(params["service_order_no"])
                        if params.get("service_order_no")
                        else await self.backend.get_shipment(**params)
                    )
                    data = value.model_dump(mode="json")
                    receipt = Receipt(
                        status=data["status"],
                        order_no=data.get("order_no"),
                        tracking_no=data.get("tracking_no"),
                        service_order_no=data.get("service_order_no"),
                        updated_at=data.get("updated_at") or data.get("created_at"),
                        data=data,
                    )
                elif kind == "warranty.check":
                    value = await self.backend.get_order(params["order_no"])
                    receipt = Receipt(
                        status="order_found",
                        order_no=value.order_no,
                        data=value.model_dump(mode="json"),
                    )
                else:
                    value = await self.backend.create_service_order(ServiceOrderRequest(**params))
                    receipt = Receipt(
                        status=value.status,
                        service_order_no=value.service_order_no,
                        order_no=value.order_no,
                        eta_days=value.eta_days,
                        next_step=f"预计 {value.eta_days} 个工作日发出，请保留服务单号",
                        data=value.model_dump(mode="json"),
                    )
        except (BackendError, TimeoutError) as exc:
            error = Timeout() if isinstance(exc, TimeoutError) else exc
            receipt = Receipt(status="failed", next_step=error.user_message)
            await self.store.finish(
                idempotency_key,
                stored["attempt"],
                "failed",
                receipt.model_dump(mode="json"),
                {
                    "code": type(error).__name__,
                    "recoverable": error.recoverable,
                    "message": error.user_message,
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
                stored["execution_id"], "failed", receipt, recoverable=error.recoverable
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
                "summary": "模拟业务查询或办理完成",
            }
        )
        return ExecutionResult(stored["execution_id"], "succeeded", receipt)
