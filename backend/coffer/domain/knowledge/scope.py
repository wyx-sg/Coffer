"""Knowledge scope value objects.

A scope is *where a piece of knowledge belongs*. There are three, and the
resource name encodes which:

- ``global``            — knowledge that follows the user everywhere
- ``project-<ULID>``    — resolved from the cwd's git root, provisioned on
                          first use; the user never creates one by hand
- any other name        — a collection the user made deliberately (what used
                          to be a separate ``knowledge_base`` kind)

The first two auto-provision, because an agent that wants to write something
should not have to ask permission first. The third does not: a named
collection exists because someone decided it should, and silently conjuring
one from a typo'd name would be worse than an error.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from coffer.domain.knowledge.document import WORKSPACE_GLOBAL_PROJECT_ID

__all__ = [
    "GLOBAL_SCOPE_NAME",
    "PROJECT_SCOPE_PREFIX",
    "WORKSPACE_GLOBAL_PROJECT_ID",
    "KnowledgeScope",
    "ResolvedScope",
    "project_scope_name",
    "scope_kind_of",
]

GLOBAL_SCOPE_NAME = "global"
PROJECT_SCOPE_PREFIX = "project-"


class KnowledgeScope(StrEnum):
    GLOBAL = "global"
    PROJECT = "project"
    NAMED = "named"


def project_scope_name(project_id: str) -> str:
    """The resource name for a per-project scope."""
    return f"{PROJECT_SCOPE_PREFIX}{project_id}"


def scope_kind_of(resource_name: str) -> KnowledgeScope:
    """Which of the three a resource name denotes.

    Derived from the name rather than stored, so the two can never disagree.
    """
    if resource_name == GLOBAL_SCOPE_NAME:
        return KnowledgeScope.GLOBAL
    if resource_name.startswith(PROJECT_SCOPE_PREFIX):
        return KnowledgeScope.PROJECT
    return KnowledgeScope.NAMED


@dataclass(frozen=True)
class ResolvedScope:
    """The outcome of resolving a requested scope to a concrete store."""

    scope: KnowledgeScope
    #: The project ULID for PROJECT, the global sentinel for GLOBAL, and the
    #: collection's own name for NAMED — whatever keys this scope's documents.
    project_id: str
    #: ``~/.coffer/knowledge/<scope>/``; filled by the infrastructure paths
    #: module so the domain stays free of path construction.
    store_dir: Path
    #: The resource name, which is also the scope's identity on the wire.
    resource_name: str

    @property
    def is_global(self) -> bool:
        return self.scope is KnowledgeScope.GLOBAL

    @property
    def is_named(self) -> bool:
        return self.scope is KnowledgeScope.NAMED
