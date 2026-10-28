"""The lines Coffer writes about each copy into Claude Code's ``MEMORY.md``
block and ``rules/coffer-memory.md`` (spec memory "Write global memories into
a Claude Code global project and point at them from a rules file")."""

from __future__ import annotations

import pathlib

import pytest

from coffer.domain.memory.hub import CODEX, TYPE_USER, HubEntry, Origin
from coffer.domain.memory.sync_plan import CopyRecord, Target
from coffer.infrastructure.memory.writers.claude_code import (
    GLOBAL_ROOT,
    RULES_LINE_TEXT,
    RULES_MAX_BYTES,
    ClaudeCodeMemoryWriter,
    memory_dir,
)

#: A preference from Codex's summary, and a bullet of one of its task groups.
_PREFERENCE = "memories/memory_summary.md::profile::User preferences::1"
_PROFILE = "memories/memory_summary.md::profile::user-profile"


def _group(name: str) -> str:
    return f"memories/MEMORY.md::{name}::User preferences::1"


# A Codex bullet: its title is its first clause, its description all of it.
_BULLET = "keep account knowledge in `shopee-account`; generic knowledge goes in `shopee-platform`."


def _entry(
    eid: str, title: str, description: str, source: str = _PREFERENCE, updated: str = ""
) -> HubEntry:
    return HubEntry(
        id=eid,
        origin=Origin(machine="m", agent=CODEX, source=source),
        project="",
        type=TYPE_USER,
        title=title,
        description=description,
        body=description,
        created_at="2026-10-16T00:00:00Z",
        updated_at=updated or f"2026-10-16T00:00:0{eid[-1]}Z",
    )


def _aux(tmp_path: pathlib.Path, entries: list[HubEntry]) -> dict[str, str]:
    config_dir = str(tmp_path)
    folder = memory_dir(config_dir, GLOBAL_ROOT)
    targets = {e.id: Target(e, None, e.body) for e in entries}
    copies = {
        str(folder / f"coffer_{e.id}.md"): CopyRecord(
            str(folder / f"coffer_{e.id}.md"), e.id, "", ""
        )
        for e in entries
    }
    writes = ClaudeCodeMemoryWriter().aux(config_dir, copies, targets, list(targets.values()))
    return {pathlib.Path(w.path).name: w.content or "" for w in writes}


def test_a_title_that_opens_its_description_is_not_repeated(tmp_path: pathlib.Path) -> None:
    out = _aux(tmp_path, [_entry("e1", "keep account knowledge in `shopee-account`", _BULLET)])

    rules = out["coffer-memory.md"]
    assert rules.count("keep account knowledge") == 1
    assert "- **keep account knowledge in `shopee-account`**; generic knowledge goes in" in rules
    index = out["MEMORY.md"]
    assert index.count("keep account knowledge") == 1
    assert "(coffer_e1.md) — generic knowledge goes in `shopee-platform`. (from Codex)" in index


def test_a_cut_off_title_gives_way_to_its_description(tmp_path: pathlib.Path) -> None:
    out = _aux(tmp_path, [_entry("e2", "keep account knowledge in...", _BULLET)])

    rules = out["coffer-memory.md"]
    assert f"- {_BULLET} (" in rules
    assert rules.count("keep account knowledge") == 1


def test_a_description_equal_to_its_title_is_written_once(tmp_path: pathlib.Path) -> None:
    out = _aux(tmp_path, [_entry("e3", "prefers Chinese", "prefers Chinese")])

    assert out["coffer-memory.md"].count("prefers Chinese") == 1
    assert out["MEMORY.md"].count("prefers Chinese") == 1


def test_a_separate_description_still_follows_its_title(tmp_path: pathlib.Path) -> None:
    out = _aux(tmp_path, [_entry("e4", "Reply language", "The user wants replies in Chinese.")])

    assert "- **Reply language**: The user wants replies in Chinese. (" in out["coffer-memory.md"]
    assert "(coffer_e4.md) — The user wants replies in Chinese. (from Codex)" in out["MEMORY.md"]


@pytest.mark.acceptance(
    spec="memory", scenario="a Codex task memory is named by its topic, not listed"
)
def test_task_memories_are_named_by_topic_not_listed(tmp_path: pathlib.Path) -> None:
    out = _aux(
        tmp_path,
        [
            _entry("e1", "Prefers Chinese", "Prefers Chinese"),
            _entry("e2", "leave Optimised? blank", "leave Optimised? blank", _group("IA sheet")),
            _entry("e3", "keep remarks terse", "keep remarks terse", _group("IA sheet")),
        ],
    )

    rules = out["coffer-memory.md"]
    assert "- **Prefers Chinese** (coffer_e1.md)" in rules
    assert "Optimised" not in rules and "terse" not in rules
    assert "Topics: IA sheet (2)." in rules
    index = out["MEMORY.md"]
    standing, ia = index.index("## About the person"), index.index("## IA sheet")
    assert standing < index.index("(coffer_e1.md)") < ia < index.index("(coffer_e2.md)")
    assert ia < index.index("(coffer_e3.md)")


def test_the_profile_comes_first_and_lines_stay_short(tmp_path: pathlib.Path) -> None:
    profile = _entry("p0", "User Profile", "The user is a backend developer. " * 20, _PROFILE)
    newer = _entry("e9", "Prefers Chinese", "Prefers Chinese")

    rules = _aux(tmp_path, [newer, profile])["coffer-memory.md"]

    assert rules.index("**User Profile**") < rules.index("**Prefers Chinese**")
    line = next(ln for ln in rules.splitlines() if "User Profile" in ln)
    text = line.removeprefix("- ").removesuffix(" (coffer_p0.md)").replace("**", "")
    assert len(text) <= RULES_LINE_TEXT


@pytest.mark.acceptance(spec="memory", scenario="the rules file stays bounded")
def test_the_rules_file_is_bounded_and_names_the_rest(tmp_path: pathlib.Path) -> None:
    entries = [
        _entry(
            f"e{i:03d}",
            f"Preference number {i}",
            f"Preference number {i}; " + "x" * 200,
            updated=f"2026-10-16T00:{i // 60:02d}:{i % 60:02d}Z",
        )
        for i in range(200)
    ]
    entries.append(_entry("t1", "a task note", "a task note", _group("Release")))

    rules = _aux(tmp_path, entries)["coffer-memory.md"]

    assert len(rules.encode("utf-8")) <= RULES_MAX_BYTES
    assert "Preference number 199" in rules and "Preference number 0 " not in rules
    assert "more, listed in" in rules
    assert "Topics: Release (1)." in rules
