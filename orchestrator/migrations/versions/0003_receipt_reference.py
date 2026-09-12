"""票 41：演示订单与经销商名录。

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

STATEMENTS = [
    """create table if not exists orders_mock (
        order_no text primary key,
        sku text not null,
        channel text not null,
        purchase_date date not null
    )""",
    """create table if not exists dealers (
        name text primary key,
        region text not null,
        authorized boolean not null,
        warranty_note text not null default ''
    )""",
]
BUSINESS_TABLES = ["orders_mock", "dealers"]


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for table in reversed(BUSINESS_TABLES):
        op.execute(f"drop table if exists {table}")
