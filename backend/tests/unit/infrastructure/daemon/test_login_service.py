"""The launchd agent's contents — spec daemon FR-028.

Installing one needs a Mac and a session bus, so what is pinned here is the
plist itself: the three keys that are decisions rather than boilerplate, each
of which has a plausible-looking wrong value.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from coffer.infrastructure.daemon import login_service


def _plist() -> dict[str, object]:
    return login_service.build_plist(
        program=["/Users/u/.coffer/bin/coffer-daemon"],
        path_env="/opt/homebrew/bin:/usr/bin",
        log_file=Path("/Users/u/.coffer/logs/daemon.log"),
    )


@pytest.mark.acceptance(
    spec="daemon",
    scenario="the daemon is up before anything asks for it",
)
def test_the_agent_starts_at_login_and_survives_a_crash() -> None:
    plist = _plist()
    assert plist["RunAtLoad"] is True
    assert plist["ProgramArguments"] == ["/Users/u/.coffer/bin/coffer-daemon"]


@pytest.mark.acceptance(
    spec="daemon",
    scenario="a daemon nothing has wanted stands down",
)
def test_a_clean_exit_is_not_restarted() -> None:
    """The one key that would quietly break the idle shutdown.

    ``KeepAlive: true`` reads like the obvious way to say "keep it running",
    and it turns a deliberate stand-down into a restart a second later,
    forever. Only an *unsuccessful* exit is restarted.
    """
    assert _plist()["KeepAlive"] == {"SuccessfulExit": False}


def test_the_agent_carries_the_users_own_path() -> None:
    # launchd hands an agent a minimal PATH, and the daemon spawns npx/uvx
    # MCP upstreams that then resolve to nothing.
    env = _plist()["EnvironmentVariables"]
    assert isinstance(env, dict)
    assert env["PATH"] == "/opt/homebrew/bin:/usr/bin"


def test_the_agent_logs_where_everything_else_does() -> None:
    # One timeline, not a second file nothing tells anyone about (FR-022).
    plist = _plist()
    assert plist["StandardOutPath"] == "/Users/u/.coffer/logs/daemon.log"
    assert plist["StandardErrorPath"] == plist["StandardOutPath"]


def test_the_label_is_distinct_from_the_desktop_bundle() -> None:
    # Same domain, different program, different lifetime — the app's own
    # identifier is `dev.coffer.desktop`.
    assert login_service.LABEL == "dev.coffer.daemon"
    assert login_service.plist_path().name == "dev.coffer.daemon.plist"
