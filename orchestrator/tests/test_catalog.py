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
    # 2026-10-08 只收主办方资料包内的 8 款产品，sku 即 PN；三个品类都在范围内
    assert {p.sku for p in catalog.products} == {
        "T2080", "T2351", "T2352", "T2353", "T2280", "T2292", "T8D04", "T8170",
    }
    assert all(p.in_scope for p in catalog.products)
    assert set(catalog.categories) == {"robot_vacuum", "breast_pump", "security_cam"}
    assert {spec.line for spec in catalog.categories.values()} == {"Anker eufy"}
    assert len({p.sku for p in catalog.products}) == len(catalog.products)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("S1 Pro", ["T2080", "T8D04"]),  # 同名异类：两个候选都在范围内，按名称稳定排序
        ("扫地机 X10", ["T2351"]),  # 单命中
        ("随便", []),  # 零命中
        ("扫地机器人", []),  # 只有品类词
        ("", []),
        ("x10 pro omni", ["T2351"]),
        ("T2351", ["T2351"]),
        ("T8D04121", ["T8D04"]),  # 订单完整 SKU 按 PN 前缀归一
        ("T2351V11-F", ["T2351"]),
        ("我的 eufy E28 吸力变小了", ["T2352"]),
        ("吸奶器s1pro", ["T2080", "T8D04"]),  # 目录只按别名匹配，品类词不参与排除；由产品卡片消歧
        ("E28 和 E25 哪个", ["T2353", "T2352"]),
        ("扫地机 X10 Pro Omin", ["T2351"]),  # 模糊
        ("充电宝 A1257", []),  # 目录外产品
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
    assert catalog.category_hint("摄像头离线了") == "security_cam"
    assert catalog.category_hint("充电宝坏了") is None  # 目录外品类
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
        {"sku": "T9999", "name": "eufy Z1", "category": "robot_vacuum", "aliases": ["Z1"]}
    )
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    assert cat.reload(p) is False and cat.lookup_product("Z1") == []  # 版本没变不重载
    data["version"] = "2099.1"
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    assert cat.reload(p) is True and cat.lookup_product("Z1")[0].sku == "T9999"


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
        assert {c.sku for c in loaded.lookup_product("S1 Pro")} == {"T2080", "T8D04"}
        assert all(p.in_scope for p in loaded.products)
    finally:
        await pool.close()
