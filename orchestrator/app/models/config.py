"""models.yaml 的结构、加载与一致性校验（model-selection §3.7）。

启动时任何缺失或不一致都要报出具体项：文件、YAML 语法、字段类型、别名 / 厂商引用、视觉能力、
默认通道覆盖、embedding / rerank 别名。
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

Sdk = Literal["openai", "anthropic", "google_genai"]
Lane = Literal["domestic", "overseas"]
Effort = Literal["low", "medium", "high"]
Structured = Literal["native", "json_object", "none"]
ModelKind = Literal["chat", "embedding", "rerank"]

# 业务节点会用到的 task 名；默认通道必须为每一个给出链（model-selection §3.7）
KNOWN_TASKS: tuple[str, ...] = (
    "intake",
    "disambiguate.clarify",
    "diagnose.vision",
    "diagnose.synthesize",
    "guide.step",
    "reply.stream",
    "escalate.summary",
    "warranty.receipt_ocr",
)
# 可选增强任务：配置里可以缺链（缺时对应功能按不可用处理），不参与「默认通道必须覆盖」校验
OPTIONAL_TASKS: tuple[str, ...] = ("query.rewrite",)

UNSET_MODEL_ID = "TBD"


class ConfigError(RuntimeError):
    """配置缺失或不一致；message 列出全部问题，一次修完。"""

    def __init__(self, path: str | Path, problems: list[str]):
        self.path = str(path)
        self.problems = problems
        bullet = "\n".join(f"  - {p}" for p in problems)
        super().__init__(f"models config invalid ({self.path}):\n{bullet}")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProviderSpec(_Strict):
    sdk: Sdk
    api_key_env: str = Field(min_length=1)
    base_url: str | None = None
    lane: Lane = "domestic"
    """厂商所属通道；domestic 链尾接 overseas 别名即跨通道降级，路由表据此标注。"""


class ModelSpec(_Strict):
    provider: str
    id: str = Field(min_length=1)
    kind: ModelKind = "chat"
    vision: bool = False
    structured: Structured = "none"
    max_images: int | None = Field(default=None, ge=1)
    timeout_s: float = Field(default=20, gt=0)
    dim: int | None = Field(default=None, ge=1)

    @property
    def id_pending(self) -> bool:
        return self.id.upper() == UNSET_MODEL_ID


class TaskRoute(_Strict):
    chain: list[str] = Field(min_length=1)
    effort: Effort = "low"
    max_tokens: int | None = Field(default=None, ge=1)
    needs_vision: bool = False
    stream: bool = False


class RetrySpec(_Strict):
    same_model_max: int = Field(default=1, ge=0)
    rate_limit_max: int = Field(default=3, ge=0)
    """429 专用：同模型最多重试次数，退避 1 / 2 / 4 s + 抖动（07 §13）。"""
    chain_max: int = Field(default=3, ge=1)
    sdk_max_retries: int = Field(default=0, ge=0)


class ConcurrencySpec(_Strict):
    max_in_flight: int = Field(default=50, ge=1)
    """全局同时进行的模型调用上限，满则立即拒绝（07 §13）。"""


class ModelsConfig(_Strict):
    version: str
    default_lane: str
    providers: dict[str, ProviderSpec]
    models: dict[str, ModelSpec]
    lanes: dict[str, dict[str, TaskRoute]]
    retry: RetrySpec = Field(default_factory=RetrySpec)
    concurrency: ConcurrencySpec = Field(default_factory=ConcurrencySpec)

    # ---- 查询 ----
    def route(self, task: str, lane: str | None = None) -> TaskRoute:
        lane = lane or self.default_lane
        try:
            return self.lanes[lane][task]
        except KeyError as exc:
            raise KeyError(f"no route for task {task!r} in lane {lane!r}") from exc

    def provider_of(self, alias: str) -> ProviderSpec:
        return self.providers[self.models[alias].provider]

    def lane_of(self, alias: str) -> Lane:
        return self.provider_of(alias).lane

    def aliases_of_kind(self, kind: ModelKind) -> list[str]:
        return [a for a, m in self.models.items() if m.kind == kind]

    # ---- 一致性 ----
    def consistency_problems(self) -> list[str]:
        problems: list[str] = []
        if self.default_lane not in self.lanes:
            problems.append(f"default_lane {self.default_lane!r} not in lanes {sorted(self.lanes)}")
        for alias, m in self.models.items():
            if m.provider not in self.providers:
                problems.append(f"models.{alias}.provider {m.provider!r} not in providers")
        for lane, tasks in self.lanes.items():
            for task, route in tasks.items():
                where = f"lanes.{lane}.{task}"
                for alias in route.chain:
                    m = self.models.get(alias)
                    if m is None:
                        problems.append(f"{where}.chain: unknown alias {alias!r}")
                        continue
                    if m.kind != "chat":
                        problems.append(f"{where}.chain: {alias!r} is {m.kind}, not a chat model")
                    if route.needs_vision and not m.vision:
                        problems.append(f"{where}: needs_vision but {alias!r} has vision: false")
                if len(route.chain) > self.retry.chain_max:
                    problems.append(
                        f"{where}.chain has {len(route.chain)} models, "
                        f"retry.chain_max is {self.retry.chain_max}"
                    )
        default_tasks = self.lanes.get(self.default_lane, {})
        all_tasks = set(KNOWN_TASKS)
        for tasks in self.lanes.values():
            all_tasks.update(tasks)
        for task in sorted(all_tasks - set(default_tasks) - set(OPTIONAL_TASKS)):
            problems.append(f"lanes.{self.default_lane}: task {task!r} has no chain")
        for kind in ("embedding", "rerank"):
            if not self.aliases_of_kind(kind):  # type: ignore[arg-type]
                problems.append(f"models: no alias with kind: {kind}")
        return problems


def _format_validation_error(exc: ValidationError) -> list[str]:
    out = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "<root>"
        out.append(f"{loc}: {err['msg']}")
    return out


def load_models_config(path: str | Path, lane_override: str | None = None) -> ModelsConfig:
    """读取并校验；`lane_override`（MODEL_LANE）非空时替换 default_lane，且必须是已定义通道。"""
    path = Path(path)
    if not path.is_file():
        raise ConfigError(path, ["file not found"])
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        raise ConfigError(path, [f"invalid yaml{where}: {getattr(exc, 'problem', exc)}"]) from exc
    if not isinstance(raw, dict):
        raise ConfigError(path, ["top level must be a mapping"])
    try:
        cfg = ModelsConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(path, _format_validation_error(exc)) from exc
    if lane_override:
        if lane_override not in cfg.lanes:
            raise ConfigError(
                path, [f"MODEL_LANE={lane_override!r} is not a defined lane {sorted(cfg.lanes)}"]
            )
        cfg = cfg.model_copy(update={"default_lane": lane_override})
    problems = cfg.consistency_problems()
    if problems:
        raise ConfigError(path, problems)
    return cfg
