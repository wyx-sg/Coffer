"""Skill catalog — the discovery surface (FR-032/FR-033).

A catalog is a list of installable skills (name, description, Git coordinates,
publisher) that a user can browse and install without already knowing a Git URL.
This module is pure: the entry shape plus a substring search. Where the entries
come from (a bundled starter list today; a fetched remote index later) lives in
the application layer.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogEntry:
    """One installable skill in the catalog."""

    name: str
    description: str
    git_url: str
    git_ref: str
    git_subpath: str
    publisher: str


def search_catalog(entries: list[CatalogEntry], query: str | None) -> list[CatalogEntry]:
    """Filter the catalog by a case-insensitive substring over name,
    description, and publisher. An empty/None query returns everything.

    Results are sorted by name for a stable browse order.
    """
    items = entries
    if query:
        q = query.strip().lower()
        if q:
            items = [
                e
                for e in entries
                if q in e.name.lower() or q in e.description.lower() or q in e.publisher.lower()
            ]
    return sorted(items, key=lambda e: e.name)
