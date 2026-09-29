"""The SQL half of cursor paging (spec resource-framework "Page growing lists
by an opaque cursor"): "strictly after this row" in a newest-first order.

Every growing list stored in SQLite orders by a timestamp and breaks ties on
its unique id, both descending. The row after ``(ts, id)`` in that order is one
that is older, or exactly as old with a smaller id — a keyset predicate the
timestamp indexes serve, where an ``OFFSET`` would re-count the head on every
page and shift when a row lands there.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, and_, or_


def newest_first_after(
    ts_col: Any, id_col: Any, after: tuple[datetime, Any]
) -> ColumnElement[bool]:
    """Rows strictly after ``after`` in ``ts DESC, id DESC`` order."""
    ts, row_id = after
    return or_(ts_col < ts, and_(ts_col == ts, id_col < row_id))
