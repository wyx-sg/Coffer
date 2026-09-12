"""Unit tests for the Claude Code + Codex transcript parsers."""

from __future__ import annotations

import json
from datetime import UTC

from coffer.infrastructure.agent.transcript_parsers import _parse_iso
from coffer.infrastructure.agent.transcript_reader import parse_claude_code, parse_codex

CLAUDE = [
    json.dumps(
        {
            "type": "user",
            "cwd": "/repo",
            "sessionId": "s1",
            "timestamp": "2026-06-01T00:00:00Z",
            "message": {"role": "user", "content": "set up auth"},
        }
    ),
    json.dumps(
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "I'll use JWT."},
                    {"type": "tool_use", "name": "Bash", "input": {"command": "echo SECRET"}},
                ],
            },
        }
    ),
    '{"oops": "unparseable-but-survives"}',
]


def test_parse_claude_counts_text_turns_and_keeps_metadata() -> None:
    s = parse_claude_code(CLAUDE, source_path="/a.jsonl")
    assert s.project_path == "/repo"
    assert s.session_id == "s1"
    assert s.agent_type_value == "claude_code"
    assert s.message_count == 2  # user + assistant; the metadata-only line is not a turn
    assert s.title == "set up auth"


def test_parse_claude_tool_only_record_is_not_a_turn() -> None:
    """A record whose content is purely tool_use carries no text — not a turn."""
    lines = [
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}],
                },
            }
        ),
    ]
    s = parse_claude_code(lines, source_path="/tools.jsonl")
    assert s.message_count == 0


def test_parse_claude_falls_back_to_source_path_when_no_session_id() -> None:
    s = parse_claude_code(["not json at all"], source_path="/no-id.jsonl")
    assert s.session_id == "/no-id.jsonl"
    assert s.message_count == 0
    assert s.title is None


def test_parse_codex_defensive() -> None:
    lines = [
        '{"type":"session_meta","cwd":"/repo","id":"c1"}',
        '{"type":"message","role":"user","content":"hi"}',
        "not json",
        '{"type":"message","role":"assistant","content":"hello"}',
    ]
    s = parse_codex(lines, source_path="/b.jsonl")
    assert s.project_path == "/repo"
    assert s.session_id == "c1"
    assert s.message_count == 2  # the non-JSON line is skipped, not fatal


def test_parse_codex_list_of_blocks_content() -> None:
    """parse_codex handles content as a list of typed blocks (real rollout format)."""
    lines = [
        '{"type":"session_meta","cwd":"/repo","id":"c2"}',
        json.dumps(
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "What is the deploy process?"},
                    {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
                ],
            }
        ),
        json.dumps(
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Run make release to deploy."}],
            }
        ),
    ]
    s = parse_codex(lines, source_path="/c.jsonl")
    assert s.message_count == 2
    assert s.title == "What is the deploy process?"


def test_parse_codex_real_rollout_payload_format() -> None:
    """Real Codex rollout wraps every event in a ``payload`` envelope.

    cwd/id live in ``session_meta.payload``; turns are ``response_item`` events
    whose ``payload.type == "message"``. The duplicate ``event_msg``
    user_message/agent_message UI events MUST NOT be double-counted.
    """
    lines = [
        json.dumps(
            {
                "timestamp": "2026-05-10T16:55:56Z",
                "type": "session_meta",
                "payload": {"id": "sess-1", "cwd": "/Users/x/proj"},
            }
        ),
        json.dumps(
            {
                "timestamp": "2026-05-10T16:56:00Z",
                "type": "event_msg",
                "payload": {"type": "task_started"},
            }
        ),
        json.dumps(
            {
                "timestamp": "2026-05-10T16:56:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "add a retry helper"}],
                },
            }
        ),
        json.dumps(
            {
                "timestamp": "2026-05-10T16:56:05Z",
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "add a retry helper"},
            }
        ),
        json.dumps(
            {
                "timestamp": "2026-05-10T16:56:30Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "Done, added retry()."}],
                },
            }
        ),
        json.dumps(
            {
                "timestamp": "2026-05-10T16:56:31Z",
                "type": "event_msg",
                "payload": {"type": "agent_message", "message": "Done, added retry()."},
            }
        ),
    ]
    s = parse_codex(lines, source_path="/x.jsonl")
    assert s.project_path == "/Users/x/proj"
    assert s.session_id == "sess-1"
    assert s.message_count == 2  # event_msg not double-counted
    assert s.title == "add a retry helper"
    assert s.started_at is not None
    assert s.last_activity_at is not None
    assert s.last_activity_at > s.started_at


def test_parse_codex_live_stream_item_completed() -> None:
    """The ``codex exec --json`` live shape counts agent_message items only."""
    lines = [
        json.dumps({"type": "thread.started", "thread_id": "t1", "cwd": "/repo"}),
        json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "hi"}}),
        json.dumps({"type": "item.completed", "item": {"type": "command_execution"}}),
    ]
    s = parse_codex(lines, source_path="/live.jsonl")
    assert s.session_id == "t1"
    assert s.project_path == "/repo"
    assert s.message_count == 1


def test_parse_codex_title_skips_noise_preamble() -> None:
    """The title skips environment/instructions blocks and slash commands,
    taking the first *real* user message — without dropping those turns from
    the count."""
    lines = [
        json.dumps({"type": "session_meta", "payload": {"id": "s2", "cwd": "/repo"}}),
        json.dumps(
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "<environment_context>\n/repo\n</environment_context>",
                        }
                    ],
                },
            }
        ),
        json.dumps(
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "<command-name>/clear</command-name>"}
                    ],
                },
            }
        ),
        json.dumps(
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "修复登录重定向 bug"}],
                },
            }
        ),
    ]
    s = parse_codex(lines, source_path="/y.jsonl")
    assert s.title == "修复登录重定向 bug"
    assert s.message_count == 3  # only title-derivation skips noise; turns are kept


def test_parse_claude_ai_title_latest_wins_and_last_activity() -> None:
    """Claude Code stores its own ``ai-title`` (updated over time); latest wins,
    and last_activity_at tracks the final timestamped event."""
    lines = [
        json.dumps(
            {
                "type": "user",
                "cwd": "/repo",
                "sessionId": "c1",
                "timestamp": "2026-06-01T00:00:00Z",
                "message": {"role": "user", "content": "start"},
            }
        ),
        json.dumps({"type": "ai-title", "aiTitle": "Initial title", "sessionId": "c1"}),
        json.dumps(
            {
                "type": "assistant",
                "timestamp": "2026-06-01T00:05:00Z",
                "message": {"role": "assistant", "content": [{"type": "text", "text": "ok"}]},
            }
        ),
        json.dumps({"type": "ai-title", "aiTitle": "Refine auth flow", "sessionId": "c1"}),
    ]
    s = parse_claude_code(lines, source_path="/c.jsonl")
    assert s.title == "Refine auth flow"
    assert s.started_at is not None
    assert s.last_activity_at is not None
    assert s.last_activity_at > s.started_at


def test_parse_claude_title_falls_back_to_first_user_message() -> None:
    """With no ai-title line, the title falls back to the first real user msg."""
    lines = [
        json.dumps(
            {
                "type": "user",
                "cwd": "/repo",
                "sessionId": "c2",
                "timestamp": "2026-06-01T00:00:00Z",
                "message": {"role": "user", "content": "Refactor the payment module"},
            }
        ),
        json.dumps(
            {
                "type": "assistant",
                "message": {"role": "assistant", "content": [{"type": "text", "text": "sure"}]},
            }
        ),
    ]
    s = parse_claude_code(lines, source_path="/d.jsonl")
    assert s.title == "Refactor the payment module"


def test_title_is_one_truncated_line_with_secrets_redacted() -> None:
    """A pasted key must not travel to the UI inside the title, and a long
    first line is capped to a single short line."""
    long_prompt = "rotate sk-abcdefghijklmnopqrstuvwxyz now " + ("x" * 200) + "\nsecond line"
    lines = [
        json.dumps(
            {
                "type": "user",
                "cwd": "/repo",
                "sessionId": "c3",
                "message": {"role": "user", "content": long_prompt},
            }
        ),
    ]
    s = parse_claude_code(lines, source_path="/e.jsonl")
    assert s.title is not None
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in s.title
    assert "[redacted]" in s.title
    assert len(s.title) <= 80
    assert s.title.endswith("…")
    assert "second line" not in s.title


def test_parse_iso_bare_timestamp_is_tz_aware() -> None:
    """Bare timestamps become tz-aware (UTC) so cross-session sorts never mix."""
    dt = _parse_iso("2026-01-01T10:00:00")  # no offset
    assert dt is not None
    assert dt.tzinfo == UTC

    dt2 = _parse_iso("2026-06-01T00:00:00Z")  # Z suffix
    assert dt2 is not None
    assert dt2.tzinfo is not None

    assert _parse_iso("not-a-timestamp") is None
    assert _parse_iso(None) is None
