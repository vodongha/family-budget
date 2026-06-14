"""wallet icon and color

Adds wallets.icon (emoji/icon key) and wallets.color (hex) so a wallet can be
personalised. Both nullable; the client falls back to a default look when unset.

Revision ID: b8e2d4f6a019
Revises: a7d9f1c4e682
Create Date: 2026-06-14 18:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b8e2d4f6a019'
down_revision: str | None = 'a7d9f1c4e682'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('wallets', sa.Column('icon', sa.String(length=32), nullable=True))
    op.add_column('wallets', sa.Column('color', sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column('wallets', 'color')
    op.drop_column('wallets', 'icon')
