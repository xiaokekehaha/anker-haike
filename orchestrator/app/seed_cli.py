"""参考数据 seed：haike-seed [products] [--config-dir DIR]，可重复执行。

订单、物流与经销商名录直接读 data/official；排障计划由官方 Q&A 在进程内生成（app.plans.qa），都不进数据库。
另：haike-plans-schema 输出计划模型 JSON Schema（可 --out 写文件，--enum 收窄为当前 Q&A 计划 id）。
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
from app.plans import plan_json_schema
from app.settings import CONFIG_DIR, settings


async def _run(config_dir: Path) -> int:
    try:
        catalog = ProductCatalog.from_yaml(config_dir / "products.yaml")
    except (CatalogError, OSError) as exc:
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
        print("products", await catalog_store.seed_products(pool, catalog))
    finally:
        await pool.close()
    return 0


def seed(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="写入产品目录参考数据（幂等）")
    p.add_argument("what", nargs="?", default="products", choices=["products", "all"])
    p.add_argument("--config-dir", default=str(CONFIG_DIR))
    args = p.parse_args(argv)
    return asyncio.run(_run(Path(args.config_dir)))


def plans_schema(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="输出计划模型 JSON Schema")
    p.add_argument("--out", default=None)
    p.add_argument("--enum", action="store_true", help="plan_id 收窄为当前官方 Q&A 计划枚举")
    args = p.parse_args(argv)
    ids = None
    if args.enum:
        from app.plans.runtime import get_plan_library

        ids = get_plan_library().plan_ids
    text = json.dumps(plan_json_schema(ids), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text, end="")
    return 0
