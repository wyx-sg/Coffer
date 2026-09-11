"""The loopback-Host guard (spec mcp-gateway FR-027).

The daemon's served index.html carries the live API token, so a DNS-rebound
page — one on ``evil.com`` whose hostname resolves to 127.0.0.1, which the
browser therefore treats as same-origin — could otherwise fetch ``/`` and read
the token out of the body. Rebinding does not change the ``Host`` header, so
refusing every non-loopback authority closes it.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from coffer.surfaces.http import host_guard


@pytest.fixture(autouse=True)
def _enforce(monkeypatch: pytest.MonkeyPatch) -> None:
    """The suite-wide ``COFFER_ALLOWED_HOSTS=*`` escape hatch is off in here."""
    monkeypatch.delenv("COFFER_ALLOWED_HOSTS", raising=False)


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/v1/ping")
    async def _ping() -> dict[str, str]:
        return {"pong": "yes"}

    host_guard.install(app)
    return app


@pytest.mark.parametrize(
    "authority",
    ["127.0.0.1", "127.0.0.1:8000", "localhost", "localhost:8003", "[::1]", "[::1]:8000", "::1"],
)
def test_loopback_authorities_are_accepted(authority: str) -> None:
    client = TestClient(_app())
    r = client.get("/api/v1/ping", headers={"Host": authority})
    assert r.status_code == 200, authority


@pytest.mark.acceptance(
    spec="mcp-gateway",
    scenario="a rebound page is refused before it can read the token",
)
@pytest.mark.parametrize(
    "authority",
    [
        "evil.com",
        "evil.com:8000",
        "coffer.evil.com",
        "192.168.1.4:8000",
        "localhost.evil.com",
        "127.0.0.1.evil.com",
    ],
)
def test_non_loopback_authorities_are_refused(authority: str) -> None:
    """Under rebinding the browser still sends the attacker's own hostname."""
    client = TestClient(_app())
    r = client.get("/api/v1/ping", headers={"Host": authority})
    assert r.status_code == 421, authority
    assert r.json()["error"]["code"] == "HOST_NOT_LOOPBACK"


def test_a_request_with_no_host_header_is_refused() -> None:
    """No browser omits Host, so the empty case has nothing legitimate to lose."""
    assert host_guard.is_loopback_authority(None) is False
    assert host_guard.is_loopback_authority("") is False


def test_the_escape_hatch_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    """``COFFER_ALLOWED_HOSTS`` names extra authorities; ``*`` disables the check."""
    assert host_guard.is_loopback_authority("testserver") is False
    monkeypatch.setenv("COFFER_ALLOWED_HOSTS", "testserver")
    assert host_guard.is_loopback_authority("testserver") is True
    assert host_guard.is_loopback_authority("evil.com") is False
    monkeypatch.setenv("COFFER_ALLOWED_HOSTS", "*")
    assert host_guard.is_loopback_authority("evil.com") is True
