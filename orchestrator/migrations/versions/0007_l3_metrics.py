"""Issue-grain outcome facts for L3 metrics; conversation retention is independent."""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

def upgrade():
    op.execute("""create table service_episodes(
        episode_id uuid primary key, session_id text, issue_id text, case_id uuid references cases(case_id),
        outcome text not null, human_involved bool not null default false,
        source text not null default 'live' check(source in ('live','replay','smoke')),
        rating int check(rating between 1 and 5), intent_correct bool,
        updated_at timestamptz not null default now(), unique(session_id,issue_id))""")
    op.execute("create index service_episodes_window_idx on service_episodes(updated_at)")

def downgrade():
    op.execute("drop table service_episodes")
