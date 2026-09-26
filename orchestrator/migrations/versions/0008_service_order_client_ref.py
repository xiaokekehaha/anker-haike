"""Caller idempotency reference on demo service orders: an ambiguous timeout is resolved by lookup."""
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("alter table service_orders_mock add column if not exists client_ref text")
    op.execute(
        "create unique index if not exists service_orders_mock_client_ref_idx"
        " on service_orders_mock(client_ref)"
    )


def downgrade():
    op.execute("drop index if exists service_orders_mock_client_ref_idx")
    op.execute("alter table service_orders_mock drop column if exists client_ref")
