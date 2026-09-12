"""基线：票 05/07/22 的会话表与票 19/31 的目录 / 计划表。

Revision ID: 0001
Revises: None
Create Date: 2026-09-12

全部用 IF NOT EXISTS：既能从空库建到当前版本，也能「收编」在迁移引入之前由各 store.setup() 建好的库。
此后所有业务表结构变更只能通过新迁移，不得再改 store 里的 DDL 字符串。
"""

from __future__ import annotations

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

STATEMENTS = [
    # ---- 会话骨架（08 §2；票 05 / 07 / 22）----
    """create table if not exists sessions (
        session_id         text primary key,
        version            integer not null default 0,
        stage              text not null default 'intake',
        active_run_id      text,
        pending_input_json jsonb,
        created_at         timestamptz not null default now(),
        updated_at         timestamptz not null default now()
    )""",
    """create table if not exists session_events (
        session_id  text not null,
        seq         integer not null,
        run_id      text not null,
        event_json  jsonb not null,
        created_at  timestamptz not null default now(),
        primary key (session_id, seq)
    )""",
    "create index if not exists session_events_run_idx on session_events(session_id, run_id, seq)",
    "alter table session_events drop constraint if exists session_events_session_id_fkey",
    """create table if not exists session_actions (
        session_id  text not null,
        action_id   text not null,
        result_json jsonb,
        created_at  timestamptz not null default now(),
        primary key (session_id, action_id)
    )""",
    # ---- 产品目录（票 19）----
    """create table if not exists products (
        sku        text primary key,
        name       text not null,
        aliases    text[] not null default '{}',
        category   text not null,
        image_url  text,
        in_scope   boolean not null default true,
        updated_at timestamptz not null default now()
    )""",
    """create table if not exists catalog_meta (
        key   text primary key,
        value text not null
    )""",
    # ---- 预写排障计划（票 31）----
    """create table if not exists plans (
        plan_id    text not null,
        version    integer not null,
        fault      text not null,
        applies_to jsonb not null,
        steps      jsonb not null,
        updated_at timestamptz not null default now(),
        primary key (plan_id, version)
    )""",
]

BUSINESS_TABLES = [
    "sessions",
    "session_events",
    "session_actions",
    "products",
    "catalog_meta",
    "plans",
]


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for table in reversed(BUSINESS_TABLES):
        op.execute(f"drop table if exists {table}")
