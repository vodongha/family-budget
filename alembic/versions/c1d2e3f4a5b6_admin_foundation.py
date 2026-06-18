"""admin foundation

Adds platform super-admin support, separate from the family-scoped owner/member
role:
- ``users.is_superadmin`` — a boolean flag gating access to the ``/admin`` panel.
- ``admin_audit_log`` — an append-only record of every admin mutation (who did
  what, to which target, when), so privileged actions are always traceable.

Revision ID: c1d2e3f4a5b6
Revises: b3d5f7a9c024
Create Date: 2026-06-18 21:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: str | None = 'b3d5f7a9c024'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Boolean renders as NUMBER(1) on Oracle. server_default keeps existing rows
    # valid under NOT NULL (every current account is a non-admin).
    op.add_column(
        'users',
        sa.Column(
            'is_superadmin', sa.Boolean(), server_default=sa.text('0'), nullable=False
        ),
    )
    op.create_table(
        'admin_audit_log',
        sa.Column('id', sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column('rid', sa.String(length=26), nullable=False),
        # The admin who performed the action. Nullable so a deleted admin's history
        # survives (the FK is cleared, the log row stays).
        sa.Column('actor_user_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(length=60), nullable=False),
        sa.Column('target_type', sa.String(length=40), nullable=True),
        sa.Column('target_rid', sa.String(length=26), nullable=True),
        # Free-form JSON detail (before/after, reason, etc.). CLOB on Oracle.
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(),
            server_default=sa.text('CURRENT_TIMESTAMP'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['actor_user_id'], ['users.id'], ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('rid'),
    )
    op.create_index(
        op.f('ix_admin_audit_log_created_at'),
        'admin_audit_log',
        ['created_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_admin_audit_log_created_at'), table_name='admin_audit_log'
    )
    op.drop_table('admin_audit_log')
    op.drop_column('users', 'is_superadmin')
