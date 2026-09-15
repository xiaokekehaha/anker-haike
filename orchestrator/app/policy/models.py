from datetime import date
from typing import Literal

from haike_contracts.common import Clause, PolicyDecision, RemedyDecision, Strict
from pydantic import Field


class PolicyInput(Strict):
    sku: str | None = None
    category: str = "robot_vacuum"
    region_purchase: str | None = None
    region_use: str | None = None
    channel: str | None = None
    platform: str | None = None
    purchase_date: date | None = None
    receipt_status: str = "not_collected"
    dealer_authorized: bool | None = None
    fault_class: Literal["quality", "user_damage", "safety", "unknown"] = "unknown"
    prior_remedies: list[str] = Field(default_factory=list)
    today: date


__all__ = ["Clause", "PolicyDecision", "PolicyInput", "RemedyDecision"]
