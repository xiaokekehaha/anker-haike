from datetime import date
from typing import Literal

from haike_contracts.common import Clause, PolicyDecision, RemedyDecision, Strict
from pydantic import Field

# 真实保修期是「品类 × 系列 × 部件」三级，不是品类一级：同品类不同系列能差一倍
# （Anker 移动电源 Prime 24 个月、其余 18 个月），同一台设备的不同部件也能不同
# （eufy 智能锁整机 18 个月、机械部件 36 个月；吸奶器整机 12 个月、配件 3 个月）。
PartClass = Literal["main_unit", "battery", "mechanical", "accessory", "cable"]


class PolicyInput(Strict):
    sku: str | None = None
    category: str | None = None  # 未知品类匹配不到任何政策 → no_policy_matched 转人工，不默认成某个品类
    # 系列名（Prime / MagGo / PowerLine III …）。留空时引擎从 sku 与目录里的产品名反查；
    # 用户自己说得出系列名时也可以直接给，不必先确认到 SKU。
    series: str | None = None
    part_class: PartClass = "main_unit"
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


__all__ = ["Clause", "PartClass", "PolicyDecision", "PolicyInput", "RemedyDecision"]
