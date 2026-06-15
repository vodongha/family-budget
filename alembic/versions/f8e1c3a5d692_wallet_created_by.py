"""wallet created_by_user_id

Track who created each wallet so the **creator** of a shared (family) wallet can
edit/delete it too — not only the family owner. Nullable: existing wallets have
an unknown creator and stay owner-managed; personal wallets already gate on
``owner_user_id``.

Revision ID: f8e1c3a5d692
Revises: e7d9b2f4c581
Create Date: 2026-06-15 09:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f8e1c3a5d692'
down_revision: str | None = 'e7d9b2f4c581'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'wallets',
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    )
    op.create_index(
        op.f('ix_wallets_created_by_user_id'), 'wallets', ['created_by_user_id']
    )
    op.create_foreign_key(
        'fk_wallets_created_by_user_id_users',
        'wallets',
        'users',
        ['created_by_user_id'],
        ['id'],
    )


def downgrade() -> None:
    op.drop_constraint(
        'fk_wallets_created_by_user_id_users', 'wallets', type_='foreignkey'
    )
    op.drop_index(op.f('ix_wallets_created_by_user_id'), table_name='wallets')
    op.drop_column('wallets', 'created_by_user_id')
