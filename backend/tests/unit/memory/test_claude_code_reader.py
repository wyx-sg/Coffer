"""Claude Code's per-fact Markdown files, read into `RawFact`s.

Builds a `<config_dir>/projects/<slug>/memory/` tree under `tmp_path` for
each test; nothing here touches the real `~/.claude`. `tmp_path` is a real
directory, so a slug built from a real project directory under it round-trips
through `resolve_project_slug`'s filesystem walk exactly as a real one would
(the algorithm itself is exercised directly, against a fake in-memory tree,
in `tests/unit/domain/agent/test_native_memory.py`).
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.domain.memory.errors import UnreadableMemory
from coffer.domain.memory.fact import TYPE_FEEDBACK
from coffer.infrastructure.memory.readers.claude_code import ClaudeCodeMemoryReader


def _encode(name: str) -> str:
    return "".join(ch if ch.isalnum() and ch.isascii() else "-" for ch in name)


def _slug_of(project_root: pathlib.Path) -> str:
    parts = [p for p in project_root.parts if p != "/"]
    return "-" + "-".join(_encode(p) for p in parts)


def _memory_dir(
    tmp_path: pathlib.Path, agent_name: str, project_root: pathlib.Path
) -> pathlib.Path:
    config_dir = tmp_path / agent_name
    memory_dir = config_dir / "projects" / _slug_of(project_root) / "memory"
    memory_dir.mkdir(parents=True)
    return memory_dir


_FACT = """---
name: feedback-worktree-development
description: Always develop in a git worktree
metadata:
  node_type: memory
  type: feedback
  originSessionId: abc-123
---

Body prose.

**Why:** because parallel sessions share the repo.
"""


@pytest.mark.acceptance(
    spec="memory", scenario="a Claude Code memory file becomes a normalised fact"
)
def test_a_fact_file_becomes_one_raw_fact(tmp_path: pathlib.Path) -> None:
    project_root = tmp_path / "Users" / "dev" / "my-project"
    project_root.mkdir(parents=True)
    memory_dir = _memory_dir(tmp_path, "claude", project_root)
    (memory_dir / "feedback-worktree-development.md").write_text(_FACT, encoding="utf-8")

    reader = ClaudeCodeMemoryReader()
    sources = reader.sources(str(tmp_path / "claude"))
    assert len(sources) == 1

    facts = reader.read(sources[0])
    assert len(facts) == 1
    fact = facts[0]
    assert fact.title == "feedback-worktree-development"
    assert fact.description == "Always develop in a git worktree"
    assert fact.type == TYPE_FEEDBACK
    assert "Body prose." in fact.body
    assert "---" not in fact.body
    assert fact.anchor == "feedback-worktree-development"
    assert fact.project_root == str(project_root)


def test_memory_index_file_is_ignored(tmp_path: pathlib.Path) -> None:
    project_root = tmp_path / "Users" / "dev" / "indexed-project"
    project_root.mkdir(parents=True)
    memory_dir = _memory_dir(tmp_path, "claude", project_root)
    (memory_dir / "feedback-worktree-development.md").write_text(_FACT, encoding="utf-8")
    (memory_dir / "MEMORY.md").write_text(
        "# Memory\n\n- a roll-up Claude Code regenerates", "utf-8"
    )

    reader = ClaudeCodeMemoryReader()
    sources = reader.sources(str(tmp_path / "claude"))
    assert [pathlib.Path(s.path).name for s in sources] == ["feedback-worktree-development.md"]


def test_a_reference_typed_file_is_skipped(tmp_path: pathlib.Path) -> None:
    project_root = tmp_path / "Users" / "dev" / "ref-project"
    project_root.mkdir(parents=True)
    memory_dir = _memory_dir(tmp_path, "claude", project_root)
    text = _FACT.replace("type: feedback", "type: reference")
    (memory_dir / "some-reference.md").write_text(text, encoding="utf-8")

    reader = ClaudeCodeMemoryReader()
    sources = reader.sources(str(tmp_path / "claude"))
    assert reader.read(sources[0]) == ()


@pytest.mark.acceptance(
    spec="memory", scenario="an agent whose native memory shape is unreadable degrades loudly"
)
@pytest.mark.parametrize(
    "text",
    [
        "no frontmatter fence at all",
        "---\nname: unterminated\ndescription: no closing fence\n",
        "---\nname: [this, is, not, a, mapping]\n---\nbody",
        "---\ndescription: missing the name field\n---\nbody",
    ],
)
def test_malformed_or_incomplete_frontmatter_raises(tmp_path: pathlib.Path, text: str) -> None:
    project_root = tmp_path / "Users" / "dev" / "broken-project"
    project_root.mkdir(parents=True)
    memory_dir = _memory_dir(tmp_path, "claude", project_root)
    bad_file = memory_dir / "broken.md"
    bad_file.write_text(text, encoding="utf-8")

    reader = ClaudeCodeMemoryReader()
    source = reader.sources(str(tmp_path / "claude"))[0]
    with pytest.raises(UnreadableMemory) as exc_info:
        reader.read(source)
    assert exc_info.value.path == str(bad_file)


def test_sources_skips_a_dangling_file_rather_than_dying(tmp_path: pathlib.Path) -> None:
    project_root = tmp_path / "Users" / "dev" / "dangling-project"
    project_root.mkdir(parents=True)
    memory_dir = _memory_dir(tmp_path, "claude", project_root)
    (memory_dir / "good.md").write_text(_FACT, encoding="utf-8")
    (memory_dir / "dangling.md").symlink_to(memory_dir / "does-not-exist.md")

    reader = ClaudeCodeMemoryReader()
    sources = reader.sources(str(tmp_path / "claude"))
    assert [pathlib.Path(s.path).name for s in sources] == ["good.md"]


def test_a_deleted_project_still_yields_a_fact_with_a_best_effort_root(
    tmp_path: pathlib.Path,
) -> None:
    # The project directory named by the slug is never created — as if it
    # had been deleted since Claude Code last wrote to it (FR-005's
    # degrade-loudly is about parsing; a missing *project* root is not a
    # parse failure, so this must not raise).
    config_dir = tmp_path / "claude"
    memory_dir = config_dir / "projects" / "-Users-dev-gone-project" / "memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "feedback-worktree-development.md").write_text(_FACT, encoding="utf-8")

    reader = ClaudeCodeMemoryReader()
    sources = reader.sources(str(config_dir))
    fact = reader.read(sources[0])[0]
    assert fact.project_root  # non-empty best-effort reconstruction, never a crash
