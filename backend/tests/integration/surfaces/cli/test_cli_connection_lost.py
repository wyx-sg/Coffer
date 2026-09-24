"""A daemon that goes away mid-command is reported, not dumped as a traceback.

spec mcp-gateway "Manage MCP servers as resources": the CLI exits with code 3 and
names the condition when no daemon is reachable. Detect-or-spawn covers a daemon
that is absent when the command starts; this covers one that stops answering
after the client was built.
"""

from __future__ import annotations

import socket
import sys
import threading
from collections.abc import Iterator

import httpx
import pytest

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli import main as cli_main


def _closed_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.mark.acceptance(spec="mcp-gateway", scenario="a daemon lost mid-command exits 3")
def test_a_connection_lost_mid_command_exits_3_with_a_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    client = httpx.Client(base_url=f"http://127.0.0.1:{_closed_port()}/api/v1", timeout=2)
    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (client, object()))
    monkeypatch.setattr(sys, "argv", ["coffer", "mcp", "list"])

    with pytest.raises(SystemExit) as exc:
        cli_main.run()

    assert exc.value.code == 3
    err = capsys.readouterr().err
    assert err.count("daemon not reachable") == 1
    assert "Traceback" not in err


@pytest.fixture
def dropping_port() -> Iterator[int]:
    """A server that accepts a connection, reads the request, and closes the
    socket without answering — a daemon dying mid-request, which httpx reports
    as a transport error other than ``ConnectError``."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    stop = threading.Event()

    def serve() -> None:
        server.settimeout(0.2)
        while not stop.is_set():
            try:
                conn, _ = server.accept()
            except OSError:
                continue
            with conn:
                conn.recv(65536)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield int(server.getsockname()[1])
    finally:
        stop.set()
        thread.join(timeout=2)
        server.close()


@pytest.mark.acceptance(spec="mcp-gateway", scenario="a daemon lost mid-command exits 3")
def test_a_connection_dropped_mid_request_exits_3_with_a_message(
    dropping_port: int, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    client = httpx.Client(base_url=f"http://127.0.0.1:{dropping_port}/api/v1", timeout=2)
    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (client, object()))
    monkeypatch.setattr(sys, "argv", ["coffer", "mcp", "list"])

    with pytest.raises(SystemExit) as exc:
        cli_main.run()

    assert exc.value.code == 3
    err = capsys.readouterr().err
    assert err.count("daemon not reachable") == 1
    assert "Traceback" not in err


def test_render_http_error_maps_every_transport_error_to_daemon_unreachable(
    capsys: pytest.CaptureFixture[str],
) -> None:
    for err in (
        httpx.RemoteProtocolError("Server disconnected without sending a response."),
        httpx.ReadError("connection reset"),
        httpx.ReadTimeout("timed out"),
    ):
        code = _cli_client.render_http_error(err, verbose=False)
        assert code == _cli_client.ExitCode.DAEMON_UNREACHABLE
        assert "daemon not reachable" in capsys.readouterr().err
