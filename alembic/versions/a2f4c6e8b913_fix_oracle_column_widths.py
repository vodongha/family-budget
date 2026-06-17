"""fix Oracle column issues: transactions.type width + nullable hashed_password

Two latent bugs that only surface on Oracle (SQLite hides both, so the test suite
stayed green):

- ``transactions.type`` was ``VARCHAR2(10)`` but the transfer leg values
  ``transfer_out`` (12) / ``transfer_in`` (11) are longer — Oracle rejects the
  insert with ORA-12899, so **every transfer 500s**. Widen to 20.
- ``users.hashed_password`` was NOT NULL, but Google-only accounts have no
  password. Oracle stores ``''`` as NULL, so creating a new Google account hit
  ORA-01400. Make it nullable (the service now writes NULL, not '').

Revision ID: a2f4c6e8b913
Revises: f8e1c3a5d692
Create Date: 2026-06-17 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a2f4c6e8b913'
down_revision: str | None = 'f8e1c3a5d692'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        'transactions',
        'type',
        existing_type=sa.String(length=10),
        type_=sa.String(length=20),
        existing_nullable=False,
    )
    op.alter_column(
        'users',
        'hashed_password',
        existing_type=sa.String(length=255),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        'users',
        'hashed_password',
        existing_type=sa.String(length=255),
        nullable=False,
    )
    op.alter_column(
        'transactions',
        'type',
        existing_type=sa.String(length=20),
        type_=sa.String(length=10),
        existing_nullable=False,
    )
