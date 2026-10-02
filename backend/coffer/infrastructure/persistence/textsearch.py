"""A free-text "contains" filter over several columns, for the log tables.

The Activity page's search box is applied by the database (spec web-ui "Read
each Activity tab from its record owner's route"), so a page of results is the
first page of what matches, not a filter over whatever happened to be loaded.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import ColumnElement, or_
from sqlalchemy.orm import InstrumentedAttribute

_ESCAPE = "\\"


def contains_any(
    columns: Iterable[InstrumentedAttribute[str] | InstrumentedAttribute[str | None]],
    needle: str,
) -> ColumnElement[bool]:
    """Rows where ``needle`` appears, in any case, in at least one of ``columns``.

    ``%``, ``_`` and the escape character in ``needle`` match themselves.
    """
    escaped = (
        needle.replace(_ESCAPE, _ESCAPE * 2).replace("%", f"{_ESCAPE}%").replace("_", f"{_ESCAPE}_")
    )
    pattern = f"%{escaped}%"
    return or_(*(column.ilike(pattern, escape=_ESCAPE) for column in columns))


__all__ = ["contains_any"]
