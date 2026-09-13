"""管理员观测台的 analytics schema（docs/planning/2026-09-13_admin-observability-console）。

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-13

独立 schema：生命周期与业务表解耦——业务会话 TTL 到点整体删除（票 48），analytics 事实仍在。
黑客松范围（02_hackathon-scope.md）：5 张事实表 + cases；不做 messages / rule_hits / daily_rollups / 分区。
不建外键：analytics 行比原会话活得久。
"""

from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

SCHEMA = "analytics"

STATEMENTS = [
    f"create schema if not exists {SCHEMA}",
    # ---- 会话事实：一会话一行，每个 run 结束时 upsert ----
    f"""create table if not exists {SCHEMA}.session_facts (
        session_id        text primary key,
        lane              text,
        created_at        timestamptz not null default now(),
        last_run_at       timestamptz not null default now(),
        runs              integer not null default 0,
        user_messages     integer not null default 0,
        first_question    text,
        product_state     text,
        sku               text,
        category          text,
        emotion_level     text,
        fault_plan_ids    text[] not null default '{{}}',
        steps_executed    integer not null default 0,
        clarifications    integer not null default 0,
        knowledge_status  text,
        receipt_status    text,
        outcome           text not null default 'in_progress',
        outcome_reason    text,
        outcome_at        timestamptz,
        total_latency_ms  integer not null default 0,
        model_calls       integer not null default 0,
        tokens_in         integer not null default 0,
        tokens_out        integer not null default 0,
        raw_available_until timestamptz
    )""",
    f"create index if not exists session_facts_created_idx on {SCHEMA}.session_facts (created_at desc)",
    f"create index if not exists session_facts_outcome_idx on {SCHEMA}.session_facts (outcome, created_at desc)",
    f"create index if not exists session_facts_product_idx on {SCHEMA}.session_facts (category, sku)",
    # ---- run 事实 ----
    f"""create table if not exists {SCHEMA}.run_facts (
        run_id           text not null,
        session_id       text not null,
        seq_no           integer not null default 1,
        started_at       timestamptz not null default now(),
        ended_at         timestamptz,
        duration_ms      integer,
        entry            text,
        stage_from       text,
        stage_to         text,
        done_reason      text,
        error_code       text,
        first_visible_ms integer,
        card_ready_ms    integer,
        card_kind        text,
        model_calls      integer not null default 0,
        tokens_in        integer not null default 0,
        tokens_out       integer not null default 0,
        node_count       integer not null default 0,
        -- run_id 单独不够唯一：历史 / 测试数据里存在跨会话复用的 run_id
        primary key (session_id, run_id)
    )""",
    f"create index if not exists run_facts_seq_idx on {SCHEMA}.run_facts (session_id, seq_no)",
    f"create index if not exists run_facts_started_idx on {SCHEMA}.run_facts (started_at desc)",
    # ---- 节点执行：DAG 路径与聚合流量的原材料 ----
    f"""create table if not exists {SCHEMA}.node_runs (
        id         bigint generated always as identity primary key,
        session_id text not null,
        run_id     text not null,
        idx        integer not null,
        node       text not null,
        prev_node  text,
        started_at timestamptz not null default now(),
        duration_ms integer,
        status     text not null default 'ok',
        summary    jsonb
    )""",
    f"create unique index if not exists node_runs_run_idx on {SCHEMA}.node_runs (session_id, run_id, idx)",
    f"create index if not exists node_runs_session_idx on {SCHEMA}.node_runs (session_id, run_id, idx)",
    f"create index if not exists node_runs_node_idx on {SCHEMA}.node_runs (node, started_at desc)",
    f"create index if not exists node_runs_edge_idx on {SCHEMA}.node_runs (prev_node, node)",
    # ---- 模型调用（不存 prompt 正文；prompt 级排查去 Langfuse / JSONL）----
    f"""create table if not exists {SCHEMA}.model_calls (
        id            bigint generated always as identity primary key,
        session_id    text,
        run_id        text,
        node          text,
        task          text not null,
        model_used    text,
        lane          text,
        status        text not null,
        attempts      integer not null default 1,
        fallback_used boolean not null default false,
        stream        boolean not null default false,
        latency_ms    integer,
        tokens_in     integer,
        tokens_out    integer,
        error_type    text,
        created_at    timestamptz not null default now()
    )""",
    f"create index if not exists model_calls_created_idx on {SCHEMA}.model_calls (created_at desc)",
    f"create index if not exists model_calls_task_idx on {SCHEMA}.model_calls (task, model_used, created_at desc)",
    f"create index if not exists model_calls_run_idx on {SCHEMA}.model_calls (session_id, run_id)",
    # 幂等：同一次调用（同 run、同 task、同微秒）只留一行，日志回填可反复跑。
    # nulls not distinct：会话外的调用（探活 / 评测）session_id 为空也能去重。
    f"""create unique index if not exists model_calls_dedup_idx
        on {SCHEMA}.model_calls (session_id, run_id, task, created_at) nulls not distinct""",
    # ---- 检索 ----
    f"""create table if not exists {SCHEMA}.retrieval_calls (
        id            bigint generated always as identity primary key,
        session_id    text,
        run_id        text,
        node          text,
        round         integer,
        kb            text,
        product_state text,
        sku           text,
        category      text,
        status        text not null,
        allowed_count integer,
        hits          integer,
        top_score     real,
        latency_ms    integer,
        query         text,
        created_at    timestamptz not null default now()
    )""",
    f"create index if not exists retrieval_calls_created_idx on {SCHEMA}.retrieval_calls (created_at desc)",
    f"create index if not exists retrieval_calls_run_idx on {SCHEMA}.retrieval_calls (session_id, run_id)",
    f"create index if not exists retrieval_calls_status_idx on {SCHEMA}.retrieval_calls (status, created_at desc)",
    f"""create unique index if not exists retrieval_calls_dedup_idx
        on {SCHEMA}.retrieval_calls (session_id, run_id, kb, round, created_at) nulls not distinct""",
    # ---- 案例库与标注（好案例沉淀 / 坏案例复盘）----
    f"""create table if not exists {SCHEMA}.cases (
        case_id     text primary key,
        session_id  text not null,
        run_id      text,
        verdict     text not null,
        reason_tags text[] not null default '{{}}',
        note        text,
        labeled_by  text,
        labeled_at  timestamptz not null default now(),
        status      text not null default 'open',
        exported_to jsonb,
        fixed_in    text
    )""",
    f"create index if not exists cases_verdict_idx on {SCHEMA}.cases (verdict, status, labeled_at desc)",
    f"create unique index if not exists cases_session_idx on {SCHEMA}.cases (session_id)",
]

TABLES = [
    "session_facts",
    "run_facts",
    "node_runs",
    "model_calls",
    "retrieval_calls",
    "cases",
]


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"drop table if exists {SCHEMA}.{table}")
    op.execute(f"drop schema if exists {SCHEMA}")
