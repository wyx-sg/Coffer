"""The shim names the Coffer-run turn its agent process belongs to (spec
mcp-gateway "Let an agent ask the owner a question during a Coffer turn").

A turn's agent process has ``COFFER_TURN_TOKEN`` in its environment; the shim
forwards it as ``X-Coffer-Turn`` on every request to ``/mcp`` — including the
handshake replayed after a daemon restart — and sends nothing when the variable
is unset (an agent started in a terminal).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.application.turn_ask import TURN_HEADER, TURN_TOKEN_ENV
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.shim.main import _Bridge


def _info() -> DaemonInfo:
    return DaemonInfo(
        version=1,
        pid=1,
        port=18000,
        token="t",
        started_at=datetime.now(tz=UTC),
        binary_path="/usr/bin/python3",
    )


def test_the_environment_names_the_header_and_the_variable() -> None:
    # The names are contract: the Codex entry passes the variable through, the
    # gateway reads the header.
    assert TURN_TOKEN_ENV == "COFFER_TURN_TOKEN"
    assert TURN_HEADER == "X-Coffer-Turn"


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="an agent in a Coffer turn sees and calls coffer__ask"
)
def test_the_turn_token_rides_every_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TURN_TOKEN_ENV, "abc123")
    bridge = _Bridge(_info())
    assert bridge._request_headers()[TURN_HEADER] == "abc123"
    assert bridge._request_headers()["X-Coffer-Token"] == "t"
    bridge._session_id = "sess"
    headers = bridge._request_headers()
    assert headers[TURN_HEADER] == "abc123" and headers["Mcp-Session-Id"] == "sess"
    # The client the bridge posts with is built from the same headers (the SSE
    # stream and the replayed handshake included).
    assert bridge._headers[TURN_HEADER] == "abc123"


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="coffer__ask is not offered outside a Coffer turn"
)
def test_no_turn_token_means_no_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(TURN_TOKEN_ENV, raising=False)
    assert TURN_HEADER not in _Bridge(_info())._request_headers()
    monkeypatch.setenv(TURN_TOKEN_ENV, "")
    assert TURN_HEADER not in _Bridge(_info())._request_headers()
