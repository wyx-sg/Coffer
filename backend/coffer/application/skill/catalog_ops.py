"""Catalog discovery operations for SkillService (FR-032/FR-033).

Loads the bundled starter catalog, supports browse/search, and installs a
catalog entry by delegating to the existing Git-fetch path — so install reuses
the SSRF guard, AgentSkills validation, and content scan with no new trust
surface. Free functions in the skill subpackage style.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coffer.application.skill.catalog_builtin import BUILTIN_CATALOG
from coffer.domain.errors import ResourceNotFound
from coffer.domain.skill.catalog import CatalogEntry, search_catalog

if TYPE_CHECKING:
    from coffer.application.skill.service import SkillService
    from coffer.domain.resource import Resource


def load_catalog() -> list[CatalogEntry]:
    """The available catalog entries (bundled starter list for v1)."""
    return [CatalogEntry(**row) for row in BUILTIN_CATALOG]


def browse_catalog(query: str | None = None) -> list[CatalogEntry]:
    """Browse/search the catalog (FR-032)."""
    return search_catalog(load_catalog(), query)


def find_entry(name: str) -> CatalogEntry:
    """Look up one catalog entry by name, or raise ResourceNotFound."""
    for entry in load_catalog():
        if entry.name == name:
            return entry
    raise ResourceNotFound("catalog-skill", name)


async def install_from_catalog(*, service: SkillService, name: str, actor: str) -> Resource:
    """Install a catalog entry by fetching its Git source (FR-033).

    Delegates to ``SkillService.fetch_git`` so the install rides the same
    SSRF-guarded fetch, AgentSkills validation, and content scan as a manual
    fetch — discovery adds no new ingest path.
    """
    entry = find_entry(name)
    return await service.fetch_git(
        git_url=entry.git_url,
        git_ref=entry.git_ref,
        git_subpath=entry.git_subpath,
        actor=actor,
    )
