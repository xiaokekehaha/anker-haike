"""Organizer data replaces the self-made demo backend.

Orders and the dealer directory are read-only organizer data loaded from data/official;
only service orders are written. The US policy engine is gone, so a case keeps the
warranty decision instead of a policy decision, and executions no longer carry a policy
version. No data migration: every row in the dropped tables referred to invented orders.
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

STATEMENTS = [
    "drop table if exists service_orders_mock",
    "drop table if exists shipments_mock",
    "drop table if exists orders_mock",
    "drop table if exists dealers",
    """create table service_orders(
        service_order_no text primary key,
        type text not null check(type in ('replace','refund','reship','carrier_investigation')),
        order_no text, sku text, reason text not null,
        evidence jsonb not null default '{}',
        status text not null default 'submitted',
        client_ref text not null unique,
        created_at timestamptz not null default now())""",
    "alter table cases rename column policy_decision to warranty",
    "alter table action_executions drop column if exists policy_version",
]


def upgrade():
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade():
    raise NotImplementedError("0009 drops invented demo data; restore from a backup instead")
