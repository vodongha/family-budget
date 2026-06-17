"""multi-currency: wallets.currency + exchange_rates table (seeded)

Adds a per-wallet ISO-4217 ``currency`` (default the base currency, VND, so every
existing wallet keeps its meaning) and an ``exchange_rates`` table holding how many
base units equal one unit of each currency. Seeded with a static snapshot so
conversion works before the first scheduled refresh; a Celery-beat job updates it.

Revision ID: b3d5f7a9c024
Revises: a2f4c6e8b913
Create Date: 2026-06-17 11:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b3d5f7a9c024'
down_revision: str | None = 'a2f4c6e8b913'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Approximate VND-per-unit snapshot; refreshed by the scheduled job.
_SEED_RATES: list[dict[str, object]] = [
    {"currency": "USD", "rate_to_base": 25400.0},
    {"currency": "EUR", "rate_to_base": 27500.0},
    {"currency": "JPY", "rate_to_base": 165.0},
    {"currency": "GBP", "rate_to_base": 32000.0},
    {"currency": "AUD", "rate_to_base": 16800.0},
    {"currency": "SGD", "rate_to_base": 18800.0},
    {"currency": "KRW", "rate_to_base": 18.5},
    {"currency": "CNY", "rate_to_base": 3500.0},
    {"currency": "THB", "rate_to_base": 720.0},
]


def upgrade() -> None:
    op.add_column(
        'wallets',
        sa.Column(
            'currency',
            sa.String(length=3),
            server_default=sa.text("'VND'"),
            nullable=False,
        ),
    )
    op.create_table(
        'exchange_rates',
        sa.Column('id', sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('rate_to_base', sa.Float(), nullable=False),
        sa.Column(
            'updated_at',
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_exchange_rates_currency', 'exchange_rates', ['currency'], unique=True
    )

    rates = sa.table(
        'exchange_rates',
        sa.column('currency', sa.String),
        sa.column('rate_to_base', sa.Float),
    )
    op.bulk_insert(rates, _SEED_RATES)


def downgrade() -> None:
    op.drop_index('ix_exchange_rates_currency', table_name='exchange_rates')
    op.drop_table('exchange_rates')
    op.drop_column('wallets', 'currency')
