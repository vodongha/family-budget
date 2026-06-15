"""personal categories and budgets

Categories and budgets can be **personal** (owned by a user, ``family_id`` null)
or **family** (shared). Add ``owner_user_id`` to both and make ``family_id``
nullable, mirroring wallets.

Revision ID: d1a4c7e8b362
Revises: c9f3a1b7d240
Create Date: 2026-06-14 21:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd1a4c7e8b362'
down_revision: str | None = 'c9f3a1b7d240'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'categories',
        sa.Column('owner_user_id', sa.Integer(), nullable=True),
    )
    op.create_index(
        op.f('ix_categories_owner_user_id'), 'categories', ['owner_user_id']
    )
    op.create_foreign_key(
        'fk_categories_owner_user_id_users',
        'categories',
        'users',
        ['owner_user_id'],
        ['id'],
    )
    op.alter_column(
        'categories', 'family_id', existing_type=sa.Integer(), nullable=True
    )

    op.add_column(
        'budgets',
        sa.Column('owner_user_id', sa.Integer(), nullable=True),
    )
    op.create_index(
        op.f('ix_budgets_owner_user_id'), 'budgets', ['owner_user_id']
    )
    op.create_foreign_key(
        'fk_budgets_owner_user_id_users',
        'budgets',
        'users',
        ['owner_user_id'],
        ['id'],
    )
    op.alter_column(
        'budgets', 'family_id', existing_type=sa.Integer(), nullable=True
    )


def downgrade() -> None:
    op.alter_column(
        'budgets', 'family_id', existing_type=sa.Integer(), nullable=False
    )
    op.drop_constraint('fk_budgets_owner_user_id_users', 'budgets', type_='foreignkey')
    op.drop_index(op.f('ix_budgets_owner_user_id'), table_name='budgets')
    op.drop_column('budgets', 'owner_user_id')

    op.alter_column(
        'categories', 'family_id', existing_type=sa.Integer(), nullable=False
    )
    op.drop_constraint(
        'fk_categories_owner_user_id_users', 'categories', type_='foreignkey'
    )
    op.drop_index(op.f('ix_categories_owner_user_id'), table_name='categories')
    op.drop_column('categories', 'owner_user_id')
