"""故障卡（票 33，07 §7）：sku_fault_cards 表 + L4 预加载 + 命中判断 + token 预算工具。"""

from app.faultcards.library import (
    FaultCard,
    FaultCardLibrary,
    FaultCardsError,
    estimate_tokens,
    fit_prompt_budget,
    load_fault_cards_config,
)
from app.faultcards.runtime import get_fault_card_library, set_fault_card_library

__all__ = [
    "FaultCard",
    "FaultCardLibrary",
    "FaultCardsError",
    "estimate_tokens",
    "fit_prompt_budget",
    "get_fault_card_library",
    "load_fault_cards_config",
    "set_fault_card_library",
]
