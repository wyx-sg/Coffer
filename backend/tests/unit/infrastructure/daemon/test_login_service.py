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


# --- the rule that keeps this module from shutting Coffer down -------------


def test_nothing_here_boots_a_loaded_job_out() -> None:
    """`launchctl bootout` terminates the job's process, and on this machine
    that process is usually the daemon serving the Settings page the call
    came from. The reply never arrives, the switch reverts over a change that
    did happen, and the replacement mints a token the open page does not
    have. Read off the source, because the failure needs a Mac with a loaded
    agent and a live request to show itself."""
    import inspect

    # The quoted form is the argument a `_launchctl(...)` call would pass;
    # the prose above may name the verb freely, and does.
    assert '"bootout"' not in inspect.getsource(login_service)


def test_the_path_comes_from_the_login_shell_not_the_daemons_environment() -> None:
    """The key exists because a GUI-launched process has a truncated PATH —
    and when this runs inside the daemon, `os.environ` IS that truncated
    one."""
    import inspect

    assert "login_shell_path()" in inspect.getsource(login_service.install)
