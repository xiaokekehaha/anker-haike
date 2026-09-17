"""票 19：产品目录配置、别名匹配、L4 重载、products 表 seed。"""

from __future__ import annotations

import asyncio

import pytest
import yaml

from app.catalog import CatalogError, ProductCatalog, load_catalog_config
from app.settings import REPO_ROOT

REAL = REPO_ROOT / "config" / "products.yaml"


@pytest.fixture(scope="module")
def catalog() -> ProductCatalog:
    return ProductCatalog.from_yaml(REAL)


def test_seed_config_shape(catalog):
    assert len(catalog.products) >= 20
    # 2026-09-17 多品类：只有家用储能（电工安装、专业售后）留在范围外；每个品类都标注官网产品线
    out_of_scope = [p for p in catalog.products if not p.in_scope]
    assert {p.category for p in out_of_scope} == {"home_storage"}
    assert {spec.line for spec in catalog.categories.values()} == {
        "Anker Charging", "Anker SOLIX", "Anker eufy", "Anker soundcore", "Anker eufyMake",
    }
    assert len({p.sku for p in catalog.products}) == len(catalog.products)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("S1 Pro", ["EUFY-BP-S1-PRO", "EUFY-S1-PRO"]),  # 同名异类：两个候选都在范围内，按名称稳定排序
        ("扫地机 X", ["EUFY-X10-PRO-OMNI"]),  # 单命中
        ("随便", []),  # 零命中
        ("扫地机器人", []),  # 只有品类词
        ("", []),
        ("x10 pro omni", ["EUFY-X10-PRO-OMNI"]),
        ("EUFY-X9-PRO", ["EUFY-X9-PRO"]),
        ("我的 eufy X8 Pro 吸力变小了", ["EUFY-X8-PRO-SES"]),
        ("吸奶器s1pro", ["EUFY-BP-S1-PRO"]),
        ("X10 和 X9 哪个", ["EUFY-X10-PRO-OMNI", "EUFY-X9-PRO"]),
        ("扫地机 X8Pro", ["EUFY-X8-PRO-SES"]),
        ("扫地机 G30 Verg", ["EUFY-G30-VERGE"]),  # 模糊
        ("充电宝 A1257", ["ANKER-A1257"]),
    ],
)
def test_lookup_product(catalog, query, expected):
    assert [c.sku for c in catalog.lookup_product(query)] == expected


def test_candidates_carry_in_scope_and_contract_shape(catalog):
    cands = catalog.lookup_product("S1 Pro")
    assert [c.in_scope for c in cands] == [True, True]  # 2026-09-17 多品类：吸奶器也在范围内
    assert {c.category for c in cands} == {"breast_pump", "robot_vacuum"}
    assert set(cands[0].model_dump()) == {"sku", "name", "category", "image", "in_scope"}


def test_category_hint(catalog):
    assert catalog.category_hint("我家扫地机不吸了") == "robot_vacuum"
    assert catalog.category_hint("吸奶器坏了") == "breast_pump"
    # 2026-09-17 会话 cd45df：目录里只有一个机器人品类，单说「机器人」就该认出来
    assert catalog.category_hint("我的机器人有问题") == "robot_vacuum"
    assert catalog.category_hint("随便") is None


def test_config_errors(tmp_path):
    data = yaml.safe_load(REAL.read_text(encoding="utf-8"))
    data["products"][0]["category"] = "ghost"
    data["products"].append(dict(data["products"][1]))
    p = tmp_path / "products.yaml"
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    with pytest.raises(CatalogError) as ei:
        load_catalog_config(p)
    assert "unknown category 'ghost'" in str(ei.value) and "duplicate sku" in str(ei.value)
    with pytest.raises(CatalogError, match="not found"):
        load_catalog_config(tmp_path / "nope.yaml")


def test_reload_only_when_version_changes(tmp_path):
    data = yaml.safe_load(REAL.read_text(encoding="utf-8"))
    p = tmp_path / "products.yaml"
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    cat = ProductCatalog.from_yaml(p)
    data["products"].append(
        {"sku": "NEW-1", "name": "eufy Z1", "category": "robot_vacuum", "aliases": ["Z1"]}
    )
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    assert cat.reload(p) is False and cat.lookup_product("Z1") == []  # 版本没变不重载
    data["version"] = "2099.1"
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    assert cat.reload(p) is True and cat.lookup_product("Z1")[0].sku == "NEW-1"


# ---- products 表（本机 / Compose 的 postgres 可连时运行）----


async def _pool():
    import psycopg
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool

    from app.settings import settings

    try:
        async with await asyncio.wait_for(
            psycopg.AsyncConnection.connect(settings.database_url, connect_timeout=1), 1.5
        ):
            pass
    except Exception:  # noqa: BLE001
        pytest.skip("postgres not reachable")
    pool = AsyncConnectionPool(
        settings.database_url,
        min_size=1,
        max_size=2,
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    await pool.open(wait=True, timeout=5)
    return pool


async def test_seed_products_is_idempotent(catalog):
    from app.catalog import store

    pool = await _pool()
    try:
        first = await store.seed_products(pool, catalog)
        second = await store.seed_products(pool, catalog)
        assert first["total"] == second["total"] == len(catalog.products)
        assert second["removed"] == 0
        loaded = await store.load_from_db(pool, catalog.categories)
        assert loaded.version == catalog.version
        assert {p.sku for p in loaded.products} == {p.sku for p in catalog.products}
        assert {c.sku for c in loaded.lookup_product("S1 Pro")} == {"EUFY-S1-PRO", "EUFY-BP-S1-PRO"}
        assert any(not p.in_scope and p.category == "home_storage" for p in loaded.products)
    finally:
        await pool.close()
