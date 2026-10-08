"""产品目录与匹配服务（03 §1.3、§3.1；07 §12 L4 缓存）。

匹配规则（不用模型猜型号）：
1. 精确：归一化后的查询等于某 SKU / 名称 / 别名，或查询中出现完整别名（词边界）→ 命中。
2. 模糊：去掉品类词（扫地机、机器人……）后的剩余文本与别名做归一化相似度 ≥ 0.85 → 命中。
3. 同一别名对应多个 SKU（如「S1 Pro」扫地机与吸奶器）→ 全部返回，候选带 in_scope 供前端展示。
4. 命中为空 → 返回 []；调用方（disambiguate）据此追问品类。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import yaml
from haike_contracts.common import ProductCandidate
from pydantic import BaseModel, ConfigDict, Field, ValidationError

FUZZY_THRESHOLD = 0.85


class CatalogError(RuntimeError):
    pass


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CategorySpec(_Strict):
    name: str
    line: str  # 官网产品线：Anker Charging / Anker SOLIX / Anker eufy / Anker soundcore / Anker eufyMake
    in_scope: bool
    keywords: list[str] = Field(default_factory=list)


class ProductSpec(_Strict):
    sku: str = Field(min_length=1)
    name: str = Field(min_length=1)
    category: str
    aliases: list[str] = Field(default_factory=list)
    image: str | None = None


class CatalogConfig(_Strict):
    version: str
    categories: dict[str, CategorySpec]
    products: list[ProductSpec] = Field(min_length=1)


def load_catalog_config(path: str | Path) -> CatalogConfig:
    path = Path(path)
    if not path.is_file():
        raise CatalogError(f"catalog config not found: {path}")
    try:
        cfg = CatalogConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except (yaml.YAMLError, ValidationError) as exc:
        raise CatalogError(f"catalog config invalid ({path}): {exc}") from exc
    problems = []
    seen: set[str] = set()
    for p in cfg.products:
        if p.category not in cfg.categories:
            problems.append(f"{p.sku}: unknown category {p.category!r}")
        if p.sku in seen:
            problems.append(f"duplicate sku {p.sku}")
        seen.add(p.sku)
    if problems:
        raise CatalogError(f"catalog config invalid ({path}): " + "; ".join(problems))
    return cfg


# 订单 SKU = PN + 颜色 / 区域后缀：T8D04121、T2351V11-F、T81701W1
_FULL_SKU = re.compile(r"\b(T8D\d{2}|T\d{4})[0-9A-Z]{2,5}(?:-[A-Z])?\b")

_SEP = re.compile(r"[\s\-_/·.，,。！!？?：:；;（）()\[\]【】「」]+")


def normalize(text: str) -> str:
    """忽略大小写、空格、连字符与标点；中英文混排不分词。"""
    return _SEP.sub("", text).casefold()


def _alias_regex(alias: str) -> re.Pattern[str]:
    """别名作为句中片段：各 token 间允许任意分隔符，两端不能紧贴 ASCII 字母数字（x 不匹配 x10）。"""
    tokens = [re.escape(tok) for tok in _SEP.split(alias.casefold()) if tok]
    body = r"[\s\-_/·.]*".join(tokens)
    return re.compile(rf"(?<![a-z0-9]){body}(?![a-z0-9])")


@dataclass(frozen=True)
class ProductRecord:
    sku: str
    name: str
    category: str
    in_scope: bool
    aliases: tuple[str, ...]
    image: str | None = None

    def to_candidate(self) -> ProductCandidate:
        return ProductCandidate(
            sku=self.sku,
            name=self.name,
            category=self.category,
            image=self.image,
            in_scope=self.in_scope,
        )

    def as_row(self) -> dict[str, Any]:
        return {
            "sku": self.sku,
            "name": self.name,
            "aliases": list(self.aliases),
            "category": self.category,
            "image_url": self.image,
            "in_scope": self.in_scope,
        }


@dataclass
class ProductCatalog:
    """L4 内存缓存：进程内只读；`reload()` 在配置版本变化时整体替换。"""

    version: str
    products: list[ProductRecord]
    categories: dict[str, CategorySpec]
    _alias_index: dict[str, list[ProductRecord]] = field(default_factory=dict, repr=False)
    _alias_patterns: list[tuple[re.Pattern[str], str]] = field(default_factory=list, repr=False)
    _category_words: list[str] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        self._alias_index = {}
        raw_by_key: dict[str, str] = {}
        for p in self.products:
            for key in (p.sku, p.name, *p.aliases):
                nk = normalize(key)
                self._alias_index.setdefault(nk, [])
                raw_by_key.setdefault(nk, key)
                if p not in self._alias_index[nk]:
                    self._alias_index[nk].append(p)
        # 长别名优先匹配，命中区间被占用后短别名（如 X 之于 X10）不再匹配
        self._alias_patterns = [
            (_alias_regex(raw_by_key[nk]), nk)
            for nk in sorted(self._alias_index, key=len, reverse=True)
            if len(nk) >= 2 or not nk.isascii()
        ]
        # 单字符 ASCII 别名（如 X）也要能匹配，只是排在最后
        self._alias_patterns += [
            (_alias_regex(raw_by_key[nk]), nk)
            for nk in self._alias_index
            if len(nk) < 2 and nk.isascii()
        ]
        words = {kw for c in self.categories.values() for kw in c.keywords}
        # 长词优先删除，避免「扫地机器人」先被「扫地机」截断留下「器人」
        self._category_words = sorted(words, key=len, reverse=True)

    # ---- 构建 ----
    @classmethod
    def from_config(cls, cfg: CatalogConfig) -> ProductCatalog:
        products = [
            ProductRecord(
                sku=p.sku,
                name=p.name,
                category=p.category,
                in_scope=cfg.categories[p.category].in_scope,
                aliases=tuple(p.aliases),
                image=p.image,
            )
            for p in cfg.products
        ]
        return cls(cfg.version, products, dict(cfg.categories))

    @classmethod
    def from_yaml(cls, path: str | Path) -> ProductCatalog:
        return cls.from_config(load_catalog_config(path))

    def reload(self, path: str | Path) -> bool:
        """配置版本变更时重载；返回是否发生了替换。"""
        cfg = load_catalog_config(path)
        if cfg.version == self.version:
            return False
        fresh = ProductCatalog.from_config(cfg)
        self.version, self.products, self.categories = (
            fresh.version,
            fresh.products,
            fresh.categories,
        )
        self.__post_init__()
        return True

    # ---- 查询 ----
    def get(self, sku: str) -> ProductRecord | None:
        return next((p for p in self.products if p.sku == sku), None)

    def category_hint(self, text: str) -> str | None:
        """文本里出现某品类关键词 → 该品类（消歧降级 category_only 用）。"""
        norm = normalize(text)
        # 最长关键词优先：「无线充电器」不能被「充电器」抢走，「割草机器人」不能被「机器人」抢走
        best: tuple[int, str] | None = None
        for cat, spec in self.categories.items():
            for kw in spec.keywords:
                k = normalize(kw)
                if k and k in norm and (best is None or len(k) > best[0]):
                    best = (len(k), cat)
        return best[1] if best else None

    def strip_category_words(self, text: str) -> str:
        out = text
        for w in self._category_words:
            out = re.sub(re.escape(w), " ", out, flags=re.IGNORECASE)
        return out.strip()

    def lookup_product(self, text: str, *, limit: int = 5) -> list[ProductCandidate]:
        """型号精确 + 别名模糊匹配，返回候选（含 in_scope）。零命中返回 []。"""
        hits: list[ProductRecord] = []

        def add(records: list[ProductRecord]) -> None:
            for r in records:
                if r not in hits:
                    hits.append(r)

        q_full = normalize(text)
        if not q_full:
            return []
        # 0) 完整订单 SKU（T8D04121、T2351V11-F）按 PN 前缀归一
        for match in _FULL_SKU.finditer(text.upper()):
            add(self._alias_index.get(normalize(match.group(1)), []))
        # 1) 整句就是一个型号 / 别名
        add(self._alias_index.get(q_full, []))
        # 2) 别名作为完整片段出现在句中；长别名先占位，被占用区间内的短别名不再计
        if not hits:
            lowered = text.casefold()
            taken: list[tuple[int, int]] = []
            for pattern, key in self._alias_patterns:
                for m in pattern.finditer(lowered):
                    if any(m.start() < e and m.end() > s for s, e in taken):
                        continue
                    taken.append((m.start(), m.end()))
                    add(self._alias_index[key])
        # 3) 去掉品类词后的剩余文本与别名做归一化模糊匹配（容忍少量错拼）
        if not hits:
            rest = normalize(self.strip_category_words(text))
            if len(rest) >= 2:
                best = 0.0
                for key in self._alias_index:
                    ratio = SequenceMatcher(None, rest, key).ratio()
                    if ratio >= FUZZY_THRESHOLD and ratio >= best:
                        if ratio > best:
                            hits.clear()
                        best = ratio
                        add(self._alias_index[key])
        # 范围内优先、再按名称，稳定排序
        hits.sort(key=lambda r: (not r.in_scope, r.name))
        return [r.to_candidate() for r in hits[:limit]]
