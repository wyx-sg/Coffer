"""Codex's `MEMORY.md` task groups and `memory_summary.md` profile (FR-004).

Builds a `<config_dir>/memories/` tree under `tmp_path` for each test; nothing
here touches the real `~/.codex`.

The part worth the most attention is the **search terms**. Codex is the one
source that states, in its own voice, what it would look each task group up
by, and the previous design threw that away and left retrieval to guesswork.
The terms live in `memory_summary.md` and the material they describe lives in
`MEMORY.md`, so the reader joins the two on the group's title — a join Codex
does not make exact for it, since it re-words a title when it summarises it.
The join is therefore deliberately conservative: a wrong attribution is worse
than none, so terms travel only when exactly one group clears the bar and
exactly one topic claims that group.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.domain.memory.note import TYPE_PROJECT, TYPE_USER
from coffer.infrastructure.memory.readers.codex import CodexMemoryReader

_MEMORY_MD = """# Task Group: alpha service configuration and rollout

scope: do alpha things
applies_to: cwd=/Users/dev/alpha; reuse_rule=recheck the alpha service first

## Task 1: something, success

### rollout_summary_files

- some rollout reference, not an entry

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

- beta needs its own entry here. [Task 1]

# Task Group: gamma pipeline ingestion latency

applies_to: cwd=/Users/dev/gamma

## Reusable knowledge

- the gamma pipeline batches at 500. [Task 2]
"""

_SUMMARY_MD = """v1

## User Profile

The user likes concise Chinese replies and worktree isolation.

## User preferences

- Always ask before merging. [ad-hoc note]

## What's in Memory

### /Users/dev/alpha

- alpha service configuration rollout: `alpha service`, `rollout`
  - desc: what was done in the alpha service
  - learnings: recheck the service first

### /Users/dev/gamma

- gamma pipeline ingestion latency: `gamma latency`
  - desc: one half of the gamma work
- gamma pipeline ingestion: `gamma batching`
  - desc: the other half, summarised separately

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
    (memories_dir / "rollout_summaries").mkdir()
    return config_dir


def _memory_source(reader: CodexMemoryReader, config_dir: pathlib.Path):  # type: ignore[no-untyped-def]
    return next(s for s in reader.sources(str(config_dir)) if s.path.endswith("MEMORY.md"))


def _summary_source(reader: CodexMemoryReader, config_dir: pathlib.Path):  # type: ignore[no-untyped-def]
    return next(s for s in reader.sources(str(config_dir)) if s.path.endswith("memory_summary.md"))


def test_sources_lists_only_the_two_distilled_files(tmp_path: pathlib.Path) -> None:
    config_dir = _write_codex_memories(tmp_path)
    reader = CodexMemoryReader()
    names = sorted(pathlib.Path(s.path).name for s in reader.sources(str(config_dir)))
    assert names == ["MEMORY.md", "memory_summary.md"]


def test_sources_of_an_agent_with_no_memories_directory_is_empty(tmp_path: pathlib.Path) -> None:
    assert CodexMemoryReader().sources(str(tmp_path / "never-configured")) == ()


@pytest.mark.acceptance(
    spec="memory",
    scenario="a Codex task group becomes raw entries carrying its own search terms",
)
def test_a_task_group_becomes_one_entry_per_populated_bullet_section(
    tmp_path: pathlib.Path,
) -> None:
    config_dir = _write_codex_memories(tmp_path)
    reader = CodexMemoryReader()

    entries = reader.read(_memory_source(reader, config_dir))

    # 3 from the alpha group (one per populated fixed section), 1 from beta,
    # 1 from gamma.
    assert len(entries) == 5

    alpha = [e for e in entries if e.project_root == "/Users/dev/alpha"]
    assert len(alpha) == 3
    assert {e.type for e in alpha} == {TYPE_USER, TYPE_PROJECT}

    preference = next(e for e in alpha if e.type == TYPE_USER)
    assert preference.title == "prefer X over Y because Z"
    assert preference.body == "prefer X over Y because Z -> always do Z. [Task 1]"
    assert preference.anchor.startswith(
        "alpha service configuration and rollout::User preferences::"
    )

    knowledge = next(e for e in alpha if "alpha service needs" in e.body)
    assert knowledge.title == "the alpha service needs W"
    assert knowledge.type == TYPE_PROJECT


@pytest.mark.acceptance(
    spec="memory",
    scenario="a Codex task group becomes raw entries carrying its own search terms",
)
def test_each_entry_carries_the_search_terms_its_groups_summary_states(
    tmp_path: pathlib.Path,
) -> None:
    """The source's own answer to "what would you look this up by" (FR-004),
    which the index line then restates (FR-029)."""
    config_dir = _write_codex_memories(tmp_path)
    reader = CodexMemoryReader()

    entries = reader.read(_memory_source(reader, config_dir))

    alpha = [e for e in entries if e.project_root == "/Users/dev/alpha"]
    assert alpha
    assert all(e.search_terms == ("alpha service", "rollout") for e in alpha)


def test_terms_are_declined_rather_than_guessed_when_two_topics_claim_one_group(
    tmp_path: pathlib.Path,
) -> None:
    """A wrong attribution is worse than none: two summary topics landing on
    one group is an ambiguity, and neither claim survives it."""
    config_dir = _write_codex_memories(tmp_path)
    reader = CodexMemoryReader()

    entries = reader.read(_memory_source(reader, config_dir))

    gamma = [e for e in entries if e.project_root == "/Users/dev/gamma"]
    assert len(gamma) == 1
    assert gamma[0].search_terms == ()


@pytest.mark.acceptance(
    spec="memory",
    scenario="a Codex task group becomes raw entries carrying its own search terms",
)
def test_a_groups_rollout_reference_subsections_never_surface_as_entries(
    tmp_path: pathlib.Path,
) -> None:
    config_dir = _write_codex_memories(tmp_path)
    reader = CodexMemoryReader()

    entries = reader.read(_memory_source(reader, config_dir))

    assert not any("rollout reference" in e.body for e in entries)
    assert not any(e.title.startswith("some rollout") for e in entries)
    assert not any(e.body == "alpha, beta" for e in entries)


def test_a_group_with_no_recorded_cwd_yields_an_empty_project_root(
    tmp_path: pathlib.Path,
) -> None:
    config_dir = _write_codex_memories(tmp_path)
    reader = CodexMemoryReader()

    entries = reader.read(_memory_source(reader, config_dir))

    beta = [e for e in entries if "beta needs its own entry" in e.body]
    assert len(beta) == 1
    assert beta[0].project_root == ""


@pytest.mark.acceptance(spec="memory", scenario="the Codex profile becomes global raw entries")
def test_the_profile_becomes_entries_with_an_empty_project_root(tmp_path: pathlib.Path) -> None:
    config_dir = _write_codex_memories(tmp_path)
    reader = CodexMemoryReader()

    entries = reader.read(_summary_source(reader, config_dir))

    assert len(entries) == 2
    # An empty project root is what files them into ``global`` (FR-011).
    assert all(e.project_root == "" for e in entries)
    assert all(e.type == TYPE_USER for e in entries)

    profile = next(e for e in entries if e.title == "User Profile")
    assert "concise Chinese replies" in profile.body

    preference = next(e for e in entries if e.title != "User Profile")
    assert preference.title == "Always ask before merging"


@pytest.mark.acceptance(spec="memory", scenario="the Codex profile becomes global raw entries")
def test_the_summarys_general_tips_roll_up_is_not_read_as_entries(
    tmp_path: pathlib.Path,
) -> None:
    config_dir = _write_codex_memories(tmp_path)
    reader = CodexMemoryReader()

    entries = reader.read(_summary_source(reader, config_dir))

    assert not any("ignore this section" in e.body for e in entries)
    assert not any("What's in Memory" in e.title for e in entries)


def test_the_profile_states_no_search_terms_because_codex_states_none_for_it(
    tmp_path: pathlib.Path,
) -> None:
    config_dir = _write_codex_memories(tmp_path)
    reader = CodexMemoryReader()
    entries = reader.read(_summary_source(reader, config_dir))
    assert all(e.search_terms == () for e in entries)


def test_anchors_are_stable_across_repeated_reads(tmp_path: pathlib.Path) -> None:
    """The anchor is half of a note's provenance and the name a raw entry
    keeps under ``.raw/`` (FR-009), so a re-read of unchanged text must
    produce the same one."""
    config_dir = _write_codex_memories(tmp_path)
    reader = CodexMemoryReader()
    source = _memory_source(reader, config_dir)

    first = {e.anchor for e in reader.read(source)}
    second = {e.anchor for e in reader.read(source)}

    assert first == second
    assert len(first) == 5  # every entry got a distinct anchor


def test_a_missing_sibling_summary_costs_the_terms_not_the_entries(
    tmp_path: pathlib.Path,
) -> None:
    config_dir = tmp_path / "codex"
    memories_dir = config_dir / "memories"
    memories_dir.mkdir(parents=True)
    (memories_dir / "MEMORY.md").write_text(_MEMORY_MD, encoding="utf-8")

    reader = CodexMemoryReader()
    entries = reader.read(_memory_source(reader, config_dir))

    assert len(entries) == 5
    assert all(e.search_terms == () for e in entries)


def test_a_long_bullet_gets_a_trimmed_handle_and_keeps_its_whole_body(
    tmp_path: pathlib.Path,
) -> None:
    """The title is a handle for the distil pass, not a title a person reads
    — the note's title is Coffer's to write (FR-020)."""
    long_bullet = "x" * 300
    config_dir = tmp_path / "codex"
    memories_dir = config_dir / "memories"
    memories_dir.mkdir(parents=True)
    (memories_dir / "MEMORY.md").write_text(
        f"# Task Group: long\n\napplies_to: cwd=/Users/dev/long\n\n"
        f"## Reusable knowledge\n\n- {long_bullet}\n",
        encoding="utf-8",
    )

    reader = CodexMemoryReader()
    (entry,) = reader.read(_memory_source(reader, config_dir))

    assert len(entry.title) == 100
    assert entry.title.endswith("...")
    assert entry.body == long_bullet
