"""Unit tests for gateway_handlers helpers and the ``_invoke`` pipeline.

Covers a contract adjacent to spec credentials "Hold plaintext only in memory
at the moment of use": arbitrary upstream exception text must
not leak into the invocation log via str(e). Coffer-internal errors (whose
text is authored by us) are still preserved for debuggability.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from mcp import MCPError

from coffer.application.mcp.gateway_handlers import _safe_error_summary, handle_tools_call
from coffer.application.mcp.invocation_outcome import answered_rpc_error, is_upstream_answered
from coffer.domain.errors import (
    ResourceNotFound,
    ToolDisabled,
    UpstreamTimeout,
    UpstreamUnavailable,
)
from coffer.domain.mcp.capability import MCPInvocation
from coffer.domain.resource import Resource

SENTINEL = "COFFER_LEAK_SENTINEL_abc123xyz"


def test_arbitrary_exception_message_is_not_persisted() -> None:
    """A non-CofferError exception (e.g., bubbled up from the MCP SDK) might
    carry upstream-controlled text — including credentials echoed back by a
    misbehaving server. _safe_error_summary must drop the message and keep
    only the class name so the invocation log stays clean.
    """
    summary = _safe_error_summary(RuntimeError(f"auth failed: token={SENTINEL}"))
    assert SENTINEL not in summary
    assert summary == "RuntimeError"


def test_value_error_message_is_not_persisted() -> None:
    summary = _safe_error_summary(ValueError(f"bad input contains {SENTINEL}"))
    assert SENTINEL not in summary
    assert summary == "ValueError"


def test_coffer_internal_errors_keep_their_message() -> None:
    """CofferError text is authored by Coffer code, never by upstream — so
    it's safe (and useful) to keep."""
    summary = _safe_error_summary(UpstreamTimeout("upstream 'fs' did not respond in 30s"))
    assert "UpstreamTimeout" in summary
    assert "did not respond" in summary


def test_resource_not_found_keeps_message() -> None:
    summary = _safe_error_summary(ResourceNotFound.named("mcp_server", "ghost"))
    assert "ResourceNotFound" in summary
    assert "ghost" in summary


def test_upstream_unavailable_keeps_message() -> None:
    summary = _safe_error_summary(UpstreamUnavailable("'fs' is in cooldown until 2026-01-01"))
    assert "UpstreamUnavailable" in summary
    assert "cooldown" in summary


def test_tool_disabled_keeps_message() -> None:
    summary = _safe_error_summary(ToolDisabled("tool:'write_file' is disabled"))
    assert "ToolDisabled" in summary
    assert "write_file" in summary


# --------------------------------------------------------------------------- #
# _invoke — every call leaves exactly one invocation row                        #
# --------------------------------------------------------------------------- #


class _Resources:
    def __init__(self, *, enabled: bool = True) -> None:
        now = datetime.now(tz=UTC)
        self.row = Resource(
            id=1,
            uid="0f1e2d3c4b5a69788796a5b4c3d2e1f0",
            kind="mcp_server",
            name="fs",
            description=None,
            config={},
            enabled=enabled,
            created_at=now,
            updated_at=now,
        )

    async def get_by_name(self, kind: str, name: str) -> Resource:
        return self.row


class _Prefs:
    async def find(self, *_a: Any) -> None:
        return None  # no preference row → the capability is enabled


class _Invocations:
    def __init__(self) -> None:
        self.rows: list[MCPInvocation] = []

    async def insert(self, inv: MCPInvocation) -> None:
        self.rows.append(inv)


class _Conn:
    def __init__(self, raises: BaseException | None = None) -> None:
        self._raises = raises

    async def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if self._raises is not None:
            raise self._raises
        return {"content": []}


class _Supervisor:
    """``get_or_spawn`` either raises (the upstream would not start) or hands
    back ``conn``; every ``evict`` is recorded."""

    def __init__(self, *, spawn_error: Exception | None = None, conn: _Conn | None = None) -> None:
        self._spawn_error = spawn_error
        self._conn = conn or _Conn()
        self.spawns = 0
        self.evicted: list[str] = []

    async def get_or_spawn(self, name: str) -> _Conn:
        self.spawns += 1
        if self._spawn_error is not None:
            raise self._spawn_error
        return self._conn

    async def evict(self, name: str) -> None:
        self.evicted.append(name)


async def _call(
    supervisor: _Supervisor,
    invocations: _Invocations,
    *,
    resources: _Resources | None = None,
    ensure_subscribed: Any = None,
) -> Any:
    async def _noop(_name: str) -> None:
        return None

    return await handle_tools_call(
        {"name": "fs__read_file", "arguments": {"path": "/secret"}},
        resources=resources or _Resources(),
        supervisor=supervisor,
        prefs=_Prefs(),
        invocations=invocations,
        session_id="s1",
        clock=lambda: datetime.now(tz=UTC),
        ensure_subscribed=ensure_subscribed or _noop,
    )


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="invocation log records calls without arguments"
)
@pytest.mark.asyncio
async def test_call_against_an_upstream_that_will_not_start_is_recorded() -> None:
    """A cooldown / exhausted spawn ladder is still a call: exactly one
    ``error`` row, and no eviction — there was never a connection to evict."""
    sup = _Supervisor(spawn_error=UpstreamUnavailable("'fs' is in cooldown until 2026-01-01"))
    inv = _Invocations()
    with pytest.raises(UpstreamUnavailable):
        await _call(sup, inv)
    assert len(inv.rows) == 1
    row = inv.rows[0]
    assert (row.status, row.capability_key) == ("error", "read_file")
    assert row.error_message is not None and "UpstreamUnavailable" in row.error_message
    assert "/secret" not in row.error_message
    assert sup.evicted == []


@pytest.mark.asyncio
async def test_failed_subscription_is_recorded_without_eviction() -> None:
    async def _boom(_name: str) -> None:
        raise UpstreamUnavailable("subscribe failed")

    sup = _Supervisor()
    inv = _Invocations()
    with pytest.raises(UpstreamUnavailable):
        await _call(sup, inv, ensure_subscribed=_boom)
    assert [r.status for r in inv.rows] == ["error"]
    assert sup.evicted == []


@pytest.mark.asyncio
async def test_disabled_server_is_refused_and_recorded_as_denied() -> None:
    """A session that listed the server before it was disabled still knows its
    names; the call is refused before the supervisor is asked for anything."""
    sup = _Supervisor()
    inv = _Invocations()
    with pytest.raises(ToolDisabled):
        await _call(sup, inv, resources=_Resources(enabled=False))
    assert [r.status for r in inv.rows] == ["denied"]
    assert sup.spawns == 0


@pytest.mark.asyncio
async def test_answered_jsonrpc_error_is_marked_and_not_evicted() -> None:
    """A well-formed JSON-RPC error is the upstream answering: the row carries
    the answered marker (code only, never the upstream's text) and the healthy
    connection stays."""
    sup = _Supervisor(conn=_Conn(raises=MCPError(-32602, f"bad args {SENTINEL}")))
    inv = _Invocations()
    with pytest.raises(MCPError):
        await _call(sup, inv)
    (row,) = inv.rows
    assert row.error_message == answered_rpc_error(-32602)
    assert is_upstream_answered(row)
    assert sup.evicted == []


@pytest.mark.asyncio
async def test_transport_failure_is_evicted_and_not_marked_answered() -> None:
    sup = _Supervisor(conn=_Conn(raises=BrokenPipeError()))
    inv = _Invocations()
    with pytest.raises(BrokenPipeError):
        await _call(sup, inv)
    (row,) = inv.rows
    assert row.status == "error"
    assert not is_upstream_answered(row)
    assert sup.evicted == ["fs"]
