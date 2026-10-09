"""A secret never follows a redirect to another origin (spec secret "Send a
secret only to the origin it was approved for").

Two real origins on loopback: the first redirects every request to the second,
which records what reaches it. Each test makes one of Coffer's outbound paths
send a secret to the first and then asks the second whether it arrived — in a
header httpx would not strip (``X-API-Key``), in the query, or as git's Basic
credential.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from coffer.domain.mcp.http_api import HttpApiTool, HttpApiTransport
from coffer.domain.mcp.server_config import HttpTransport
from coffer.infrastructure.mcp.http_api_client import build_request, send_request
from coffer.infrastructure.mcp.http_client import HttpUpstreamConnection
from coffer.infrastructure.provider.introspector import ProviderIntrospector
from coffer.infrastructure.vault import git as vault_git
from tests.support.redirect_origins import redirect_origins

SECRET = "sk-redirect-canary-0123456789"


@pytest.mark.acceptance(
    spec="secret", scenario="a redirect to another origin is never sent the secret"
)
async def test_a_custom_tool_does_not_follow_a_redirect_with_its_header() -> None:
    with redirect_origins() as origins:
        transport = HttpApiTransport(base_url=origins.first.url, headers={})
        tool = HttpApiTool(name="get", method="GET", path="/thing")
        request = build_request(
            transport, transport.environments[0], tool, {}, {"X-API-Key": SECRET}
        )
        outcome = await send_request(request, timeout_seconds=5, secrets=[SECRET])
        assert outcome.status == 307
        assert origins.first.received(SECRET)
        assert origins.second.seen == []


async def test_an_http_mcp_upstream_does_not_carry_its_header_to_another_origin() -> None:
    with redirect_origins() as origins:
        connection = HttpUpstreamConnection(
            HttpTransport(url=f"{origins.first.url}/mcp"),
            {"X-API-Key": SECRET},
            spawn_timeout_seconds=5,
        )
        with pytest.raises(Exception):  # noqa: B017 - nothing answers MCP here
            await connection.spawn_and_initialize()
        await connection.close()
        assert origins.first.received(SECRET)
        assert not origins.second.received(SECRET)
        assert origins.second.seen == []


async def test_the_provider_probe_does_not_follow_a_redirect_with_its_key() -> None:
    probe = ProviderIntrospector()
    for provider in ("anthropic", "openai"):
        with redirect_origins() as origins:
            with pytest.raises(Exception):  # noqa: B017
                await probe.list_models(
                    provider=provider, base_url=origins.first.url, api_key=SECRET
                )
            with pytest.raises(Exception):  # noqa: B017
                await probe.test_chat(
                    provider=provider, model="m", base_url=origins.first.url, api_key=SECRET
                )
            assert len(origins.first.seen) >= 2  # both calls really went out
            assert origins.second.seen == []


def _git_origin_requiring_auth() -> tuple[ThreadingHTTPServer, list[dict[str, str]]]:
    seen: list[dict[str, str]] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_: Any) -> None:
            return None

        def do_GET(self) -> None:
            seen.append({k.lower(): v for k, v in self.headers.items()})
            self.send_response(401 if "Authorization" not in self.headers else 404)
            self.send_header("WWW-Authenticate", 'Basic realm="r"')
            self.send_header("Content-Length", "0")
            self.end_headers()

    return ThreadingHTTPServer(("127.0.0.1", 0), Handler), seen


@contextmanager
def _serving(server: ThreadingHTTPServer) -> Iterator[int]:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _ls_remote(root: Path, url: str) -> None:
    vault_git.run(root, "init", "--quiet")
    vault_git.run(root, "ls-remote", "--", url, check=False, token=SECRET, timeout=30)


def test_the_sync_remote_token_is_not_offered_to_a_redirect_target(tmp_path: Path) -> None:
    """git follows the first redirect and asks its credential helper again, for
    the new host: the helper must answer only for the remote's own origin."""
    with redirect_origins(status=302) as origins:
        _ls_remote(tmp_path, f"{origins.first.url}/r.git")
        assert origins.second.seen
        assert not any("authorization" in request for request in origins.second.seen)


def test_no_outbound_client_is_built_to_follow_redirects() -> None:
    """The rule is written down once (``infrastructure/net/redirects``); this
    keeps a new client from breaking it: only the SeaTalk media download (a
    bearer token httpx strips across origins) and ``coffer update``'s release
    download (no credential at all; GitHub answers it with a redirect to its
    file host) may follow, and an SDK-built client names ``follow_redirects``."""
    root = Path(__file__).resolve().parents[3] / "coffer"
    allowed = {
        "infrastructure/channel/seatalk_media.py",
        "infrastructure/daemon/binary_update.py",
    }
    sdk_calls = ("AsyncOpenAI(", "ChatOpenAI(", "ChatAnthropic(")
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        text = path.read_text()
        if "follow_redirects=True" in text and relative not in allowed:
            offenders.append(f"{relative}: follow_redirects=True")
        if any(call in text for call in sdk_calls) and "follow_redirects" not in text:
            offenders.append(f"{relative}: SDK client without follow_redirects=False")
    assert offenders == []


def test_the_sync_remote_token_still_goes_to_the_remote_itself(tmp_path: Path) -> None:
    server, seen = _git_origin_requiring_auth()
    with _serving(server) as port:
        _ls_remote(tmp_path, f"http://127.0.0.1:{port}/r.git")
    assert any("authorization" in request for request in seen)
