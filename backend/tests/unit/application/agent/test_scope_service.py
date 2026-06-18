"""Unit tests for AgentMcpScopeService (ADR-026).

Fakes only: a dict-backed repo shaped like AgentMcpScopeRepo (keyed by agent
resource id), a FakeResourceService that resolves agent + mcp_server names to
ids, and a real AuditService over an in-memory FakeAuditRepo. No DB.

Covers:
  * allowed_server_names: None for auto / unknown agent, the set for selected
  * get_scope: mode + sorted server names
  * set_scope("selected", ...): validates each server, persists, audits
  * set_scope("selected", [unknown]): raises AgentMcpScopeServerUnknown
  * set_scope("auto", ...): clears the allowlist
  * unknown agent: ResourceNotFound (both get and set)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from coffer.application.agent.scope_service import AgentMcpScopeService
from coffer.application.audit_service import AuditService
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ResourceNotFound
from coffer.domain.resource import Resource, ResourceRef
from coffer.domain.scope_errors import AgentMcpScopeServerUnknown

pytestmark = pytest.mark.asyncio

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _resource(rid: int, kind: str, name: str) -> Resource:
    return Resource(
        id=rid,
        kind=kind,
        name=name,
        description=None,
        config={},
        enabled=True,
        created_at=_NOW,
        updated_at=_NOW,
    )


@dataclass
class FakeScopeRepo:
    """Dict-backed AgentMcpScopeRepo: agent_id -> (mode, [server_ids])."""

    rows: dict[int, tuple[str, list[int]]] = field(default_factory=dict)
    set_calls: list[tuple[int, str, list[int]]] = field(default_factory=list)

    async def get_mode(self, agent_resource_id: int) -> str | None:
        row = self.rows.get(agent_resource_id)
        return row[0] if row is not None else None

    async def get_allowed_server_ids(self, agent_resource_id: int) -> set[int]:
        row = self.rows.get(agent_resource_id)
        return set(row[1]) if row is not None else set()

    async def set(self, agent_resource_id: int, mode: str, server_ids: list[int]) -> None:
        self.set_calls.append((agent_resource_id, mode, list(server_ids)))
        self.rows[agent_resource_id] = (mode, list(server_ids))


@dataclass
class FakeResourceService:
    """Resolves agent + mcp_server names to persisted Resource objects."""

    resources: list[Resource] = field(default_factory=list)

    async def get(self, ref: ResourceRef) -> Resource:
        for r in self.resources:
            if r.kind == ref.kind and r.name == ref.name:
                return r
        raise ResourceNotFound(ref.kind, ref.name)

    async def list(self, kind: str | None = None, enabled: bool | None = None) -> list[Resource]:
        return [r for r in self.resources if kind is None or r.kind == kind]


class FakeAuditRepo:
    def __init__(self) -> None:
        self.entries: list = []

    async def insert(self, entry) -> None:
        self.entries.append(entry)

    async def query(self, *, kind=None, name=None, event_type=None, since=None, limit=50):
        return self.entries[:limit]


def _build() -> tuple[AgentMcpScopeService, FakeScopeRepo, FakeResourceService, FakeAuditRepo]:
    repo = FakeScopeRepo()
    resources = FakeResourceService(
        resources=[
            _resource(1, "agent", "cc"),
            _resource(10, "mcp_server", "fs"),
            _resource(11, "mcp_server", "git"),
        ]
    )
    audit_repo = FakeAuditRepo()
    svc = AgentMcpScopeService(repo, resources, AuditService(audit_repo))  # type: ignore[arg-type]
    return svc, repo, resources, audit_repo


async def test_allowed_server_names_none_for_auto() -> None:
    svc, _repo, _res, _audit = _build()
    # No row at all -> auto -> unscoped.
    assert await svc.allowed_server_names("cc") is None


async def test_allowed_server_names_none_for_unknown_agent() -> None:
    svc, _repo, _res, _audit = _build()
    assert await svc.allowed_server_names("ghost") is None


async def test_allowed_server_names_set_for_selected() -> None:
    svc, repo, _res, _audit = _build()
    repo.rows[1] = ("selected", [10])
    assert await svc.allowed_server_names("cc") == {"fs"}


async def test_get_scope_auto_when_no_row() -> None:
    svc, _repo, _res, _audit = _build()
    scope = await svc.get_scope("cc")
    assert scope.mode == "auto"
    assert scope.servers == ()
    assert scope.agent_name == "cc"


async def test_get_scope_selected_returns_sorted_servers() -> None:
    svc, repo, _res, _audit = _build()
    repo.rows[1] = ("selected", [11, 10])  # git, fs (unsorted ids)
    scope = await svc.get_scope("cc")
    assert scope.mode == "selected"
    assert scope.servers == ("fs", "git")  # sorted by name


async def test_get_scope_unknown_agent_raises() -> None:
    svc, _repo, _res, _audit = _build()
    with pytest.raises(ResourceNotFound):
        await svc.get_scope("ghost")


async def test_set_scope_selected_persists_and_audits() -> None:
    svc, repo, _res, audit_repo = _build()
    result = await svc.set_scope("cc", "selected", ["fs"], actor="tester")
    # Persisted via repo.set with the resolved server id.
    assert repo.set_calls == [(1, "selected", [10])]
    assert repo.rows[1] == ("selected", [10])
    # Returned scope reflects the new state.
    assert result.mode == "selected"
    assert result.servers == ("fs",)
    # Audit event recorded with mode + servers.
    assert len(audit_repo.entries) == 1
    entry = audit_repo.entries[0]
    assert entry.event_type == AuditEventType.AGENT_MCP_SCOPE_SET.value
    assert entry.actor == "tester"
    assert entry.resource_kind == "agent"
    assert entry.resource_name == "cc"
    assert entry.details == {"mode": "selected", "servers": ["fs"]}


async def test_set_scope_selected_unknown_server_raises() -> None:
    svc, repo, _res, audit_repo = _build()
    with pytest.raises(AgentMcpScopeServerUnknown) as exc:
        await svc.set_scope("cc", "selected", ["nope"], actor="tester")
    assert exc.value.server_name == "nope"
    # Nothing persisted, nothing audited on the failure path.
    assert repo.set_calls == []
    assert audit_repo.entries == []


async def test_set_scope_auto_clears_allowlist() -> None:
    svc, repo, _res, audit_repo = _build()
    repo.rows[1] = ("selected", [10, 11])
    result = await svc.set_scope("cc", "auto", ["fs"], actor="tester")
    # auto ignores the server list and clears the allowlist.
    assert repo.set_calls == [(1, "auto", [])]
    assert repo.rows[1] == ("auto", [])
    assert result.mode == "auto"
    assert result.servers == ()
    # Audit details report an empty server list for auto.
    assert audit_repo.entries[0].details == {"mode": "auto", "servers": []}


async def test_set_scope_unknown_agent_raises_before_write() -> None:
    svc, repo, _res, audit_repo = _build()
    with pytest.raises(ResourceNotFound):
        await svc.set_scope("ghost", "selected", ["fs"], actor="tester")
    assert repo.set_calls == []
    assert audit_repo.entries == []
