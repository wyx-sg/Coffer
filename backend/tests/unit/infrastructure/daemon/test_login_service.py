"""The launchd agent's contents — spec daemon "Run as a login service".

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
    scenario="the daemon is up before anything asks for it",
)
def test_a_crash_is_restarted_and_a_clean_exit_is_not() -> None:
    """A daemon that dies badly is restarted; one that exited on purpose is not.

    ``KeepAlive: true`` reads like the obvious way to say "keep it running",
    and it would fight every deliberate exit — ``coffer daemon stop``, a quit
    from the desktop shell, a superseded daemon standing down — restarting it
    a second later. Only an *unsuccessful* exit is restarted.
    """
    assert _plist()["KeepAlive"] == {"SuccessfulExit": False}


def test_the_agent_carries_the_users_own_path() -> None:
    # launchd hands an agent a minimal PATH, and the daemon spawns npx/uvx
    # MCP upstreams that then resolve to nothing.
    env = _plist()["EnvironmentVariables"]
    assert isinstance(env, dict)
    assert env["PATH"] == "/opt/homebrew/bin:/usr/bin"


def test_the_agent_logs_where_everything_else_does() -> None:
    # One timeline, not a second file nothing tells anyone about (see "Write
    # one bounded daemon log in one format").
    plist = _plist()
    assert plist["StandardOutPath"] == "/Users/u/.coffer/logs/daemon.log"
    assert plist["StandardErrorPath"] == plist["StandardOutPath"]


def test_the_label_is_distinct_from_the_desktop_bundle() -> None:
    # Same domain, different program, different lifetime — the app's own
    # identifier is `dev.coffer.desktop`.
    assert login_service.LABEL == "dev.coffer.daemon"
    assert login_service.plist_path().name == "dev.coffer.daemon.plist"


# --- the rule that keeps this module from shutting Coffer down -------------


@pytest.fixture
def launchd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[tuple[str, ...]]:
    """A fake launchd: records every launchctl call; the job is loaded with the
    pid in ``state["pid"]`` (``None`` = loaded, nothing running under it)."""
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(login_service, "is_supported", lambda: True)
    monkeypatch.setattr(login_service, "plist_path", lambda: tmp_path / "x.plist")
    monkeypatch.setattr(login_service, "_is_loaded", lambda: True)
    monkeypatch.setattr(login_service, "_launchctl", lambda *a: calls.append(a) or None)
    return calls


@pytest.mark.acceptance(
    spec="daemon", scenario="removing the login service unloads it without stopping the daemon"
)
def test_uninstall_does_not_boot_out_a_job_with_a_running_daemon(
    launchd: list[tuple[str, ...]], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`launchctl bootout` terminates the job's process — usually the daemon
    serving the Settings page the call came from."""
    (tmp_path / "x.plist").write_text("x")
    monkeypatch.setattr(login_service, "_job_pid", lambda: 4242)
    assert login_service.uninstall() is True
    assert not (tmp_path / "x.plist").exists()
    assert launchd == []  # nothing booted out


@pytest.mark.acceptance(
    spec="daemon", scenario="removing the login service unloads it without stopping the daemon"
)
def test_uninstall_boots_out_an_idle_loaded_job(
    launchd: list[tuple[str, ...]], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "x.plist").write_text("x")
    monkeypatch.setattr(login_service, "_job_pid", lambda: None)
    login_service.uninstall()
    assert [c[0] for c in launchd] == ["bootout"]


@pytest.mark.acceptance(
    spec="daemon", scenario="removing the login service unloads it without stopping the daemon"
)
def test_the_daemon_that_is_the_job_boots_it_out_as_it_exits(
    launchd: list[tuple[str, ...]], monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    monkeypatch.setattr(login_service, "_job_pid", lambda: os.getpid())
    assert login_service.release_job_if_uninstalled() is True
    assert [c[0] for c in launchd] == ["bootout"]


def test_a_daemon_that_is_not_the_job_leaves_it_alone(
    launchd: list[tuple[str, ...]], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(login_service, "_job_pid", lambda: 4_194_000)  # someone else's
    assert login_service.release_job_if_uninstalled() is False
    # And while the setting is still on, nothing is released at all.
    (tmp_path / "x.plist").write_text("x")
    monkeypatch.setattr(login_service, "_job_pid", lambda: __import__("os").getpid())
    assert login_service.release_job_if_uninstalled() is False
    assert launchd == []


def test_the_path_comes_from_the_login_shell_not_the_daemons_environment() -> None:
    """The key exists because a GUI-launched process has a truncated PATH —
    and when this runs inside the daemon, `os.environ` IS that truncated
    one."""
    import inspect

    assert "login_shell_path()" in inspect.getsource(login_service.install)


def test_the_agent_execs_the_deploys_current_build_symlink(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Not the versioned path behind it.

    The frozen deploy copies each build into `~/.coffer/bin/<version>/`,
    flips `~/.coffer/bin/coffer-daemon` to it, and keeps only the newest two
    version directories. An agent pinned to `…/0.1.1/coffer-daemon` survives
    exactly two upgrades and then execs a pruned file — and a launchd job
    that cannot exec fails silently, so autostart would stop with nothing
    said.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    versioned = tmp_path / ".coffer" / "bin" / "0.1.1"
    versioned.mkdir(parents=True)
    (versioned / "coffer-daemon").write_text("#!/bin/sh\n")
    link = tmp_path / ".coffer" / "bin" / "coffer-daemon"
    link.symlink_to(versioned / "coffer-daemon")

    assert login_service.agent_program() == [str(link)]
    # The version is what moves; the link is what does not.
    assert "0.1.1" not in login_service.agent_program()[0]


def test_a_source_install_has_no_symlink_and_falls_back(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    from coffer.infrastructure.daemon.spawn import daemon_spawn_command

    assert login_service.agent_program() == daemon_spawn_command()
