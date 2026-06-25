"""Server-side table pagination for the admin panel.

The admin tables fetch one page at a time over AJAX (sort / search / paging are
query params), so a large table never loads every row. ``TableParams`` parses
and validates the request's query string against a per-table whitelist (sort
keys, page size) — untrusted input never reaches an ``ORDER BY`` column — and
``paginate`` runs the windowed query + a matching ``COUNT``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from math import ceil
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session
from starlette.requests import Request

# The page sizes offered in every table's selector.
PAGE_SIZES = (10, 25, 50, 100)


@dataclass(frozen=True)
class TableParams:
    """Validated paging/sort/search state for one table request."""

    page: int
    per_page: int
    sort: str
    dir: str
    q: str

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page

    @property
    def descending(self) -> bool:
        return self.dir == "desc"


def table_params(
    request: Request,
    *,
    allowed_sorts: dict[str, InstrumentedAttribute[Any]],
    default_sort: str,
    default_per_page: int = 25,
) -> TableParams:
    """Parse ``page/per_page/sort/dir/q`` from the query string, clamped to safe
    values. ``sort`` must be a key of ``allowed_sorts`` (anything else falls back
    to ``default_sort``), so the caller can map it straight to a column."""
    qp = request.query_params

    try:
        page = max(1, int(qp.get("page", 1)))
    except (TypeError, ValueError):
        page = 1

    try:
        per_page = int(qp.get("per_page", default_per_page))
    except (TypeError, ValueError):
        per_page = default_per_page
    if per_page not in PAGE_SIZES:
        per_page = default_per_page

    sort = qp.get("sort", default_sort)
    if sort not in allowed_sorts:
        sort = default_sort

    direction = (qp.get("dir") or "asc").lower()
    if direction not in ("asc", "desc"):
        direction = "asc"

    q = (qp.get("q") or "").strip()
    return TableParams(page=page, per_page=per_page, sort=sort, dir=direction, q=q)


def is_partial(request: Request) -> bool:
    """True when the client wants only the rows+footer fragment (AJAX), not the
    whole page."""
    return request.query_params.get("partial") == "1"


@dataclass
class Page:
    """A single rendered page of rows plus the paging state the template needs to
    draw the footer and keep the controls in sync."""

    items: list[Any]
    total: int
    params: TableParams

    @property
    def page(self) -> int:
        return self.params.page

    @property
    def per_page(self) -> int:
        return self.params.per_page

    @property
    def sort(self) -> str:
        return self.params.sort

    @property
    def dir(self) -> str:
        return self.params.dir

    @property
    def q(self) -> str:
        return self.params.q

    @property
    def pages(self) -> int:
        return max(1, ceil(self.total / self.per_page)) if self.per_page else 1

    @property
    def start(self) -> int:
        return 0 if self.total == 0 else self.params.offset + 1

    @property
    def end(self) -> int:
        return min(self.params.offset + self.per_page, self.total)

    @property
    def page_sizes(self) -> tuple[int, ...]:
        return PAGE_SIZES


def paginate(
    session: Session,
    base: Select[Any],
    params: TableParams,
    *,
    sort_columns: dict[str, InstrumentedAttribute[Any]],
    search_columns: list[InstrumentedAttribute[Any]] | None = None,
    tiebreak: InstrumentedAttribute[Any] | None = None,
    options: list[Any] | None = None,
) -> Page:
    """Run ``base`` as a windowed, sorted, optionally-searched query and return a
    :class:`Page`.

    ``base`` selects exactly one entity (so ``COUNT`` over the same filters is
    well-defined). ``search_columns`` are matched case-insensitively against the
    ``q`` term; ``sort_columns`` maps the validated sort key to a column;
    ``tiebreak`` keeps paging stable when the sort column has duplicates;
    ``options`` (e.g. ``joinedload``) load on the row query only, never the count.
    """
    stmt = base
    if params.q and search_columns:
        like = f"%{params.q.lower()}%"
        stmt = stmt.where(or_(*[func.lower(c).like(like) for c in search_columns]))

    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = session.scalar(count_stmt) or 0

    column = sort_columns[params.sort]
    order = column.desc() if params.descending else column.asc()
    stmt = stmt.order_by(order)
    if tiebreak is not None:
        stmt = stmt.order_by(tiebreak.desc() if params.descending else tiebreak.asc())

    stmt = stmt.offset(params.offset).limit(params.per_page)
    if options:
        stmt = stmt.options(*options)
    items = list(session.scalars(stmt).all())
    return Page(items=items, total=total, params=params)


def _sortable(value: Any) -> tuple[bool, Any]:
    """A sort key that tolerates ``None`` and mixed string casing within one
    (homogeneous) column. ``None`` sorts before real values; strings compare
    case-insensitively."""
    if value is None:
        return (False, "")
    if isinstance(value, str):
        return (True, value.lower())
    return (True, value)


def paginate_iterable(
    items: Iterable[Any],
    params: TableParams,
    *,
    sort_keys: dict[str, Callable[[Any], Any]],
    search_text: Callable[[Any], str] | None = None,
) -> Page:
    """In-memory equivalent of :func:`paginate` for the small, **derived** tables
    (a user's wallets, a family's members/categories/budgets, the dependency
    report) whose rows aren't a plain DB query. Bounded data only — it materialises
    the whole list, then searches / sorts / slices it in Python.
    """
    data = list(items)
    if params.q and search_text is not None:
        needle = params.q.lower()
        data = [it for it in data if needle in (search_text(it) or "").lower()]
    total = len(data)
    key = sort_keys.get(params.sort)
    if key is not None:
        data.sort(key=lambda it: _sortable(key(it)), reverse=params.descending)
    start = params.offset
    return Page(
        items=data[start : start + params.per_page], total=total, params=params
    )
