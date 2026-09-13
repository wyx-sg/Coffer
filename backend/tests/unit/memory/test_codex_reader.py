"""Codex's `MEMORY.md` task groups and `memory_summary.md` profile.

Builds a `<config_dir>/memories/` tree under `tmp_path` for each test;
nothing here touches the real `~/.codex`.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.domain.memory.fact import TYPE_PROJECT, TYPE_USER
from coffer.infrastructure.memory.readers.codex import CodexMemoryReader

_MEMORY_MD = """# Task Group: alpha work

scope: do alpha things
applies_to: cwd=/Users/dev/alpha; reuse_rule=recheck the alpha service first

## Task 1: something, success

### rollout_summary_files

- some rollout reference, not a fact

### keywords

- alpha, beta

## User preferences

- prefer X over Y because Z -> always do Z. [Task 1]

## Reusable knowledge

- the alpha service needs W. [Task 1]

## Failures and how to do differently

- Symptom: crashed. Fix: retry with backoff. [Task 1]

# Task Group: beta work with no recorded cwd

scope: something with no applies_to line at all

## Reusable knowledge

- beta needs its own fact here. [Task 1]
"""

_SUMMARY_MD = """v1

## User Profile

The user likes concise Chinese replies and worktree isolation.

## User preferences

- Always ask before merging. [ad-hoc note]

## General Tips

- ignore this section entirely, it is not extracted.
"""


def _write_codex_memories(tmp_path: pathlib.Path) -> pathlib.Path:
    config_dir = tmp_path / "codex"
    memories_dir = config_dir / "memories"
    memories_dir.mkdir(parents=True)
    (memories_dir / "MEMORY.md").write_text(_MEMORY_MD, encoding="utf-8")
    (memories_dir / "memory_summary.md").write_text(_SUMMARY_MD, encoding="utf-8")
    # Must never be read (FR-003): raw transcripts, not distilled memory.
    (memories_dir / "raw_memories.md").write_text("raw transcript dump", encoding="utf-8")
    return config_dir


def test_sources_lists_only_the_two_distilled_files(tmp_path: pathlib.Path) -> None:
    config_dir = _write_codex_memories(tmp_path)
    reader = CodexMemoryReader()
    names = sorted(pathlib.Path(s.path).name for s in reader.sources(str(config_dir)))
    assert names == ["MEMORY.md", "memory_summary.md"]


@pytest.mark.acceptance(
    spec="memory", scenario="a Codex task group becomes normalised facts partitioned by its cwd"
)
def test_a_task_group_becomes_facts_carrying_its_cwd(tmp_path: pathlib.Path) -> None:
    config_dir = _write_codex_memories(tmp_path)
    reader = CodexMemoryReader()
    source = next(s for s in reader.sources(str(config_dir)) if s.path.endswith("MEMORY.md"))
    facts = reader.read(source)

    # 3 facts from "alpha work" (one per fixed bullet section) + 1 from
    # "beta work" (only "Reusable knowledge" has a bullet there).
    assert len(facts) == 4

    alpha_facts = [f for f in facts if f.project_root == "/Users/dev/alpha"]
    assert len(alpha_facts) == 3
    assert {f.type for f in alpha_facts} == {TYPE_USER, TYPE_PROJECT}

    preference = next(f for f in alpha_facts if f.type == TYPE_USER)
    assert preference.title == "prefer X over Y because Z"
    assert preference.body == "prefer X over Y because Z -> always do Z. [Task 1]"
    assert preference.anchor.startswith("alpha work::User preferences::")

    knowledge = next(f for f in alpha_facts if "alpha service" in f.body)
    assert knowledge.title == "the alpha service needs W"

    # "## Task 1: ..." and its "### rollout_summary_files" / "### keywords"
    # subsections must never surface as facts of their own.
    assert not any("rollout reference" in f.body for f in facts)
    assert not any(f.title.startswith("some rollout") for f in facts)


def test_a_group_with_no_recorded_cwd_yields_an_empty_project_root(
    tmp_path: pathlib.Path,
) -> None:
    config_dir = _write_codex_memories(tmp_path)
    reader = CodexMemoryReader()
    source = next(s for s in reader.sources(str(config_dir)) if s.path.endswith("MEMORY.md"))
    facts = reader.read(source)

    beta_facts = [f for f in facts if "beta needs its own fact" in f.body]
    assert len(beta_facts) == 1
    assert beta_facts[0].project_root == ""


@pytest.mark.acceptance(spec="memory", scenario="the Codex profile becomes global facts")
def test_the_profile_becomes_global_facts(tmp_path: pathlib.Path) -> None:
    config_dir = _write_codex_memories(tmp_path)
    reader = CodexMemoryReader()
    source = next(
        s for s in reader.sources(str(config_dir)) if s.path.endswith("memory_summary.md")
    )
    facts = reader.read(source)

    assert len(facts) == 2
    assert all(f.project_root == "" for f in facts)
    assert all(f.type == TYPE_USER for f in facts)

    profile = next(f for f in facts if f.title == "User Profile")
    assert "concise Chinese replies" in profile.body

    preference = next(f for f in facts if f.title != "User Profile")
    assert preference.title == "Always ask before merging"

    # "## General Tips" is Codex's own roll-up of what MEMORY.md already
    # holds and must not be read as facts (FR-004's index-avoidance rule).
    assert not any("ignore this section" in f.body for f in facts)


def test_anchors_are_stable_across_repeated_reads(tmp_path: pathlib.Path) -> None:
    config_dir = _write_codex_memories(tmp_path)
    reader = CodexMemoryReader()
    source = next(s for s in reader.sources(str(config_dir)) if s.path.endswith("MEMORY.md"))
    first = {f.anchor for f in reader.read(source)}
    second = {f.anchor for f in reader.read(source)}
    assert first == second
    assert len(first) == 4  # every fact got a distinct anchor
