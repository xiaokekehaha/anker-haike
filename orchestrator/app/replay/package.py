"""录制包：清单、事件记录、键计算与版本核对（票 43，09 §6）。

目录：`<replay_dir>/<case_id>/manifest.json`、`events.jsonl`。
- manifest.versions = {prompt_ver, models_ver, kb_ver, rules_ver}；启动时与当前进程版本逐项比对。
- events.jsonl 每行一条：
  model  {"kind":"model","key":sha256,"task":..,"mode":"invoke"|"stream","schema":..,"output":{..}|"text":..,"model_used":..}
  knowledge {"kind":"knowledge","key":sha256,"kb":..,"status":..,"hits":[..],"hint":..,"truncated":..,"allowed_count":..}
- 键：模型 = sha256(task, schema 名, 规范化消息)，图片以字节 sha256 代入；检索 = sha256(kb, query, scope, top_k)。
  不含 session_id / run_id / 时间，同一对话重跑得到同一键。
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langchain_core.messages import BaseMessage
from langchain_core.messages.utils import convert_to_messages

log = logging.getLogger("replay.package")

VERSION_KEYS: tuple[str, ...] = ("prompt_ver", "models_ver", "kb_ver", "rules_ver", "actions_version")
MANIFEST_FILE = "manifest.json"
EVENTS_FILE = "events.jsonl"
FORMAT_VERSION = 3


class ReplayIncompatible(RuntimeError):
    """清单与当前进程版本不符（或录制包缺失 / 损坏）：启动失败，不静默降级。"""

    def __init__(self, case_id: str, problems: list[str]):
        self.case_id = case_id
        self.problems = problems
        super().__init__(f"replay_incompatible case={case_id!r}: " + "; ".join(problems))


# ---- 键 ----------------------------------------------------------------------


def _canonical_part(part: Any) -> Any:
    if isinstance(part, str):
        return {"text": part}
    if not isinstance(part, dict):
        return {"text": str(part)}
    kind = part.get("type")
    if kind in ("image", "image_url"):
        url = part.get("image_url")
        if isinstance(url, dict):
            url = url.get("url")
        if not url and part.get("data"):
            url = f"data:{part.get('mime_type', '')};base64,{part['data']}"
        return {"image": _image_digest(str(url or ""))}
    if kind == "text" or "text" in part:
        return {"text": str(part.get("text", ""))}
    return {"json": json.dumps(part, ensure_ascii=False, sort_keys=True)}


def _image_digest(url: str) -> str:
    if url.startswith("data:") and ";base64," in url:
        b64 = url.split(";base64,", 1)[1]
        try:
            return hashlib.sha256(base64.b64decode(b64)).hexdigest()
        except ValueError:
            pass
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def canonical_messages(messages: Sequence[BaseMessage | tuple[str, str] | dict[str, Any]]) -> list:
    out = []
    for m in convert_to_messages(list(messages)):
        content = m.content
        parts = (
            [_canonical_part(content)]
            if isinstance(content, str)
            else [_canonical_part(p) for p in content]
        )
        out.append({"role": m.type, "content": parts})
    return out


def model_key(task: str, schema_name: str | None, messages: Sequence[Any]) -> str:
    from app.replay.context import context_identity

    structured, _ = context_identity(messages)
    payload = {"task": task, "schema": schema_name, "messages": structured if structured is not None else canonical_messages(messages)}
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def knowledge_key(kb: str, query: str, scope: Any, top_k: int) -> str:
    payload = {
        "kb": kb,
        "query": " ".join(str(query).split()),
        "scope": {
            "product_state": getattr(scope, "product_state", None),
            "category": getattr(scope, "category", None),
            "sku": getattr(scope, "sku", None),
        },
        "top_k": top_k,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


# ---- 版本 ----------------------------------------------------------------------


PROMPT_VERSION_SOURCES: tuple[tuple[str, str, str], ...] = (
    ("system", "app.prompts.system", "PROMPT_VERSION"),
    ("interpret", "app.conversation.interpret", "INTERPRET_PROMPT_VERSION"),
    ("reply", "app.prompts.reply", "REPLY_PROMPT_VERSION"),
    ("guide", "app.prompts.guide", "GUIDE_PROMPT_VERSION"),
    ("clarify", "app.sessions.clarify", "CLARIFY_PROMPT_VERSION"),
    ("vision", "app.diagnose.vision", "VISION_PROMPT_VERSION"),
    ("ocr", "app.sessions.receipt", "OCR_PROMPT_VERSION"),
    ("summary", "app.escalation.polish", "PROMPT_VERSION"),
)


def prompt_version() -> str:
    """所有带版本的 Prompt 模板；全部一致时给单值，否则列出各项（任一变化都要重新录制）。

    模块按名字动态取（各票并行开发中可能尚未合入），缺失的项不计入。
    """
    import importlib

    parts: dict[str, str] = {}
    for name, module, attr in PROMPT_VERSION_SOURCES:
        try:
            parts[name] = str(getattr(importlib.import_module(module), attr))
        except (ImportError, AttributeError):
            continue
    if not parts:
        return "unknown"
    if len(set(parts.values())) == 1:
        return next(iter(parts.values()))
    return ";".join(f"{k}={v}" for k, v in parts.items())


def kb_version(manifest_path: str | Path, override: str = "") -> str | None:
    if override:
        return override
    p = Path(manifest_path)
    if not p.is_file():
        return None
    try:
        return str(json.loads(p.read_text(encoding="utf-8")).get("kb_ver") or "") or None
    except (OSError, ValueError):
        return None


def rules_version(rules_path: str | Path) -> str | None:
    from app.rules.service import load_rules_config

    try:
        return load_rules_config(rules_path).version
    except Exception:  # noqa: BLE001 - 规则表坏了由规则服务自己报错，这里只影响清单比对
        return None


def current_versions(
    *,
    models_ver: str,
    rules_path: str | Path,
    kb_manifest_path: str | Path,
    kb_ver_override: str = "",
) -> dict[str, str | None]:
    from app.actions.registry import ActionRegistry
    return {
        "actions_version": ActionRegistry().version,
        "prompt_ver": prompt_version(),
        "models_ver": models_ver,
        "kb_ver": kb_version(kb_manifest_path, kb_ver_override),
        "rules_ver": rules_version(rules_path),
    }


# ---- 清单与包 ----------------------------------------------------------------


@dataclass
class ReplayManifest:
    case_id: str
    title: str
    versions: dict[str, str]
    recorded_at: str
    format: int = FORMAT_VERSION
    counts: dict[str, int] = field(default_factory=dict)
    notes: str | None = None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "format": self.format,
            "case_id": self.case_id,
            "title": self.title,
            "recorded_at": self.recorded_at,
            "versions": self.versions,
            "counts": self.counts,
        }
        if self.notes:
            out["notes"] = self.notes
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReplayManifest:
        return cls(
            case_id=str(data["case_id"]),
            title=str(data.get("title") or data["case_id"]),
            versions={k: str(v) for k, v in (data.get("versions") or {}).items()},
            recorded_at=str(data.get("recorded_at") or ""),
            format=int(data.get("format") or 1),
            counts={k: int(v) for k, v in (data.get("counts") or {}).items()},
            notes=data.get("notes"),
        )

    def problems_against(self, current: dict[str, str | None]) -> list[str]:
        problems = []
        for key in VERSION_KEYS:
            recorded, now = self.versions.get(key), current.get(key)
            if recorded is None:
                problems.append(f"{key}: manifest missing")
            elif now is None:
                problems.append(f"{key}: recorded={recorded!r} current=missing")
            elif recorded != now:
                problems.append(f"{key}: recorded={recorded!r} current={now!r}")
        return problems


@dataclass
class ReplayPackage:
    manifest: ReplayManifest
    models: dict[str, dict[str, Any]] = field(default_factory=dict)
    knowledge: dict[str, dict[str, Any]] = field(default_factory=dict)
    path: Path | None = None

    @property
    def case_id(self) -> str:
        return self.manifest.case_id

    def describe(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "title": self.manifest.title,
            "recorded_at": self.manifest.recorded_at,
            "versions": dict(self.manifest.versions),
            "counts": {"model": len(self.models), "knowledge": len(self.knowledge)},
        }

    def check(self, current: dict[str, str | None]) -> None:
        problems = self.manifest.problems_against(current)
        if problems:
            raise ReplayIncompatible(self.case_id, problems)


def load_package(replay_dir: str | Path, case_id: str) -> ReplayPackage:
    """读取录制包；目录 / 文件缺失或格式错误也算 replay_incompatible（不能静默跑到真实模型上）。"""
    base = Path(replay_dir) / case_id
    mp, ep = base / MANIFEST_FILE, base / EVENTS_FILE
    if not mp.is_file():
        raise ReplayIncompatible(case_id, [f"manifest not found: {mp}"])
    try:
        manifest = ReplayManifest.from_dict(json.loads(mp.read_text(encoding="utf-8")))
    except (ValueError, KeyError) as exc:
        raise ReplayIncompatible(case_id, [f"manifest invalid: {exc}"]) from exc
    if manifest.case_id != case_id:
        raise ReplayIncompatible(case_id, [f"manifest case_id={manifest.case_id!r} != {case_id!r}"])
    if manifest.format != FORMAT_VERSION:
        raise ReplayIncompatible(case_id, [f"format {manifest.format} != {FORMAT_VERSION}"])
    pkg = ReplayPackage(manifest, path=base)
    if not ep.is_file():
        raise ReplayIncompatible(case_id, [f"events not found: {ep}"])
    for n, line in enumerate(ep.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError as exc:
            raise ReplayIncompatible(case_id, [f"events.jsonl line {n} invalid: {exc}"]) from exc
        kind, key = rec.get("kind"), rec.get("key")
        if kind == "model" and key:
            pkg.models.setdefault(key, rec)
        elif kind == "knowledge" and key:
            pkg.knowledge.setdefault(key, rec)
        else:
            raise ReplayIncompatible(case_id, [f"events.jsonl line {n}: unknown record {kind!r}"])
    return pkg


# ---- 录制 ----------------------------------------------------------------------


class Recorder:
    """录制器：RecordingRouter / RecordingKnowledgeAdapter 往这里写记录；save() 落盘。同键先到先得。"""

    def __init__(self, case_id: str, title: str, versions: dict[str, str | None]):
        missing = [k for k in VERSION_KEYS if not versions.get(k)]
        if missing:
            raise ReplayIncompatible(case_id, [f"cannot record without {k}" for k in missing])
        self.case_id = case_id
        self.title = title
        self.versions = {k: str(versions[k]) for k in VERSION_KEYS}
        self.models: dict[str, dict[str, Any]] = {}
        self.knowledge: dict[str, dict[str, Any]] = {}
        self.misses: list[dict[str, Any]] = []

    def add_model(self, key: str, record: dict[str, Any]) -> None:
        self.models.setdefault(key, {"kind": "model", "key": key, **record})

    def add_knowledge(self, key: str, record: dict[str, Any]) -> None:
        self.knowledge.setdefault(key, {"kind": "knowledge", "key": key, **record})

    def package(self) -> ReplayPackage:
        manifest = ReplayManifest(
            case_id=self.case_id,
            title=self.title,
            versions=self.versions,
            recorded_at=datetime.now(UTC).isoformat(timespec="seconds"),
            counts={"model": len(self.models), "knowledge": len(self.knowledge)},
        )
        return ReplayPackage(manifest, dict(self.models), dict(self.knowledge))

    def save(self, replay_dir: str | Path) -> Path:
        pkg = self.package()
        base = Path(replay_dir) / self.case_id
        base.mkdir(parents=True, exist_ok=True)
        (base / MANIFEST_FILE).write_text(
            json.dumps(pkg.manifest.as_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        with (base / EVENTS_FILE).open("w", encoding="utf-8") as fh:
            for rec in [*pkg.models.values(), *pkg.knowledge.values()]:
                fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
        log.info(
            "replay package saved case=%s models=%d knowledge=%d dir=%s",
            self.case_id,
            len(pkg.models),
            len(pkg.knowledge),
            base,
        )
        return base
