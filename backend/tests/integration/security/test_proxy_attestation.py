"""The model proxy proves it is Coffer's before the daemon sends it any key."""

from __future__ import annotations

import contextlib
import json
import os
import signal
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

import coffer
from coffer.domain.model_proxy.state import ProxyState
from coffer.infrastructure.model_proxy import supervisor as sup_mod
from coffer.infrastructure.model_proxy.attest import sign
from coffer.infrastructure.model_proxy.info import ProxyInfo, read_info, write_info
from coffer.infrastructure.model_proxy.supervisor import ProxySupervisor
from tests.integration.model_proxy.conftest import member, state
from tests.integration.model_proxy.harness import free_port

pytestmark = pytest.mark.timeout(60)
KEY = bytes(range(32))
SECRET = "sk-real-attest-test"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    home = tmp_path / "home"
    (home / ".coffer").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("COFFER_LOG_DIR", str(home / "logs"))
    yield home
    info = read_info(home / ".coffer")
    if info is not None and info.pid != os.getpid():
        with contextlib.suppress(ProcessLookupError):
            os.kill(info.pid, signal.SIGKILL)


class _Fake:
    """Answers health with the right version; optionally relays a signature."""

    def __init__(self, port: int, signer_port: int | None = None) -> None:
        self.seen: list[tuple[str, str, bytes]] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a: object) -> None: ...

            def _do(self) -> None:
                n = int(self.headers.get("content-length") or 0)
                body = self.rfile.read(n)
                outer.seen.append((self.command, self.path, body))
                if self.path == "/_coffer/attest" and signer_port is not None:
                    nonce = json.loads(body)["nonce"]
                    out = {"signature": sign(KEY, nonce, signer_port)}
                    code = 200
                elif self.path == "/_coffer/health":
                    out, code = {"version": coffer.__version__, "pid": os.getpid()}, 200
                else:
                    out, code = {}, 404
                data = json.dumps(out).encode()
                self.send_response(code)
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST = do_PUT = _do  # noqa: N815

        self.server = HTTPServer(("127.0.0.1", port), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def received_secret(self) -> bool:
        return any(m == "PUT" or SECRET.encode() in b for m, _, b in self.seen)


def _supervisor(home: Path, port: int, key: bytes | None = KEY, **kw: object) -> ProxySupervisor:
    async def provider() -> ProxyState:
        return state(member("http://127.0.0.1:9", "a", key=SECRET))

    return ProxySupervisor(
        provider,
        port=port,
        coffer_dir=home / ".coffer",
        version=coffer.__version__,
        attest_key=lambda: key,
        env={"HOME": str(home), "COFFER_PROXY_SPOOL_DIR": str(home / "spool")},
        interval=60.0,
        **kw,  # type: ignore[arg-type]
    )


def _plant(home: Path, port: int) -> None:
    write_info(
        ProxyInfo(
            port=port,
            pid=os.getpid(),
            started_at="2026-01-01T00:00:00Z",
            version=coffer.__version__,
            control_token="t" * 20,
        )
    )


async def test_a_proxy_started_by_the_supervisor_attests_and_receives_state(home: Path) -> None:
    sv = _supervisor(home, free_port())
    await sv.start()
    try:
        assert sv.status().running and sv.status().revision == 1
    finally:
        await sv.stop()


@pytest.mark.parametrize("signer", ["none", "other-port"])
async def test_an_impostor_is_never_sent_state(
    home: Path, signer: str, caplog: pytest.LogCaptureFixture
) -> None:
    port = free_port()
    fake = _Fake(port, signer_port=None if signer == "none" else port + 1)
    try:
        _plant(home, port)
        sv = _supervisor(home, port)
        await sv.start()
        await sv.refresh()
        await sv.stop()
    finally:
        fake.close()
    assert not fake.received_secret()
    assert not sv.status().running
    assert "model_proxy.attest_failed" in caplog.text
    assert SECRET not in caplog.text and KEY.hex() not in caplog.text


async def test_a_daemon_without_a_key_pushes_nothing(home: Path) -> None:
    port = free_port()
    fake = _Fake(port, signer_port=port)
    try:
        _plant(home, port)
        sv = _supervisor(home, port, key=None)
        await sv.start()
        await sv.stop()
    finally:
        fake.close()
    assert not fake.received_secret()


def test_the_attest_key_never_travels_in_argv_or_env(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio
    import subprocess

    captured: dict[str, object] = {}

    class _Stdin:
        def __init__(self) -> None:
            self.data = b""

        def write(self, b: bytes) -> None:
            self.data += b

        def close(self) -> None: ...

    class _Proc:
        pid = 1
        returncode = 9
        stdin = _Stdin()

        def poll(self) -> int:
            return 9

    def fake_popen(command: list[str], **kwargs: object) -> _Proc:
        captured.update(command=command, **kwargs)
        return _Proc()

    monkeypatch.setattr(sup_mod.subprocess, "Popen", fake_popen)
    sv = _supervisor(home, free_port())
    with pytest.raises(RuntimeError):
        asyncio.run(sv._spawn())
    hexkey = KEY.hex()
    assert captured["stdin"] == subprocess.PIPE
    assert all(hexkey not in a for a in captured["command"])  # type: ignore[union-attr]
    assert all(hexkey not in v for v in captured["env"].values())  # type: ignore[union-attr]
    assert _Proc.stdin.data == hexkey.encode() + b"\n"


def test_a_proxy_without_a_key_refuses_to_attest() -> None:
    from coffer.infrastructure.model_proxy.app import ModelProxyApp

    app = ModelProxyApp(control_token="t", version="v", started_at="x")
    assert app._attest_key is None
