"""invitation phone

Adds invitations.phone and makes invitations.email nullable so a member can be
invited by phone number (contact label) as well as email.

Revision ID: c3f5d7b9e246
Revises: b2e4c6a8d135
Create Date: 2026-06-13 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3f5d7b9e246'
down_revision: str | None = 'b2e4c6a8d135'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('invitations', sa.Column('phone', sa.String(length=32), nullable=True))
    op.alter_column(
        'invitations', 'email',
        existing_type=sa.String(length=255),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        'invitations', 'email',
        existing_type=sa.String(length=255),
        nullable=False,
    )
    op.drop_column('invitations', 'phone')
