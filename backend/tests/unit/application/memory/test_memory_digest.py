"""Unit: the SessionStart project-memory digest renderer (FR-055). Pure."""

from __future__ import annotations

from datetime import UTC, datetime

from coffer.application.memory.session_context import render_memory_digest
from coffer.domain.memory.fact import MemoryFact
from coffer.domain.memory.journal import JournalEntry


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


def _entry(day: int, body: str) -> JournalEntry:
    return JournalEntry(timestamp=datetime(2026, 7, day, 9, tzinfo=UTC), body=body)


def test_render_includes_journal_and_facts() -> None:
    out = render_memory_digest(
        [_fact("Auth flow", "how login works")],
        [_entry(6, "deployed the gateway")],
        max_chars=10_000,
    )
    assert "## Project memory (via Coffer)" in out
    assert "### Recent activity" in out
    assert "2026-07-06: deployed the gateway" in out
    # Knowledge is a TITLE-ONLY index (no bodies/descriptions) — agent recalls.
    assert "### Known topics" in out
    assert "- Auth flow" in out
    assert "how login works" not in out


def test_render_empty_when_nothing_to_surface() -> None:
    assert render_memory_digest([], [], max_chars=10_000) == ""


def test_render_empty_when_no_budget() -> None:
    assert render_memory_digest([_fact("x", "y")], [_entry(1, "z")], max_chars=0) == ""
    assert render_memory_digest([_fact("x", "y")], [], max_chars=-5) == ""


def test_render_truncates_to_max_chars() -> None:
    facts = [_fact(f"fact-{i}", "d" * 200) for i in range(50)]
    out = render_memory_digest(facts, [], max_chars=300)
    assert len(out) == 300


def test_render_collapses_multiline_bodies() -> None:
    out = render_memory_digest(
        [], [_entry(6, "line one\nline two\n\nline three")], max_chars=10_000
    )
    # A multi-line journal body becomes a single bullet line (no embedded newline).
    assert "- 2026-07-06: line one line two line three" in out
