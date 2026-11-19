"""Add admin email notification settings and logs table.

Revision ID: 0005_admin_email_notifications
Revises: 0004_test_scenario_results
"""
from alembic import op
import sqlalchemy as sa

revision = '0005_admin_email_notifications'
down_revision = '0004_test_scenario_results'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'admin_email_settings',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('admin_name', sa.String(120), nullable=False, server_default='Main Security Administrator'),
        sa.Column('admin_email', sa.String(255), nullable=False),
        sa.Column('enabled', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('smtp_host', sa.String(120), nullable=False, server_default='smtp.gmail.com'),
        sa.Column('smtp_port', sa.Integer(), nullable=False, server_default='587'),
        sa.Column('smtp_user', sa.String(255), nullable=True),
        sa.Column('smtp_password', sa.String(255), nullable=True),
        sa.Column('sender_name', sa.String(120), nullable=False, server_default='AccessGuard Security Sentinel'),
        sa.Column('notify_on_high_risk', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('notify_on_attack_detected', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('notify_on_reviews_queued', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        'email_alert_logs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('recipient', sa.String(255), nullable=False),
        sa.Column('subject', sa.String(255), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('status', sa.String(30), nullable=False, server_default='sent'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('trigger_type', sa.String(80), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_email_logs_sent', 'email_alert_logs', ['sent_at'])


def downgrade():
    op.drop_table('email_alert_logs')
    op.drop_table('admin_email_settings')
