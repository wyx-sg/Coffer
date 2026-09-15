"""Unit coverage for the transcript message iterators.

These are the body half of the same parse the browse list does. The property
worth pinning is that the two halves agree: whatever ``parse_*`` counted as a
turn is exactly what ``iter_*_messages`` yields. If they ever drift, a session
lists as six messages and renders five, and nothing on the page says which
number is wrong.

Pure: every case is a list of literal lines, no filesystem.
"""

from __future__ import annotations

import json

from coffer.domain.agent.transcripts import MAX_MESSAGE_CHARS
from coffer.infrastructure.agent.transcript_messages import (
    iter_claude_code_messages,
    iter_codex_messages,
)
from coffer.infrastructure.agent.transcript_reader import parse_claude_code, parse_codex

CLAUDE_LINES = [
    json.dumps({"type": "ai-title", "aiTitle": "Fix the login redirect"}),
    json.dumps(
        {
            "timestamp": "2026-05-01T10:00:00Z",
            "sessionId": "s1",
            "cwd": "/proj",
            "message": {"role": "user", "content": "why is the redirect looping"},
        }
    ),
    json.dumps(
        {
            "timestamp": "2026-05-01T10:00:05Z",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Because the guard runs twice."},
                    {"type": "tool_use", "name": "Read", "input": {}},
                ],
            },
        }
    ),
    # A record whose whole content is a tool call is not a conversational turn.
    json.dumps(
        {
            "timestamp": "2026-05-01T10:00:06Z",
            "message": {"role": "assistant", "content": [{"type": "tool_use", "name": "Edit"}]},
        }
    ),
    "not json at all",
    "",
]

CODEX_LINES = [
    json.dumps(
        {
            "timestamp": "2026-05-01T10:00:00Z",
            "type": "session_meta",
            "payload": {"id": "a", "cwd": "/proj"},
        }
    ),
    json.dumps(
        {
            "timestamp": "2026-05-01T10:00:01Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "add the beta dashboard"}],
            },
        }
    ),
    # The UI's own duplicate of the turn above — dropped, or it is counted twice.
    json.dumps(
        {
            "timestamp": "2026-05-01T10:00:01Z",
            "type": "event_msg",
            "payload": {"type": "user_message"},
        }
    ),
    json.dumps(
        {
            "timestamp": "2026-05-01T10:00:09Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "done"}],
            },
        }
    ),
]


def test_claude_messages_are_exactly_the_turns_the_summary_counted() -> None:
    messages = list(iter_claude_code_messages(CLAUDE_LINES, source_path="/t.jsonl"))
    summary = parse_claude_code(CLAUDE_LINES, source_path="/t.jsonl")
    assert len(messages) == summary.message_count == 2
    assert [m.role for m in messages] == ["user", "assistant"]
    assert messages[0].text == "why is the redirect looping"
    # Tool blocks are dropped from a turn's text but the prose around them stays.
    assert messages[1].text == "Because the guard runs twice."
    assert messages[0].timestamp is not None


def test_codex_messages_are_exactly_the_turns_the_summary_counted() -> None:
    messages = list(iter_codex_messages(CODEX_LINES, source_path="/r.jsonl"))
    summary = parse_codex(CODEX_LINES, source_path="/r.jsonl")
    assert len(messages) == summary.message_count == 2
    assert [(m.role, m.text) for m in messages] == [
        ("user", "add the beta dashboard"),
        ("assistant", "done"),
    ]


def test_codex_live_stream_agent_message_is_attributed_to_the_assistant() -> None:
    lines = [
        json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "shipped"}})
    ]
    assert [(m.role, m.text) for m in iter_codex_messages(lines, source_path="/r.jsonl")] == [
        ("assistant", "shipped")
    ]


def test_a_turn_is_scrubbed_before_it_is_a_value() -> None:
    lines = [
        json.dumps(
            {"message": {"role": "user", "content": "ship it with sk-abcdefghijklmnopqrst now"}}
        )
    ]
    (message,) = iter_claude_code_messages(lines, source_path="/t.jsonl")
    assert "sk-abcdefghijklmnopqrst" not in message.text
    assert "[redacted]" in message.text


def test_an_oversized_turn_is_cut_and_says_so() -> None:
    """One pasted log must not become the size of the page."""
    huge = "x" * (MAX_MESSAGE_CHARS + 500)
    lines = [json.dumps({"message": {"role": "user", "content": huge}})]
    (message,) = iter_claude_code_messages(lines, source_path="/t.jsonl")
    assert message.truncated is True
    assert len(message.text) == MAX_MESSAGE_CHARS


def test_a_window_stops_reading_once_it_is_full() -> None:
    """The iterator is lazy, which is what bounds a 60 MB file to a page of it."""
    consumed = 0

    def lines():
        nonlocal consumed
        for _ in range(1000):
            consumed += 1
            yield json.dumps({"message": {"role": "user", "content": "hi"}})

    window = []
    for message in iter_claude_code_messages(lines(), source_path="/t.jsonl"):
        window.append(message)
        if len(window) == 3:
            break
    assert consumed == 3
