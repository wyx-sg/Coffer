"""Failover happens only before the first content byte, only to members that
serve the same model, and never on a request's own error."""

from __future__ import annotations

import json

import pytest

from tests.integration.model_proxy.conftest import Proxy, claude_headers, member, state
from tests.integration.model_proxy.harness import free_port, json_reply, sse, sse_reply

BODY = b'{"model":"m1","stream":true}'

START = sse("message_start", {"type": "message_start", "message": {"usage": {"input_tokens": 5}}})
PING = b'event: ping\ndata: {"type": "ping"}\n\n'
CONTENT = sse("content_block_start", {"type": "content_block_start", "index": 0})
DELTA = sse("content_block_delta", {"type": "content_block_delta", "delta": {"text": "x"}})
ERROR = sse("error", {"type": "error", "error": {"type": "overloaded_error", "message": "busy"}})
FINISH = sse("message_delta", {"type": "message_delta", "usage": {"output_tokens": 7}}) + sse(
    "message_stop", {"type": "message_stop"}
)
GOOD = START + CONTENT + DELTA + FINISH


def _post(proxy: Proxy, body: bytes = BODY, **headers: str) -> tuple[int, bytes]:
    r = proxy.client.post("/anthropic/v1/messages", content=body, headers=claude_headers(**headers))
    return r.status_code, r.content


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a failure before the first byte moves to another connection serving the model",
)
def test_5xx_fails_over_and_records_both_attempts(proxy: Proxy, upstreams) -> None:
    bad, bad_srv = upstreams()
    good, good_srv = upstreams()
    bad.script = json_reply(500, {"type": "error"}, headers={"request-id": "req_bad"})
    good.script = sse_reply([GOOD], headers={"request-id": "req_good"})
    proxy.push(state([member(bad_srv, "a"), member(good_srv, "b", models=["m1"])]))
    status, body = _post(proxy)
    assert status == 200 and body == GOOD
    first, second = proxy.records(2)
    assert (first["connection_uid"], first["outcome"], first["failed_over"], first["status"]) == (
        "a",
        "upstream_error",
        True,
        500,
    )
    assert first["dedupe_key"] == "req_bad" and first["usage_known"] is False
    assert (second["connection_uid"], second["outcome"], second["failed_over"]) == (
        "b",
        "completed",
        False,
    )
    assert second["dedupe_key"] == "req_good" and second["output_tokens"] == 7
    assert first["attempt_id"] != second["attempt_id"]


def test_429_with_retry_after_cools_the_member(proxy: Proxy, upstreams) -> None:
    limited, limited_srv = upstreams()
    good, good_srv = upstreams()
    limited.script = json_reply(429, {"type": "error"}, headers={"retry-after": "60"})
    good.script = sse_reply([GOOD])
    proxy.push(state([member(limited_srv, "a"), member(good_srv, "b", models=["m1"])]))
    assert _post(proxy)[0] == 200
    assert _post(proxy)[0] == 200
    assert len(limited.requests) == 1  # benched for 60 s: the second request skipped it
    assert len(good.requests) == 2


def test_pre_content_error_event_fails_over_invisibly(proxy: Proxy, upstreams) -> None:
    flaky, flaky_srv = upstreams()
    good, good_srv = upstreams()
    flaky.script = sse_reply([START, PING, ERROR])
    good.script = sse_reply([GOOD])
    proxy.push(state([member(flaky_srv, "a"), member(good_srv, "b", models=["m1"])]))
    status, body = _post(proxy)
    assert status == 200 and body == GOOD  # nothing of the failed attempt leaked
    first, second = proxy.records(2)
    assert (first["outcome"], first["failed_over"]) == ("error_event", True)
    assert second["outcome"] == "completed"


def test_connect_refused_fails_over(proxy: Proxy, upstreams) -> None:
    good, good_srv = upstreams()
    good.script = sse_reply([GOOD])
    dead = f"http://127.0.0.1:{free_port()}"
    proxy.push(state([member(dead, "a"), member(good_srv, "b", models=["m1"])]))
    status, body = _post(proxy)
    assert status == 200 and body == GOOD
    first, _ = proxy.records(2)
    assert (first["outcome"], first["failed_over"], first["status"]) == (
        "connect_error",
        True,
        None,
    )
    assert first["dedupe_key"] == f"attempt:{first['attempt_id']}"


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="an error after the first content byte is passed to the agent",
)
def test_no_failover_after_the_first_content_byte(proxy: Proxy, upstreams) -> None:
    broken, broken_srv = upstreams()
    other, other_srv = upstreams()
    broken.script = sse_reply([START, CONTENT, DELTA, ERROR])
    other.script = sse_reply([GOOD])
    proxy.push(state([member(broken_srv, "a"), member(other_srv, "b", models=["m1"])]))
    status, body = _post(proxy, **{"x-claude-code-session-id": "s1"})
    assert status == 200 and body == START + CONTENT + DELTA + ERROR  # passed through
    assert other.requests == []
    [rec] = proxy.records(1)
    assert (rec["outcome"], rec["failed_over"], rec["usage_known"]) == ("error_event", False, False)
    # The failure marked the member, so the agent's own retry lands elsewhere.
    assert _post(proxy, **{"x-claude-code-session-id": "s1"}) == (200, GOOD)
    assert len(broken.requests) == 1 and len(other.requests) == 1


def test_truncation_after_content_is_passed_through_and_marks_the_member(
    proxy: Proxy, upstreams
) -> None:
    cut, cut_srv = upstreams()
    cut.script = sse_reply([START, CONTENT, DELTA])  # ends without message_stop
    proxy.push(state([member(cut_srv, "a")]))
    assert _post(proxy) == (200, START + CONTENT + DELTA)
    [rec] = proxy.records(1)
    assert rec["outcome"] == "truncated" and rec["usage_known"] is False
    assert not proxy.app.book.available(proxy.app.state.routes[0].members[0])


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a request problem is never failed over",
)
def test_400_is_relayed_not_failed_over(proxy: Proxy, upstreams) -> None:
    bad, bad_srv = upstreams()
    other, other_srv = upstreams()
    error = {
        "type": "error",
        "error": {"type": "invalid_request_error", "message": "exact wording"},
    }
    bad.script = json_reply(400, error)
    proxy.push(state([member(bad_srv, "a"), member(other_srv, "b", models=["m1"])]))
    status, body = _post(proxy)
    assert status == 400 and json.loads(body) == error
    assert other.requests == []
    [rec] = proxy.records(1)
    assert (rec["outcome"], rec["status"], rec["failed_over"]) == ("upstream_error", 400, False)


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="failover never changes the model",
)
def test_failover_only_to_a_member_listing_the_model(proxy: Proxy, upstreams) -> None:
    bad, bad_srv = upstreams()
    wrong, wrong_srv = upstreams()
    right, right_srv = upstreams()
    bad.script = json_reply(529, {"type": "error"})
    right.script = sse_reply([GOOD])
    proxy.push(
        state(
            [
                member(bad_srv, "a"),
                member(wrong_srv, "b", models=["other-model"]),
                member(wrong_srv, "c"),  # no list: not assumed to serve m1
                member(right_srv, "d", models=["m1"]),
            ]
        )
    )
    assert _post(proxy) == (200, GOOD)
    assert wrong.requests == [] and len(right.requests) == 1
    assert json.loads(right.requests[0].body)["model"] == "m1"  # never substituted


def test_exhausted_pool_relays_the_last_upstream_response(proxy: Proxy, upstreams) -> None:
    bad, bad_srv = upstreams()
    bad.script = json_reply(
        503,
        {"type": "error", "error": {"message": "upstream says no"}},
        headers={"retry-after": "1"},
    )
    dead = f"http://127.0.0.1:{free_port()}"
    proxy.push(state([member(bad_srv, "a"), member(dead, "b", models=["m1"])]))
    r = proxy.client.post("/anthropic/v1/messages", content=BODY, headers=claude_headers())
    assert r.status_code == 503 and r.json()["error"]["message"] == "upstream says no"
    assert r.headers["retry-after"] == "1"


def test_nothing_reachable_is_a_wire_shaped_502(proxy: Proxy, upstreams) -> None:
    proxy.push(state([member(f"http://127.0.0.1:{free_port()}", "a")]))
    r = proxy.client.post("/anthropic/v1/messages", content=BODY, headers=claude_headers())
    assert r.status_code == 502
    assert r.json()["type"] == "error" and r.json()["error"]["type"] == "api_error"


def test_401_disables_the_member_and_moves_on(proxy: Proxy, upstreams) -> None:
    revoked, revoked_srv = upstreams()
    good, good_srv = upstreams()
    revoked.script = json_reply(401, {"type": "error"})
    good.script = sse_reply([GOOD])
    proxy.push(state([member(revoked_srv, "a"), member(good_srv, "b", models=["m1"])]))
    assert _post(proxy) == (200, GOOD)
    assert _post(proxy) == (200, GOOD)
    assert len(revoked.requests) == 1
    # A pushed state with a new key for the member re-enables it.
    proxy.push(
        state(
            [member(revoked_srv, "a", key="sk-fixed"), member(good_srv, "b", models=["m1"])],
            revision=2,
        )
    )
    revoked.script = sse_reply([GOOD])
    assert _post(proxy) == (200, GOOD)
    assert len(revoked.requests) == 2 and revoked.requests[1].all("x-api-key") == ["sk-fixed"]
