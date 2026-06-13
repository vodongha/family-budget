"""The default categories seeded into every new family.

``key`` is the stable identifier the app localizes (EN/VN); ``name`` is the
English fallback stored in the row. Users can edit/add/remove freely afterwards.
"""

from app.domains.categories.models import CategoryKind

# (key, English name, emoji, AARRGGBB colour, kind)
DEFAULT_CATEGORIES: list[tuple[str, str, str, str, CategoryKind]] = [
    ("food", "Food & drink", "🍜", "FFEF5350", CategoryKind.EXPENSE),
    ("transport", "Transport", "⛽", "FF42A5F5", CategoryKind.EXPENSE),
    ("shopping", "Shopping", "🛍️", "FFAB47BC", CategoryKind.EXPENSE),
    ("bills", "Bills & utilities", "🧾", "FF26A69A", CategoryKind.EXPENSE),
    ("housing", "Housing", "🏠", "FF8D6E63", CategoryKind.EXPENSE),
    ("health", "Health", "💊", "FFEC407A", CategoryKind.EXPENSE),
    ("entertainment", "Entertainment", "🎬", "FFFFA726", CategoryKind.EXPENSE),
    ("education", "Education", "📚", "FF5C6BC0", CategoryKind.EXPENSE),
    ("otherExpense", "Other", "🏷️", "FF78909C", CategoryKind.EXPENSE),
    ("salary", "Salary", "💰", "FF66BB6A", CategoryKind.INCOME),
    ("bonus", "Bonus", "🎁", "FF26C6DA", CategoryKind.INCOME),
    ("otherIncome", "Other", "🏷️", "FF78909C", CategoryKind.INCOME),
]
