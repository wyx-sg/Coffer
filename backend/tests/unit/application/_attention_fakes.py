"""Shared fakes for the per-kind attention-source unit tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from coffer.domain.resource import Resource

T0 = datetime(2026, 9, 1, tzinfo=UTC)


def resource(
    uid: str,
    kind: str,
    config: dict[str, Any],
    *,
    name: str | None = None,
    enabled: bool = True,
    title: str | None = None,
) -> Resource:
    return Resource(
        uid=uid,
        kind=kind,
        name=name or uid,
        description=None,
        config=config,
        enabled=enabled,
        created_at=T0,
        updated_at=T0,
        title=title,
    )


class FakeResources:
    """Filters the way the real repo does, so a source that forgot to ask for
    enabled rows only would see the disabled ones."""

    def __init__(self, rows: list[Resource], cited: dict[str, list[Resource]] | None = None):
        self.rows = rows
        self.cited = cited or {}

    async def list(self, kind: str | None = None, enabled: bool | None = None) -> list[Resource]:
        return [
            r
            for r in self.rows
            if (kind is None or r.kind == kind) and (enabled is None or r.enabled == enabled)
        ]

    async def cited_credential_refs(self) -> dict[str, list[Resource]]:
        return self.cited
