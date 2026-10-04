"""The relay: bytes unchanged, open-list headers, the member's key injected."""

from __future__ import annotations

import json
import random

import pytest

from coffer.domain.model_proxy.state import UpstreamAuth
from tests.integration.model_proxy.conftest import (
    CODEX_TOKEN,
    Proxy,
    claude_headers,
    member,
    state,
)
from tests.integration.model_proxy.harness import free_port, json_reply, sse_reply, wait_for

#: A recorded Anthropic stream: pings, comments, CRLF and LF line endings, a
#: multi-line data field and a trailing unknown event.
RECORDED_SSE = (
    b": proxy keep-alive comment\n\n"
    b'event: message_start\r\ndata: {"type":"message_start","message":{"id":"msg_1",'
    b'"usage":{"input_tokens":11,"cache_read_input_tokens":3,"output_tokens":1}}}\r\n\r\n'
    b'event: ping\ndata: {"type": "ping"}\n\n'
    b'event: content_block_start\ndata: {"type":"content_block_start","index":0,'
    b'"content_block":{"type":"text","text":""}}\n\n'
    b": another comment\n"
    b'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,'
    b'"delta":{"type":"text_delta","text":"h\xc3\xa9llo"}}\n\n'
    b'event: ping\ndata: {"type": "ping"}\n\n'
    b'event: content_block_stop\ndata: {"type":"content_block_stop","index":0}\n\n'
    b'event: message_delta\ndata: {"type":"message_delta","delta":{},'
    b'"usage":{"output_tokens":42}}\n\n'
    b'event: message_stop\ndata: {"type":"message_stop"}\n\n'
    b"event: future_event\ndata: line1\ndata: line2\n\n"
)


def _random_chunks(raw: bytes, seed: int = 7) -> list[bytes]:
    rng = random.Random(seed)
    chunks, i = [], 0
    while i < len(raw):
        n = rng.randint(1, 23)
        chunks.append(raw[i : i + n])
        i += n
    return chunks


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="the proxy relays a stream byte for byte",
)
def test_recorded_sse_is_relayed_byte_for_byte(proxy: Proxy, upstreams) -> None:
    up, server = upstreams()
    up.script = sse_reply(
        _random_chunks(RECORDED_SSE),
        headers={
            "request-id": "req_abc",
            "anthropic-ratelimit-tokens-remaining": "99",
            "retry-after": "2",
            "x-should-retry": "false",
        },
    )
    proxy.push(state(member(server, "a")))
    body = b'{"model":"m1","stream":true,"messages":[]}'
    with proxy.client.stream(
        "POST", "/anthropic/v1/messages", content=body, headers=claude_headers()
    ) as r:
        got = b"".join(r.iter_raw())
        assert r.status_code == 200
        assert r.headers["content-type"] == "text/event-stream"
        assert r.headers["request-id"] == "req_abc"
        assert r.headers["anthropic-ratelimit-tokens-remaining"] == "99"
        assert r.headers["retry-after"] == "2" and r.headers["x-should-retry"] == "false"
        assert "content-encoding" not in r.headers
    assert got == RECORDED_SSE
    [rec] = proxy.records(1)
    assert rec["outcome"] == "completed" and rec["usage_known"] is True
    assert (rec["input_tokens"], rec["cache_read_tokens"], rec["output_tokens"]) == (11, 3, 42)
    assert rec["dedupe_key"] == "req_abc" and rec["stream"] is True


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="unknown anthropic headers and body fields reach the upstream untouched",
)
def test_unknown_headers_and_body_fields_reach_the_upstream_untouched(
    proxy: Proxy, upstreams
) -> None:
    up, server = upstreams()
    up.script = sse_reply([b"event: message_stop\ndata: {}\n\n"])
    proxy.push(state(member(server, "a")))
    # Odd spacing, key order and an unknown field: any re-serialization shows.
    body = b'{ "zz_unknown_field" : {"nested": [1, 2.50, "\\u00e9"]},"model":"m1",  "stream":true }'
    r = proxy.client.post(
        "/anthropic/v1/messages?beta=true",
        content=body,
        headers=claude_headers(
            **{
                "anthropic-beta": "some-unknown-feature-2099-01-01",
                "anthropic-dangerous-direct-browser-access": "maybe",
                "cookie": "session=abc",
                "accept-encoding": "gzip",
                "x-claude-code-session-id": "sess-1",
            }
        ),
    )
    assert r.status_code == 200
    [rec] = up.requests
    assert rec.path == "/v1/messages" and rec.query == b"beta=true"
    assert rec.body == body
    assert rec.header("anthropic-beta") == "some-unknown-feature-2099-01-01"
    assert rec.header("anthropic-dangerous-direct-browser-access") == "maybe"
    assert rec.header("anthropic-version") == "2023-06-01"
    assert rec.header("x-claude-code-session-id") == "sess-1"
    # Client credentials never reach the upstream; the member's key does.
    assert rec.all("x-api-key") == ["sk-real-a"]
    assert rec.all("authorization") == ["Bearer sk-real-a"]
    assert rec.header("cookie") is None
    assert rec.header("accept-encoding") == "identity"
    assert "local-claude-token" not in json.dumps(
        [(k.decode(), v.decode()) for k, v in rec.headers]
    )


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="an upstream error reaches the agent as sent",
)
def test_an_upstream_error_reaches_the_agent_as_sent(proxy: Proxy, upstreams) -> None:
    error = {"type": "error", "error": {"type": "overloaded_error", "message": "busy"}}
    up, server = upstreams()
    up.script = json_reply(503, error, headers={"retry-after": "5"})
    other, _ = upstreams()
    proxy.push(state(member(server, "a")))
    r = proxy.client.post(
        "/anthropic/v1/messages", content=b'{"model":"m1"}', headers=claude_headers()
    )
    assert r.status_code == 503
    assert r.json() == error and r.headers["retry-after"] == "5"
    assert len(up.requests) == 1 and other.requests == []
    [rec] = proxy.records(1)
    assert rec["outcome"] == "upstream_error" and rec["status"] == 503


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="an unreachable upstream is answered with 502",
)
def test_an_unreachable_upstream_is_answered_with_502(proxy: Proxy) -> None:
    proxy.push(state(member(f"http://127.0.0.1:{free_port()}", "a")))
    r = proxy.client.post(
        "/anthropic/v1/messages", content=b'{"model":"m1"}', headers=claude_headers()
    )
    assert r.status_code == 502 and r.json()["type"] == "error"
    [rec] = proxy.records(1)
    assert rec["outcome"] == "connect_error"


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a keyless local runtime gets no key",
)
def test_keyless_local_member_gets_no_auth_header(proxy: Proxy, upstreams) -> None:
    up, server = upstreams()
    proxy.push(state(openai=member(server, "ollama", auth=UpstreamAuth.NONE, local=True)))
    r = proxy.client.post(
        "/openai/v1/responses",
        content=b'{"model":"llama"}',
        headers={"authorization": f"Bearer {CODEX_TOKEN}"},
    )
    assert r.status_code == 200
    [rec] = up.requests
    assert rec.path == "/v1/responses"
    assert rec.header("authorization") is None and rec.header("x-api-key") is None


def test_bearer_member_on_the_responses_route(proxy: Proxy, upstreams) -> None:
    up, server = upstreams()
    proxy.push(state(openai=member(server, "oai", auth=UpstreamAuth.BEARER)))
    r = proxy.client.post(
        "/openai/v1/responses",
        content=b'{"model":"gpt"}',
        headers={"authorization": f"Bearer {CODEX_TOKEN}", "session_id": "cx-1"},
    )
    assert r.status_code == 200
    [rec] = up.requests
    assert rec.all("authorization") == ["Bearer sk-real-oai"] and rec.header("x-api-key") is None
    [usage] = proxy.records(1)
    assert usage["session_id"] == "cx-1" and usage["agent_type"] == "codex"


def test_count_tokens_and_models_are_forwarded_but_not_metered(proxy: Proxy, upstreams) -> None:
    up, server = upstreams()
    proxy.push(state(member(server, "a")))
    r = proxy.client.post(
        "/anthropic/v1/messages/count_tokens", content=b'{"model":"m1"}', headers=claude_headers()
    )
    assert r.status_code == 200
    r = proxy.client.get("/anthropic/v1/models?limit=5", headers=claude_headers())
    assert r.status_code == 200
    assert [(x.method, x.path, x.query) for x in up.requests] == [
        ("POST", "/v1/messages/count_tokens", b""),
        ("GET", "/v1/models", b"limit=5"),
    ]
    assert up.requests[1].all("x-api-key") == ["sk-real-a"]
    assert not wait_for(lambda: bool(list(proxy.spool_dir.glob("*.jsonl"))), timeout=0.5)


def test_client_disconnect_closes_the_upstream(proxy: Proxy, upstreams) -> None:
    up, server = upstreams()
    first = (
        b'event: message_start\ndata: {"type":"message_start","message":{"usage":{}}}\n\n'
        b'event: content_block_start\ndata: {"type":"content_block_start"}\n\n'
    )
    up.script = sse_reply([first], hang_after=True)
    proxy.push(state(member(server, "a")))
    with proxy.client.stream(
        "POST", "/anthropic/v1/messages", content=b'{"stream":true}', headers=claude_headers()
    ) as r:
        assert next(r.iter_raw()).startswith(b"event: message_start")
    assert wait_for(lambda: bool(up.requests) and up.requests[0].disconnected.is_set())
    [rec] = proxy.records(1)
    assert rec["outcome"] == "client_cancel" and rec["usage_known"] is False


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="an unserved model is replaced by the projected default and the rewrite is logged",
)
def test_unserved_model_is_replaced_and_logged(
    proxy: Proxy, upstreams, caplog: pytest.LogCaptureFixture
) -> None:
    up, server = upstreams()
    up.script = json_reply(200, {"usage": {"input_tokens": 1, "output_tokens": 2}})
    proxy.push(
        state(
            openai=member(server, "a", auth=UpstreamAuth.BEARER),
            served=["deepseek-flash", "deepseek-v4-pro"],
            fallback="deepseek-flash",
        )
    )
    body = b'{ "input":"hi", "model" : "gpt-6-luna" , "reasoning":{"effort":"xhigh"} }'
    with caplog.at_level("INFO"):
        r = proxy.client.post(
            "/openai/v1/responses",
            content=body,
            headers={"authorization": f"Bearer {CODEX_TOKEN}"},
        )
    assert r.status_code == 200
    [rec] = up.requests
    assert rec.body == (
        b'{ "input":"hi", "model" : "deepseek-flash" , "reasoning":{"effort":"xhigh"} }'
    )
    line = next(m for m in caplog.messages if m.startswith("model_proxy.model_replaced"))
    assert "requested=gpt-6-luna" in line and "used=deepseek-flash" in line
    assert "agent=agent-codex" in line and "hi" not in line.replace("agent", "")
    [usage] = proxy.records(1)
    assert usage["model"] == "deepseek-flash"


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a served model is forwarded byte for byte",
)
def test_served_model_is_forwarded_untouched(
    proxy: Proxy, upstreams, caplog: pytest.LogCaptureFixture
) -> None:
    up, server = upstreams()
    proxy.push(
        state(
            member(server, "a"),
            served=["deepseek-flash", "deepseek-v4-pro"],
            fallback="deepseek-flash",
        )
    )
    body = b'{ "model" : "deepseek-v4-pro" ,"messages":[]}'
    with caplog.at_level("INFO"):
        r = proxy.client.post("/anthropic/v1/messages", content=body, headers=claude_headers())
    assert r.status_code == 200
    assert up.requests[0].body == body
    assert not any("model_replaced" in m for m in caplog.messages)


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a connection without a curated set is never rewritten",
)
def test_connection_without_curated_set_is_never_rewritten(proxy: Proxy, upstreams) -> None:
    up, server = upstreams()
    proxy.push(state(member(server, "a"), served=[], fallback="deepseek-flash"))
    body = b'{"model":"anything-at-all","messages":[]}'
    r = proxy.client.post(
        "/anthropic/v1/messages/count_tokens", content=body, headers=claude_headers()
    )
    assert r.status_code == 200
    assert up.requests[0].body == body


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="an unserved Claude model falls back to its tier's model",
)
def test_unserved_claude_model_takes_its_tier_model_on_the_anthropic_wire_only(
    proxy: Proxy, upstreams
) -> None:
    up, server = upstreams()
    tiers = {"haiku": "deepseek-flash", "sonnet": "deepseek-v4-pro"}
    proxy.push(
        state(
            member(server, "a"),
            member(server, "a", auth=UpstreamAuth.BEARER),
            served=["deepseek-flash", "deepseek-v4-pro", "deepseek-chat"],
            fallback="deepseek-chat",
            tiers=tiers,
        )
    )
    r = proxy.client.post(
        "/anthropic/v1/messages",
        content=b'{"model":"claude-haiku-4-5","messages":[]}',
        headers=claude_headers(),
    )
    assert r.status_code == 200
    assert up.requests[0].body == b'{"model":"deepseek-flash","messages":[]}'
    # No tier keyword: the default.
    proxy.client.post(
        "/anthropic/v1/messages", content=b'{"model":"gpt-6-luna"}', headers=claude_headers()
    )
    assert up.requests[1].body == b'{"model":"deepseek-chat"}'
    # The Codex wire ignores tiers even when the route carries them.
    proxy.client.post(
        "/openai/v1/responses",
        content=b'{"model":"gpt-haiku-x"}',
        headers={"authorization": f"Bearer {CODEX_TOKEN}"},
    )
    assert up.requests[2].body == b'{"model":"deepseek-chat"}'
