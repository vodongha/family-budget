"""user google_sub

Adds users.google_sub (nullable, unique) to link a Google identity for
Sign-In with Google.

Revision ID: b2e4c6a8d135
Revises: 9f3c1a7b2d04
Create Date: 2026-06-13 09:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b2e4c6a8d135'
down_revision: str | None = '9f3c1a7b2d04'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('users', sa.Column('google_sub', sa.String(length=255), nullable=True))
    op.create_index(
        op.f('ix_users_google_sub'), 'users', ['google_sub'], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_users_google_sub'), table_name='users')
    op.drop_column('users', 'google_sub')
