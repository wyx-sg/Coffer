"""The proxy as a real process: the entry module, the daemon binary's proxy
mode, and the supervisor's spawn / re-attach / restart / drain."""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

import coffer
from coffer.domain.model_proxy.state import CONTROL_TOKEN_HEADER, ProxyState
from coffer.infrastructure.model_proxy.info import read_info
from coffer.infrastructure.model_proxy.supervisor import ProxySupervisor
from tests.integration.model_proxy.conftest import CLAUDE_TOKEN, claude_headers, member, state
from tests.integration.model_proxy.harness import free_port, sse_reply, wait_for

pytestmark = pytest.mark.timeout(60)

_SOURCE = str(Path(coffer.__file__).resolve().parent.parent)


@pytest.fixture
def home(tmp_path: Path) -> Iterator[Path]:
    home = tmp_path / "home"
    (home / ".coffer").mkdir(parents=True)
    yield home
    info = read_info(home / ".coffer")  # never leave a proxy behind
    if info is not None:
        with contextlib.suppress(ProcessLookupError):
            os.kill(info.pid, signal.SIGKILL)


def _env(home: Path) -> dict[str, str]:
    return {
        **os.environ,
        "HOME": str(home),
        "COFFER_PROXY_SPOOL_DIR": str(home / "spool"),
        "COFFER_LOG_DIR": str(home / "logs"),
        "PYTHONPATH": _SOURCE,
    }


def _health(port: int, token: str) -> dict[str, object]:
    r = httpx.get(
        f"http://127.0.0.1:{port}/_coffer/health",
        headers={CONTROL_TOKEN_HEADER: token},
        trust_env=False,
    )
    r.raise_for_status()
    return r.json()


@pytest.mark.parametrize(
    "argv",
    [
        ["-m", "coffer.infrastructure.model_proxy.entry"],
        ["-m", "coffer.infrastructure.daemon.entry", "proxy"],
    ],
    ids=["entry-module", "daemon-proxy-mode"],
)
def test_entry_binds_publishes_and_exits_on_sigterm(home: Path, argv: list[str]) -> None:
    port = free_port()
    proc = subprocess.Popen(
        [sys.executable, *argv, "--port", str(port)],
        env=_env(home),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        assert wait_for(lambda: read_info(home / ".coffer") is not None, 20), proc.stderr
        info = read_info(home / ".coffer")
        assert info is not None and info.pid == proc.pid and info.port == port
        assert (home / ".coffer" / "proxy.json").stat().st_mode & 0o777 == 0o600
        assert wait_for(lambda: _try_health(port, info.control_token), 10)
        assert _health(port, info.control_token)["version"] == coffer.__version__
        assert not (home / ".coffer" / "daemon.json").exists()  # proxy mode is not the daemon
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(15) == 0
        assert read_info(home / ".coffer") is None
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def _try_health(port: int, token: str) -> bool:
    try:
        _health(port, token)
    except httpx.HTTPError:
        return False
    return True


def test_entry_refuses_a_held_port(home: Path) -> None:
    import socket

    with socket.socket() as held:
        held.bind(("127.0.0.1", 0))
        held.listen()
        port = held.getsockname()[1]
        proc = subprocess.run(
            [sys.executable, "-m", "coffer.infrastructure.model_proxy.entry", "--port", str(port)],
            env=_env(home),
            capture_output=True,
            timeout=30,
        )
    assert proc.returncode == 2 and b"in use" in proc.stderr
    assert read_info(home / ".coffer") is None


@pytest.mark.acceptance(
    spec="daemon",
    scenario="the daemon restarts a crashed proxy",
)
@pytest.mark.acceptance(
    spec="daemon",
    scenario="a daemon restart re-attaches to the running proxy",
)
async def test_supervisor_spawns_attaches_restarts_and_drains(
    home: Path, upstreams, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("COFFER_LOG_DIR", str(home / "logs"))
    up, server = upstreams()
    up.script = sse_reply([b"event: message_stop\ndata: {}\n\n"])
    pushed: list[ProxyState] = []

    async def provider() -> ProxyState:
        st = state([member(server, "a")], revision=len(pushed) + 1)
        pushed.append(st)
        return st

    port = free_port()
    env = {"HOME": str(home), "COFFER_PROXY_SPOOL_DIR": str(home / "spool")}
    common = {"port": port, "coffer_dir": home / ".coffer", "env": env, "interval": 0.2}
    first = ProxySupervisor(provider, version=coffer.__version__, **common)
    await first.start()
    status = first.status()
    assert status.running and status.pid and status.port == port and status.restarts == 0
    assert status.revision == 1
    assert (home / "logs" / "proxy.log").exists()
    async with httpx.AsyncClient(trust_env=False) as client:
        r = await client.post(
            f"http://127.0.0.1:{port}/anthropic/v1/messages",
            content=b'{"model":"m1","stream":true}',
            headers=claude_headers(),
        )
        assert r.status_code == 200 and up.requests[0].all("x-api-key") == ["sk-real-a"]
    await first.stop()
    pid = status.pid

    # A second daemon of the same build re-attaches: same pid, no spawn.
    second = ProxySupervisor(provider, version=coffer.__version__, **common)
    await second.start()
    assert second.status().pid == pid and second.status().revision == 2

    # kill -9: the watchdog notices and spawns a fresh proxy, then re-pushes state.
    os.kill(pid, signal.SIGKILL)
    import asyncio

    for _ in range(200):
        if second.status().restarts == 1 and second.status().running:
            break
        await asyncio.sleep(0.05)
    status = second.status()
    assert status.restarts == 1 and status.pid != pid and status.running
    assert status.revision == len(pushed)
    await second.stop()
    assert _try_health(port, read_info(home / ".coffer").control_token)  # stop() leaves it running

    # A daemon of another build drains the old proxy and replaces it.
    old = read_info(home / ".coffer")
    assert old is not None
    third = ProxySupervisor(provider, version="0.0.0-other", **common)
    await third.start()
    new = read_info(home / ".coffer")
    assert new is not None and new.pid != old.pid and third.status().running
    assert wait_for(lambda: not _alive(old.pid), 5)
    await third.stop()
    token_ok = httpx.post(
        f"http://127.0.0.1:{port}/anthropic/v1/messages",
        content=b"{}",
        headers={"x-api-key": CLAUDE_TOKEN},
        trust_env=False,
    )
    assert token_ok.status_code == 200


def _alive(pid: int) -> bool:
    with contextlib.suppress(ChildProcessError):
        os.waitpid(pid, os.WNOHANG)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True
