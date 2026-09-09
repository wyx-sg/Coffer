"""Unit: the SessionStart project-memory digest renderer (FR-055). Pure."""

from __future__ import annotations

from datetime import UTC, datetime

from coffer.application.memory.session_context import render_memory_digest
from coffer.domain.memory.fact import MemoryFact


def _fact(title: str, description: str) -> MemoryFact:
    now = datetime(2026, 7, 1, tzinfo=UTC)
    return MemoryFact(
        id="01J",
        title=title,
        description=description,
        body="body",
        actor="agent",
        created_at=now,
        updated_at=now,
    )


def test_render_includes_facts() -> None:
    out = render_memory_digest([_fact("Auth flow", "how login works")], max_chars=10_000)
    assert "## Project memory (via Coffer)" in out
    # Knowledge is a TITLE-ONLY index (no bodies/descriptions) — agent recalls.
    assert "### Known topics" in out
    assert "- Auth flow" in out
    assert "how login works" not in out


def test_render_empty_when_nothing_to_surface() -> None:
    assert render_memory_digest([], max_chars=10_000) == ""


def test_render_empty_when_no_budget() -> None:
    assert render_memory_digest([_fact("x", "y")], max_chars=0) == ""
    assert render_memory_digest([_fact("x", "y")], max_chars=-5) == ""


def test_render_truncates_to_max_chars() -> None:
    facts = [_fact(f"fact-{i}", "d" * 200) for i in range(50)]
    out = render_memory_digest(facts, max_chars=300)
    assert len(out) == 300


def test_render_collapses_multiline_titles() -> None:
    out = render_memory_digest([_fact("line one\nline two", "d")], max_chars=10_000)
    # A multi-line title becomes a single bullet line (no embedded newline).
    assert "- line one line two" in out
