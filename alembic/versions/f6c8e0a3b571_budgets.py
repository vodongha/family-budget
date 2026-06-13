"""budgets

Adds the budgets table — a monthly spending limit per category (family-level).
One budget per (family, category).

Revision ID: f6c8e0a3b571
Revises: e5b7f9d2a468
Create Date: 2026-06-13 14:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f6c8e0a3b571'
down_revision: str | None = 'e5b7f9d2a468'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'budgets',
        sa.Column('id', sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column('rid', sa.String(length=26), nullable=False),
        sa.Column('family_id', sa.Integer(), nullable=False),
        sa.Column('category_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.BigInteger(), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(['family_id'], ['families.id']),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id']),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('rid'),
        sa.UniqueConstraint(
            'family_id', 'category_id', name='uq_budget_family_category'
        ),
    )
    op.create_index(op.f('ix_budgets_family_id'), 'budgets', ['family_id'])
    op.create_index(op.f('ix_budgets_category_id'), 'budgets', ['category_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_budgets_category_id'), table_name='budgets')
    op.drop_index(op.f('ix_budgets_family_id'), table_name='budgets')
    op.drop_table('budgets')
