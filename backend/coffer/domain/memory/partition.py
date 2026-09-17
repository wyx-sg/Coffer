"""How a repository becomes a partition name.

One rule, and it exists because of a specific past failure: per-project stores
were once keyed as ``project-<ULID>`` and nobody could tell which project a
store belonged to, which is the first reason the projection layer was removed.
So a partition is named from its repository, readably, and the absolute root is
recorded in the partition's own ``MEMORY.md`` (spec memory FR-014).

*Which* repository a directory belongs to — and whether it is inside one at
all — is :mod:`coffer.domain.memory.repository`'s question, not this module's.
This one only turns a name into a safe, readable, unique slug.
"""

from __future__ import annotations

import re

#: The one partition that is not a repository: notes about the person,
#: delivered wherever they are working (FR-011).
GLOBAL_PARTITION = "global"

_UNSAFE = re.compile(r"[^A-Za-z0-9._\- 一-鿿]+")
_DASHES = re.compile(r"-{2,}")


def partition_slug(project_root: str) -> str:
    """A readable partition name for a repository root or its name.

    The directory's own name, which is what the developer calls the project.
    Collisions are resolved by :func:`disambiguate`, never by falling back to
    an id — an unreadable name is the failure this function exists to avoid.
    """
    cleaned = (project_root or "").rstrip("/")
    name = cleaned.rsplit("/", 1)[-1] if cleaned else ""
    slug = _slug(name)
    return slug or GLOBAL_PARTITION


def disambiguate(project_root: str, taken: frozenset[str]) -> str:
    """A partition name for ``project_root`` that is not already ``taken``.

    Two repositories can share a directory name. Rather than appending a number —
    which would tell the reader nothing — this walks up the path and prefixes
    the parent directory, so ``work/api`` and ``personal/api`` become
    ``work-api`` and ``personal-api``.
    """
    segments = [s for s in (project_root or "").split("/") if s]
    if not segments:
        return GLOBAL_PARTITION
    for depth in range(1, len(segments) + 1):
        candidate = _slug("-".join(segments[-depth:]))
        if candidate and candidate not in taken:
            return candidate
    # Every ancestor is taken too, which means the same absolute path is
    # already registered under a different name; the caller's own bookkeeping
    # is wrong, and a numeric suffix is the honest last resort.
    base = _slug("-".join(segments))
    suffix = 2
    while f"{base}-{suffix}" in taken:
        suffix += 1
    return f"{base}-{suffix}"


def _slug(value: str) -> str:
    slug = _UNSAFE.sub("-", value.strip()).strip("-. ")
    slug = _DASHES.sub("-", slug)
    return slug.lower()
