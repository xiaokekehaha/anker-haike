"""config/bakeoff.yaml：门槛、价目、重复次数。"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.settings import REPO_ROOT

DEFAULT_PATH = REPO_ROOT / "config" / "bakeoff.yaml"
TEXT_TASKS = (
    "intake",
    "disambiguate.clarify",
    "diagnose.synthesize",
    "guide.step",
    "reply.stream",
    "escalate.summary",
    "query.rewrite",
)
VISION_TASKS = ("diagnose.vision", "warranty.receipt_ocr")
ALL_TASKS = (*TEXT_TASKS, *VISION_TASKS)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Price(_Strict):
    input: float = Field(ge=0)
    output: float = Field(ge=0)
    currency: Literal["CNY", "USD"] = "CNY"
    note: str | None = None


class PrimaryThreshold(_Strict):
    schema_pass: float = 0.95
    accuracy_text: float = 0.90
    accuracy_vision: float = 0.80
    accuracy_receipt: float = 0.85


class FallbackThreshold(_Strict):
    schema_pass: float = 0.90
    accuracy_delta_max: float = 0.10
    latency_ratio_max: float = 1.5


class Thresholds(_Strict):
    primary: PrimaryThreshold = Field(default_factory=PrimaryThreshold)
    fallback: FallbackThreshold = Field(default_factory=FallbackThreshold)
    latency_p50_ms: dict[str, int] = Field(default_factory=dict)
    conversation_cost_cny_max: float = 0.5


class BakeoffConfig(_Strict):
    version: str
    repeats: int = Field(default=3, ge=1)
    concurrency: int = Field(default=4, ge=1)
    fx_cny_per_usd: float = Field(default=7.2, gt=0)
    thresholds: Thresholds = Field(default_factory=Thresholds)
    prices: dict[str, Price] = Field(default_factory=dict)
    # 一次 A1 对话按 task 的调用次数，用于「一次完整对话成本」（§3.8 成本门槛）
    conversation_profile: dict[str, int] = Field(default_factory=dict)

    def accuracy_threshold(self, task: str) -> float:
        p = self.thresholds.primary
        if task == "warranty.receipt_ocr":
            return p.accuracy_receipt
        if task == "diagnose.vision":
            return p.accuracy_vision
        return p.accuracy_text

    def price_cny(self, alias: str) -> tuple[float, float] | None:
        """每 1M token 的（输入, 输出）人民币价；未登记返回 None。"""
        p = self.prices.get(alias)
        if p is None:
            return None
        k = self.fx_cny_per_usd if p.currency == "USD" else 1.0
        return p.input * k, p.output * k


def load_bakeoff_config(path: str | Path | None = None) -> BakeoffConfig:
    p = Path(path) if path else DEFAULT_PATH
    return BakeoffConfig.model_validate(yaml.safe_load(p.read_text(encoding="utf-8")))
