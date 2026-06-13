"""transaction transfer group

Adds transactions.transfer_group_rid — the shared ULID linking the two legs
(transfer_out / transfer_in) of a wallet-to-wallet transfer.

Revision ID: a7d9f1c4e682
Revises: f6c8e0a3b571
Create Date: 2026-06-13 14:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a7d9f1c4e682'
down_revision: str | None = 'f6c8e0a3b571'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'transactions',
        sa.Column('transfer_group_rid', sa.String(length=26), nullable=True),
    )
    op.create_index(
        op.f('ix_transactions_transfer_group_rid'),
        'transactions',
        ['transfer_group_rid'],
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_transactions_transfer_group_rid'), table_name='transactions'
    )
    op.drop_column('transactions', 'transfer_group_rid')
