# backend/coffer/application/repos.py
"""Repository Protocols used by the application layer.

Concrete implementations live in `coffer.infrastructure.persistence.repos`
(kind-agnostic core) and `coffer.infrastructure.mcp.persistence` (MCP
kind-specific).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from coffer.domain.audit import AuditEntry
from coffer.domain.resource import Resource
from coffer.domain.retention import RetentionPolicy
from coffer.domain.scope import Scope


class ResourceRepo(Protocol):
    """Every row is addressed by its ``uid``.

    The port used to take a ``(kind, name)`` pair, which is what made "address
    a resource by its label" a rule of the persistence layer rather than a
    choice any one surface made. A uid is the identity, so it is what every
    mutation names; ``find_by_name`` exists for the two jobs that genuinely
    start from a label — resolving what a human typed, and enforcing the
    within-kind uniqueness the label still has.
    """

    async def find(self, uid: str) -> Resource | None: ...
    async def find_by_name(self, kind: str, name: str) -> Resource | None: ...
    async def list(
        self,
        kind: str | None = None,
        enabled: bool | None = None,
    ) -> list[Resource]: ...
    async def create(self, resource: Resource) -> Resource: ...
    # ``description`` is written UNCONDITIONALLY — passing ``None`` clears the
    # column. It is required rather than defaulted for exactly that reason:
    # there is no "leave it alone" at this layer, so a caller that only means
    # to rewrite the config has to say what the description should be, and a
    # caller that forgets cannot silently erase one. Distinguishing "absent"
    # from "explicitly null" is the surface's job, where the request body knows
    # which keys it carried (``resource_routes.update_resource``).
    async def update_config(
        self,
        uid: str,
        config: dict[str, Any],
        description: str | None,
    ) -> Resource: ...
    async def set_enabled(self, uid: str, enabled: bool) -> Resource: ...
    async def update_scope(
        self,
        uid: str,
        scope: Scope | None,
    ) -> Resource | None: ...
    # Moving the label, not the resource: ``ResourceAlreadyExists`` when the
    # target name is taken within the kind.
    async def rename(self, uid: str, new_name: str) -> Resource: ...
    async def delete(self, uid: str) -> None: ...


class AuditRepo(Protocol):
    async def insert(self, entry: AuditEntry) -> None: ...
    async def query(
        self,
        *,
        kind: str | None = None,
        resource_id: int | None = None,
        event_type: str | None = None,
        event_prefix: str | None = None,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[AuditEntry]: ...


class RetentionRepo(Protocol):
    async def get(self, table_name: str) -> RetentionPolicy: ...
    async def list(self) -> list[RetentionPolicy]: ...
    async def upsert(self, table_name: str, retention_days: int | None) -> None: ...
    async def update_retention(self, table_name: str, retention_days: int | None) -> None: ...
    async def touch_pruned(self, table_name: str, rows: int) -> None: ...
    async def delete_older_than(
        self,
        table: str,
        timestamp_column: str,
        cutoff: datetime,
    ) -> int: ...
    async def archive_older_than(
        self,
        target_table: str,
        match_column: str,
        set_column: str,
        cutoff: datetime,
        now: datetime,
    ) -> int: ...
    async def exists(self, table_name: str) -> bool: ...
