"""One validated configuration for conversational context and derived memory."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.model_tasks import KNOWN_TASKS, OPTIONAL_TASKS
from app.settings import CONFIG_DIR


class ConversationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    recent_turns: int = Field(default=6, ge=1)
    max_input_tokens: int = Field(default=8000, ge=1024)
    input_budgets: dict[str, Annotated[int, Field(ge=1024)]] = Field(default_factory=dict)
    token_estimate_margin: float = Field(default=1.25, ge=1)
    history_page_entries: int = Field(default=200, ge=12)
    summary_after_turns: int = Field(default=12, ge=6)
    summary_max_tokens: int = Field(default=1200, ge=100)
    summary_trigger_ratio: float = Field(default=0.6, gt=0, le=1)

    @field_validator("input_budgets")
    @classmethod
    def known_budget_tasks(cls, budgets: dict[str, int]) -> dict[str, int]:
        unknown = budgets.keys() - set(KNOWN_TASKS) - set(OPTIONAL_TASKS)
        if unknown:
            raise ValueError(f"unknown context budget tasks: {sorted(unknown)}")
        return budgets

    def input_budget(self, task: str | None = None) -> int:
        return self.input_budgets.get(task, self.max_input_tokens) if task else self.max_input_tokens


@lru_cache(maxsize=1)
def conversation_config() -> ConversationConfig:
    path = Path(
        os.environ.get("CONVERSATION_CONFIG_PATH")
        or CONFIG_DIR / "conversation.yaml"
    )
    return ConversationConfig.model_validate(yaml.safe_load(path.read_text()))
