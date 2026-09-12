"""数据库运维（票 47）：Alembic 迁移与启动期版本校验。"""

from app.db.migrations import (
    SchemaOutOfDate,
    current_revision,
    ensure_schema,
    head_revision,
    sqlalchemy_url,
    upgrade_to_head,
)

__all__ = [
    "SchemaOutOfDate",
    "current_revision",
    "ensure_schema",
    "head_revision",
    "sqlalchemy_url",
    "upgrade_to_head",
]
