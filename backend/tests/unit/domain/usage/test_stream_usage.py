"""Golden tests for the pure SSE parser and the two usage readers."""

from __future__ import annotations

import json

import pytest

from coffer.domain.usage.stream_usage import (
    AnthropicUsageReader,
    ResponsesUsageReader,
    SseEvent,
    SseParser,
    StreamUsage,
)


def _sse(*events: tuple[str, object]) -> bytes:
    return b"".join(
        f"event: {name}\ndata: {json.dumps(data)}\n\n".encode() for name, data in events
    )


def _feed_bytewise(reader: AnthropicUsageReader | ResponsesUsageReader, raw: bytes) -> None:
    for i in range(len(raw)):
        reader.feed(raw[i : i + 1])


# --- SseParser -------------------------------------------------------------------


@pytest.mark.parametrize("eol", [b"\n", b"\r\n", b"\r"])
def test_parser_handles_every_line_ending(eol: bytes) -> None:
    # A trailing lone CR may be half of a CRLF, so it is only settled by the
    # next byte — the partial third event supplies it.
    raw = b"event: a" + eol + b"data: 1" + eol + eol + b"data: 2" + eol + eol + b"data: 3"
    assert SseParser().feed(raw) == [SseEvent("a", "1"), SseEvent("message", "2")]


def test_parser_reassembles_events_split_at_every_byte() -> None:
    raw = b'event: x\r\ndata: {"k": "\xc3\xa9"}\r\n\r\n: ping\r\n\r\nevent: y\ndata: z\n\n'
    parser = SseParser()
    events: list[SseEvent] = []
    for i in range(len(raw)):
        events.extend(parser.feed(raw[i : i + 1]))
    assert events == [SseEvent("x", '{"k": "é"}'), SseEvent("y", "z")]


def test_parser_skips_comments_and_joins_multiline_data() -> None:
    raw = b": keep-alive\n\ndata: line one\ndata:line two\nid: 7\nretry: 5\n\n"
    assert SseParser().feed(raw) == [SseEvent("message", "line one\nline two")]


def test_parser_holds_an_incomplete_event() -> None:
    parser = SseParser()
    assert parser.feed(b"event: a\ndata: 1\n") == []
    assert parser.feed(b"\n") == [SseEvent("a", "1")]


# --- Anthropic -------------------------------------------------------------------

_START = {
    "type": "message_start",
    "message": {
        "id": "msg_1",
        "usage": {
            "input_tokens": 10,
            "cache_creation_input_tokens": 100,
            "cache_creation": {"ephemeral_5m_input_tokens": 60, "ephemeral_1h_input_tokens": 40},
            "cache_read_input_tokens": 5,
            "output_tokens": 1,
        },
    },
}


def test_message_delta_overrides_message_start() -> None:
    raw = _sse(
        ("message_start", _START),
        ("content_block_start", {"type": "content_block_start", "index": 0}),
        (
            "message_delta",
            {
                "type": "message_delta",
                "usage": {
                    "input_tokens": 12,
                    "cache_creation_input_tokens": 300,  # grew; no new breakdown
                    "cache_read_input_tokens": 7,
                    "output_tokens": 250,
                },
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    )
    reader = AnthropicUsageReader()
    _feed_bytewise(reader, raw)
    assert reader.saw_terminal and reader.first_content_seen and not reader.saw_error_event
    # The final total wins; the part the stale breakdown does not explain is 5m.
    assert reader.usage() == StreamUsage(
        input_tokens=12,
        cache_write_5m_tokens=260,
        cache_write_1h_tokens=40,
        cache_read_tokens=7,
        output_tokens=250,
        reasoning_tokens=None,
        web_search_requests=0,
    )


def test_server_tool_iterations_extend_the_totals() -> None:
    raw = _sse(
        ("message_start", _START),
        ("content_block_start", {"type": "content_block_start"}),
        (
            "message_delta",
            {
                "type": "message_delta",
                "usage": {"output_tokens": 40, "server_tool_use": {"web_search_requests": 1}},
            },
        ),
        (
            "message_delta",
            {
                "type": "message_delta",
                "usage": {
                    "input_tokens": 900,
                    "output_tokens": 120,
                    "cache_creation": {
                        "ephemeral_5m_input_tokens": 70,
                        "ephemeral_1h_input_tokens": 80,
                    },
                    "cache_creation_input_tokens": 150,
                    "server_tool_use": {"web_search_requests": 3},
                    "speed": "fast",
                    "inference_geo": "us",
                },
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    )
    reader = AnthropicUsageReader()
    reader.feed(raw)
    usage = reader.usage()
    assert usage is not None
    assert (usage.input_tokens, usage.output_tokens, usage.web_search_requests) == (900, 120, 3)
    assert (usage.cache_write_5m_tokens, usage.cache_write_1h_tokens) == (70, 80)
    assert (usage.speed, usage.inference_geo) == ("fast", "us")


def test_a_bare_cache_creation_total_counts_as_five_minute_writes() -> None:
    reader = AnthropicUsageReader()
    reader.read_json(
        json.dumps(
            {
                "type": "message",
                "usage": {"input_tokens": 3, "cache_creation_input_tokens": 50, "output_tokens": 9},
            }
        ).encode()
    )
    usage = reader.usage()
    assert usage is not None
    assert (usage.cache_write_5m_tokens, usage.cache_write_1h_tokens) == (50, 0)
    assert usage.cache_read_tokens == 0


def test_truncated_anthropic_stream_has_unknown_usage() -> None:
    reader = AnthropicUsageReader()
    reader.feed(
        _sse(("message_start", _START), ("content_block_start", {"type": "content_block_start"}))
    )
    assert reader.first_content_seen and not reader.saw_terminal
    assert reader.usage() is None


def test_anthropic_error_event_is_flagged_before_content() -> None:
    reader = AnthropicUsageReader()
    reader.feed(_sse(("message_start", _START)) + b": ping\n\n")
    reader.feed(_sse(("error", {"type": "error", "error": {"type": "overloaded_error"}})))
    assert reader.saw_error_event and not reader.first_content_seen
    assert reader.usage() is None


def test_a_malformed_stream_never_raises() -> None:
    reader = AnthropicUsageReader()
    reader.feed(b"event: message_start\ndata: {not json\n\ndata: [1,2]\n\n\xff\xfe\n\n")
    reader.read_json(b"\x00garbage")
    assert reader.usage() is None


# --- Responses -------------------------------------------------------------------

_COMPLETED = {
    "type": "response.completed",
    "response": {
        "id": "resp_1",
        "status": "completed",
        "usage": {
            "input_tokens": 1000,
            "input_tokens_details": {"cached_tokens": 800},
            "output_tokens": 300,
            "output_tokens_details": {"reasoning_tokens": 120},
        },
    },
}


def test_responses_cached_and_reasoning_tokens() -> None:
    raw = _sse(
        ("response.created", {"type": "response.created"}),
        ("response.output_item.added", {"type": "response.output_item.added"}),
        ("response.output_text.delta", {"type": "response.output_text.delta", "delta": "hi"}),
        ("response.completed", _COMPLETED),
    )
    reader = ResponsesUsageReader()
    _feed_bytewise(reader, raw)
    assert reader.first_content_seen and reader.saw_terminal and not reader.saw_error_event
    assert reader.usage() == StreamUsage(
        input_tokens=200, cache_read_tokens=800, output_tokens=300, reasoning_tokens=120
    )


def test_responses_content_starts_at_the_first_delta() -> None:
    reader = ResponsesUsageReader()
    reader.feed(_sse(("response.created", {"type": "response.created"})))
    assert not reader.first_content_seen
    reader.feed(
        _sse(
            (
                "response.reasoning_summary_text.delta",
                {"type": "response.reasoning_summary_text.delta"},
            )
        )
    )
    assert reader.first_content_seen


def test_truncated_responses_stream_has_unknown_usage() -> None:
    reader = ResponsesUsageReader()
    reader.feed(_sse(("response.output_text.delta", {"type": "response.output_text.delta"})))
    assert reader.usage() is None


def test_response_failed_is_terminal_and_an_error() -> None:
    failed = {
        "type": "response.failed",
        "response": {"status": "failed", "usage": {"input_tokens": 5, "output_tokens": 0}},
    }
    reader = ResponsesUsageReader()
    reader.feed(_sse(("response.failed", failed)))
    assert reader.saw_terminal and reader.saw_error_event
    usage = reader.usage()
    assert usage is not None and usage.input_tokens == 5


def test_responses_error_event_is_flagged() -> None:
    reader = ResponsesUsageReader()
    reader.feed(_sse(("error", {"type": "error", "message": "boom"})))
    assert reader.saw_error_event and not reader.saw_terminal


def test_responses_non_streamed_body() -> None:
    reader = ResponsesUsageReader()
    reader.read_json(json.dumps(_COMPLETED["response"] | {"object": "response"}).encode())
    usage = reader.usage()
    assert usage is not None and usage.cache_read_tokens == 800 and usage.input_tokens == 200
    error = ResponsesUsageReader()
    error.read_json(b'{"error": {"message": "bad", "type": "invalid_request_error"}}')
    assert error.saw_error_event and error.usage() is None
