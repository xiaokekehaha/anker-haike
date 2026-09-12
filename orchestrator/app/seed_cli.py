"""参考数据 seed（票 19 / 31）：haike-seed [products|plans|all] [--config-dir DIR]，可重复执行。

另：haike-plans-schema 输出计划模型 JSON Schema（可 --out 写文件）。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.catalog import CatalogError, ProductCatalog
from app.catalog import store as catalog_store
from app.plans import PlanLibrary, PlansError, plan_json_schema
from app.plans import store as plans_store
from app.settings import REPO_ROOT, settings

CONFIG_DIR = REPO_ROOT / "config"


async def _run(what: str, config_dir: Path) -> int:
    try:
        catalog = ProductCatalog.from_yaml(config_dir / "products.yaml")
        library = PlanLibrary.from_yaml(config_dir / "plans.yaml")
    except (CatalogError, PlansError) as exc:
        print(exc, file=sys.stderr)
        return 2
    pool = AsyncConnectionPool(
        settings.database_url,
        min_size=1,
        max_size=2,
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    await pool.open(wait=True, timeout=settings.health_timeout_s * 3)
    try:
        if what in ("products", "all"):
            print("products", await catalog_store.seed_products(pool, catalog))
        if what in ("plans", "all"):
            print("plans", await plans_store.seed_plans(pool, library))
    finally:
        await pool.close()
    return 0


def seed(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="写入 products / plans 参考数据（幂等）")
    p.add_argument("what", nargs="?", default="all", choices=["products", "plans", "all"])
    p.add_argument("--config-dir", default=str(CONFIG_DIR))
    args = p.parse_args(argv)
    return asyncio.run(_run(args.what, Path(args.config_dir)))


def plans_schema(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="输出计划模型 JSON Schema")
    p.add_argument("--config", default=str(CONFIG_DIR / "plans.yaml"))
    p.add_argument("--out", default=None)
    p.add_argument("--enum", action="store_true", help="plan_id 收窄为当前配置的枚举")
    args = p.parse_args(argv)
    library = PlanLibrary.from_yaml(args.config)
    schema = plan_json_schema(library.plan_ids if args.enum else None)
    text = json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text, end="")
    return 0
