"""V7 business-resource governance review evidence, privacy limited.
Revision ID: v7_0001
Revises: v6_0001
"""
from alembic import op
from app.models import GovernedResourcePolicy, GovernedResourceUse
revision='v7_0001'
down_revision='v6_0001'
branch_labels=None
depends_on=None

def upgrade():
    bind=op.get_bind()
    for model in (GovernedResourcePolicy, GovernedResourceUse):
        model.__table__.create(bind,checkfirst=True)

def downgrade():
    raise RuntimeError('V7 downgrade blocked; restore a tested backup instead')
