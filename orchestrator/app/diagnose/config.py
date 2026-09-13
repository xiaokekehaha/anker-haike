"""config/retrieval.yaml：检索编排开关（03 §1.4.2）。"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QueryRewriteConfig(_Strict):
    enabled: bool = False
    max_query_chars: int = Field(default=200, ge=20, le=500)
    budget_ms: int = Field(default=3000, ge=500)
    min_remaining_ms: int = Field(default=8000, ge=0)
    # true 时启用早期「整句必须可由原文切出」的严格模式；实测拒掉几乎所有自然改写（阶段 6），默认关
    strict_terms: bool = False
    synonyms: dict[str, list[str]] = Field(default_factory=dict)


class RetrievalRounds(_Strict):
    top_k: int = Field(default=5, ge=1, le=20)
    second_round_budget_ms: int = Field(default=3000, ge=500)
    min_remaining_for_second_round_ms: int = Field(default=3000, ge=0)


class MultiQueryConfig(_Strict):
    """S0/S1：已审核同义词表的确定性多查询 + 本地 RRF 合并（design.md §3.2）。"""

    enabled: bool = False
    max_variants: int = Field(default=2, ge=0, le=4)  # 不含原 query
    max_requests_per_round: int = Field(default=6, ge=2, le=12)
    rrf_k: int = Field(default=60, ge=1)


class FaqConfig(_Strict):
    """本地 FAQ 索引接入首轮检索（design.md §14）。"""

    enabled: bool = False
    top_k: int = Field(default=3, ge=1, le=10)
    threshold: float = Field(default=0.3, ge=0.0, le=1.0)


class RerankConfig(_Strict):
    """适配器侧调百炼 gte-rerank-v2（WeKnora hybrid-search 不重排）。"""

    enabled: bool = False
    model: str = "gte-rerank-v2"
    timeout_ms: int = Field(default=2000, ge=200)
    min_remaining_ms: int = Field(default=5000, ge=0)


class GradeConfig(_Strict):
    """S2 相关性评分（design.md §3.2）：一次轻量模型调用，只剔除 irrelevant，coverage 供 S3 决策。"""

    enabled: bool = False
    budget_ms: int = Field(default=4000, ge=500)
    min_remaining_ms: int = Field(default=6000, ge=0)
    max_items: int = Field(default=8, ge=1, le=20)
    keep_min: int = Field(default=1, ge=0, le=5)
    second_round: bool = False


class ParentExpandConfig(_Strict):
    """S4 small-to-big：手册命中的同父子块拼接成父块正文给 synthesize（design.md §3.2）。"""

    enabled: bool = False
    max_items: int = Field(default=3, ge=1, le=10)
    max_chars: int = Field(default=800, ge=200, le=3000)


class SynthesizeConfig(_Strict):
    budget_ms: int = Field(default=8000, ge=1000)
    max_hypotheses: int = Field(default=3, ge=1, le=5)


class RetrievalConfig(_Strict):
    version: str = "0"
    query_rewrite: QueryRewriteConfig = Field(default_factory=QueryRewriteConfig)
    retrieval: RetrievalRounds = Field(default_factory=RetrievalRounds)
    multi_query: MultiQueryConfig = Field(default_factory=MultiQueryConfig)
    faq: FaqConfig = Field(default_factory=FaqConfig)
    rerank: RerankConfig = Field(default_factory=RerankConfig)
    parent_expand: ParentExpandConfig = Field(default_factory=ParentExpandConfig)
    grade: GradeConfig = Field(default_factory=GradeConfig)
    synthesize: SynthesizeConfig = Field(default_factory=SynthesizeConfig)


def load_retrieval_config(path: str | Path | None = None) -> RetrievalConfig:
    if path is None:
        from app.settings import REPO_ROOT

        path = os.environ.get("RETRIEVAL_CONFIG_PATH") or REPO_ROOT / "config" / "retrieval.yaml"
    path = Path(path)
    if not path.is_file():
        return RetrievalConfig()
    return RetrievalConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


_cfg: RetrievalConfig | None = None


def get_retrieval_config() -> RetrievalConfig:
    global _cfg
    if _cfg is None:
        _cfg = load_retrieval_config()
    return _cfg


def set_retrieval_config(cfg: RetrievalConfig | None) -> None:
    global _cfg
    _cfg = cfg
