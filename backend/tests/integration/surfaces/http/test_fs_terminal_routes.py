"""HTTP coverage for /api/v1/fs/terminal and /api/v1/fs/terminals.

See spec daemon "Open an agent session in a terminal" and "List the terminals
installed on this host". The launcher spawn is recorded, never run.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
from types import SimpleNamespace
from typing import Any

import pytest
from starlette.testclient import TestClient

from coffer.application.fs import terminal_service
from coffer.infrastructure.platform import terminals
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

TOKEN = "test-token-fs-terminal"
_REAL_WHICH = shutil.which


def _linux_with(monkeypatch: pytest.MonkeyPatch, *found: str) -> None:
    """A Linux host that has exactly ``found`` on PATH (and ``git``, which the
    daemon needs to open the vault)."""
    monkeypatch.setattr("sys.platform", "linux")

    def which(cmd: str, *args: object, **kwargs: object) -> str | None:
        if cmd == "git":
            return _REAL_WHICH("git")
        return f"/usr/bin/{cmd}" if cmd in found else None

    monkeypatch.setattr(terminals.shutil, "which", which)


def _client(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, port: int) -> TestClient:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port + 9))
    set_active_token(TOKEN)
    return TestClient(create_app(), headers={"X-Coffer-Token": TOKEN})


def _patch_popen(monkeypatch: pytest.MonkeyPatch, popen: Any) -> None:
    """Replace the module reference the service holds, not ``Popen`` itself: the
    daemon spawns ``git`` through the same ``subprocess``."""
    monkeypatch.setattr(
        terminal_service,
        "subprocess",
        SimpleNamespace(Popen=popen, DEVNULL=subprocess.DEVNULL),
    )


def _record_spawns(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []
    _patch_popen(monkeypatch, lambda argv, **_: calls.append(list(argv)))
    return calls


@pytest.mark.acceptance(
    spec="daemon", scenario="a resume opens the agent's resume command in the session's directory"
)
def test_a_resume_starts_the_system_terminal_with_the_resume_command(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = tmp_path / "api"
    work.mkdir()
    _linux_with(monkeypatch, "x-terminal-emulator")
    calls = _record_spawns(monkeypatch)

    with _client(tmp_path, monkeypatch, 59700) as c:
        r = c.post(
            "/api/v1/fs/terminal",
            json={"agent": "claude_code", "cwd": str(work), "resume": "abc-123"},
        )

    assert r.status_code == 204, r.text
    assert calls == [
        ["x-terminal-emulator", "-e", "sh", "-lc", f"cd '{work}' && claude --resume abc-123"]
    ]


@pytest.mark.acceptance(spec="daemon", scenario="a prompt never appears on a command line")
def test_a_prompt_is_written_privately_and_missing_cwd_uses_the_default_workspace(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _linux_with(monkeypatch, "konsole")
    calls = _record_spawns(monkeypatch)

    with _client(tmp_path, monkeypatch, 59710) as c:
        r = c.post(
            "/api/v1/fs/terminal",
            json={"terminal": "konsole", "agent": "codex", "prompt": "rotate sk-test"},
        )

    assert r.status_code == 204, r.text
    workspace = tmp_path / ".coffer" / "content" / "workspace"
    assert workspace.is_dir()
    [argv] = calls
    assert argv[:3] == ["konsole", "--workdir", str(workspace)]
    assert "sk-test" not in " ".join(argv)
    [file] = list((tmp_path / ".coffer" / "tmp" / "handoff").iterdir())
    assert file.read_text() == "rotate sk-test"
    assert f"codex \"$(cat '{file}'; rm -f '{file}')\"" in argv[-1]


@pytest.mark.acceptance(
    spec="daemon", scenario="an unsafe session id is refused before anything starts"
)
def test_invalid_bodies_are_400_and_start_nothing(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _linux_with(monkeypatch, "x-terminal-emulator")
    calls = _record_spawns(monkeypatch)

    with _client(tmp_path, monkeypatch, 59720) as c:
        bodies = [
            {"agent": "claude_code", "resume": "abc;touch /tmp/x"},
            {"agent": "gemini", "resume": "abc"},
            {"agent": "claude_code", "cwd": "relative", "resume": "abc"},
            {"agent": "claude_code", "resume": "abc", "prompt": "hi"},
            {"agent": "claude_code", "resume": "abc", "terminal": "mycli --dir {cwd}"},
            {"agent": "claude_code", "resume": "abc", "terminal": "hyper"},
        ]
        answers = [c.post("/api/v1/fs/terminal", json=b) for b in bodies]

    assert [a.status_code for a in answers] == [400] * len(bodies)
    assert {a.json()["error"]["code"] for a in answers} == {"FS_TERMINAL_INVALID"}
    assert calls == []


def test_a_launcher_that_cannot_start_is_502(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _linux_with(monkeypatch)  # no terminal on this host

    with _client(tmp_path, monkeypatch, 59730) as c:
        none_found = c.post("/api/v1/fs/terminal", json={"agent": "codex", "resume": "abc"})

        _linux_with(monkeypatch, "x-terminal-emulator")

        def refuse(argv: list[str], **_: Any) -> None:
            raise FileNotFoundError("x-terminal-emulator")

        _patch_popen(monkeypatch, refuse)
        spawn_failed = c.post("/api/v1/fs/terminal", json={"agent": "codex", "resume": "abc"})

    assert none_found.status_code == 502, none_found.text
    assert none_found.json()["error"]["code"] == "FS_TERMINAL_FAILED"
    assert spawn_failed.status_code == 502
    assert spawn_failed.json()["error"]["code"] == "FS_TERMINAL_FAILED"


@pytest.mark.acceptance(spec="daemon", scenario="the terminal route needs the token")
def test_the_terminal_routes_need_the_token(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _linux_with(monkeypatch, "x-terminal-emulator")
    calls = _record_spawns(monkeypatch)

    with _client(tmp_path, monkeypatch, 59740) as c:
        c.headers.pop("X-Coffer-Token")
        opened = c.post("/api/v1/fs/terminal", json={"agent": "codex", "resume": "abc"})
        listed = c.get("/api/v1/fs/terminals")

    assert opened.status_code == 401 and listed.status_code == 401
    assert calls == []


@pytest.mark.acceptance(
    spec="daemon", scenario="the daemon lists the terminals installed on this host"
)
def test_terminals_lists_the_installed_ones_and_starts_nothing(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _linux_with(monkeypatch, "konsole", "gnome-terminal")
    calls = _record_spawns(monkeypatch)

    with _client(tmp_path, monkeypatch, 59750) as c:
        r = c.get("/api/v1/fs/terminals")

    assert r.status_code == 200, r.text
    assert r.json()["terminals"] == [
        {"label": "GNOME Terminal", "value": "gnome-terminal"},
        {"label": "Konsole", "value": "konsole"},
    ]
    assert calls == []
