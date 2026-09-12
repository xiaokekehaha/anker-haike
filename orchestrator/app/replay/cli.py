"""haike-replay（票 43）：录制 / 校验 / 回放核对 A1–A3 录制包。

haike-replay record <case_id> [--scenario a1_hair_wrap] [--replay-dir ../replay]
    进程内起编排图（内存存储），真实 ModelRouter + WeKnora 适配器包上录制器，跑脚本后落盘
    replay/<case_id>/{manifest.json,events.jsonl}，并刷新 replay/kb_manifest.json（kb_ver 快照，镜像内比对用）。
haike-replay check <case_id>      清单与当前进程版本比对：不符打印 replay_incompatible 并以 2 退出。
haike-replay verify <case_id>     以 ReplayRouter / ReplayKnowledgeAdapter 重跑脚本（不发任何网络请求）：
                                  出现未命中或缺少预期事件以 1 退出。
haike-replay list                 列出录制包与清单版本。
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import logging
import sys
import uuid
from pathlib import Path
from typing import Any

from app.replay.package import (
    MANIFEST_FILE,
    Recorder,
    ReplayIncompatible,
    ReplayPackage,
    load_package,
)
from app.replay.scenarios import IMAGES, SCENARIOS

log = logging.getLogger("replay.cli")


# ---- 进程内会话运行时 ------------------------------------------------------------


class _Harness:
    """与 tests/conftest.mem_runtime 同构：内存存储 + 内存 checkpointer + 内存图片库，不需要数据库。"""

    def __enter__(self):
        from langgraph.checkpoint.memory import InMemorySaver

        from app.images import InMemoryImageStore
        from app.images.runtime import set_image_store
        from app.main import app
        from app.sessions.graph import build_graph
        from app.sessions.locks import InMemorySessionLock
        from app.sessions.manager import RunManager
        from app.sessions.store import InMemorySessionStore

        self.app = app
        store = InMemorySessionStore()
        app.state.session_store = store
        app.state.session_graph = build_graph(InMemorySaver())
        app.state.run_manager = RunManager(store, app.state.session_graph)
        app.state.session_lock = InMemorySessionLock()
        img = InMemoryImageStore()
        app.state.image_store = img
        set_image_store(img)
        return self

    def __exit__(self, *exc):
        from app.images.runtime import set_image_store

        for name in (
            "session_store",
            "session_graph",
            "run_manager",
            "session_lock",
            "image_store",
        ):
            setattr(self.app.state, name, None)
        set_image_store(None)


async def run_scenario(app, scenario: dict[str, Any]) -> list[dict[str, Any]]:
    """按脚本驱动一条会话，返回全部事件（含每轮 run）。"""
    from httpx import ASGITransport, AsyncClient

    from app.sessions import sse

    events: list[dict[str, Any]] = []
    pending: dict[str, Any] | None = None

    def _absorb(evs: list[dict[str, Any]]) -> None:
        nonlocal pending
        events.extend(evs)
        for e in evs:
            if e["type"] == "awaiting_input":
                pending = e
        if evs and evs[-1]["type"] == "done" and evs[-1].get("reason") != "awaiting_input":
            pending = None

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://replay") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        for step in scenario["steps"]:
            if "message" in step:
                files = None
                if step.get("image"):
                    files = [
                        (
                            "images",
                            (
                                f"{step['image']}.png",
                                io.BytesIO(IMAGES[step["image"]]),
                                "image/png",
                            ),
                        )
                    ]
                r = await client.post(
                    f"/sessions/{sid}/messages",
                    data={"text": step["message"], "purpose": step.get("purpose", "fault")},
                    files=files,
                )
                if r.status_code != 200:
                    raise RuntimeError(f"message failed {r.status_code}: {r.text[:300]}")
                _absorb(sse.parse(r.text))
                continue
            kind = step["action"]
            until, max_n = step.get("until"), int(step.get("max") or 1)
            for _ in range(max_n):
                if pending is None:
                    raise RuntimeError(f"no pending input for action {kind!r}")
                if until and pending["kind"] == until:
                    break
                body = {
                    "action_id": uuid.uuid4().hex,
                    "interrupt_id": pending["interrupt_id"],
                    "card_id": pending["card_id"],
                    "expected_version": pending["version"],
                    "kind": kind,
                    "payload": step["payload"],
                }
                r = await client.post(f"/sessions/{sid}/actions", json=body)
                if r.status_code != 200:
                    raise RuntimeError(f"action {kind} failed {r.status_code}: {r.text[:300]}")
                _absorb(sse.parse(r.text))
                if not until:
                    break
            else:
                if until and (pending is None or pending["kind"] != until):
                    raise RuntimeError(f"pending never became {until!r} after {max_n} rounds")
    return events


def _summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    types = [e["type"] for e in events]
    return {
        "events": len(events),
        "runs": types.count("run_started"),
        "types": sorted(set(types)),
        "evidence_status": sorted(
            {i.get("status", "ok") for e in events if e["type"] == "evidence" for i in e["items"]}
        ),
        "errors": [e.get("code") or e.get("message") for e in events if e["type"] == "error"],
    }


# ---- 子命令 ------------------------------------------------------------------------


def _versions() -> dict[str, str | None]:
    from app.replay.runtime import versions_now

    return versions_now()


async def _record(case_id: str, scenario_key: str, replay_dir: Path) -> int:
    from app.knowledge.runtime import get_knowledge_adapter, set_knowledge_adapter
    from app.models import ModelRegistry, ModelRouter, load_models_config
    from app.models.runtime import set_model_router
    from app.replay.knowledge import RecordingKnowledgeAdapter
    from app.replay.router import RecordingRouter
    from app.replay.runtime import replay_case_id
    from app.settings import settings

    if replay_case_id():
        print("REPLAY_CASE_ID 已设置：录制必须在非回放模式下进行", file=sys.stderr)
        return 2
    scenario = SCENARIOS[scenario_key]
    versions = _versions()
    recorder = Recorder(case_id, scenario["title"], versions)
    cfg = load_models_config(settings.models_config_path, lane_override=settings.model_lane)
    router = RecordingRouter(ModelRouter(ModelRegistry(cfg)), recorder)
    inner_adapter = get_knowledge_adapter()
    if inner_adapter is None:
        print(
            "知识适配器不可用（缺 WEKNORA_API_KEY 或 manifest）：录制包必须含真实检索结果",
            file=sys.stderr,
        )
        return 2
    set_model_router(router)  # type: ignore[arg-type]
    set_knowledge_adapter(RecordingKnowledgeAdapter(inner_adapter, recorder))
    try:
        with _Harness() as h:
            events = await run_scenario(h.app, scenario)
    finally:
        set_model_router(None)
        set_knowledge_adapter(None)
    summary = _summarize(events)
    missing = [t for t in scenario["expect"] if t not in summary["types"]]
    if missing or summary["errors"]:
        print(f"录制流程未完整：缺少事件 {missing} / error {summary['errors']}", file=sys.stderr)
        return 1
    base = recorder.save(replay_dir)
    _write_kb_snapshot(replay_dir, versions)
    print(
        json.dumps(
            {
                "case_id": case_id,
                "scenario": scenario_key,
                "dir": str(base),
                "versions": versions,
                "models": len(recorder.models),
                "knowledge": len(recorder.knowledge),
                "model_failures": recorder.misses,
                **summary,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _write_kb_snapshot(replay_dir: Path, versions: dict[str, str | None]) -> None:
    """镜像里没有 data/knowledge/manifest.json；把 kb_ver 快照放进录制目录随镜像打包（KB_MANIFEST_PATH 指向它）。"""
    replay_dir.mkdir(parents=True, exist_ok=True)
    (replay_dir / "kb_manifest.json").write_text(
        json.dumps(
            {"kb_ver": versions["kb_ver"], "note": "票 43：仅 kb_ver 快照，供回放清单比对"},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _check(case_id: str, replay_dir: Path) -> int:
    try:
        pkg = load_package(replay_dir, case_id)
        pkg.check(_versions())
    except ReplayIncompatible as exc:
        print(f"replay_incompatible: {'; '.join(exc.problems)}", file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, **pkg.describe()}, ensure_ascii=False, indent=2))
    return 0


async def _verify(case_id: str, replay_dir: Path, scenario_key: str | None) -> int:
    from app.knowledge.runtime import set_knowledge_adapter
    from app.models import ModelRegistry, load_models_config
    from app.models.runtime import set_model_router
    from app.replay.knowledge import ReplayKnowledgeAdapter
    from app.replay.router import ReplayRouter
    from app.replay.runtime import set_replay_package
    from app.settings import settings

    try:
        pkg = load_package(replay_dir, case_id)
        pkg.check(_versions())
    except ReplayIncompatible as exc:
        print(f"replay_incompatible: {'; '.join(exc.problems)}", file=sys.stderr)
        return 2
    scenario = SCENARIOS[scenario_key or _scenario_of(pkg)]
    cfg = load_models_config(settings.models_config_path, lane_override=settings.model_lane)
    router = ReplayRouter(ModelRegistry(cfg), pkg, stream_delay_s=0)
    adapter = ReplayKnowledgeAdapter(pkg)
    set_replay_package(pkg)
    set_model_router(router)  # type: ignore[arg-type]
    set_knowledge_adapter(adapter)
    try:
        with _Harness() as h:
            events = await run_scenario(h.app, scenario)
    finally:
        set_model_router(None)
        set_knowledge_adapter(None)
        set_replay_package(None)
    summary = _summarize(events)
    missing = [t for t in scenario["expect"] if t not in summary["types"]]
    report = {
        "case_id": case_id,
        "model_hits": router.hits,
        "model_misses": router.misses,
        "knowledge_hits": adapter.hits,
        "knowledge_misses": adapter.misses,
        "missing_expected": missing,
        **summary,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    ok = not router.misses and not adapter.misses and not missing and not summary["errors"]
    return 0 if ok else 1


def _scenario_of(pkg: ReplayPackage) -> str:
    for key, sc in SCENARIOS.items():
        if sc["title"] == pkg.manifest.title:
            return key
    raise SystemExit(f"录制包 {pkg.case_id} 的标题不对应任何内置脚本，请用 --scenario 指定")


def _list(replay_dir: Path) -> int:
    rows = []
    for mp in sorted(replay_dir.glob(f"*/{MANIFEST_FILE}")):
        try:
            pkg = load_package(replay_dir, mp.parent.name)
            rows.append(pkg.describe())
        except ReplayIncompatible as exc:
            rows.append({"case_id": mp.parent.name, "invalid": exc.problems})
    print(
        json.dumps(
            {"replay_dir": str(replay_dir), "current": _versions(), "cases": rows},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    from app.settings import settings

    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--replay-dir", default=settings.replay_dir)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record")
    r.add_argument("case_id")
    r.add_argument("--scenario", choices=sorted(SCENARIOS), default=None)
    c = sub.add_parser("check")
    c.add_argument("case_id")
    v = sub.add_parser("verify")
    v.add_argument("case_id")
    v.add_argument("--scenario", choices=sorted(SCENARIOS), default=None)
    sub.add_parser("list")
    ns = p.parse_args(sys.argv[1:] if argv is None else argv)
    replay_dir = Path(ns.replay_dir)
    if ns.cmd == "record":
        return asyncio.run(_record(ns.case_id, ns.scenario or ns.case_id, replay_dir))
    if ns.cmd == "check":
        return _check(ns.case_id, replay_dir)
    if ns.cmd == "verify":
        return asyncio.run(_verify(ns.case_id, replay_dir, ns.scenario))
    return _list(replay_dir)


if __name__ == "__main__":
    raise SystemExit(main())
