# backend/tests/unit/surfaces/http/test_mcp_tools_changed.py
import asyncio

import pytest

from coffer.domain.reconcile import Changed
from coffer.surfaces.http.mcp import session_registry


class _FakeSession:
    def __init__(self) -> None:
        self.announced = 0

    async def announce_tools_changed(self) -> None:
        self.announced += 1


@pytest.fixture
def sessions(monkeypatch):  # type: ignore[no-untyped-def]
    live = {"s1": _FakeSession(), "s2": _FakeSession()}
    monkeypatch.setattr(session_registry, "_ACTIVE_SESSIONS", live)
    monkeypatch.setattr(session_registry, "_ANNOUNCE_SETTLE_S", 0.01)
    monkeypatch.setattr(session_registry, "_announcing", None)
    return live


async def _settle() -> None:
    await asyncio.sleep(0.05)


@pytest.mark.acceptance(spec="mcp-gateway", scenario="A reach change reaches a running session")
async def test_scenario_reach_change_reaches_a_running_session(sessions) -> None:  # type: ignore[no-untyped-def]
    sink = session_registry.tools_changed_sink(asyncio.get_running_loop())
    sink(Changed(kind="mcp_server", uid="u1"))
    await _settle()
    assert [s.announced for s in sessions.values()] == [1, 1]


@pytest.mark.acceptance(spec="mcp-gateway", scenario="A burst of server writes is announced once")
async def test_scenario_burst_is_announced_once(sessions) -> None:  # type: ignore[no-untyped-def]
    sink = session_registry.tools_changed_sink(asyncio.get_running_loop())
    for op in ("upsert", "upsert", "delete"):
        sink(Changed(kind="mcp_server", uid="u1", op=op))  # type: ignore[arg-type]
    await _settle()
    assert [s.announced for s in sessions.values()] == [1, 1]


async def test_a_write_to_another_kind_announces_nothing(sessions) -> None:  # type: ignore[no-untyped-def]
    sink = session_registry.tools_changed_sink(asyncio.get_running_loop())
    sink(Changed(kind="skill", uid="u1"))
    await _settle()
    assert [s.announced for s in sessions.values()] == [0, 0]


async def test_a_hint_from_another_thread_is_announced(sessions) -> None:  # type: ignore[no-untyped-def]
    sink = session_registry.tools_changed_sink(asyncio.get_running_loop())
    await asyncio.to_thread(sink, Changed(kind="mcp_server", uid="u1"))
    await _settle()
    assert [s.announced for s in sessions.values()] == [1, 1]
