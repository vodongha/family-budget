"""nullable family_id on wallets and transactions

Personal data (wallets + their transactions) is owned by the user
(``owner_user_id``), independent of any family, so a user with no family can
still use the personal space. Make ``wallets.family_id`` and
``transactions.family_id`` nullable; personal wallets/transactions set it null.

Revision ID: c9f3a1b7d240
Revises: b8e2d4f6a019
Create Date: 2026-06-14 19:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c9f3a1b7d240'
down_revision: str | None = 'b8e2d4f6a019'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column('wallets', 'family_id', existing_type=sa.Integer(), nullable=True)
    op.alter_column(
        'transactions', 'family_id', existing_type=sa.Integer(), nullable=True
    )


def downgrade() -> None:
    op.alter_column(
        'transactions', 'family_id', existing_type=sa.Integer(), nullable=False
    )
    op.alter_column('wallets', 'family_id', existing_type=sa.Integer(), nullable=False)
