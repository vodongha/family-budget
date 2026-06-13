"""user phone

Adds users.phone (nullable, unique) — an optional contact number stored in E.164.
Unique so it can be used to invite an existing account into a family.

Revision ID: d4a6e8c1f357
Revises: c3f5d7b9e246
Create Date: 2026-06-13 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4a6e8c1f357'
down_revision: str | None = 'c3f5d7b9e246'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('users', sa.Column('phone', sa.String(length=32), nullable=True))
    op.create_index(op.f('ix_users_phone'), 'users', ['phone'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_users_phone'), table_name='users')
    op.drop_column('users', 'phone')
