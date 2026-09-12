"""会话期图片表 session_images（票 29；03 §3.1、07 §9）。

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-12

IF NOT EXISTS：收编已由 PostgresImageStore.setup() 建好的库。字节只存数据库，编排服务本地不落盘；1 小时后由清理任务删除。
"""

from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

STATEMENTS = [
    """create table if not exists session_images (
        image_id   text primary key,
        session_id text not null,
        purpose    text not null,
        sha256     text not null,
        mime       text not null,
        size       integer not null,
        bytes      bytea not null,
        created_at timestamptz not null default now()
    )""",
    "create index if not exists session_images_session_idx on session_images(session_id)",
    "create index if not exists session_images_created_idx on session_images(created_at)",
]

BUSINESS_TABLES = ["session_images"]


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for table in reversed(BUSINESS_TABLES):
        op.execute(f"drop table if exists {table}")
