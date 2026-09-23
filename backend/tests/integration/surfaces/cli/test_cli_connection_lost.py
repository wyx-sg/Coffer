"""A daemon that goes away mid-command is reported, not dumped as a traceback.

spec mcp-gateway "Manage MCP servers as resources": the CLI exits with code 3 and
names the condition when no daemon is reachable. Detect-or-spawn covers a daemon
that is absent when the command starts; this covers one that stops answering
after the client was built.
"""

from __future__ import annotations

import socket
import sys

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
