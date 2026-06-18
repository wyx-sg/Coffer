"""Unit tests for the per-agent MCP scoping helpers (ADR-026).

Pure logic over a tiny fake ``resources`` object (``.list(kind, enabled)``)
and a fake scope (``.allowed_server_names``) — no DB, no gateway session.

Covers ``effective_mcp_servers`` (list-time hiding) and ``authorize_server``
(call-time gating) across the unscoped, auto, and selected cases.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from coffer.application.mcp.gateway_scope import (
    allowed_server_names,
    authorize_server,
    effective_mcp_servers,
)
from coffer.domain.scope_errors import AgentMcpServerNotInScope

pytestmark = pytest.mark.asyncio


@dataclass
class _FakeResource:
    name: str
    enabled: bool = True


@dataclass
class _FakeResources:
    """Minimal stand-in for ResourceService.list used by the scope helpers."""

    servers: list[_FakeResource] = field(default_factory=list)
    list_calls: list[tuple[str | None, bool | None]] = field(default_factory=list)

    async def list(
        self, kind: str | None = None, enabled: bool | None = None
    ) -> list[_FakeResource]:
        self.list_calls.append((kind, enabled))
        out = self.servers
        if kind is not None:
            out = [r for r in out if True]  # only mcp_server resources in this fake
        if enabled is not None:
            out = [r for r in out if r.enabled is enabled]
        return out


@dataclass
class _FakeScope:
    """Satisfies AgentMcpScopePort structurally: name -> allowlist|None."""

    mapping: dict[str, set[str] | None] = field(default_factory=dict)

    async def allowed_server_names(self, agent_name: str) -> set[str] | None:
        return self.mapping.get(agent_name)


def _resources() -> _FakeResources:
    return _FakeResources(servers=[_FakeResource("a"), _FakeResource("b")])


async def test_effective_servers_unscoped_no_scope_object() -> None:
    res = _resources()
    # No scope object at all (anonymous / in-process ask agent) -> everything.
    assert await effective_mcp_servers(res, None, "anyone") == ["a", "b"]


async def test_effective_servers_unscoped_no_agent_name() -> None:
    res = _resources()
    scope = _FakeScope({"cc": {"a"}})
    # A scope object but no bound agent -> unscoped, sees everything.
    assert await effective_mcp_servers(res, scope, None) == ["a", "b"]


async def test_effective_servers_auto_mode_sees_all_enabled() -> None:
    res = _resources()
    # allowed_server_names returns None for an auto-mode agent.
    scope = _FakeScope({"cc": None})
    assert await effective_mcp_servers(res, scope, "cc") == ["a", "b"]


async def test_effective_servers_selected_intersects_enabled() -> None:
    res = _resources()
    # "a" is allowlisted, "z" doesn't exist -> only the enabled ∩ allowlist.
    scope = _FakeScope({"cc": {"a", "z"}})
    assert await effective_mcp_servers(res, scope, "cc") == ["a"]


async def test_effective_servers_pushes_enabled_filter_to_list() -> None:
    res = _resources()
    await effective_mcp_servers(res, None, "cc")
    # CODE-021: the enabled=True filter is pushed to the list query.
    assert res.list_calls == [("mcp_server", True)]


async def test_allowed_server_names_passthrough_and_none() -> None:
    scope = _FakeScope({"cc": {"a"}})
    assert await allowed_server_names(scope, "cc") == {"a"}
    assert await allowed_server_names(scope, None) is None
    assert await allowed_server_names(None, "cc") is None


async def test_authorize_server_noop_when_unscoped() -> None:
    # No scope / no agent / auto-mode -> any server name is allowed.
    await authorize_server(None, "cc", "b")
    await authorize_server(_FakeScope({"cc": None}), "cc", "b")
    await authorize_server(_FakeScope({"cc": {"a"}}), None, "b")


async def test_authorize_server_noop_when_in_scope() -> None:
    await authorize_server(_FakeScope({"cc": {"a", "b"}}), "cc", "a")


async def test_authorize_server_raises_when_out_of_scope() -> None:
    scope = _FakeScope({"cc": {"a"}})
    with pytest.raises(AgentMcpServerNotInScope) as exc:
        await authorize_server(scope, "cc", "b")
    assert exc.value.server_name == "b"
    assert exc.value.code == "MCP_SERVER_OUT_OF_SCOPE"
