# backend/tests/unit/surfaces/http/test_mcp_tools_changed.py
import pytest

from coffer.surfaces.http.mcp import session_registry


class _FakeSession:
    def __init__(self) -> None:
        self.announced = 0

    async def announce_tools_changed(self) -> None:
        self.announced += 1


@pytest.mark.acceptance(spec="mcp-gateway", scenario="A reach change reaches a running session")
async def test_scenario_reach_change_reaches_a_running_session(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    sessions = {"s1": _FakeSession(), "s2": _FakeSession()}
    monkeypatch.setattr(session_registry, "_ACTIVE_SESSIONS", sessions)
    await session_registry.announce_tools_changed()
    assert [s.announced for s in sessions.values()] == [1, 1]
