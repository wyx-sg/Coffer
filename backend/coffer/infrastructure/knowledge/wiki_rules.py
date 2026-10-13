"""The rules a collection's README sets for its check, read off its frontmatter
on every build (spec knowledge "Ask for a recheck of a page after the
collection's interval", "Check a collection mechanically on every read").

Two keys, both optional, both the person's to change:

* ``verify_after_days`` — how many days a page's ``verified`` date holds
  (90 by default, ``0`` turns the recheck off). ``review_after_days`` is read
  as the same key, so a collection written with that name works as it reads.
  A page may set either key in its own frontmatter to override the
  collection's interval for itself.
* ``types_without_sources`` — the page types that are navigation rather than
  claims, so a page of one is not asked for ``sources`` (``overview`` by
  default). A page of any other type that has no ``sources`` but lists
  ``evidence`` (code it read, a config, an observation) is not asked either.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter
from coffer.infrastructure.knowledge.fs import decode

VERIFY_KEY = "verify_after_days"
#: Read as :data:`VERIFY_KEY` when that one is absent.
REVIEW_KEY = "review_after_days"
DEFAULT_VERIFY_DAYS = 90

SOURCELESS_KEY = "types_without_sources"
DEFAULT_SOURCELESS_TYPES = ("overview",)


@dataclass(frozen=True)
class Rules:
    verify_after_days: int = DEFAULT_VERIFY_DAYS
    types_without_sources: tuple[str, ...] = DEFAULT_SOURCELESS_TYPES


def as_list(value: object) -> tuple[str, ...]:
    """A frontmatter list that a writer may have given as one string."""
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(v.strip() for v in value.split(",") if v.strip())
    if isinstance(value, Mapping):
        return tuple(str(k).strip() for k, v in value.items() if v not in (None, "", []))
    if isinstance(value, Iterable):
        return tuple(str(v).strip() for v in value if v is not None and str(v).strip())
    return (str(value),)


def days(frontmatter: Mapping[str, Any]) -> int | None:
    """The interval a frontmatter sets, ``None`` when it sets none or one that
    is not a whole, non-negative number of days."""
    value = frontmatter.get(VERIFY_KEY, frontmatter.get(REVIEW_KEY))
    if value is None or isinstance(value, bool) or not isinstance(value, int | str):
        return None
    try:
        number = int(value)
    except ValueError:
        return None
    return number if number >= 0 else None


def read(collection: str) -> Rules:
    """The collection's rules from its README, defaults where it sets none."""
    readme = paths.readme_path(collection)
    if not readme.is_file():
        return Rules()
    fm, _ = split_frontmatter(decode(readme.read_bytes()))
    interval = days(fm)
    sourceless = fm.get(SOURCELESS_KEY)
    return Rules(
        verify_after_days=DEFAULT_VERIFY_DAYS if interval is None else interval,
        types_without_sources=(
            DEFAULT_SOURCELESS_TYPES
            if sourceless is None
            else tuple(t.lower() for t in as_list(sourceless))
        ),
    )


__all__ = [
    "DEFAULT_SOURCELESS_TYPES",
    "DEFAULT_VERIFY_DAYS",
    "REVIEW_KEY",
    "SOURCELESS_KEY",
    "VERIFY_KEY",
    "Rules",
    "as_list",
    "days",
    "read",
]
