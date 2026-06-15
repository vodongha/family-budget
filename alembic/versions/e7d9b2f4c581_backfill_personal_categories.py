"""Backfill personal default categories for existing users.

New accounts get a personal default category set at sign-up (register / Google),
but accounts created **before** that seeding existed — or accounts that
registered *with* a family (which only seeded the family's set) — have an empty
personal space. This one-off data migration gives every active user the same
default personal categories a new account would receive, so the Personal tab is
usable for everyone.

Idempotent: a user who already has *any* personal category (``owner_user_id``
set) is skipped, so re-running never duplicates.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from ulid import ULID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7d9b2f4c581"
down_revision: str | None = "d1a4c7e8b362"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Mirrors app.domains.categories.defaults.DEFAULT_CATEGORIES — inlined so the
# migration stays stable even if the app's default set changes later.
# (key, English name, emoji, AARRGGBB colour, kind)
_DEFAULT_CATEGORIES: list[tuple[str, str, str, str, str]] = [
    ("food", "Food & drink", "🍜", "FFEF5350", "expense"),
    ("transport", "Transport", "⛽", "FF42A5F5", "expense"),
    ("shopping", "Shopping", "🛍️", "FFAB47BC", "expense"),
    ("bills", "Bills & utilities", "🧾", "FF26A69A", "expense"),
    ("housing", "Housing", "🏠", "FF8D6E63", "expense"),
    ("health", "Health", "💊", "FFEC407A", "expense"),
    ("entertainment", "Entertainment", "🎬", "FFFFA726", "expense"),
    ("education", "Education", "📚", "FF5C6BC0", "expense"),
    ("otherExpense", "Other", "🏷️", "FF78909C", "expense"),
    ("salary", "Salary", "💰", "FF66BB6A", "income"),
    ("bonus", "Bonus", "🎁", "FF26C6DA", "income"),
    ("otherIncome", "Other", "🏷️", "FF78909C", "income"),
]


def upgrade() -> None:
    conn = op.get_bind()

    # Active users (Oracle has no native boolean — compare the NUMBER(1) with 0).
    user_ids = [
        row[0]
        for row in conn.execute(
            sa.text("SELECT id FROM users WHERE is_deleted = 0")
        )
    ]
    # Users who already have a personal category — skip them (idempotent).
    seeded = {
        row[0]
        for row in conn.execute(
            sa.text(
                "SELECT DISTINCT owner_user_id FROM categories "
                "WHERE owner_user_id IS NOT NULL"
            )
        )
    }
    targets = [uid for uid in user_ids if uid not in seeded]
    if not targets:
        return

    categories = sa.table(
        "categories",
        sa.column("rid", sa.String),
        sa.column("family_id", sa.Integer),
        sa.column("owner_user_id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("icon", sa.String),
        sa.column("color", sa.String),
        sa.column("kind", sa.String),
        sa.column("default_key", sa.String),
    )

    rows = [
        {
            "rid": str(ULID()),
            "family_id": None,
            "owner_user_id": uid,
            "name": name,
            "icon": icon,
            "color": color,
            "kind": kind,
            "default_key": key,
        }
        for uid in targets
        for (key, name, icon, color, kind) in _DEFAULT_CATEGORIES
    ]
    # id (Identity), created_at and is_archived fall back to their server
    # defaults — only the explicit columns above are supplied.
    op.bulk_insert(categories, rows)


def downgrade() -> None:
    # Data backfill — there is no safe automatic way to tell a backfilled
    # personal category from one a user created or kept, so this is a no-op.
    pass
