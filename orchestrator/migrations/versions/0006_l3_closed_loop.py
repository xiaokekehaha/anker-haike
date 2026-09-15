"""L3 demo backends, audited executions, cases, approvals and satisfaction."""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

STATEMENTS = [
    "alter table orders_mock add column if not exists region_purchase text, add column if not exists platform text, add column if not exists amount numeric(12,2), add column if not exists currency text",
    """create table shipments_mock(tracking_no text primary key, order_no text not null references orders_mock(order_no), carrier text not null, status text not null, events jsonb not null default '[]', updated_at timestamptz not null)""",
    "create index shipments_mock_order_idx on shipments_mock(order_no)",
    """create table service_orders_mock(service_order_no text primary key, order_no text not null references orders_mock(order_no), sku text not null, type text not null, reason_code text not null, status text not null, created_at timestamptz not null default now(), eta_days int not null default 3, unique(order_no,type))""",
    """create table cases(case_id uuid primary key, session_id text, issue_id text, sku text, category text, status text not null, complaint_risk bool not null default false, priority text not null default 'normal', policy_decision jsonb, proposal jsonb, chosen_option_id text, gate_result jsonb, owner text, external_refs jsonb not null default '{}', opened_at timestamptz not null default now(), updated_at timestamptz not null default now(), closed_at timestamptz, reopened_count int not null default 0, revision int not null default 0, unique(session_id,issue_id))""",
    "create index cases_queue_idx on cases(status,priority,opened_at)",
    """create table case_events(id bigserial primary key, case_id uuid not null references cases(case_id), seq int not null, type text not null, payload jsonb not null, actor text not null, at timestamptz not null default now(), unique(case_id,seq))""",
    """create table action_executions(execution_id uuid primary key, case_id uuid references cases(case_id), session_id text, issue_id text, run_id text, action_kind text not null, idempotency_key text not null unique, request jsonb not null, gate_result jsonb, status text not null check(status in ('running','succeeded','failed','stale')), receipt jsonb, error jsonb, policy_version text, actions_version text not null, attempt int not null default 1, started_at timestamptz not null default now(), finished_at timestamptz)""",
    """create table human_decisions(decision_id uuid primary key, case_id uuid not null references cases(case_id), actor text not null, decision text not null check(decision in ('approve','reject','request_info')), edited_proposal jsonb, option_id text, override_reason text, note text not null, at timestamptz not null default now(), consumed_input_id text, case_revision int not null, unique(case_id,case_revision))""",
    """create table satisfaction_ratings(id bigserial primary key, session_id text, issue_id text, case_id uuid references cases(case_id), score int not null check(score between 1 and 5), comment text, at timestamptz not null default now(), unique(session_id,issue_id))""",
]


def upgrade():
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade():
    for table in (
        "satisfaction_ratings",
        "human_decisions",
        "action_executions",
        "case_events",
        "cases",
        "service_orders_mock",
        "shipments_mock",
    ):
        op.execute(f"drop table {table}")
    op.execute(
        "alter table orders_mock drop column region_purchase, drop column platform, drop column amount, drop column currency"
    )
