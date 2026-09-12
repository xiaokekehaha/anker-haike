"""config/retrieval.yaml：检索编排开关（03 §1.4.2）。"""

from __future__ import annotations

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
    synonyms: dict[str, list[str]] = Field(default_factory=dict)


class RetrievalRounds(_Strict):
    top_k: int = Field(default=5, ge=1, le=20)
    second_round_budget_ms: int = Field(default=3000, ge=500)
    min_remaining_for_second_round_ms: int = Field(default=3000, ge=0)


class SynthesizeConfig(_Strict):
    budget_ms: int = Field(default=8000, ge=1000)
    max_hypotheses: int = Field(default=3, ge=1, le=5)


class RetrievalConfig(_Strict):
    version: str = "0"
    query_rewrite: QueryRewriteConfig = Field(default_factory=QueryRewriteConfig)
    retrieval: RetrievalRounds = Field(default_factory=RetrievalRounds)
    synthesize: SynthesizeConfig = Field(default_factory=SynthesizeConfig)


def load_retrieval_config(path: str | Path | None = None) -> RetrievalConfig:
    if path is None:
        from app.settings import REPO_ROOT

        path = REPO_ROOT / "config" / "retrieval.yaml"
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
