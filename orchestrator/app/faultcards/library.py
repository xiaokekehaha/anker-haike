"""故障卡加载、渲染与命中（07 §7）。

- 每张卡 ≤ 800 token（中文 1 字 ≈ 1 token，ASCII 约 4 字符 1 token），超出启动失败。
- faults[].plan_id 必须存在于 PlanLibrary（可选校验，传入 plan_ids 时启用）。
- 命中判断：症状 / 查询文本包含某条 fault 的 keyword → 该 fault 命中；命中项以「fault_card」来源进入 synthesize 证据，
  未命中不伪造 no_match、也不触发改写（票 33 验收）。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

MAX_CARD_TOKENS = 800
MAX_PROMPT_TOKENS = 8000
_ASCII_RUN = re.compile(r"[A-Za-z0-9_\-./]+")
_CJK = re.compile(r"[一-鿿]")


class FaultCardsError(RuntimeError):
    pass


def estimate_tokens(text: str) -> int:
    """粗略 token 估算：CJK 每字 1，ASCII 串每 4 字符 1（向上取整），其余标点 / 空白按 0.5 计。"""
    cjk = len(_CJK.findall(text))
    ascii_tokens = sum((len(m.group(0)) + 3) // 4 for m in _ASCII_RUN.finditer(text))
    rest = len(text) - cjk - sum(len(m.group(0)) for m in _ASCII_RUN.finditer(text))
    return cjk + ascii_tokens + (rest + 1) // 2


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FaultEntry(_Strict):
    fault: str
    plan_id: str = Field(pattern=r"^[a-z0-9_]+$")
    keywords: list[str] = Field(min_length=1)
    first_step: str


class FaultCard(_Strict):
    key: str  # SKU 或 category:<category>
    doc_version: str
    title: str
    faults: list[FaultEntry] = Field(min_length=1, max_length=8)
    safety: list[str] = Field(default_factory=list)

    @property
    def is_category(self) -> bool:
        return self.key.startswith("category:")

    def render(self) -> str:
        lines = [f"【{self.title}】（版本 {self.doc_version}）", "常见故障与首步："]
        for i, f in enumerate(self.faults, 1):
            lines.append(f"{i}. {f.fault} → 首步：{f.first_step}（计划 {f.plan_id}）")
        if self.safety:
            lines.append("安全禁忌：")
            lines += [f"- {s}" for s in self.safety]
        return "\n".join(lines)

    def tokens(self) -> int:
        return estimate_tokens(self.render())

    def match(self, texts: list[str]) -> list[FaultEntry]:
        blob = " ".join(t for t in texts if t).casefold()
        return [f for f in self.faults if any(k.casefold() in blob for k in f.keywords)]

    def evidence_items(self, hits: list[FaultEntry]) -> list[dict[str, Any]]:
        """命中项作为证据（source=fault_card，evidence_id 稳定），供 synthesize 引用。"""
        return [
            {
                "evidence_id": f"fc:{self.key}:{self.doc_version}:{f.plan_id}",
                "source": "fault_card",
                "doc_id": self.key,
                "doc_version": self.doc_version,
                "chunk_id": f.plan_id,
                "snippet": f"{f.fault}：{f.first_step}",
                "score": 0.6,
                "status": "ok",
            }
            for f in hits
        ]


class FaultCardsConfig(_Strict):
    version: str
    cards: list[FaultCard] = Field(min_length=1)


def load_fault_cards_config(
    path: str | Path, *, plan_ids: set[str] | None = None
) -> FaultCardsConfig:
    path = Path(path)
    if not path.is_file():
        raise FaultCardsError(f"fault cards config not found: {path}")
    try:
        cfg = FaultCardsConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except (yaml.YAMLError, ValidationError) as exc:
        raise FaultCardsError(f"fault cards config invalid ({path}): {exc}") from exc
    problems = []
    seen: set[str] = set()
    for c in cfg.cards:
        if c.key in seen:
            problems.append(f"duplicate card {c.key}")
        seen.add(c.key)
        if (n := c.tokens()) > MAX_CARD_TOKENS:
            problems.append(f"{c.key}: {n} tokens > {MAX_CARD_TOKENS}")
        if plan_ids is not None:
            for f in c.faults:
                if f.plan_id not in plan_ids:
                    problems.append(f"{c.key}: unknown plan_id {f.plan_id}")
    if problems:
        raise FaultCardsError(f"fault cards config invalid ({path}): " + "; ".join(problems))
    return cfg


class FaultCardLibrary:
    def __init__(self, cfg: FaultCardsConfig):
        self.version = cfg.version
        self._by_key = {c.key: c for c in cfg.cards}

    @classmethod
    def from_yaml(cls, path: str | Path, *, plan_ids: set[str] | None = None) -> FaultCardLibrary:
        return cls(load_fault_cards_config(path, plan_ids=plan_ids))

    @property
    def cards(self) -> list[FaultCard]:
        return list(self._by_key.values())

    def for_scope(self, *, sku: str | None, category: str | None) -> FaultCard | None:
        """confirmed_sku 优先取 SKU 卡，没有则退回品类卡；category_only 只取品类卡。"""
        if sku and sku in self._by_key:
            return self._by_key[sku]
        if category and f"category:{category}" in self._by_key:
            return self._by_key[f"category:{category}"]
        return None


def fit_prompt_budget(
    parts: list[str], *, budget: int = MAX_PROMPT_TOKENS
) -> tuple[list[str], bool]:
    """按顺序保留片段直到累计 token 达上限；返回 (保留的片段, 是否截断)。"""
    used = 0
    kept: list[str] = []
    for p in parts:
        n = estimate_tokens(p)
        if used + n > budget:
            return kept, True
        used += n
        kept.append(p)
    return kept, False
