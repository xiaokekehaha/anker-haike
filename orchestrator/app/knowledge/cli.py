"""haike-kb：WeKnora 知识库运维。

haike-kb bootstrap            注册项目独立 tenant（本地自助注册）并打印 tenant id；key 写入 .env 的 WEKNORA_API_KEY
haike-kb ingest [--keep-legacy]
                              官方 Q&A（data/official/qa.yaml）幂等导入 haike_kb_qa，一条 Q&A 一个知识；
                              删除不再使用的中文手册 / FAQ / 合成工单库（--keep-legacy 保留）；写 manifest
haike-kb eval [--arm A] [--config data/eval/retrieval/configs/B.yaml] [--cases …] [--top-k 5]
                              用评测集直接打 KnowledgeAdapter，输出 hit@k / precision@k / 泄漏 / 延迟到 reports/retrieval/
haike-kb verify               打印各知识库解析状态与 custom_metadata
haike-kb anchors              证据可达性基线：锚点分块 / 检索可达 / 元数据完整
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

from app.knowledge.adapter import WeKnoraKnowledgeAdapter
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


def _rerank_spec() -> dict | None:
    """有 DASHSCOPE_API_KEY 时登记百炼 gte-rerank-v2（models.yaml rerank-primary，D17）并绑到知识库。"""
    key = os.environ.get("RERANK_API_KEY") or os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        return None
    return {
        "name": os.environ.get("RERANK_MODEL_NAME") or "gte-rerank-v2",
        "type": "Rerank",
        "source": "remote",
        "description": "百炼 gte-rerank-v2（D17）",
        "parameters": {
            "provider": "aliyun",
            "base_url": os.environ.get("RERANK_BASE_URL")
            or "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank",
            "api_key": key,
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


async def _ingest(wait: bool, keep_legacy: bool = False) -> int:
    from app.knowledge.official_qa import drop_legacy_kbs, ingest_qa, qa_manifest_chunking

    async with _client() as c:
        ing = Ingestor(c)
        embedding_id = await ing.ensure_embedding_model(_embedding_spec())
        await ing.ensure_rerank_model(_rerank_spec())
        dropped = [] if keep_legacy else await drop_legacy_kbs(c)
        kb = await ingest_qa(c, ing.report, embedding_model_id=embedding_id)
        if wait:
            print("kb_qa parse_status", await wait_parsed(c, kb["id"], timeout_s=900))
        manifest = write_manifest(MANIFEST, ing.report, source_root=REPO_ROOT / "data" / "official")
        manifest["chunking"] = qa_manifest_chunking()
        MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {**{k: manifest[k] for k in ("kb_ver", "knowledge_bases", "counts", "errors")}, "dropped_kbs": dropped},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1 if ing.report.errors else 0


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


async def _anchors(top_k: int) -> int:
    """证据可达性基线（G4-A/B/C）：锚点标记与正文是否同块、锚点是否检索得到、元数据是否完整。"""
    from app.knowledge.reachability import check_chunking, check_reachable, plan_anchors
    from app.plans.runtime import get_plan_library

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    anchors = plan_anchors(get_plan_library())
    async with _client() as c:
        adapter = WeKnoraKnowledgeAdapter(c, manifest["knowledge_bases"])
        await adapter.refresh_index()
        await adapter.refresh_chunks()
        by_doc: dict[str, list[dict]] = {}
        for e in adapter.index["kb_manual"]:
            by_doc.setdefault(e.doc_id, []).extend(adapter.chunks.get(e.knowledge_id) or [])
        chunking = check_chunking(anchors, by_doc)
        reach = await check_reachable(anchors, adapter, top_k=top_k)
        missing = [
            it
            for kb, kb_id in manifest["knowledge_bases"].items()
            if kb != "kb_faq"
            for it in await verify_metadata(c, kb_id)
            if not (it["custom_metadata"] or {}).get("doc_version")
        ]
    print("== B 分块：标记与正文同块 ==")
    for r in chunking:
        print(f"  {r['verdict']:<13} {r['evidence_key']:<24} {r['text'][:24]}")
    print("== A 可达：步骤标题能否检索到锚点 ==")
    for r in reach:
        rank = f"@{r['hit_rank']}" if r["hit_rank"] else "-"
        print(
            f"  {r['verdict']:<16} {r['evidence_key']:<24} {rank:<4} "
            f"match={r['match']:<12} scope={r.get('scope', '-'):<18} q={r['query']}"
        )
    print("== C 元数据：doc_version 缺失 ==")
    print(f"  missing={len(missing)}")
    bad_b = [r for r in chunking if r["verdict"] in ("split", "text_missing", "marker_missing")]
    bad_a = [r for r in reach if r["verdict"] == "unreachable"]
    print(
        json.dumps(
            {"chunking_bad": len(bad_b), "unreachable": len(bad_a), "metadata_missing": len(missing)},
            ensure_ascii=False,
        )
    )
    return 1 if (bad_b or bad_a or missing) else 0


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
    i.add_argument("--no-wait", action="store_true")
    i.add_argument("--keep-legacy", action="store_true")
    ev = sub.add_parser("eval")
    ev.add_argument("--arm", default="A")
    ev.add_argument(
        "--cases", default=str(REPO_ROOT / "data" / "eval" / "retrieval" / "cases.yaml")
    )
    ev.add_argument("--top-k", type=int, default=5)
    ev.add_argument("--out-dir", default=str(REPO_ROOT / "reports" / "retrieval"))
    ev.add_argument(
        "--config", default=None, help="覆盖 config/retrieval.yaml（各对照组的开关文件）"
    )
    ev.add_argument(
        "--with-synthesize",
        action="store_true",
        help="再用真实模型跑 grade（若开）+ synthesize，比较 expected_plan / expected_outcome（需厂商 key）",
    )
    sub.add_parser("verify")
    an = sub.add_parser("anchors")
    an.add_argument("--top-k", type=int, default=6)
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
            return asyncio.run(_ingest(not args.no_wait, args.keep_legacy))
        if args.cmd == "eval":
            from app.knowledge.eval import run_eval

            return asyncio.run(
                run_eval(
                    _client(),
                    Path(args.cases),
                    arm=args.arm,
                    top_k=args.top_k,
                    out_dir=Path(args.out_dir),
                    config_path=Path(args.config) if args.config else None,
                    with_synthesize=args.with_synthesize,
                )
            )
        if args.cmd == "verify":
            return asyncio.run(_verify())
        if args.cmd == "anchors":
            return asyncio.run(_anchors(args.top_k))
        if args.cmd == "search":
            return asyncio.run(_search(args.query))
        return asyncio.run(_snapshot(args.action, args.dir))
    except WeKnoraError as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
