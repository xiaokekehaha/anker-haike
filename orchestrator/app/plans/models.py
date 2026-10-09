"""计划模型（09 §3.1）。JSON Schema 供 diagnose.synthesize 的 plan_id 枚举与校验使用。"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TERMINALS = ("DONE", "EXHAUSTED")
EVIDENCE_REF = re.compile(r"^evidence:(?P<doc_id>[A-Za-z0-9_\-.]+)#(?P<chunk_id>[A-Za-z0-9_\-.]+)$")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NextOn(_Strict):
    solved: str
    not_solved: str
    cannot_do: str


StepKind = Literal["action", "question", "statement", "material_request", "handoff"]


class PlanStep(_Strict):
    step_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    instruction_src: str = Field(description="evidence:<doc_id>#<chunk_id>")
    expected_result: str = Field(min_length=1)
    caution: str | None = None
    stop_conditions: list[str] = Field(default_factory=list)
    next_on: NextOn
    required_resources: list[str] = Field(default_factory=lambda: ["device"])
    # 2026-10-09 第二批：段落对用户意味着什么。question 带 options，按 branches（选项 → step_id）分支，
    # 没列出的选项走 next_on.not_solved；statement / material_request 不计已操作；handoff 不出卡。
    kind: StepKind = "action"
    options: list[str] = Field(default_factory=list)
    branches: dict[str, str] = Field(default_factory=dict)

    @field_validator("instruction_src")
    @classmethod
    def _ref_format(cls, v: str) -> str:
        if not EVIDENCE_REF.match(v):
            raise ValueError("instruction_src must look like evidence:<doc_id>#<chunk_id>")
        return v

    @property
    def evidence_key(self) -> str:
        return self.instruction_src.removeprefix("evidence:")


class AppliesTo(_Strict):
    scope: Literal["category_generic", "sku"]
    category: str
    sku_list: list[str] = Field(default_factory=list)
    excluded_skus: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sku_list_when_sku(self) -> AppliesTo:
        if self.scope == "sku" and not self.sku_list:
            raise ValueError("applies_to.scope=sku requires sku_list")
        return self


class Plan(_Strict):
    plan_id: str = Field(pattern=r"^[a-z0-9_]+$")
    version: int = Field(ge=1)
    fault: str = Field(min_length=1)
    applies_to: AppliesTo
    symptom_codes: list[str] = Field(default_factory=list)
    steps: list[PlanStep] = Field(min_length=1)

    @model_validator(mode="after")
    def _steps_consistent(self) -> Plan:
        ids = [s.step_id for s in self.steps]
        dup = {i for i in ids if ids.count(i) > 1}
        if dup:
            raise ValueError(f"duplicate step_id {sorted(dup)}")
        allowed = set(ids) | set(TERMINALS)
        for s in self.steps:
            for fb, target in s.next_on.model_dump().items():
                if target not in allowed:
                    raise ValueError(
                        f"step {s.step_id}.next_on.{fb} -> {target!r} is not a step_id of this plan nor DONE/EXHAUSTED"
                    )
                if target == s.step_id:
                    raise ValueError(f"step {s.step_id}.next_on.{fb} points to itself")
            for option, target in s.branches.items():
                if target not in allowed or target == s.step_id:
                    raise ValueError(f"step {s.step_id}.branches[{option!r}] -> {target!r} is not another step_id of this plan")
                if option not in s.options:
                    raise ValueError(f"step {s.step_id}.branches[{option!r}] is not one of its options")
        return self

    def step(self, step_id: str) -> PlanStep:
        return next(s for s in self.steps if s.step_id == step_id)

    def first_step(self) -> PlanStep:
        return self.steps[0]

    def next_step_id(
        self, step_id: str, feedback: Literal["solved", "not_solved", "cannot_do"]
    ) -> str:
        """规则推进：返回下一 step_id 或 DONE / EXHAUSTED（09 §3.2）。"""
        return getattr(self.step(step_id).next_on, feedback)

    def applies(self, *, category: str, sku: str | None = None) -> bool:
        if self.applies_to.category != category or sku in self.applies_to.excluded_skus:
            return False
        return self.applies_to.scope == "category_generic" or (
            sku is not None and sku in self.applies_to.sku_list
        )


class EvidenceEntry(_Strict):
    source: str
    doc_version: str
    snippet: str


class PlansConfig(_Strict):
    version: str
    evidence: dict[str, EvidenceEntry]
    plans: list[Plan] = Field(min_length=1)


def plan_json_schema(plan_ids: list[str] | None = None) -> dict:
    """计划模型 Schema；给定 plan_ids 时把 plan_id 收窄为枚举（synthesize 的允许集合）。"""
    schema = Plan.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "TroubleshootPlan"
    if plan_ids is not None:
        schema["properties"]["plan_id"] = {"type": "string", "enum": sorted(plan_ids)}
    return schema
