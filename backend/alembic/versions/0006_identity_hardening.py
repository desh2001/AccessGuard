"""Add explicit account_type and native_id_namespace with partial unique index.

Revision ID: 0006_identity_hardening
Revises: 0005_admin_email_notifications
"""
from alembic import op
import sqlalchemy as sa

revision = '0006_identity_hardening'
down_revision = '0005_admin_email_notifications'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('accounts') as batch_op:
        batch_op.add_column(
            sa.Column('account_type', sa.String(24), nullable=False, server_default='unknown')
        )
        batch_op.add_column(
            sa.Column('native_id_namespace', sa.String(255), nullable=True)
        )
        batch_op.create_check_constraint(
            'account_type_valid',
            "account_type IN ('human','service','shared','emergency','vendor','workload','machine','unknown')"
        )
        batch_op.create_index(
            'uq_account_system_native_tuple',
            ['system_id', 'native_id_type', 'native_id_namespace', 'native_id'],
            unique=True,
            postgresql_where=sa.text("native_id IS NOT NULL AND native_id_type IS NOT NULL AND native_id_namespace IS NOT NULL"),
            sqlite_where=sa.text("native_id IS NOT NULL AND native_id_type IS NOT NULL AND native_id_namespace IS NOT NULL")
        )


def downgrade():
    with op.batch_alter_table('accounts') as batch_op:
        batch_op.drop_index('uq_account_system_native_tuple')
        batch_op.drop_constraint('account_type_valid', type_='check')
        batch_op.drop_column('native_id_namespace')
        batch_op.drop_column('account_type')
