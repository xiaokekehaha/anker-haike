"""analytics 事实行的类型定义，与 migrations/versions/0004_analytics.py 一一对应。

字段命名与列名相同；store 按 COLUMNS 顺序取值，改列必须同时改这里（test_analytics 有比对）。
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import Any

SCHEMA = "analytics"


class Row:
    """所有事实行的基类：按 dataclass 字段顺序给出列名与值。"""

    @classmethod
    def columns(cls) -> tuple[str, ...]:
        return tuple(f.name for f in fields(cls))  # type: ignore[arg-type]

    def values(self) -> tuple[Any, ...]:
        return tuple(getattr(self, name) for name in self.columns())


@dataclass
class SessionFacts(Row):
    """一会话一行；每个 run 结束时按 session_id upsert（created_at 保持首次值）。"""

    session_id: str
    lane: str | None = None
    created_at: datetime | None = None
    last_run_at: datetime | None = None
    runs: int = 0
    user_messages: int = 0
    first_question: str | None = None
    product_state: str | None = None
    sku: str | None = None
    category: str | None = None
    emotion_level: str | None = None
    fault_plan_ids: list[str] = field(default_factory=list)
    steps_executed: int = 0
    clarifications: int = 0
    knowledge_status: str | None = None
    receipt_status: str | None = None
    outcome: str = "in_progress"
    outcome_reason: str | None = None
    outcome_at: datetime | None = None
    total_latency_ms: int = 0
    model_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    raw_available_until: datetime | None = None


@dataclass
class RunFacts(Row):
    run_id: str
    session_id: str
    seq_no: int = 1
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_ms: int | None = None
    entry: str | None = None
    stage_from: str | None = None
    stage_to: str | None = None
    done_reason: str | None = None
    error_code: str | None = None
    first_visible_ms: int | None = None
    card_ready_ms: int | None = None
    card_kind: str | None = None
    model_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    node_count: int = 0


@dataclass
class NodeRun(Row):
    """一次节点执行。duration_ms 为「上一个节点产出到本节点产出」的间隔（见 runner 注释）。"""

    session_id: str
    run_id: str
    idx: int
    node: str
    prev_node: str | None = None
    started_at: datetime | None = None
    duration_ms: int | None = None
    status: str = "ok"
    summary: dict[str, Any] | None = None


@dataclass
class ModelCall(Row):
    task: str
    session_id: str | None = None
    run_id: str | None = None
    node: str | None = None
    model_used: str | None = None
    lane: str | None = None
    status: str = "ok"
    attempts: int = 1
    fallback_used: bool = False
    stream: bool = False
    latency_ms: int | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    error_type: str | None = None
    created_at: datetime | None = None


@dataclass
class RetrievalCall(Row):
    status: str
    session_id: str | None = None
    run_id: str | None = None
    node: str | None = None
    round: int | None = None
    kb: str | None = None
    product_state: str | None = None
    sku: str | None = None
    category: str | None = None
    allowed_count: int | None = None
    hits: int | None = None
    top_score: float | None = None
    latency_ms: int | None = None
    query: str | None = None
    created_at: datetime | None = None


@dataclass
class Case(Row):
    case_id: str
    session_id: str
    run_id: str | None = None
    verdict: str = "review"
    reason_tags: list[str] = field(default_factory=list)
    note: str | None = None
    labeled_by: str | None = None
    labeled_at: datetime | None = None
    status: str = "open"
    exported_to: dict[str, Any] | None = None
    fixed_in: str | None = None


# sink 的写操作类型 → 行类；键即 analytics 表名（单数形式的 node_run 等除外，见 TABLE_OF）
ROW_TYPES: dict[str, type[Row]] = {
    "session_facts": SessionFacts,
    "run_facts": RunFacts,
    "node_run": NodeRun,
    "model_call": ModelCall,
    "retrieval_call": RetrievalCall,
    "case": Case,
}

TABLE_OF: dict[str, str] = {
    "session_facts": "session_facts",
    "run_facts": "run_facts",
    "node_run": "node_runs",
    "model_call": "model_calls",
    "retrieval_call": "retrieval_calls",
    "case": "cases",
}

# upsert 的冲突键；不在表内的 kind 走纯 insert
CONFLICT_KEY: dict[str, str] = {
    "session_facts": "session_id",
    # 日志回填可反复跑：重复的调用行直接忽略（见 INSERT_ONLY）
    "model_call": "session_id, run_id, task, created_at",
    "retrieval_call": "session_id, run_id, kb, round, created_at",
    "run_facts": "session_id, run_id",
    "node_run": "session_id, run_id, idx",
    "case": "case_id",
}

# 冲突时丢弃而不是覆盖：调用事实是不可变的历史，重复只可能来自重跑回填
INSERT_ONLY: set[str] = {"model_call", "retrieval_call"}

# upsert 时不覆盖的列（保留首次写入值）
KEEP_ON_CONFLICT: dict[str, set[str]] = {
    "session_facts": {"created_at"},
    "run_facts": {"started_at"},
    "node_run": set(),
    "case": {"labeled_at"},
}
