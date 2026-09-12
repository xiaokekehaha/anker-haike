"""Alembic 环境：业务表（sessions / session_events / session_actions / products / catalog_meta / plans）。

LangGraph checkpoint 表由框架 AsyncPostgresSaver.setup() 自管（checkpoint_migrations），不进本迁移。
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine, pool

from app.db.migrations import sqlalchemy_url

config = context.config


def run_migrations_offline() -> None:
    context.configure(
        url=sqlalchemy_url(), literal_binds=True, dialect_opts={"paramstyle": "named"}
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(sqlalchemy_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
