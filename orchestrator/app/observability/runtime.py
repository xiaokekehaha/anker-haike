"""本地 JSONL 始终可用；Langfuse 投递用有界后台队列，不进入业务预算。"""

from __future__ import annotations

import asyncio
import json
import logging
import logging.handlers
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.observability.privacy import sanitize

log = logging.getLogger("observability")
run_id_context: ContextVar[str | None] = ContextVar("observation_run_id", default=None)
STANDARD = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime", "data"}


def now() -> str:
    return datetime.now(UTC).isoformat()


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        extra = {k: v for k, v in record.__dict__.items() if k not in STANDARD}
        data = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            **extra,
            **getattr(record, "data", {}),
        }
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        return json.dumps(sanitize(data), ensure_ascii=False, default=str)


def configure_logging(path: str) -> logging.Handler:
    root = logging.getLogger()
    for handler in root.handlers:
        handler.setFormatter(JsonFormatter())
    output = Path(path)
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            output, maxBytes=10_000_000, backupCount=3, encoding="utf-8"
        )
    except OSError:
        # 文件系统不可写时继续向 stderr 输出，不阻止业务启动。
        handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    return handler


def ingestion_batch(data: dict[str, Any]) -> dict[str, Any]:
    """OTLP HTTP/JSON，generation 根 span 按 session_id 聚合，兼容 v4 events_only。"""
    data = sanitize(data)
    end = datetime.fromisoformat(data["timestamp"])
    end_ns = int(end.timestamp()) * 1_000_000_000 + end.microsecond * 1000
    attrs = {
        "langfuse.observation.type": "generation",
        "langfuse.session.id": data.get("session_id"),
        "langfuse.observation.model.name": data.get("model_used"),
        "langfuse.observation.input": json.dumps(data.get("input"), ensure_ascii=False),
        "langfuse.observation.output": json.dumps(data.get("output"), ensure_ascii=False),
    }
    for key in ("run_id", "lane", "status", "attempts", "stream", "output_truncated"):
        value = data.get(key)
        if value is not None:
            attrs[f"langfuse.observation.metadata.{key}"] = (
                value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            )
    usage = data.get("usage") or {}
    if usage:
        attrs["langfuse.observation.usage_details"] = json.dumps(
            {
                key: usage[src]
                for key, src in (("input", "input_tokens"), ("output", "output_tokens"))
                if src in usage
            }
        )
    span = {
        "traceId": uuid.uuid4().hex,
        "spanId": uuid.uuid4().hex[:16],
        "name": data["task"],
        "kind": 1,
        "startTimeUnixNano": str(end_ns - int(data["latency_ms"] * 1_000_000)),
        "endTimeUnixNano": str(end_ns),
        "attributes": [
            {"key": k, "value": {"stringValue": v}} for k, v in attrs.items() if v is not None
        ],
        "status": {"code": 1 if data["status"] == "ok" else 2},
    }
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "haike-orchestrator"}}
                    ]
                },
                "scopeSpans": [{"scope": {"name": "haike.observability"}, "spans": [span]}],
            }
        ]
    }


class LangfuseExporter:
    def __init__(
        self,
        base_url: str,
        public_key: str,
        secret_key: str,
        *,
        transport=None,
        capacity: int = 100,
    ):
        self.client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            auth=(public_key, secret_key),
            timeout=2,
            transport=transport,
        )
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=capacity)
        self.worker: asyncio.Task | None = None
        self.dropped = 0

    def start(self):
        self.worker = asyncio.create_task(self._work())

    def submit(self, data: dict[str, Any]):
        try:
            self.queue.put_nowait(ingestion_batch(data))
        except asyncio.QueueFull:
            self.dropped += 1
            log.warning("trace_queue_full", extra={"data": {"dropped": self.dropped}})

    async def _work(self):
        while True:
            batch = await self.queue.get()
            try:
                response = await self.client.post(
                    "/api/public/otel/v1/traces",
                    json=batch,
                    headers={"x-langfuse-ingestion-version": "4"},
                )
                response.raise_for_status()
                result = response.json()
                rejected = int((result.get("partialSuccess") or {}).get("rejectedSpans", 0))
                if rejected:
                    log.warning("trace_ingestion_rejected", extra={"data": {"count": rejected}})
            except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
                # 不记录 response body 或 URL 中的凭据。
                log.warning(
                    "trace_export_failed", extra={"data": {"error_type": type(exc).__name__}}
                )
            finally:
                self.queue.task_done()

    async def close(self):
        if self.worker:
            try:
                await asyncio.wait_for(self.queue.join(), timeout=3)
            except TimeoutError:
                log.warning("trace_shutdown_timeout")
            self.worker.cancel()
            await asyncio.gather(self.worker, return_exceptions=True)
        await self.client.aclose()


_exporter: LangfuseExporter | None = None


def set_exporter(exporter: LangfuseExporter | None):
    global _exporter
    _exporter = exporter


def record(event: str, **data: Any):
    """非关键路径：日志/导出故障不改变模型返回值和异常语义。"""
    try:
        data = sanitize({"timestamp": now(), "run_id": run_id_context.get(), **data})
        log.info(event, extra={"data": data})
        if event == "model_call" and _exporter is not None:
            _exporter.submit(data)
    except Exception:  # noqa: BLE001, S110 - observability must not fail business operations
        # 不能递归记录日志；业务路径保持可用。
        pass
