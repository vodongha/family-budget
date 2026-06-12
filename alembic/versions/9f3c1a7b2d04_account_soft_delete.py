"""account soft delete

Adds is_deleted + deleted_at to users and families to support self-service
account deletion (Google Play policy): soft-delete now, scheduled purge later.

Revision ID: 9f3c1a7b2d04
Revises: 745d33d56c6a
Create Date: 2026-06-12 21:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '9f3c1a7b2d04'
down_revision: str | None = '745d33d56c6a'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Boolean renders as NUMBER(1) on Oracle (no CHECK constraint in SQLAlchemy 2.0
    # by default). server_default keeps existing rows valid under NOT NULL.
    op.add_column(
        'users',
        sa.Column('is_deleted', sa.Boolean(), server_default=sa.text('0'), nullable=False),
    )
    op.add_column('users', sa.Column('deleted_at', sa.DateTime(), nullable=True))
    op.add_column(
        'families',
        sa.Column('is_deleted', sa.Boolean(), server_default=sa.text('0'), nullable=False),
    )
    op.add_column('families', sa.Column('deleted_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('families', 'deleted_at')
    op.drop_column('families', 'is_deleted')
    op.drop_column('users', 'deleted_at')
    op.drop_column('users', 'is_deleted')
