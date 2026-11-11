"""Codex's v2 memory (``memories_v2/memory_summary.md``), read beside v1 (spec
memory "Read Codex's v2 memory")."""

from __future__ import annotations

import pathlib

import pytest

from coffer.domain.agent.codex_memory import parse_codex_v2_topics
from coffer.domain.memory.hub import TYPE_PROJECT, TYPE_USER
from coffer.domain.memory.reader import RawEntry
from coffer.infrastructure.agent_files.codex_rollout_summaries import header_cwd
from coffer.infrastructure.memory.readers.codex import CodexMemoryReader

V2 = """v1

## User Profile

The user runs payments operations.

## User preferences

- Lead with the point. [ad-hoc note]
- Prefers CLI over browser.

## General Tips

Separate evidence from hypotheses.

For delivery, inspect the diff. [via Coffer]

## What's in Memory

### Payments ledger
#### 2026-11-02
- rollout_summaries/a.md — Ledger retries are idempotent; use before replaying; thread_id=t-1
  - PR: payments!42 merged.
- rollout_summaries/../../etc/passwd.md — Pointer that leaves the folder; thread_id=t-2

### Older Memory Topics
#### Historic programs
- SPB-66270 buffered UserID history; thread_id=t-3
"""

V1_SUMMARY = """## User Profile

An older profile.

## User preferences

- Prefers CLI over browser.
- Only v1 knows this.
"""


def _codex(tmp_path: pathlib.Path, *, v1_summary: str | None = None) -> pathlib.Path:
    v2 = tmp_path / "memories_v2"
    (v2 / "rollout_summaries").mkdir(parents=True)
    (v2 / "memory_summary.md").write_text(V2, encoding="utf-8")
    (v2 / "rollout_summaries" / "a.md").write_text(
        "thread_id: t-1\nupdated_at: x\nrollout_path: /r.jsonl\ncwd: /Users/dev/payments\n\n"
        "cwd: /not/the/header\n",
        encoding="utf-8",
    )
    if v1_summary is not None:
        (tmp_path / "memories").mkdir()
        (tmp_path / "memories" / "memory_summary.md").write_text(v1_summary, encoding="utf-8")
    return tmp_path


def _read(config: pathlib.Path) -> dict[str, list[RawEntry]]:
    reader = CodexMemoryReader()
    return {
        pathlib.Path(s.path).relative_to(config).as_posix(): list(reader.read(s))
        for s in reader.sources(str(config))
    }


def test_the_v2_summary_is_a_source(tmp_path: pathlib.Path) -> None:
    config = _codex(tmp_path)
    assert list(_read(config)) == ["memories_v2/memory_summary.md"]


def test_v2_yields_profile_preferences_tips_and_topics(tmp_path: pathlib.Path) -> None:
    entries = _read(_codex(tmp_path))["memories_v2/memory_summary.md"]
    by_title = {e.title: e for e in entries}
    assert by_title["User Profile"].type == TYPE_USER
    assert "Lead with the point" in by_title
    tip = by_title["Separate evidence from hypotheses"]
    assert tip.type == TYPE_PROJECT and tip.project_root == ""
    assert not any("inspect the diff" in e.body for e in entries)
    topic = by_title["Ledger retries are idempotent"]
    assert topic.type == TYPE_PROJECT
    assert topic.project_root == "/Users/dev/payments"
    assert "PR: payments!42 merged." in topic.body
    assert topic.anchor.startswith("Payments ledger::What's in Memory::")
    (escape,) = [e for e in entries if "Pointer that leaves the folder" in e.body]
    assert escape.project_root == ""
    assert by_title["SPB-66270 buffered UserID history"].anchor.startswith("Historic programs::")


@pytest.mark.acceptance(
    spec="memory", scenario="with v2 beside it, v1's summary gives only what v2 does not say"
)
def test_with_v2_beside_it_v1_gives_only_what_v2_does_not_say(tmp_path: pathlib.Path) -> None:
    v1 = _read(_codex(tmp_path, v1_summary=V1_SUMMARY))["memories/memory_summary.md"]
    assert [e.body for e in v1] == ["Only v1 knows this."]


def test_topics_are_parsed_with_scope_date_and_pointer() -> None:
    topics = parse_codex_v2_topics(V2)
    assert [(t.scope, t.date, t.rollout_file) for t in topics] == [
        ("Payments ledger", "2026-11-02", "a.md"),
        ("Payments ledger", "2026-11-02", ""),
        ("Historic programs", "", ""),
    ]
    assert topics[0].text == "Ledger retries are idempotent; use before replaying"


def test_only_the_header_names_the_cwd() -> None:
    assert header_cwd("thread_id: t\ncwd: /a\n\nbody") == "/a"
    assert header_cwd("thread_id: t\n\ncwd: /in/the/body") == ""
