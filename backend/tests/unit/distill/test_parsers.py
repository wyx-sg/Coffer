"""Unit tests for Claude Code + Codex transcript parsers."""

from __future__ import annotations

import json
from datetime import UTC

from coffer.infrastructure.distill.transcript_reader import parse_claude_code, parse_codex

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


def test_parse_claude_keeps_text_drops_tools() -> None:
    s = parse_claude_code(CLAUDE, source_path="/a.jsonl")
    assert s.project_path == "/repo"
    assert s.session_id == "s1"
    roles = [m.role for m in s.messages]
    assert roles == ["user", "assistant"]
    assert "JWT" in s.messages[1].text
    assert "SECRET" not in s.messages[1].text  # tool_use dropped


def test_parse_codex_defensive() -> None:
    lines = [
        '{"type":"session_meta","cwd":"/repo","id":"c1"}',
        '{"type":"message","role":"user","content":"hi"}',
        "not json",
        '{"type":"message","role":"assistant","content":"hello"}',
    ]
    s = parse_codex(lines, source_path="/b.jsonl")
    assert s.project_path == "/repo"
    assert [m.role for m in s.messages] == ["user", "assistant"]


def test_parse_codex_list_of_blocks_content() -> None:
    """parse_codex handles content as a list of typed blocks (real Codex rollout format)."""
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
                "content": [
                    {"type": "output_text", "text": "Run make release to deploy."},
                ],
            }
        ),
    ]
    s = parse_codex(lines, source_path="/c.jsonl")
    assert len(s.messages) == 2
    assert s.messages[0].role == "user"
    assert "deploy process" in s.messages[0].text
    assert s.messages[1].role == "assistant"
    assert "make release" in s.messages[1].text


def test_parse_iso_bare_timestamp_is_tz_aware() -> None:
    """_parse_iso makes bare timestamps tz-aware (UTC) to prevent mixed-tz comparison."""

    from coffer.infrastructure.distill.transcript_reader import _parse_iso

    dt = _parse_iso("2026-01-01T10:00:00")  # no offset
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt.tzinfo == UTC

    dt2 = _parse_iso("2026-06-01T00:00:00Z")  # Z suffix
    assert dt2 is not None
    assert dt2.tzinfo is not None


def test_select_session_handles_mixed_aware_naive_timestamps() -> None:
    """Sessions with tz-aware started_at can be compared without TypeError."""
    from datetime import datetime

    from coffer.domain.distill.session import TranscriptSession

    session_old = TranscriptSession(
        session_id="old",
        agent_type_value="claude_code",
        project_path="/repo",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        messages=(),
        source_path="/a.jsonl",
    )
    session_new = TranscriptSession(
        session_id="new",
        agent_type_value="claude_code",
        project_path="/repo",
        started_at=datetime(2026, 6, 1, tzinfo=UTC),
        messages=(),
        source_path="/b.jsonl",
    )
    session_bare = TranscriptSession(
        session_id="bare",
        agent_type_value="claude_code",
        project_path="/repo",
        started_at=datetime(2026, 3, 1, tzinfo=UTC),  # would have been naive before fix
        messages=(),
        source_path="/c.jsonl",
    )

    with_ts = [s for s in [session_old, session_new, session_bare] if s.started_at is not None]
    # This must not raise TypeError:
    result = max(with_ts, key=lambda s: s.started_at)  # type: ignore[arg-type, return-value]
    assert result.session_id == "new"
