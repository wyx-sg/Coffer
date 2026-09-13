"""The read-only proof (FR-002) — worth more than the rest of the suite.

The whole design's load-bearing constraint is that Coffer never writes an
agent's native memory. Every other test here exercises what a reader
extracts; this one exercises the one thing it must never do while extracting
it, across a full `sources()` + `read()` pass over both agents' fixtures.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.infrastructure.memory.readers.claude_code import ClaudeCodeMemoryReader
from coffer.infrastructure.memory.readers.codex import CodexMemoryReader

_CLAUDE_FACT = """---
name: some-fact
description: a description
metadata:
  node_type: memory
  type: project
---

body text
"""

_CODEX_MEMORY_MD = """# Task Group: alpha

applies_to: cwd=/Users/dev/alpha; reuse_rule=recheck

## User preferences

- a preference bullet. [Task 1]
"""

_CODEX_SUMMARY_MD = """v1

## User Profile

Some profile prose.

## User preferences

- a global preference. [ad-hoc]
"""


def _build_fixtures(tmp_path: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    claude_dir = tmp_path / "claude"
    claude_memory = claude_dir / "projects" / "-Users-dev-untouched" / "memory"
    claude_memory.mkdir(parents=True)
    (claude_memory / "some-fact.md").write_text(_CLAUDE_FACT, encoding="utf-8")
    (claude_memory / "MEMORY.md").write_text("# Memory\n\n- roll-up", encoding="utf-8")

    codex_dir = tmp_path / "codex"
    codex_memories = codex_dir / "memories"
    codex_memories.mkdir(parents=True)
    (codex_memories / "MEMORY.md").write_text(_CODEX_MEMORY_MD, encoding="utf-8")
    (codex_memories / "memory_summary.md").write_text(_CODEX_SUMMARY_MD, encoding="utf-8")

    return claude_dir, codex_dir


def _snapshot(root: pathlib.Path) -> dict[str, tuple[bytes, float]]:
    return {
        str(p): (p.read_bytes(), p.stat().st_mtime) for p in sorted(root.rglob("*")) if p.is_file()
    }


@pytest.mark.acceptance(
    spec="memory", scenario="aggregation never modifies an agent's native memory files"
)
def test_a_full_read_leaves_every_fixture_file_untouched(tmp_path: pathlib.Path) -> None:
    claude_dir, codex_dir = _build_fixtures(tmp_path)

    before = _snapshot(tmp_path)
    assert before  # sanity: the snapshot actually saw the fixture files

    claude_reader = ClaudeCodeMemoryReader()
    claude_facts_seen = 0
    for source in claude_reader.sources(str(claude_dir)):
        claude_facts_seen += len(claude_reader.read(source))
    assert claude_facts_seen == 1

    codex_reader = CodexMemoryReader()
    codex_facts_seen = 0
    for source in codex_reader.sources(str(codex_dir)):
        codex_facts_seen += len(codex_reader.read(source))
    assert codex_facts_seen == 3  # 1 group preference + profile + 1 global preference

    after = _snapshot(tmp_path)
    assert after == before
