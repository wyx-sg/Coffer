"""TunnelController: spawn/stop a cloudflared child per channel (fakes subprocess).

The real cloudflared binary is never run; asyncio.create_subprocess_exec and the
binary resolver are monkeypatched so we can assert lifecycle + the token-file
hardening (token written 0600, never on argv, removed on stop).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from coffer.infrastructure.channel import tunnel_spawn
from coffer.infrastructure.channel.tunnel_spawn import CloudflaredNotFoundError, TunnelController


class _FakeProc:
    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.returncode: int | None = None
        self.terminated = False

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.returncode = -9

    async def wait(self) -> int:
        self.returncode = 0 if self.returncode is None else self.returncode
        return self.returncode


@pytest.fixture
def spawns(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Record each spawned command; return a fresh _FakeProc per call."""
    recorded: list[list[str]] = []
    counter = {"pid": 1000}

    async def fake_exec(*command: str, **_: Any) -> _FakeProc:
        recorded.append(list(command))
        counter["pid"] += 1
        return _FakeProc(counter["pid"])

    monkeypatch.setattr(tunnel_spawn, "_resolve_cloudflared", lambda: "/usr/bin/cloudflared")
    monkeypatch.setattr(tunnel_spawn.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(tunnel_spawn, "record_spawn", lambda *a, **k: None)
    monkeypatch.setattr(tunnel_spawn, "reap_pidfile", lambda *a, **k: None)
    return recorded


def _token_file_from(command: list[str]) -> Path:
    return Path(command[command.index("--token-file") + 1])


async def test_ensure_running_spawns_with_token_file_0600_not_argv(spawns: list[list[str]]):
    tc = TunnelController()
    await tc.ensure_running("st", "SECRET-TOKEN")
    assert tc.running("st") is True
    assert tc.active() == {"st"}
    assert len(spawns) == 1
    cmd = spawns[0]
    # token value never on the command line
    assert "SECRET-TOKEN" not in cmd
    tf = _token_file_from(cmd)
    assert tf.read_text() == "SECRET-TOKEN"
    assert (tf.stat().st_mode & 0o777) == 0o600
    await tc.dispose()


async def test_same_token_is_idempotent_new_token_respawns(spawns: list[list[str]]):
    tc = TunnelController()
    await tc.ensure_running("st", "T1")
    await tc.ensure_running("st", "T1")  # no-op
    assert len(spawns) == 1
    await tc.ensure_running("st", "T2")  # respawn
    assert len(spawns) == 2
    assert _token_file_from(spawns[1]).read_text() == "T2"
    await tc.dispose()


async def test_ensure_stopped_removes_token_file_and_marks_not_running(spawns: list[list[str]]):
    tc = TunnelController()
    await tc.ensure_running("st", "T")
    tf = _token_file_from(spawns[0])
    assert tf.exists()
    await tc.ensure_stopped("st")
    assert tc.running("st") is False
    assert tc.active() == set()
    assert not tf.exists()


async def test_dispose_stops_all(spawns: list[list[str]]):
    tc = TunnelController()
    await tc.ensure_running("a", "T")
    await tc.ensure_running("b", "T")
    assert tc.active() == {"a", "b"}
    await tc.dispose()
    assert tc.active() == set()


async def test_ensure_running_raises_when_cloudflared_missing(monkeypatch: pytest.MonkeyPatch):
    def missing() -> str:
        raise CloudflaredNotFoundError("nope")

    monkeypatch.setattr(tunnel_spawn, "_resolve_cloudflared", missing)
    tc = TunnelController()
    with pytest.raises(CloudflaredNotFoundError):
        await tc.ensure_running("st", "T")
    assert tc.running("st") is False


def test_resolve_cloudflared_uses_path(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(tunnel_spawn.shutil, "which", lambda _: "/somewhere/cloudflared")
    assert tunnel_spawn._resolve_cloudflared() == "/somewhere/cloudflared"


def test_resolve_cloudflared_raises_when_absent(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(tunnel_spawn.shutil, "which", lambda _: None)
    monkeypatch.setattr(tunnel_spawn, "_FALLBACK_BINDIRS", ())
    with pytest.raises(CloudflaredNotFoundError):
        tunnel_spawn._resolve_cloudflared()
