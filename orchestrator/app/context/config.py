"""One validated configuration for conversational context and derived memory."""

import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class ConversationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    recent_turns: int = Field(default=6, ge=1)
    max_input_tokens: int = Field(default=8000, ge=1024)
    token_estimate_margin: float = Field(default=1.25, ge=1)
    history_page_entries: int = Field(default=200, ge=12)
    summary_after_turns: int = Field(default=12, ge=6)
    summary_max_tokens: int = Field(default=1200, ge=100)


@lru_cache(maxsize=1)
def conversation_config() -> ConversationConfig:
    path = Path(
        os.environ.get("CONVERSATION_CONFIG_PATH")
        or Path(__file__).resolve().parents[3] / "config/conversation.yaml"
    )
    return ConversationConfig.model_validate(yaml.safe_load(path.read_text()))
