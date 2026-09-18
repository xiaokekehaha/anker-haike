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


class ObservationOption(_Strict):
    """一个有限的检查结果选项。kind=unknown 表示「还没观察完 / 无法判断」，只记录不写成事实。"""

    option_id: str = Field(pattern=r"^[a-z0-9_]+$")
    label: str = Field(min_length=1)
    kind: Literal["finding", "unknown"] = "finding"
    # 用户自由文本回答时用于匹配的说法；label 本身总是可匹配
    phrases: list[str] = Field(default_factory=list)


class InterviewLink(_Strict):
    """已有问诊问题（symptom_taxonomy.discriminators）的 yes / no 回答与观察选项的对应关系。"""

    question: str = Field(min_length=1)
    answers: dict[Literal["yes", "no"], str]


class StepObservation(_Strict):
    """步骤要收集的检查结果：一个问题 + 有限选项。功能是否恢复仍由 feedback 三态表达。"""

    observation_id: str = Field(pattern=r"^[a-z0-9_]+$")
    question: str = Field(min_length=1)
    options: list[ObservationOption] = Field(min_length=2)
    interview_links: list[InterviewLink] = Field(default_factory=list)
    required_resources: list[str] = Field(default_factory=lambda: ["device"])
    requires_execution: bool = True

    @model_validator(mode="after")
    def _options_consistent(self) -> StepObservation:
        ids = [o.option_id for o in self.options]
        dup = {i for i in ids if ids.count(i) > 1}
        if dup:
            raise ValueError(f"observation {self.observation_id}: duplicate option_id {sorted(dup)}")
        if sum(1 for o in self.options if o.kind == "unknown") > 1:
            raise ValueError(f"observation {self.observation_id}: at most one unknown option")
        for link in self.interview_links:
            for target in link.answers.values():
                if target not in ids:
                    raise ValueError(
                        f"observation {self.observation_id}: interview link -> {target!r} is not an option"
                    )
        return self

    def option(self, option_id: str) -> ObservationOption | None:
        return next((o for o in self.options if o.option_id == option_id), None)

    def finding_ids(self) -> list[str]:
        return [o.option_id for o in self.options if o.kind == "finding"]


class ObservationCondition(_Strict):
    """计划适用条件：某个观察的结果必须落在 option_ids 之中。"""

    observation_id: str = Field(pattern=r"^[a-z0-9_]+$")
    option_ids: list[str] = Field(min_length=1)


class PlanStep(_Strict):
    step_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    instruction_src: str = Field(description="evidence:<doc_id>#<chunk_id>")
    expected_result: str = Field(min_length=1)
    caution: str | None = None
    stop_conditions: list[str] = Field(default_factory=list)
    next_on: NextOn
    observations: list[StepObservation] = Field(default_factory=list)
    required_resources: list[str] = Field(default_factory=lambda: ["device"])

    @model_validator(mode="after")
    def _observations_unique(self) -> PlanStep:
        ids = [o.observation_id for o in self.observations]
        dup = {i for i in ids if ids.count(i) > 1}
        if dup:
            raise ValueError(f"step {self.step_id}: duplicate observation_id {sorted(dup)}")
        return self

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
    # 观察门槛：requires 全部满足才可用；excluded 任一命中即排除。未知（未观察）时 requires 视为缺失，不视为不满足。
    requires_observations: list[ObservationCondition] = Field(default_factory=list)
    excluded_by_observations: list[ObservationCondition] = Field(default_factory=list)
    diagnostic_observations: list[StepObservation] = Field(default_factory=list)

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

    def observations(self) -> list[StepObservation]:
        return [*self.diagnostic_observations, *(o for s in self.steps for o in s.observations)]

    def observation_gate(self, known: dict[str, str]) -> tuple[str, list[str]]:
        """按已知观察（observation_id → option_id）判断：("ok"|"excluded"|"missing", 缺失的 observation_id)。

        未观察到的结果不能当作阴性：只会让计划「缺失」，不会让它「排除」或「满足」。
        """
        for cond in self.excluded_by_observations:
            if known.get(cond.observation_id) in cond.option_ids:
                return "excluded", []
        missing = []
        for cond in self.requires_observations:
            value = known.get(cond.observation_id)
            if value is None:
                missing.append(cond.observation_id)
            elif value not in cond.option_ids:
                return "excluded", []
        return ("missing", missing) if missing else ("ok", [])


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
