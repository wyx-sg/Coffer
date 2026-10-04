"""What the proxy refuses: foreign Host, any Origin, foreign secrets,
unknown routes — and its control routes."""

from __future__ import annotations

import pytest

from coffer.domain.model_proxy.state import CONTROL_TOKEN_HEADER
from tests.integration.model_proxy.conftest import (
    CLAUDE_TOKEN,
    CONTROL,
    Proxy,
    claude_headers,
    member,
    state,
)

BODY = b'{"model":"m1"}'


@pytest.fixture
def live(proxy: Proxy, upstreams):
    up, server = upstreams()
    proxy.push(state(member(server, "a")))
    return proxy, up


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a foreign Host or an Origin is refused",
)
def test_foreign_host_is_refused(live) -> None:
    proxy, up = live
    for host in ("evil.example", f"evil.example:{proxy.server.port}", "127.0.0.1:1"):
        r = proxy.client.post(
            "/anthropic/v1/messages", content=BODY, headers=claude_headers(host=host)
        )
        assert r.status_code == 403 and r.json()["type"] == "error"
    r = proxy.client.post(
        "/anthropic/v1/messages",
        content=BODY,
        headers=claude_headers(host=f"localhost:{proxy.server.port}"),
    )
    assert r.status_code == 200
    assert len(up.requests) == 1


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a foreign Host or an Origin is refused",
)
def test_any_origin_is_refused(live) -> None:
    proxy, up = live
    for origin in ("https://evil.example", f"http://127.0.0.1:{proxy.server.port}", "null"):
        r = proxy.client.post(
            "/anthropic/v1/messages", content=BODY, headers=claude_headers(origin=origin)
        )
        assert r.status_code == 403
    r = proxy.client.get(
        "/_coffer/health", headers={CONTROL_TOKEN_HEADER: CONTROL, "origin": "https://evil.example"}
    )
    assert r.status_code == 403
    assert up.requests == []


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"authorization": "Bearer sk-ant-oat01-" + "x" * 60},
        {"x-api-key": "sk-ant-api03-real-provider-key"},
        {"authorization": f"Basic {CLAUDE_TOKEN}"},
        # A valid token beside a foreign secret is still a foreign secret.
        {"x-api-key": CLAUDE_TOKEN, "authorization": "Bearer sk-ant-oat01-abc"},
    ],
    ids=["none", "oauth", "provider-key", "basic", "mixed"],
)
@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a request without a Coffer token is refused",
)
def test_anything_but_the_agent_token_is_401_and_nothing_is_forwarded(live, headers) -> None:
    proxy, up = live
    r = proxy.client.post("/anthropic/v1/messages", content=BODY, headers=headers)
    assert r.status_code == 401
    assert r.json()["type"] == "error" and r.json()["error"]["type"] == "authentication_error"
    r = proxy.client.post("/openai/v1/responses", content=BODY, headers=headers)
    assert r.status_code == 401 and "error" in r.json() and "type" not in r.json()
    assert up.requests == []


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a rotated token replaces the old one",
)
def test_token_rotation(live, upstreams) -> None:
    proxy, _up = live
    _, server = upstreams()
    assert (
        proxy.client.post(
            "/anthropic/v1/messages", content=BODY, headers=claude_headers()
        ).status_code
        == 200
    )
    new_token = "rotated-" + "z" * 40
    proxy.push(state(member(server, "a"), revision=2, claude_token=new_token))
    assert (
        proxy.client.post(
            "/anthropic/v1/messages", content=BODY, headers=claude_headers()
        ).status_code
        == 401
    )
    assert (
        proxy.client.post(
            "/anthropic/v1/messages", content=BODY, headers=claude_headers(new_token)
        ).status_code
        == 200
    )


def test_either_credential_header_alone_is_accepted(live) -> None:
    proxy, _ = live
    for headers in ({"x-api-key": CLAUDE_TOKEN}, {"authorization": f"Bearer {CLAUDE_TOKEN}"}):
        assert (
            proxy.client.post("/anthropic/v1/messages", content=BODY, headers=headers).status_code
            == 200
        )


def test_no_active_connection_is_a_wire_shaped_503(live) -> None:
    proxy, _ = live
    r = proxy.client.post(
        "/openai/v1/responses",
        content=BODY,
        headers={"authorization": "Bearer local-codex-token-" + "b" * 40},
    )
    assert (
        r.status_code == 503 and "No API-key connection is active" in r.json()["error"]["message"]
    )


def test_routes_outside_the_surface_are_404(live) -> None:
    proxy, up = live
    for method, path in [
        ("POST", "/v1/messages"),
        ("GET", "/anthropic/v1/messages"),
        ("POST", "/openai/v1/chat/completions"),
        ("GET", "/"),
    ]:
        r = proxy.client.request(method, path, headers=claude_headers())
        assert r.status_code == 404, path
    assert up.requests == []


def test_hello_needs_no_auth(live) -> None:
    proxy, _ = live
    for path in ("/api/hello", "/anthropic/api/hello"):
        assert proxy.client.head(path).status_code == 200
        assert proxy.client.get(path).status_code == 200


def test_control_routes_need_the_control_token(live) -> None:
    proxy, _ = live
    assert proxy.client.get("/_coffer/health").status_code == 401
    assert (
        proxy.client.get("/_coffer/health", headers={CONTROL_TOKEN_HEADER: "wrong"}).status_code
        == 401
    )
    assert proxy.client.put("/_coffer/state", content=b"{}").status_code == 401
    r = proxy.client.get("/_coffer/health", headers={CONTROL_TOKEN_HEADER: CONTROL})
    body = r.json()
    assert r.status_code == 200 and body["version"] == "test" and body["revision"] == 1
    assert set(body) >= {"version", "pid", "revision", "inflight", "started_at"}
    bad = proxy.client.put(
        "/_coffer/state", content=b'{"routes": 3}', headers={CONTROL_TOKEN_HEADER: CONTROL}
    )
    assert bad.status_code == 400


def test_drain_refuses_new_requests_and_signals_once_idle(live) -> None:
    proxy, up = live
    r = proxy.client.post("/_coffer/drain", headers={CONTROL_TOKEN_HEADER: CONTROL})
    assert r.status_code == 202
    assert proxy.app.drained == [True]  # type: ignore[attr-defined]
    r = proxy.client.post("/anthropic/v1/messages", content=BODY, headers=claude_headers())
    assert r.status_code == 503 and r.json()["type"] == "error"
    assert up.requests == []
