"""Unit tests for distillation prompt builder and insight parser."""

from __future__ import annotations

from coffer.application.distill.prompt import build_prompt, parse_insights
from coffer.domain.distill.session import TranscriptMessage, TranscriptSession


def test_build_prompt_includes_conversation_and_asks_for_json() -> None:
    s = TranscriptSession(
        session_id="s",
        agent_type_value="codex",
        project_path="/r",
        started_at=None,
        messages=(TranscriptMessage(role="user", text="why redis?"),),
        source_path="/x",
    )
    system, user = build_prompt(s)
    assert "JSON" in system
    assert "why redis?" in user


def test_parse_insights_tolerates_fenced_json() -> None:
    raw = (
        "```json\n"
        '[{"name":"Use Redis","description":"cache",'
        '"body":"We chose Redis for caching."}]\n'
        "```"
    )
    out = parse_insights(raw)
    assert len(out) == 1
    assert out[0].name == "Use Redis"
    assert out[0].body == "We chose Redis for caching."


def test_parse_insights_empty_on_garbage() -> None:
    assert parse_insights("the model refused") == []
