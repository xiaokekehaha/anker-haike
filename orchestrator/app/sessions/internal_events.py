"""Internal event schema. Never exported as a public ServerEvent."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StateCommitted(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["state_committed"] = "state_committed"
    visibility: Literal["internal"] = "internal"
    event_id: str
    recorded_at: str
    input_id: str
    checkpoint_id: str
    version: int = Field(ge=1)
    decision: dict


StoredInternalEvent = StateCommitted
