"""Fakes the memory unit tier shares.

Every file under here runs against the fresh ``HOME`` the suite-wide
``_real_home_guard`` fixture in ``backend/tests/conftest.py`` gives every test,
so no test here can reach a developer's real ``~/.claude`` or ``~/.codex``: a
reader is handed a fixture ``config_dir`` built under ``tmp_path``.
"""

from __future__ import annotations

from typing import Any

from coffer.domain.resource import Resource


class FakeAudit:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, Any]]] = []
        #: The resource each event was tied to, kept separately so a test can
        #: assert an event was attributed to an identity rather than to
        #: whatever the row happened to be called.
        self.resources: list[Resource | None] = []

    async def record(
        self,
        event_type: str,
        *,
        resource: Resource | None = None,
        actor: str = "system",
        details: dict[str, Any] | None = None,
    ) -> None:
        self.events.append((event_type, actor, details or {}))
        self.resources.append(resource)
