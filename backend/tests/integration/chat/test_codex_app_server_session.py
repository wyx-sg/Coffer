"""Integration tests for the Codex app-server subprocess seam (spec channels, T2).

The real-subprocess session is exercised here, NOT in the unit tier (unit tests
must stay pure). The lifecycle tests stand a Python child in for ``codex`` —
the session only needs stdin/stdout pipes — so they run on every CI box; only
the factory test needs the real binary and skips without it.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path

import psutil
import pytest

from coffer.infrastructure.chat.codex_app_server import (
    CodexSubprocessSession,
    default_app_server_session,
)

# Reads stdin until EOF like a JSON-RPC server would, so it stays alive until
# the session tears it down; echoes one line to stderr so drain forwarding is
# observable.
_STAND_IN = [
    sys.executable,
    "-c",
    "import sys; sys.stderr.write('stand-in up\\n'); sys.stderr.flush(); sys.stdin.read()",
]


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def _pidfiles(home: Path) -> list[Path]:
    pid_dir = home / ".coffer" / "upstream-pids"
    return sorted(pid_dir.glob("codex-app-server-*.json")) if pid_dir.exists() else []


@pytest.mark.skipif(shutil.which("codex") is None, reason="codex binary not installed")
def test_factory_builds_a_session_object(tmp_path: Path) -> None:
    session = default_app_server_session(str(tmp_path), env=None)
    assert isinstance(session, CodexSubprocessSession)
    # Not started yet — touching ``rpc`` must fail loudly rather than return a
    # half-built client.
    with pytest.raises(RuntimeError):
        _ = session.rpc


async def test_start_records_child_for_orphan_sweep_and_close_reaps_it(
    home: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    session = CodexSubprocessSession(_STAND_IN, str(tmp_path), None)
    await session.start()
    try:
        [pidfile] = _pidfiles(home)
        recorded = json.loads(pidfile.read_text())
        pid = recorded["pid"]
        assert recorded["command_line"] == _STAND_IN
        assert psutil.Process(pid).cmdline() == _STAND_IN
        # The RPC client is wired to the child's pipes.
        assert session.rpc is not None
        # stderr is drained into the daemon log rather than swallowed.
        for _ in range(100):
            if any("stand-in up" in r.getMessage() for r in caplog.records):
                break
            await asyncio.sleep(0.02)
        assert any(r.getMessage() == "codex app-server stderr: stand-in up" for r in caplog.records)
    finally:
        await session.close()

    assert _pidfiles(home) == []
    assert not psutil.pid_exists(pid) or psutil.Process(pid).status() == psutil.STATUS_ZOMBIE
    # close() is idempotent — a second call has no child left to reap.
    await session.close()


async def test_close_before_start_is_a_no_op(home: Path, tmp_path: Path) -> None:
    session = CodexSubprocessSession(_STAND_IN, str(tmp_path), None)
    await session.close()
    assert _pidfiles(home) == []
    with pytest.raises(RuntimeError):
        _ = session.rpc
