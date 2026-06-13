"""wallet visibility

Adds wallet privacy: ``wallets.visibility`` ("family" shared / "personal"
private, default "family") and ``wallets.owner_user_id`` (nullable FK → users,
set for personal wallets — the only member who can see them).

Revision ID: a1b2c3d4e5f6
Revises: f6c8e0a3b579
Create Date: 2026-06-13 16:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: str | None = 'f6c8e0a3b579'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'wallets',
        sa.Column(
            'visibility',
            sa.String(length=10),
            server_default=sa.text("'family'"),
            nullable=False,
        ),
    )
    op.add_column(
        'wallets', sa.Column('owner_user_id', sa.Integer(), nullable=True)
    )
    op.create_index(
        op.f('ix_wallets_owner_user_id'),
        'wallets',
        ['owner_user_id'],
        unique=False,
    )
    op.create_foreign_key(
        'fk_wallets_owner_user_id_users',
        'wallets',
        'users',
        ['owner_user_id'],
        ['id'],
    )


def downgrade() -> None:
    op.drop_constraint(
        'fk_wallets_owner_user_id_users', 'wallets', type_='foreignkey'
    )
    op.drop_index(op.f('ix_wallets_owner_user_id'), table_name='wallets')
    op.drop_column('wallets', 'owner_user_id')
    op.drop_column('wallets', 'visibility')
