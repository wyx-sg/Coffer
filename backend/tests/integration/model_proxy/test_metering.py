"""Usage records written to the spool: tokens per category and attribution."""

from __future__ import annotations

import pytest

from coffer.domain.model_proxy.state import UpstreamAuth
from coffer.domain.usage.records import UsageRecord
from tests.integration.model_proxy.conftest import (
    CODEX_TOKEN,
    Proxy,
    claude_headers,
    member,
    state,
)
from tests.integration.model_proxy.harness import json_reply, sse, sse_reply


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a streamed request is recorded with its tokens by category",
)
def test_responses_stream_records_cached_and_reasoning_tokens(proxy: Proxy, upstreams) -> None:
    up, server = upstreams()
    completed = {
        "type": "response.completed",
        "response": {
            "status": "completed",
            "usage": {
                "input_tokens": 1000,
                "input_tokens_details": {"cached_tokens": 600},
                "output_tokens": 90,
                "output_tokens_details": {"reasoning_tokens": 40},
            },
        },
    }
    up.script = sse_reply(
        [
            sse("response.created", {"type": "response.created"}),
            sse("response.output_text.delta", {"type": "response.output_text.delta", "delta": "x"}),
            sse("response.completed", completed),
        ],
        headers={"x-request-id": "req_oai_1"},
    )
    proxy.push(state(openai=[member(server, "oai", auth=UpstreamAuth.BEARER)]))
    r = proxy.client.post(
        "/openai/v1/responses",
        content=b'{"model":"gpt-5","stream":true}',
        headers={"authorization": f"Bearer {CODEX_TOKEN}", "session_id": "cx"},
    )
    assert r.status_code == 200
    [raw] = proxy.records(1)
    rec = UsageRecord.model_validate(raw)  # the spool line is the shared contract
    assert (rec.input_tokens, rec.cache_read_tokens, rec.output_tokens, rec.reasoning_tokens) == (
        400,
        600,
        90,
        40,
    )
    assert rec.cache_write_5m_tokens is None and rec.usage_known
    assert (rec.dedupe_key, rec.upstream_request_id) == ("req_oai_1", "req_oai_1")
    assert (rec.agent_uid, rec.agent_type, rec.session_id) == ("agent-codex", "codex", "cx")
    assert (rec.wire.value, rec.endpoint, rec.model, rec.member) == (
        "openai",
        "/v1/responses",
        "gpt-5",
        "conn oai",
    )
    assert rec.ttft_ms is not None and rec.duration_ms >= rec.ttft_ms


def test_non_streamed_anthropic_message_is_metered(proxy: Proxy, upstreams) -> None:
    up, server = upstreams()
    up.script = json_reply(
        200,
        {
            "type": "message",
            "usage": {
                "input_tokens": 4,
                "cache_creation_input_tokens": 30,
                "cache_creation": {
                    "ephemeral_5m_input_tokens": 10,
                    "ephemeral_1h_input_tokens": 20,
                },
                "cache_read_input_tokens": 2,
                "output_tokens": 8,
                "server_tool_use": {"web_search_requests": 2},
            },
        },
        headers={"request-id": "req_x"},
    )
    proxy.push(state([member(server, "a")]))
    r = proxy.client.post(
        "/anthropic/v1/messages",
        content=b'{"model":"m1"}',
        headers=claude_headers(
            **{"x-claude-code-session-id": "s", "x-claude-code-request-class": "compaction"}
        ),
    )
    assert r.status_code == 200 and r.json()["type"] == "message"
    [rec] = proxy.records(1)
    assert (
        rec["input_tokens"],
        rec["cache_write_5m_tokens"],
        rec["cache_write_1h_tokens"],
        rec["cache_read_tokens"],
        rec["output_tokens"],
        rec["web_search_requests"],
    ) == (4, 10, 20, 2, 8, 2)
    assert (rec["request_class"], rec["session_id"], rec["stream"]) == ("compaction", "s", False)
    assert rec["outcome"] == "completed" and rec["source"] == "proxy"


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="nothing stored carries a body or a key",
)
def test_spool_lines_never_carry_bodies_or_keys(proxy: Proxy, upstreams) -> None:
    up, server = upstreams()
    up.script = json_reply(200, {"type": "message", "content": "SECRET-COMPLETION", "usage": {}})
    proxy.push(state([member(server, "a", key="sk-SECRET-KEY")]))
    proxy.client.post(
        "/anthropic/v1/messages",
        content=b'{"model":"m1","messages":"SECRET-PROMPT"}',
        headers=claude_headers(),
    )
    proxy.records(1)
    text = "".join(f.read_text() for f in proxy.spool_dir.glob("*.jsonl"))
    assert "SECRET" not in text and "local-claude-token" not in text
