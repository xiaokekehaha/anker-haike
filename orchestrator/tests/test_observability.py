"""票 44：真实模型路由/会话事件的追踪接口、脱敏、导出故障隔离与统计。"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import httpx
import pytest
from pydantic import BaseModel

from app.observability.metrics import summarize
from app.observability.privacy import sanitize
from app.observability.runtime import (
    LangfuseExporter,
    configure_logging,
    ingestion_batch,
    record,
    set_exporter,
)
from app.sessions.runner import RunEmitter
from app.sessions.store import InMemorySessionStore
from tests.test_vision import CONFIG, _router


class Output(BaseModel):
    answer: str


@pytest.fixture
def logs(tmp_path):
    path = tmp_path / "events.jsonl"
    root = logging.getLogger()
    level = root.level
    root.setLevel(logging.INFO)
    handler = configure_logging(str(path))
    yield path
    root.removeHandler(handler)
    handler.close()
    root.setLevel(level)
    set_exporter(None)


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def model_data():
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "task": "intake",
        "session_id": "session1",
        "run_id": "run1",
        "status": "ok",
        "model_used": "test/model",
        "input": {"phone": "13800138000", "order_no": "ORDER-ABC"},
        "output": "联系 138 0013 8000 订单号：ORDER-ABC",
        "latency_ms": 25,
        "usage": {"input_tokens": 10, "output_tokens": 5},
        "attempts": [],
    }


def test_pii_is_removed_recursively_without_destroying_timestamps():
    data = model_data()
    clean = sanitize(data)
    text = json.dumps(clean)
    for secret in ("13800138000", "ORDER-ABC", "138 0013 8000"):
        assert secret not in text
    assert clean["timestamp"] == data["timestamp"]
    assert clean["session_id"] == "session1"
    assert sanitize(
        {"authorization": "Bearer x", "image_url": {"url": "data:image/png;base64,secret"}}
    ) == {"authorization": "[REDACTED]", "image_url": "[REDACTED]"}
    assert "2026-09-12" in sanitize("购买日期 2026-09-12")


def test_plain_logs_extra_and_exceptions_are_json_and_masked(logs):
    try:
        raise ValueError("订单号：ABC-123 手机 13800138000")
    except ValueError:
        logging.getLogger("rules").exception(
            "rule hit", extra={"event": "rule_hit", "session_id": "s", "rule_id": "R4"}
        )
    text = logs.read_text()
    assert "13800138000" not in text and "ABC-123" not in text
    row = rows(logs)[-1]
    assert row["event"] == "rule_hit" and row["rule_id"] == "R4"


async def test_invoke_records_input_output_usage_attempts_and_session(logs, tmp_path):
    router, _ = _router(tmp_path, CONFIG, [{"answer": "联系 13800138000"}])
    out = await router.invoke(
        "intake", [("user", "订单号：ABC-123")], Output, budget_ms=1000, session_id="s"
    )
    assert out.parsed.answer == "联系 13800138000"  # 脱敏只影响日志
    row = next(r for r in rows(logs) if r["event"] == "model_call")
    assert row["session_id"] == "s" and row["status"] == "ok"
    assert row["model_used"] == "p1/t1" and row["usage"]["input_tokens"] == 10
    assert row["attempts"][0]["outcome"] == "ok"
    assert "13800138000" not in logs.read_text() and "ABC-123" not in logs.read_text()


async def test_stream_logs_output_and_cancel_keeps_gate_free(logs, tmp_path):
    router, _ = _router(tmp_path, CONFIG, ["first reply", "second reply"])
    output = [
        e
        async for e in router.stream(
            "reply.stream", [("user", "hi")], budget_ms=1000, message_id="m", session_id="s"
        )
    ]
    assert output[-1].kind == "end"
    stream = router.stream(
        "reply.stream", [("user", "hi")], budget_ms=1000, message_id="m2", session_id="s"
    )
    await anext(stream)
    await stream.aclose()
    records = [r for r in rows(logs) if r["event"] == "model_call"]
    assert [r["status"] for r in records] == ["ok", "cancelled"]
    assert "first reply" in records[0]["output"]
    assert router.gate.in_flight == 0


async def test_exporter_sends_sanitized_otlp_and_handles_partial_rejection(logs):
    received = []

    def handle(request):
        assert request.url.path == "/api/public/otel/v1/traces"
        assert request.headers["x-langfuse-ingestion-version"] == "4"
        received.append(json.loads(request.content))
        return httpx.Response(200, json={"partialSuccess": {"rejectedSpans": "1"}})

    exporter = LangfuseExporter("http://test", "pk", "sk", transport=httpx.MockTransport(handle))
    exporter.start()
    set_exporter(exporter)
    record("model_call", **model_data())
    await exporter.close()
    span = received[0]["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    attrs = {item["key"]: item["value"]["stringValue"] for item in span["attributes"]}
    assert attrs["langfuse.session.id"] == "session1"
    assert len(span["traceId"]) == 32 and len(span["spanId"]) == 16
    assert json.loads(attrs["langfuse.observation.usage_details"]) == {"input": 10, "output": 5}
    assert "ORDER-ABC" not in json.dumps(received)
    assert any(r["event"] == "trace_ingestion_rejected" for r in rows(logs))


async def test_export_queue_is_bounded_and_transport_failure_is_nonfatal(logs):
    def handle(request):
        raise httpx.ConnectError("not running")

    exporter = LangfuseExporter(
        "http://test", "pk", "sk", transport=httpx.MockTransport(handle), capacity=1
    )
    exporter.submit(model_data())
    exporter.submit(model_data())
    assert exporter.queue.qsize() == 1 and exporter.dropped == 1
    exporter.start()
    await exporter.close()
    assert any(r["event"] == "trace_export_failed" for r in rows(logs))


async def test_run_emitter_records_first_visible_and_first_card_only(logs):
    store = InMemorySessionStore()
    # emitter 的 event 存储不依赖投影，测试用合法会话初始化。
    session = await store.create_session()
    sid = session.session_id
    emitter = RunEmitter(store, sid, "r")
    await emitter.emit({"type": "run_started", "resumed": False, "deadline_ms": 1000})
    await emitter.emit({"type": "progress", "stage": "intake"})
    await emitter.emit({"type": "message", "message_id": "m", "delta": ""})
    await emitter.emit({"type": "message", "message_id": "m", "delta": "你好"})
    await emitter.emit({"type": "message", "message_id": "m", "delta": "继续"})
    card = {
        "type": "receipt_card",
        "card_id": "c",
        "version": 1,
        "fields": {},
        "confidence": {},
        "unreadable": [],
    }
    await emitter.emit(card)
    await emitter.emit(card)
    metrics = [r for r in rows(logs) if r["event"] == "run_metric"]
    assert [r["metric"] for r in metrics] == ["first_visible_ms", "card_ready_ms"]
    assert all(r["value_ms"] >= 0 for r in metrics)
    assert any(r["event"] == "state_transition" for r in rows(logs))


def test_metrics_nearest_rank_missing_values_duplicates_and_bad_lines(tmp_path):
    path = tmp_path / "events.jsonl"
    data = [
        {
            "event": "run_metric",
            "session_id": "s",
            "run_id": str(i),
            "metric": "first_visible_ms",
            "value_ms": v,
        }
        for i, v in enumerate((10, 20, 30, 40, 100))
    ]
    path.write_text("\n".join(json.dumps(row) for row in data + [data[0]]) + "\nbroken\n")
    report = summarize([path])
    assert report["metrics"]["first_visible_ms"] == {"count": 5, "p50": 30, "p95": 100}
    assert report["metrics"]["card_ready_ms"] == {"count": 0, "p50": None, "p95": None}
    assert report["invalid_lines"] == 1 and len(report["sessions"]["s"]) == 5


def test_ingestion_timestamp_and_duration():
    span = ingestion_batch(model_data())["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    elapsed = int(span["endTimeUnixNano"]) - int(span["startTimeUnixNano"])
    assert elapsed == 25_000_000


def test_unknown_usage_is_not_reported_as_zero():
    data = model_data()
    data["usage"] = {}
    assert "usage_details" not in json.dumps(ingestion_batch(data))


def test_unwritable_log_file_falls_back_to_console(tmp_path):
    occupied = tmp_path / "occupied"
    occupied.write_text("file")
    handler = configure_logging(str(occupied / "events.jsonl"))
    try:
        assert isinstance(handler, logging.StreamHandler)
        assert not isinstance(handler, logging.FileHandler)
    finally:
        logging.getLogger().removeHandler(handler)
        handler.close()


def test_order_number_in_json_prompt_is_redacted():
    assert "ABC-ORDER" not in sanitize('{"order_no": "ABC-ORDER"}')
    assert "ABC-ORDER" not in sanitize("{'order_number': 'ABC-ORDER'}")
