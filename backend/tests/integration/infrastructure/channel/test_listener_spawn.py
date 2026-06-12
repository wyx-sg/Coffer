"""CallbackListenerController spawning the REAL listener subprocess.

The controller runs ``python -m coffer.surfaces.callback`` with config in the
child env; these tests probe the live listener over real loopback HTTP (the
closest thing to e2e the listener has), and pin the pidfile + idempotent
ensure_running/ensure_stopped lifecycle.
"""

from __future__ import annotations

import asyncio
import json
import socket
import sys
from pathlib import Path

import httpx
import pytest

from coffer.domain.channel.signing import seatalk_signature
from coffer.infrastructure.channel.listener_spawn import (
    CallbackListenerController,
    _listener_command,
)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _pidfiles(home: Path) -> list[Path]:
    pid_dir = home / ".coffer" / "upstream-pids"
    return sorted(pid_dir.glob("channel-callback-*.json")) if pid_dir.exists() else []


async def _wait_listening(port: int, *, timeout: float = 10.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        try:
            _reader, writer = await asyncio.open_connection("127.0.0.1", port)
        except OSError:
            await asyncio.sleep(0.05)
            continue
        writer.close()
        await writer.wait_closed()
        return
    raise AssertionError(f"listener never started serving on port {port}")


async def _wait_closed(port: int, *, timeout: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        try:
            _reader, writer = await asyncio.open_connection("127.0.0.1", port)
        except OSError:
            return
        writer.close()
        await writer.wait_closed()
        await asyncio.sleep(0.05)
    raise AssertionError(f"listener still serving on port {port} after stop")


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))  # pidfiles land under $HOME/.coffer
    return tmp_path


def _controller(port: int) -> CallbackListenerController:
    # The daemon is irrelevant to handshake tests; point at a dead loopback port.
    return CallbackListenerController(
        daemon_info=lambda: ("http://127.0.0.1:1", "daemon-token"), port=port
    )


def test_listener_command_resolves_module_entrypoint_for_source_installs() -> None:
    assert _listener_command() == [sys.executable, "-m", "coffer.surfaces.callback"]


@pytest.mark.acceptance(
    spec="009-channels", scenario="the callback listener answers the verification handshake"
)
async def test_spawned_listener_answers_verification_handshake(home: Path) -> None:
    port = _free_port()
    controller = _controller(port)
    try:
        await controller.ensure_running({"ch": "s3cret"})
        assert controller.running()
        assert controller.port == port

        # The spawn was recorded for the startup orphan sweep.
        pidfiles = _pidfiles(home)
        assert len(pidfiles) == 1
        recorded = json.loads(pidfiles[0].read_text())
        assert recorded["command_line"] == [sys.executable, "-m", "coffer.surfaces.callback"]

        await _wait_listening(port)
        body = json.dumps(
            {"event_type": "event_verification", "event": {"seatalk_challenge": "ch-42"}}
        ).encode()
        async with httpx.AsyncClient() as client:
            ok = await client.post(
                f"http://127.0.0.1:{port}/seatalk/ch",
                content=body,
                headers={
                    "Signature": seatalk_signature(body, "s3cret"),
                    "Content-Type": "application/json",
                },
            )
            # Same live listener enforces the signature boundary.
            bad = await client.post(
                f"http://127.0.0.1:{port}/seatalk/ch",
                content=body,
                headers={"Signature": "0" * 64, "Content-Type": "application/json"},
            )
        assert ok.status_code == 200
        assert ok.json() == {"seatalk_challenge": "ch-42"}
        assert bad.status_code == 401
    finally:
        await controller.ensure_stopped()

    assert not controller.running()
    assert _pidfiles(home) == []  # ensure_stopped reaped the pidfile
    await _wait_closed(port)


async def test_ensure_running_is_idempotent_and_restarts_on_secret_change(home: Path) -> None:
    port = _free_port()
    controller = _controller(port)
    try:
        await controller.ensure_running({"ch": "one"})
        [first] = _pidfiles(home)
        pid1 = json.loads(first.read_text())["pid"]

        # Same secrets → no restart, same child.
        await controller.ensure_running({"ch": "one"})
        [still] = _pidfiles(home)
        assert json.loads(still.read_text())["pid"] == pid1

        # Changed secrets → the child is replaced (env-injected secrets are
        # immutable per process, so a rotation must restart it).
        await controller.ensure_running({"ch": "two"})
        [replaced] = _pidfiles(home)
        pid2 = json.loads(replaced.read_text())["pid"]
        assert pid2 != pid1
        assert controller.running()
    finally:
        await controller.ensure_stopped()
    assert _pidfiles(home) == []
    assert not controller.running()
