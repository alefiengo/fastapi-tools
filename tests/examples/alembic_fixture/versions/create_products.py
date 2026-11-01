"""Literal Alembic revision identifiers, independent of filename convention."""
from alembic import op
import sqlalchemy as sa

revision = 'products_base'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('products', sa.Column('id', sa.Integer, primary_key=True),
                    sa.Column('name', sa.String(100)))


def downgrade():
    op.drop_table('products')
