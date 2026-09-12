"""票 47：迁移基线覆盖全部业务表；真实 Postgres 可连时校验 upgrade / current / ensure_schema。"""

import importlib.util
import re

import pytest

from app.db import migrations as m
from app.db.migrations import head_revision, sqlalchemy_url


def _revision_module(filename: str):
    path = m.ORCHESTRATOR_ROOT / "migrations" / "versions" / filename
    spec = importlib.util.spec_from_file_location(filename.removesuffix(".py"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _baseline_module():
    return _revision_module("0001_baseline.py")


HEAD = "0002"  # 0001 基线 + 0002 session_images（票 29）


def _tables_in(ddl: str) -> set[str]:
    return set(re.findall(r"create table if not exists (\w+)", ddl))


def test_head_is_single_and_latest():
    assert head_revision() == HEAD


def test_baseline_covers_every_store_ddl():
    """各 store 的 DDL 建的表，基线迁移必须一张不落（结构唯一来源是 migrations/）。"""
    from app.catalog import store as catalog_store
    from app.plans import store as plans_store
    from app.sessions import store as sessions_store

    baseline = _baseline_module()
    migrated = _tables_in("\n".join(baseline.STATEMENTS))
    expected = (
        _tables_in(sessions_store.DDL) | _tables_in(catalog_store.DDL) | _tables_in(plans_store.DDL)
    )
    assert expected <= migrated, expected - migrated
    assert set(baseline.BUSINESS_TABLES) == migrated


def test_images_migration_covers_image_store_ddl():
    """票 29 的 session_images 由 0002 建表，与 PostgresImageStore.setup() 的 DDL 一致。"""
    from app.images import store as images_store

    rev = _revision_module("0002_session_images.py")
    assert rev.down_revision == "0001"
    migrated = _tables_in("\n".join(rev.STATEMENTS))
    assert migrated == _tables_in(images_store.DDL) == {"session_images"}
    assert set(rev.BUSINESS_TABLES) == migrated


def test_sqlalchemy_url_uses_psycopg_dialect():
    assert sqlalchemy_url("postgresql://u:p@h:5432/d") == "postgresql+psycopg://u:p@h:5432/d"
    assert sqlalchemy_url("postgresql+psycopg://u:p@h/d") == "postgresql+psycopg://u:p@h/d"


async def test_ensure_schema_prod_raises_when_behind(monkeypatch):
    monkeypatch.setattr(m, "current_revision", lambda *_a, **_k: None)
    with pytest.raises(m.SchemaOutOfDate) as ei:
        await m.ensure_schema(app_env="prod")
    assert ei.value.current is None and ei.value.head == HEAD


async def test_ensure_schema_dev_upgrades(monkeypatch):
    calls = []
    seq = iter([None, HEAD])
    monkeypatch.setattr(m, "current_revision", lambda *_a, **_k: next(seq))
    monkeypatch.setattr(m, "upgrade_to_head", lambda *_a, **_k: calls.append("up") or HEAD)
    out = await m.ensure_schema(app_env="dev")
    assert out == {"head": HEAD, "before": None, "after": HEAD, "upgraded": True} and calls == [
        "up"
    ]


async def test_real_db_current_equals_head_after_upgrade():
    import psycopg

    from app.settings import settings

    try:
        psycopg.connect(settings.database_url, connect_timeout=1).close()
    except Exception:  # noqa: BLE001
        pytest.skip("postgres not reachable")
    assert m.upgrade_to_head() == HEAD  # 幂等
    assert m.current_revision() == HEAD
    out = await m.ensure_schema(app_env="prod")
    assert out["upgraded"] is False and out["after"] == HEAD
