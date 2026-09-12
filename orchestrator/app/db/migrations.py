"""Alembic 封装：head / current / upgrade，以及启动期校验（票 47）。

策略：APP_ENV=dev 时版本落后自动升级到 head（本机 / 演示机方便）；其他环境只校验，
落后则抛 SchemaOutOfDate，由调用方决定让 sessions 接口 503 还是拒绝启动。
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.settings import settings

log = logging.getLogger("db.migrations")

ORCHESTRATOR_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = ORCHESTRATOR_ROOT / "alembic.ini"


class SchemaOutOfDate(RuntimeError):
    def __init__(self, current: str | None, head: str) -> None:
        super().__init__(f"database schema at {current or 'empty'}, code expects {head}")
        self.current = current
        self.head = head


def sqlalchemy_url(database_url: str | None = None) -> str:
    """psycopg3 的 SQLAlchemy 方言前缀。"""
    url = database_url or settings.database_url
    if url.startswith("postgresql+psycopg://"):
        return url
    return url.replace("postgresql://", "postgresql+psycopg://", 1).replace(
        "postgres://", "postgresql+psycopg://", 1
    )


def alembic_config() -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ORCHESTRATOR_ROOT / "migrations"))
    return cfg


def head_revision() -> str:
    script = ScriptDirectory.from_config(alembic_config())
    heads = script.get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"expected exactly one migration head, got {heads}")
    return heads[0]


def current_revision(database_url: str | None = None, *, timeout_s: float = 5.0) -> str | None:
    """读 alembic_version；表不存在（从未迁移）返回 None。"""
    with psycopg.connect(
        database_url or settings.database_url, connect_timeout=int(max(1, timeout_s))
    ) as conn:
        row = conn.execute("select to_regclass('public.alembic_version')").fetchone()
        if row is None or row[0] is None:
            return None
        row = conn.execute("select version_num from alembic_version").fetchone()
        return None if row is None else str(row[0])


def upgrade_to_head(database_url: str | None = None) -> str:
    cfg = alembic_config()
    if database_url:
        cfg.set_main_option("sqlalchemy.url", sqlalchemy_url(database_url))
    command.upgrade(cfg, "head")
    return head_revision()


async def ensure_schema(*, app_env: str | None = None, database_url: str | None = None) -> dict:
    """启动期校验。返回 {"head", "before", "after", "upgraded"}；非 dev 且落后时抛 SchemaOutOfDate。"""
    env = app_env or settings.app_env
    head = head_revision()
    before = await asyncio.to_thread(current_revision, database_url)
    if before == head:
        return {"head": head, "before": before, "after": before, "upgraded": False}
    if env != "dev":
        raise SchemaOutOfDate(before, head)
    log.warning("schema %s != head %s, APP_ENV=dev → alembic upgrade head", before or "empty", head)
    await asyncio.to_thread(upgrade_to_head, database_url)
    after = await asyncio.to_thread(current_revision, database_url)
    return {"head": head, "before": before, "after": after, "upgraded": True}
