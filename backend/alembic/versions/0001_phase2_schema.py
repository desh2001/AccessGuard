"""Phase 2 PostgreSQL identities, accounts and grants.

Revision ID: 0001_phase2
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = '0001_phase2'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('identities',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('name', sa.String(160), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('department', sa.String(100), nullable=False),
        sa.Column('job_title', sa.String(120), nullable=False),
        sa.Column('type', sa.String(20), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('manager', sa.String(120), nullable=False),
        sa.CheckConstraint("type IN ('Human','Machine','Vendor')", name='identity_type_valid'),
        sa.CheckConstraint("status IN ('Active','Departed')", name='identity_status_valid'))
    op.create_table('systems',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('category', sa.String(80), nullable=False))
    op.create_table('accounts',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('identity_id', sa.String(32), sa.ForeignKey('identities.id', ondelete='SET NULL'), nullable=True),
        sa.Column('system_id', sa.String(32), sa.ForeignKey('systems.id'), nullable=False),
        sa.Column('external_account_id', sa.String(255), nullable=False),
        sa.Column('username', sa.String(255), nullable=False),
        sa.Column('account_email', sa.String(255), nullable=True),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('source', sa.String(30), nullable=False),
        sa.Column('mapping_method', sa.String(30), nullable=True),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('system_id','external_account_id',name='uq_account_system_external_id'),
        sa.CheckConstraint("status IN ('Active','Disabled')", name='account_status_valid'))
    op.create_index('ix_accounts_identity_id','accounts',['identity_id'])
    op.create_index('ix_accounts_system_id','accounts',['system_id'])
    op.create_table('access_grants',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('accounts.id'), nullable=False),
        sa.Column('permission', sa.String(80), nullable=False),
        sa.Column('resource', sa.String(255), nullable=False),
        sa.Column('privilege', sa.Integer(), nullable=False),
        sa.Column('cross_department', sa.Integer(), nullable=False),
        sa.Column('last_verified_use', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(20), nullable=False),
        sa.CheckConstraint("status IN ('Active','Revoked')", name='grant_status_valid'))
    op.create_index('ix_access_grants_account_id','access_grants',['account_id'])
    op.create_table('reviews',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('grant_id', sa.Integer(), sa.ForeignKey('access_grants.id'), nullable=False, unique=True),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('reviewer', sa.String(120), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('Pending','Approved','Retained','Remediated')", name='review_status_valid'))
    op.create_table('audit_logs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('actor', sa.String(120), nullable=False),
        sa.Column('action', sa.String(80), nullable=False),
        sa.Column('entity', sa.String(180), nullable=False),
        sa.Column('details', sa.Text(), nullable=False))


def downgrade():
    op.drop_table('audit_logs')
    op.drop_table('reviews')
    op.drop_index('ix_access_grants_account_id','access_grants')
    op.drop_table('access_grants')
    op.drop_index('ix_accounts_system_id','accounts')
    op.drop_index('ix_accounts_identity_id','accounts')
    op.drop_table('accounts')
    op.drop_table('systems')
    op.drop_table('identities')
