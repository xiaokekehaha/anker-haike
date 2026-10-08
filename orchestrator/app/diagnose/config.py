"""config/retrieval.yaml：检索编排开关（03 §1.4.2）。"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.settings import CONFIG_DIR


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
    candidate_k: int = Field(default=15, ge=1, le=100)
    final_k: int = Field(default=12, ge=1, le=20)
    context_chars: int = Field(default=5000, ge=200, le=12000)
    item_chars: int = Field(default=800, ge=200, le=3000)
    second_round_budget_ms: int = Field(default=3000, ge=500)
    min_remaining_for_second_round_ms: int = Field(default=3000, ge=0)


class RerankConfig(_Strict):
    """适配器侧调百炼 gte-rerank-v2（WeKnora hybrid-search 不重排）。"""

    enabled: bool = False
    model: str = "gte-rerank-v2"
    timeout_ms: int = Field(default=2000, ge=200)
    min_remaining_ms: int = Field(default=5000, ge=0)


class GradeConfig(_Strict):
    """充分性评估；仅标记质量，不删除候选。启用改写时自动评估已有证据。"""

    enabled: bool = False
    budget_ms: int = Field(default=4000, ge=500)
    min_remaining_ms: int = Field(default=6000, ge=0)
    max_items: int = Field(default=12, ge=1, le=20)
    max_chars: int = Field(default=500, ge=200, le=1000)
    second_round: bool = False


class SynthesizeConfig(_Strict):
    budget_ms: int = Field(default=8000, ge=1000)
    max_hypotheses: int = Field(default=3, ge=1, le=5)


class RetrievalConfig(_Strict):
    version: str = "0"
    query_rewrite: QueryRewriteConfig = Field(default_factory=QueryRewriteConfig)
    retrieval: RetrievalRounds = Field(default_factory=RetrievalRounds)
    rerank: RerankConfig = Field(default_factory=RerankConfig)
    grade: GradeConfig = Field(default_factory=GradeConfig)
    synthesize: SynthesizeConfig = Field(default_factory=SynthesizeConfig)


def load_retrieval_config(path: str | Path | None = None) -> RetrievalConfig:
    if path is None:
        path = os.environ.get("RETRIEVAL_CONFIG_PATH") or CONFIG_DIR / "retrieval.yaml"
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
