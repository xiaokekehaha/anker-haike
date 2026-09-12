"""haike-kb：WeKnora 知识库运维。

haike-kb bootstrap            注册项目独立 tenant（本地自助注册）并打印 tenant id；key 写入 .env 的 WEKNORA_API_KEY
haike-kb ingest [--prune]     幂等导入 kb_manual / faq / kb_tickets，写 data/knowledge/manifest.json
haike-kb verify               打印各知识库解析状态与 custom_metadata
haike-kb search "query"       用 knowledge-search 试检索（验证 rerank 不可用时仍有结果）
haike-kb snapshot export|import [DIR]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from app.knowledge.ingest import Ingestor, verify_metadata, wait_parsed, write_manifest
from app.knowledge.snapshot import export_snapshot, import_snapshot
from app.knowledge.weknora_client import WeKnoraClient, WeKnoraError
from app.settings import REPO_ROOT, settings

DATA_ROOT = REPO_ROOT / "data" / "knowledge"
MANIFEST = DATA_ROOT / "manifest.json"
SNAPSHOTS = DATA_ROOT / "snapshots"
TENANT_USER = os.environ.get("WEKNORA_TENANT_USER", "haike-orchestrator")
TENANT_EMAIL = os.environ.get("WEKNORA_TENANT_EMAIL", "haike-orchestrator@local.dev")


def _client(need_key: bool = True) -> WeKnoraClient:
    key = settings.weknora_api_key
    if need_key and not key:
        print(
            "WEKNORA_API_KEY 未配置：先运行 `make kb-bootstrap`，或在 WeKnora UI 的空间设置里创建 API Key 填入 .env",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return WeKnoraClient(settings.weknora_base_url, key)


def _embedding_spec() -> dict | None:
    """有 DASHSCOPE_API_KEY 时按 models.yaml 的 embed-primary 登记百炼 text-embedding-v4；否则沿用 WeKnora 已有模型。"""
    key = os.environ.get("EMBEDDING_API_KEY") or os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        return None
    return {
        "name": os.environ.get("EMBEDDING_MODEL_NAME") or "text-embedding-v4",
        "type": "Embedding",
        "source": "remote",
        "description": "百炼 text-embedding-v4，1024 维（model-selection §2）",
        "parameters": {
            "provider": "openai",
            "base_url": os.environ.get("EMBEDDING_BASE_URL")
            or "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key": key,
            "embedding_parameters": {"dimension": 1024},
        },
    }


async def _bootstrap(password: str) -> int:
    """注册（已存在则登录）→ active_tenant → 建全权限 API key → 写 .env。v0.8.0 实测：登录响应无 data 包装，
    tenant 在 `active_tenant`，注册不返回 api_key，需 `POST /tenants/{id}/api-keys`（受限 key 要 capabilities，
    全权限 key 传 full_access=true；只有全权限 key 能管模型）。"""
    async with WeKnoraClient(settings.weknora_base_url) as c:
        cfg = await c.auth_config()
        if cfg.get("registration_mode") not in (None, "self_serve"):
            print(
                f"registration_mode={cfg.get('registration_mode')}，请在 WeKnora UI 建空间并创建 API Key",
                file=sys.stderr,
            )
            return 2
        try:
            await c.register(TENANT_USER, TENANT_EMAIL, password)
            print(f"registered user {TENANT_USER}")
        except WeKnoraError as exc:
            if exc.status not in (400, 409):
                raise
        data = await c.login(TENANT_EMAIL, password)
        tenant = data.get("active_tenant") or data.get("tenant") or {}
        token = data.get("token") or data.get("access_token")
        if not tenant.get("id") or not token:
            print("login response missing tenant/token", file=sys.stderr)
            return 1
        created = await c.create_api_key(
            tenant["id"], token, name="haike-orchestrator", role="admin", full_access=True
        )
        key = next(
            (v for v in created.values() if isinstance(v, str) and v.startswith("sk-")), None
        )
        print(
            f"tenant id={tenant.get('id')} name={tenant.get('name')} api_key={'created' if key else 'missing'}"
        )
        if key:
            _write_env("WEKNORA_API_KEY", key)
            _write_env("WEKNORA_TENANT_ID", str(tenant["id"]))
            print("已写入 .env WEKNORA_API_KEY / WEKNORA_TENANT_ID（值不打印）")
        return 0 if key else 1


def _write_env(name: str, value: str) -> None:
    env = REPO_ROOT / ".env"
    lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
    lines = [ln for ln in lines if not ln.startswith(f"{name}=")]
    lines.append(f"{name}={value}")
    env.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def _ingest(prune: bool, wait: bool) -> int:
    async with _client() as c:
        ing = Ingestor(c)
        ing.embedding_model_id = await ing.ensure_embedding_model(_embedding_spec())
        report = await ing.ingest_all(DATA_ROOT, prune=prune)
        if wait:
            for name, kb_id in report.kb_ids.items():
                if name != "kb_faq":
                    print(name, "parse_status", await wait_parsed(c, kb_id))
        manifest = write_manifest(MANIFEST, report, source_root=DATA_ROOT)
    print(
        json.dumps(
            {k: manifest[k] for k in ("kb_ver", "knowledge_bases", "counts", "errors")},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1 if report.errors else 0


async def _verify() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    async with _client() as c:
        for name, kb_id in manifest["knowledge_bases"].items():
            if name == "kb_faq":
                print(name, "faq_entries", len(await c.list_faq_entries(kb_id)))
                continue
            items = await verify_metadata(c, kb_id)
            print(name, kb_id, len(items), "items")
            for it in items[:5]:
                print(
                    "  ",
                    it["title"],
                    it["parse_status"],
                    json.dumps(it["custom_metadata"], ensure_ascii=False),
                )
    return 0


async def _search(query: str) -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    kb_ids = [v for k, v in manifest["knowledge_bases"].items() if k != "kb_faq"]
    async with _client() as c:
        hits = await c.knowledge_search(query, knowledge_base_ids=kb_ids)
    for h in hits[:5]:
        print(
            f"{h.get('score'):.3f}" if isinstance(h.get("score"), int | float) else "-",
            h.get("knowledge_title"),
            "|",
            (h.get("content") or "")[:80].replace("\n", " "),
        )
    print(f"{len(hits)} hits")
    return 0


async def _snapshot(action: str, directory: str | None) -> int:
    async with _client() as c:
        if action == "export":
            target = await export_snapshot(c, DATA_ROOT, MANIFEST, SNAPSHOTS)
            print(f"snapshot exported to {target}")
            return 0
        if not directory:
            print("import 需要快照目录", file=sys.stderr)
            return 2
        ing = Ingestor(c)
        embedding_id = await ing.ensure_embedding_model(_embedding_spec())
        manifest = await import_snapshot(
            c, Path(directory), MANIFEST, embedding_model_id=embedding_id
        )
        print(json.dumps(manifest["counts"], ensure_ascii=False))
        return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bootstrap")
    b.add_argument(
        "--password", default=os.environ.get("WEKNORA_TENANT_PASSWORD", "haike-dev-pass-2026")
    )
    i = sub.add_parser("ingest")
    i.add_argument("--prune", action="store_true")
    i.add_argument("--no-wait", action="store_true")
    sub.add_parser("verify")
    s = sub.add_parser("search")
    s.add_argument("query")
    sn = sub.add_parser("snapshot")
    sn.add_argument("action", choices=["export", "import"])
    sn.add_argument("dir", nargs="?")
    args = p.parse_args(argv)
    try:
        if args.cmd == "bootstrap":
            return asyncio.run(_bootstrap(args.password))
        if args.cmd == "ingest":
            return asyncio.run(_ingest(args.prune, not args.no_wait))
        if args.cmd == "verify":
            return asyncio.run(_verify())
        if args.cmd == "search":
            return asyncio.run(_search(args.query))
        return asyncio.run(_snapshot(args.action, args.dir))
    except WeKnoraError as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
