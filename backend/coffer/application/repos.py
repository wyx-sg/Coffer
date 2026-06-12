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
from coffer.domain.resource import Resource, ResourceRef
from coffer.domain.retention import RetentionPolicy


class ResourceRepo(Protocol):
    async def find(self, ref: ResourceRef) -> Resource | None: ...
    async def list(
        self,
        kind: str | None = None,
        enabled: bool | None = None,
    ) -> list[Resource]: ...
    async def create(self, resource: Resource) -> Resource: ...
    async def update_config(
        self,
        ref: ResourceRef,
        config: dict[str, Any],
        description: str | None,
    ) -> Resource: ...
    async def set_enabled(self, ref: ResourceRef, enabled: bool) -> Resource: ...
    async def delete(self, ref: ResourceRef) -> None: ...


class AuditRepo(Protocol):
    async def insert(self, entry: AuditEntry) -> None: ...
    async def query(
        self,
        *,
        kind: str | None = None,
        name: str | None = None,
        event_type: str | None = None,
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
