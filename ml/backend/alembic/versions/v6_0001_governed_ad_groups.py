"""V6: stable scoped AD IDs, approved catalog, transfer dispositions and membership history.

Revision ID: v6_0001
Revises:
Create Date: 2026-11-07
"""
from alembic import op
import sqlalchemy as sa
from app.models import ADGroupCatalog, TransferAccessDisposition, ADGroupMembershipHistory

revision='v6_0001'
down_revision=None
branch_labels=None
depends_on=None


def upgrade():
    bind=op.get_bind()
    inspector=sa.inspect(bind)
    if not inspector.has_table('ad_group_memberships'):
        # Existing V5 schema expected; for a new V6 database use Base.metadata.create_all.
        raise RuntimeError('Missing V5 tables. Initialize new V6 schema or restore V5 first.')
    existing={c['name'] for c in inspector.get_columns('ad_group_memberships')}
    if 'group_key' not in existing:
        with op.batch_alter_table('ad_group_memberships') as b:
            b.add_column(sa.Column('organization_key',sa.String(100),nullable=False,server_default='demo'))
            b.add_column(sa.Column('directory_key',sa.String(120),nullable=False,server_default='primary'))
            b.add_column(sa.Column('group_key',sa.String(220),nullable=False,server_default='unknown'))
        # Backfill stable fallback identity for legacy group-name-only exports.
        op.execute(sa.text("UPDATE ad_group_memberships SET group_key = 'name:' || lower(group_name) WHERE group_key = 'unknown'"))
        with op.batch_alter_table('ad_group_memberships',recreate='always') as b:
            b.drop_constraint('uq_employee_ad_group',type_='unique')
            b.create_unique_constraint('uq_employee_ad_group_identity',
                        ['employee_id','organization_key','directory_key','group_key'])
    for model in (ADGroupCatalog, TransferAccessDisposition, ADGroupMembershipHistory):
        model.__table__.create(bind,checkfirst=True)


def downgrade():
    raise RuntimeError('V6 downgrade intentionally blocked; restore a tested backup instead.')
