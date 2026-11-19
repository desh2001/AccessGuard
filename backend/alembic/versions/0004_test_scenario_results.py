"""Add test scenario results table for built-in simulator test environment.

Revision ID: 0004_test_scenario_results
Revises: 0003_quarterly_ml_v10
"""
from alembic import op
import sqlalchemy as sa

revision = '0004_test_scenario_results'
down_revision = '0003_quarterly_ml_v10'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'test_scenario_results',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('scenario_id', sa.String(60), nullable=False),
        sa.Column('name', sa.String(160), nullable=False),
        sa.Column('category', sa.String(60), nullable=False),
        sa.Column('platform', sa.String(30), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('target_identity', sa.String(160), nullable=True),
        sa.Column('target_account', sa.String(255), nullable=True),
        sa.Column('expected_behavior', sa.Text(), nullable=False),
        sa.Column('status', sa.String(30), nullable=False, server_default='completed'),
        sa.Column('detection_result', sa.String(30), nullable=False),
        sa.Column('details', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('execution_time_ms', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('executed_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_test_scenario_company', 'test_scenario_results', ['company_id', 'executed_at'])


def downgrade():
    op.drop_table('test_scenario_results')
