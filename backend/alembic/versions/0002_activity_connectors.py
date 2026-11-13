"""Activity evidence and connector provenance tables.

Revision ID: 0002_research_lab
Revises: 0001_phase2
"""
from alembic import op
import sqlalchemy as sa

revision = '0002_research_lab'
down_revision = '0001_phase2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('activity_events',
        sa.Column('id',sa.Integer(),primary_key=True,autoincrement=True),
        sa.Column('account_id',sa.Integer(),sa.ForeignKey('accounts.id'),nullable=False),
        sa.Column('occurred_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('action',sa.String(70),nullable=False),
        sa.Column('outcome',sa.String(20),nullable=False),
        sa.Column('ip_address',sa.String(50),nullable=True),
        sa.Column('source',sa.String(40),nullable=False),
        sa.CheckConstraint("outcome IN ('Success','Failure')",name='activity_outcome_valid'))
    op.create_index('ix_activity_events_account_id','activity_events',['account_id'])
    op.create_index('ix_activity_events_occurred_at','activity_events',['occurred_at'])
    op.create_table('connector_runs',
        sa.Column('id',sa.Integer(),primary_key=True,autoincrement=True),
        sa.Column('source',sa.String(60),nullable=False),
        sa.Column('started_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('completed_at',sa.DateTime(timezone=True),nullable=True),
        sa.Column('status',sa.String(20),nullable=False),
        sa.Column('records_imported',sa.Integer(),nullable=False),
        sa.Column('details',sa.Text(),nullable=False))


def downgrade():
    op.drop_table('connector_runs')
    op.drop_index('ix_activity_events_occurred_at','activity_events')
    op.drop_index('ix_activity_events_account_id','activity_events')
    op.drop_table('activity_events')
