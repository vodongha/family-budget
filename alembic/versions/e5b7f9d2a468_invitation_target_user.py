"""invitation target user

Adds invitations.target_user_id (nullable FK to users) — set when the invited
contact matches an existing account, so the invite is delivered in-app and
accepted in one tap instead of via a registration link.

Revision ID: e5b7f9d2a468
Revises: d4a6e8c1f357
Create Date: 2026-06-13 12:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e5b7f9d2a468'
down_revision: str | None = 'd4a6e8c1f357'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'invitations', sa.Column('target_user_id', sa.Integer(), nullable=True)
    )
    op.create_index(
        op.f('ix_invitations_target_user_id'),
        'invitations',
        ['target_user_id'],
        unique=False,
    )
    op.create_foreign_key(
        'fk_invitations_target_user_id_users',
        'invitations',
        'users',
        ['target_user_id'],
        ['id'],
    )


def downgrade() -> None:
    op.drop_constraint(
        'fk_invitations_target_user_id_users', 'invitations', type_='foreignkey'
    )
    op.drop_index(op.f('ix_invitations_target_user_id'), table_name='invitations')
    op.drop_column('invitations', 'target_user_id')
