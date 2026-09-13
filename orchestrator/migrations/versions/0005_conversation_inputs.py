"""Canonical input ledger and disposable history summaries."""
from alembic import op

INPUT_DDL = """
alter table sessions add column if not exists published_checkpoint_id text;
create table if not exists session_inputs (
    session_id text not null,
    input_id text not null,
    kind text not null,
    payload_digest text not null,
    run_id text not null,
    input_event_seq integer not null,
    received_at timestamptz not null,
    status text not null default 'accepted',
    state_commit_version integer,
    last_output_seq integer,
    base_version integer not null,
    base_checkpoint_id text,
    primary key(session_id, input_id)
);
create index if not exists session_inputs_run_idx on session_inputs(session_id, run_id);
create unique index if not exists session_events_identity_idx on session_events(session_id,(event_json->>'event_id'));
create table if not exists conversation_summaries (
    session_id text not null,
    summary_id text not null,
    through_seq integer not null,
    source_context_revision integer not null,
    source_entry_ids jsonb not null,
    text text not null,
    generated_at timestamptz not null default now(),
    status text not null default 'active',
    expires_at timestamptz not null,
    primary key(session_id, summary_id)
);
"""

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("drop table if exists session_actions")
    for statement in INPUT_DDL.split(";"):
        if statement.strip():
            op.execute(statement)


def downgrade():
    op.execute("drop table if exists conversation_summaries")
    op.execute("drop table if exists session_inputs")
    op.execute("drop index if exists session_events_identity_idx")
    op.execute("alter table sessions drop column if exists published_checkpoint_id")
