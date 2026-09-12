"""票 47：迁移基线覆盖全部业务表；真实 Postgres 可连时校验 upgrade / current / ensure_schema。"""

import importlib.util
import re

import pytest

from app.db import migrations as m
from app.db.migrations import head_revision, sqlalchemy_url


def _baseline_module():
    path = m.ORCHESTRATOR_ROOT / "migrations" / "versions" / "0001_baseline.py"
    spec = importlib.util.spec_from_file_location("baseline", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _tables_in(ddl: str) -> set[str]:
    return set(re.findall(r"create table if not exists (\w+)", ddl))


def test_head_is_single_and_baseline():
    assert head_revision() == "0001"


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


def test_sqlalchemy_url_uses_psycopg_dialect():
    assert sqlalchemy_url("postgresql://u:p@h:5432/d") == "postgresql+psycopg://u:p@h:5432/d"
    assert sqlalchemy_url("postgresql+psycopg://u:p@h/d") == "postgresql+psycopg://u:p@h/d"


async def test_ensure_schema_prod_raises_when_behind(monkeypatch):
    monkeypatch.setattr(m, "current_revision", lambda *_a, **_k: None)
    with pytest.raises(m.SchemaOutOfDate) as ei:
        await m.ensure_schema(app_env="prod")
    assert ei.value.current is None and ei.value.head == "0001"


async def test_ensure_schema_dev_upgrades(monkeypatch):
    calls = []
    seq = iter([None, "0001"])
    monkeypatch.setattr(m, "current_revision", lambda *_a, **_k: next(seq))
    monkeypatch.setattr(m, "upgrade_to_head", lambda *_a, **_k: calls.append("up") or "0001")
    out = await m.ensure_schema(app_env="dev")
    assert out == {"head": "0001", "before": None, "after": "0001", "upgraded": True} and calls == [
        "up"
    ]


async def test_real_db_current_equals_head_after_upgrade():
    import psycopg

    from app.settings import settings

    try:
        psycopg.connect(settings.database_url, connect_timeout=1).close()
    except Exception:  # noqa: BLE001
        pytest.skip("postgres not reachable")
    assert m.upgrade_to_head() == "0001"  # 幂等
    assert m.current_revision() == "0001"
    out = await m.ensure_schema(app_env="prod")
    assert out["upgraded"] is False and out["after"] == "0001"
