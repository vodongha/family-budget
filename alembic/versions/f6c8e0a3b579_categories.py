"""categories

Adds the categories table (family-scoped expense/income labels with an optional
emoji icon, colour, and a default_key for localizing seeded defaults) and
transactions.category_id (nullable FK → categories).

Revision ID: f6c8e0a3b579
Revises: e5b7f9d2a468
Create Date: 2026-06-13 14:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f6c8e0a3b579'
down_revision: str | None = 'e5b7f9d2a468'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'categories',
        sa.Column('id', sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column('rid', sa.String(length=26), nullable=False),
        sa.Column('family_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=60), nullable=False),
        sa.Column('icon', sa.String(length=16), nullable=True),
        sa.Column('color', sa.String(length=8), nullable=True),
        sa.Column('kind', sa.String(length=10), nullable=False),
        sa.Column('default_key', sa.String(length=30), nullable=True),
        sa.Column(
            'is_archived', sa.Boolean(), server_default=sa.text('0'), nullable=False
        ),
        sa.Column(
            'created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(['family_id'], ['families.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('rid'),
    )
    op.create_index(
        op.f('ix_categories_family_id'), 'categories', ['family_id'], unique=False
    )

    op.add_column(
        'transactions', sa.Column('category_id', sa.Integer(), nullable=True)
    )
    op.create_index(
        op.f('ix_transactions_category_id'),
        'transactions',
        ['category_id'],
        unique=False,
    )
    op.create_foreign_key(
        'fk_transactions_category_id_categories',
        'transactions',
        'categories',
        ['category_id'],
        ['id'],
    )


def downgrade() -> None:
    op.drop_constraint(
        'fk_transactions_category_id_categories', 'transactions', type_='foreignkey'
    )
    op.drop_index(op.f('ix_transactions_category_id'), table_name='transactions')
    op.drop_column('transactions', 'category_id')
    op.drop_index(op.f('ix_categories_family_id'), table_name='categories')
    op.drop_table('categories')
