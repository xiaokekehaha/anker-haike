"""三段式等待节点的公用件（08 §3，票 20）：card_id 派生、节点内 version、产品目录访问。"""

from __future__ import annotations

import hashlib
import uuid

from langgraph.config import get_config

from app.catalog import ProductCatalog
from app.plans import PlanLibrary

_NS = uuid.UUID("6f4c1e2a-3b7d-4a55-9c1e-20260912a0c1")
_catalog: ProductCatalog | None = None
_plans: PlanLibrary | None = None


def derive_card_id(session_id: str, stage: str, key: str) -> str:
    """card_id = uuid5(session_id, 业务位置, 候选哈希 / 计划游标)：同一业务位置重跑得到同一 id。"""
    return uuid.uuid5(_NS, f"{session_id}|{stage}|{key}").hex


def candidates_key(skus: list[str]) -> str:
    return hashlib.sha1("|".join(sorted(skus)).encode()).hexdigest()[:16]


def current_version() -> int:
    """节点内取「本节点若在此中断，checkpoint 推导出的 version」= langgraph_step（探测见票 20 记录）。"""
    return int(get_config()["metadata"]["langgraph_step"])


def get_catalog() -> ProductCatalog:
    global _catalog
    if _catalog is None:
        from app.settings import settings

        _catalog = ProductCatalog.from_yaml(settings.catalog_config_path)
    return _catalog


def set_catalog(catalog: ProductCatalog | None) -> None:
    """测试 / 运行时注入。"""
    global _catalog
    _catalog = catalog


def get_plans() -> PlanLibrary:
    """预写计划库（票 24：category_only 需要该品类存在 category_generic 计划才允许继续）。"""
    global _plans
    if _plans is None:
        from app.settings import settings

        _plans = PlanLibrary.from_yaml(settings.plans_config_path)
    return _plans


def set_plans(plans: PlanLibrary | None) -> None:
    global _plans
    _plans = plans
