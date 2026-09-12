"""巡检脚本的进程内运行环境（票 45）。

与单测同构：内存存储 + InMemorySaver + RunManager + 内存锁 + 内存图片库；模型用按 task 分脚本的假模型
（不发网络请求），知识适配器用按 (kb, 轮次) 出结果的脚本适配器。first_visible_ms / card_ready_ms 从运行器的
run_metric 结构化日志里捕获（与线上口径一致），不在客户端估算。
"""

from __future__ import annotations

import io
import json
import logging
import os
import struct
import time
import uuid
import zlib
from dataclasses import dataclass, field
from typing import Any, Self

from httpx import ASGITransport, AsyncClient
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import Field

from app.diagnose.config import RetrievalConfig, get_retrieval_config, set_retrieval_config
from app.images.runtime import set_image_store
from app.images.store import InMemoryImageStore
from app.knowledge.adapter import HINTS, Hit, KnowledgeScope, ToolResult
from app.knowledge.runtime import set_knowledge_adapter
from app.main import app
from app.models.config import load_models_config
from app.models.fake import FakeChatModel, ScriptExhausted
from app.models.registry import ModelRegistry
from app.models.router import ModelRouter
from app.models.runtime import set_model_router
from app.observability.alerts import AlertManager, Thresholds, set_alert_manager
from app.plans import PlanLibrary
from app.plans.runtime import set_plan_library
from app.rules import RulesService, set_rules_service
from app.sessions import sse
from app.sessions.graph import build_graph
from app.sessions.locks import InMemorySessionLock
from app.sessions.manager import RunManager
from app.sessions.store import InMemorySessionStore
from app.settings import REPO_ROOT

MODELS_CONFIG = """
version: inspection
default_lane: domestic
providers:
  p1: {sdk: openai, api_key_env: K1}
  p2: {sdk: openai, api_key_env: K2}
models:
  fast:   {provider: p1, id: f, structured: json_object, vision: true}
  main:   {provider: p1, id: m, structured: json_object, vision: true}
  backup: {provider: p2, id: b, structured: json_object, vision: true}
  emb: {provider: p1, id: e, kind: embedding}
  rr:  {provider: p1, id: r, kind: rerank}
lanes:
  domestic:
    intake:               {chain: [fast]}
    disambiguate.clarify: {chain: [fast]}
    query.rewrite:        {chain: [fast]}
    diagnose.vision:      {chain: [main], needs_vision: true}
    diagnose.synthesize:  {chain: [main]}
    guide.step:           {chain: [main]}
    reply.stream:         {chain: [main, backup], stream: true}
    escalate.summary:     {chain: [fast]}
    warranty.receipt_ocr: {chain: [main], needs_vision: true}
"""

# ---- 常用脚本 ----
INTAKE_X9 = {"emotion_level": "calm", "product_hints": ["X9 Pro"], "symptoms": ["不吸了", "滚刷缠头发"], "wants_human": False}
INTAKE_X10 = {"emotion_level": "calm", "product_hints": ["X10"], "symptoms": ["不吸了"], "wants_human": False}
INTAKE_NONE = {"emotion_level": "calm", "product_hints": [], "symptoms": ["不吸了"], "wants_human": False}
SYNTH_HAIR = {"hypotheses": [
    {"plan_id": "rv_suction_hair_wrap", "confidence": 0.85, "evidence_ids": ["c12"]},
    {"plan_id": "rv_suction_filter_clog", "confidence": 0.4, "evidence_ids": ["c15"]},
]}
REDX = {"emotion_level": "calm", "product_hints": [], "new_symptoms": [], "negated_symptoms": [],
        "wants_human": False, "needs_clarification": False}
OBS_SMOKE = {"observations": ["smoke coming out of the vent", "外壳发黑"], "visible_parts": ["机身"]}
OBS_HAIR = {"observations": ["滚刷上缠绕大量毛发"], "visible_parts": ["滚刷"]}


def js(o: Any) -> str:
    return json.dumps(o, ensure_ascii=False)


def png_bytes(payload_size: int = 64) -> bytes:
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    chunk = struct.pack(">I", len(ihdr)) + b"IHDR" + ihdr + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr))
    data = os.urandom(payload_size)
    idat = struct.pack(">I", len(data)) + b"IDAT" + data + struct.pack(">I", zlib.crc32(b"IDAT" + data))
    return sig + chunk + idat


class TaskFake(FakeChatModel):
    """按 task 取脚本的假模型：调用元数据里的 task 决定用哪条队列，省去跨任务的脚本排序。

    队列为空或无该 task → ScriptExhausted（走既有降级路径）。`fail_all=True` 时任何调用都抛错（全模型不可用）。
    """

    by_task: dict[str, list[Any]] = Field(default_factory=dict)
    fail_all: bool = False
    tasks_called: list[str] = Field(default_factory=list)

    def _next(self, messages, run_manager, kwargs):
        meta = {
            **(getattr(run_manager, "inheritable_metadata", {}) or {}),
            **(getattr(run_manager, "metadata", {}) or {}),
        }
        task = str(meta.get("task") or "")
        self.tasks_called.append(task)
        if self.fail_all:
            self.calls.append({"messages": list(messages), "kwargs": dict(kwargs), "tags": [], "metadata": meta})
            raise RuntimeError(f"{self.name_for_trace}: upstream down")
        self.script = self.by_task.setdefault(task, [])
        try:
            return super()._next(messages, run_manager, kwargs)
        except ScriptExhausted:
            raise ScriptExhausted(f"{self.name_for_trace}: no script for task {task!r}") from None

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        # 流式（reply.stream）不经过 _next：同样按 task 选队列，避免吃掉别的任务的脚本
        cfg = self._stream_config or {}
        task = str((cfg.get("metadata") or {}).get("task") or "")
        self.tasks_called.append(task)
        if self.fail_all:
            raise RuntimeError(f"{self.name_for_trace}: upstream down")
        self.script = self.by_task.setdefault(task, [])
        async for chunk in super()._astream(messages, stop=stop, run_manager=run_manager, **kwargs):
            yield chunk


def make_router(tmp_dir, scripts: dict[str, list[Any]] | None = None, *, fail_all: bool = False) -> tuple[ModelRouter, TaskFake]:
    """一个假模型服务全部别名（fast / main / backup），脚本按 task 分队列；字典值可为 dict（自动 json）/ str / list（流）/ Exception。"""
    p = tmp_dir / "models.yaml"
    p.write_text(MODELS_CONFIG, encoding="utf-8")
    by_task: dict[str, list[Any]] = {}
    for task, items in (scripts or {}).items():
        by_task[task] = [js(x) if isinstance(x, dict) else x for x in items]
    fake = TaskFake(by_task=by_task, fail_all=fail_all, tasks_called=[], name_for_trace="stub")
    router = ModelRouter(
        ModelRegistry(load_models_config(p), env={"K1": "x", "K2": "x"}),
        model_factory=lambda r, _: fake,
    )
    return router, fake


def hit(eid: str, snippet: str, score: float = 0.4, doc: str = "manual_rv_v1", kb: str = "kb_manual") -> Hit:
    return Hit(eid, "k-" + doc, eid, doc, "2026-09-12.1", kb, snippet, score)


def OK_HAIR() -> ToolResult:
    return ToolResult("ok", [hit("c12", "翻转主机取出滚刷，割断缠绕的毛发"), hit("c15", "取出滤网清洗", 0.2)], allowed_count=2)


def NO_MATCH() -> ToolResult:
    return ToolResult("no_match", hint=HINTS["no_match"], allowed_count=2)


def EMPTY_SCOPE() -> ToolResult:
    return ToolResult("no_match", hint=HINTS["no_match_empty_scope"], allowed_count=0)


def UNAVAILABLE() -> ToolResult:
    return ToolResult("unavailable", hint=HINTS["unavailable"], allowed_count=2, detail="ConnectError")


class ScriptedAdapter:
    """按 (kb, 调用次序) 出结果；耗尽后一律 no_match。记录 query 与 scope。"""

    def __init__(self, plan: dict[str, list[ToolResult]] | None = None, default=NO_MATCH):
        self.plan = {k: list(v) for k, v in (plan or {}).items()}
        self.default = default
        self.calls: list[tuple[str, str, KnowledgeScope]] = []

    async def hybrid_search(self, kb, query, top_k, allow):
        self.calls.append((kb, query, allow))
        seq = self.plan.get(kb, [])
        r = seq.pop(0) if seq else self.default()
        r.kb, r.query = kb, query
        return r


class MetricCapture(logging.Handler):
    """抓运行器的 run_metric（first_visible_ms / card_ready_ms），按 run_id 归档。"""

    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.by_run: dict[str, dict[str, int]] = {}

    def emit(self, record: logging.LogRecord) -> None:
        data = getattr(record, "data", None)
        if not isinstance(data, dict) or record.getMessage() != "run_metric":
            return
        run_id = str(data.get("run_id") or "")
        metric = data.get("metric")
        if run_id and metric in ("first_visible_ms", "card_ready_ms"):
            self.by_run.setdefault(run_id, {})[metric] = int(data.get("value_ms") or 0)


@dataclass
class Events:
    items: list[dict]
    elapsed_ms: int
    headers: dict[str, str] = field(default_factory=dict)
    status_code: int = 200

    @property
    def types(self) -> list[str]:
        return [e["type"] for e in self.items]

    def first(self, t: str) -> dict | None:
        return next((e for e in self.items if e["type"] == t), None)

    def all(self, t: str) -> list[dict]:
        return [e for e in self.items if e["type"] == t]

    @property
    def done(self) -> dict:
        return self.items[-1]

    @property
    def run_id(self) -> str:
        return self.items[0].get("run_id", "")

    @property
    def progress(self) -> list[tuple[str, str | None]]:
        return [(e["stage"], e.get("substage")) for e in self.items if e["type"] == "progress"]

    def text(self) -> str:
        return "".join(e["delta"] for e in self.items if e["type"] == "message")


class Harness:
    """一个场景一个 Harness：进入时把 app 切到内存运行时，退出时全部还原。"""

    def __init__(
        self,
        tmp_dir,
        *,
        scripts: dict[str, list[Any]] | None = None,
        adapter: ScriptedAdapter | None = None,
        fail_all_models: bool = False,
        retrieval: RetrievalConfig | None = None,
        no_router: bool = False,
    ) -> None:
        self.tmp_dir = tmp_dir
        self.store = InMemorySessionStore()
        self.graph = build_graph(InMemorySaver())
        self.manager = RunManager(self.store, self.graph)
        self.images = InMemoryImageStore()
        self.router, self.fake = (None, None) if no_router else make_router(tmp_dir, scripts, fail_all=fail_all_models)
        self.adapter = adapter if adapter is not None else ScriptedAdapter({"kb_manual": [OK_HAIR()]})
        self.retrieval = retrieval
        self.alerts = AlertManager([], Thresholds(model_fail_streak=3, cooldown_s=0))
        self.metrics = MetricCapture()
        self.client: AsyncClient | None = None
        self._env_backup: dict[str, str | None] = {}

    async def __aenter__(self) -> Self:
        app.state.session_store = self.store
        app.state.session_graph = self.graph
        app.state.run_manager = self.manager
        app.state.session_lock = InMemorySessionLock()
        app.state.image_store = self.images
        set_image_store(self.images)
        set_model_router(self.router)
        set_knowledge_adapter(self.adapter)
        set_rules_service(RulesService(REPO_ROOT / "config" / "rules" / "safety_terms.yaml", hot_reload=False))
        set_plan_library(PlanLibrary.from_yaml(REPO_ROOT / "config" / "plans.yaml"))
        set_retrieval_config(self.retrieval)
        set_alert_manager(self.alerts)
        logging.getLogger("observability").addHandler(self.metrics)
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://inspect")
        return self

    async def __aexit__(self, *exc) -> None:
        if self.client is not None:
            await self.client.aclose()
        logging.getLogger("observability").removeHandler(self.metrics)
        set_alert_manager(None)
        set_retrieval_config(None)
        set_plan_library(None)
        set_rules_service(None)
        set_knowledge_adapter(None)
        set_model_router(None)
        set_image_store(None)
        app.state.image_store = None
        app.state.session_store = None
        app.state.session_graph = None
        app.state.run_manager = None
        app.state.session_lock = None
        await self.manager.shutdown()

    # ---- 会话操作 ----

    async def new_session(self) -> str:
        r = await self.client.post("/sessions")
        return r.json()["session_id"]

    async def send(self, sid: str, text: str, *, images: int = 0, purpose: str = "fault") -> Events:
        files = [("images", (f"p{i}.png", io.BytesIO(png_bytes(512 + i)), "image/png")) for i in range(images)]
        t0 = time.perf_counter()
        r = await self.client.post(f"/sessions/{sid}/messages", data={"text": text, "purpose": purpose}, files=files)
        elapsed = int((time.perf_counter() - t0) * 1000)
        items = sse.parse(r.text) if r.status_code == 200 else []
        return Events(items, elapsed, dict(r.headers), r.status_code)

    async def action(self, sid: str, body: dict) -> Events:
        t0 = time.perf_counter()
        r = await self.client.post(f"/sessions/{sid}/actions", json=body)
        elapsed = int((time.perf_counter() - t0) * 1000)
        items = sse.parse(r.text) if r.status_code == 200 else []
        ev = Events(items, elapsed, dict(r.headers), r.status_code)
        if r.status_code != 200:
            try:
                ev.headers["_body"] = json.dumps(r.json(), ensure_ascii=False)
            except ValueError:
                ev.headers["_body"] = r.text
        return ev

    async def snapshot(self, sid: str) -> dict:
        return (await self.client.get(f"/sessions/{sid}")).json()

    async def state(self, sid: str) -> dict:
        return (await self.graph.aget_state({"configurable": {"thread_id": sid}})).values

    def run_metrics(self, run_id: str) -> dict[str, int]:
        return dict(self.metrics.by_run.get(run_id, {}))

    # ---- 动作构造 ----

    @staticmethod
    def pending(ev: Events) -> dict:
        p = ev.first("awaiting_input")
        if p is None:
            raise AssertionError(f"no awaiting_input in {ev.types}")
        return p

    @staticmethod
    def card_action(pending: dict, kind: str, payload: dict, *, action_id: str | None = None, version: int | None = None) -> dict:
        return {
            "action_id": action_id or uuid.uuid4().hex,
            "interrupt_id": pending["interrupt_id"],
            "card_id": pending["card_id"],
            "expected_version": pending["version"] if version is None else version,
            "kind": kind,
            "payload": payload,
        }

    @staticmethod
    def feedback(pending: dict, fb: str, note: str | None = None, **kw) -> dict:
        return Harness.card_action(pending, "step_feedback", {"feedback": fb, **({"note": note} if note else {})}, **kw)

    @staticmethod
    def select(pending: dict, sku: str, **kw) -> dict:
        return Harness.card_action(pending, "select_product", {"sku": sku}, **kw)

    @staticmethod
    def request_human(version: int) -> dict:
        return {"action_id": uuid.uuid4().hex, "expected_version": version, "kind": "request_human", "payload": {}}


def rewrite_config(enabled: bool, **rw) -> RetrievalConfig:
    cfg = get_retrieval_config().model_copy(deep=True)
    cfg.query_rewrite = cfg.query_rewrite.model_copy(update={"enabled": enabled, **rw})
    return cfg
