"""A failed upstream listing must be recoverable, not a session-long outage.

The defect: a per-server discovery timeout dropped that server's whole tool
list, the client cached the truncated tools/list, and no list_changed could
ever arrive — because it would have to come from the server that never
connected. The tools stayed gone for the rest of the session.
"""

from __future__ import annotations

import pytest

from coffer.application.mcp.gateway_aggregate_lists import list_tools_across
from coffer.domain.errors import UpstreamUnavailable


class _FakeTool:
    def __init__(self, prefixed: str):
        self.prefixed_name = prefixed
        self.description = ""
        self.input_schema: dict = {}


class _Discovery:
    """Fails for 'jira' until ``heal()`` is called; 'seatalk' always works."""

    def __init__(self):
        self.healed = False
        self.invalidated: list[tuple[str, str]] = []

    async def list_tools(self, server: str):
        if server == "jira" and not self.healed:
            raise UpstreamUnavailable("cold spawn too slow")
        return [_FakeTool(f"{server}__t1")]

    def invalidate(self, server: str, slice_: str) -> None:
        self.invalidated.append((server, slice_))

    def heal(self) -> None:
        self.healed = True


async def _noop(_server: str) -> None:
    return None


@pytest.mark.asyncio
async def test_failed_server_is_reported_not_silently_dropped():
    outcome = await list_tools_across(_Discovery(), _noop, ["jira", "seatalk"])

    assert [t["name"] for t in outcome.items] == ["seatalk__t1"]
    assert outcome.failed_servers == ["jira"]


@pytest.mark.asyncio
async def test_recovered_server_returns_on_the_next_list():
    discovery = _Discovery()
    first = await list_tools_across(discovery, _noop, ["jira", "seatalk"])
    assert first.failed_servers == ["jira"]

    discovery.heal()
    second = await list_tools_across(discovery, _noop, ["jira", "seatalk"])

    assert second.failed_servers == []
    assert {t["name"] for t in second.items} == {"jira__t1", "seatalk__t1"}


@pytest.mark.asyncio
async def test_all_healthy_reports_no_failures():
    discovery = _Discovery()
    discovery.heal()

    outcome = await list_tools_across(discovery, _noop, ["jira", "seatalk"])

    assert outcome.failed_servers == []
    assert len(outcome.items) == 2


@pytest.mark.asyncio
async def test_failed_servers_preserve_the_requested_order():
    class _AllFail(_Discovery):
        async def list_tools(self, server: str):
            raise UpstreamUnavailable("down")

    outcome = await list_tools_across(_AllFail(), _noop, ["jira", "seatalk", "confluence"])

    assert outcome.failed_servers == ["jira", "seatalk", "confluence"]
    assert outcome.items == []


class _Sink:
    def __init__(self):
        self.sent: list[dict] = []

    async def __call__(self, payload: dict) -> None:
        self.sent.append(payload)


def _session(discovery, sink):
    from coffer.application.mcp.gateway import MCPGatewaySession

    session = MCPGatewaySession(
        session_id="s1",
        resource_service=None,  # type: ignore[arg-type]
        supervisor=None,  # type: ignore[arg-type]
        discovery=discovery,
        preferences=None,  # type: ignore[arg-type]
        invocations=None,  # type: ignore[arg-type]
        downstream_sink=sink,
    )
    return session


@pytest.mark.asyncio
async def test_recovery_tells_the_client_to_re_list():
    """The whole point: the client's cached tools/list gets corrected."""
    discovery = _Discovery()
    sink = _Sink()
    session = _session(discovery, sink)
    session._degraded.record(["jira"])
    assert session.degraded_servers == {"jira"}

    discovery.heal()
    recovered = await session.recover_degraded_now()

    assert recovered is True
    assert session.degraded_servers == set()
    assert discovery.invalidated == [("jira", "tool")]
    assert sink.sent == [{"method": "notifications/tools/list_changed", "params": {}}]


@pytest.mark.asyncio
async def test_a_still_dead_server_stays_degraded_and_notifies_nobody():
    discovery = _Discovery()
    sink = _Sink()
    session = _session(discovery, sink)
    session._degraded.record(["jira"])

    recovered = await session.recover_degraded_now()

    assert recovered is False
    assert session.degraded_servers == {"jira"}
    assert sink.sent == []


@pytest.mark.asyncio
async def test_dispose_cancels_a_pending_recovery():
    discovery = _Discovery()
    session = _session(discovery, _Sink())
    session._degraded.record(["jira"])

    await session._degraded.dispose()

    assert session.degraded_servers == set()
