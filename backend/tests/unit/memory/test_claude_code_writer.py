"""The lines Coffer writes about each copy into Claude Code's ``MEMORY.md``
block and ``rules/coffer-memory.md`` (spec memory "Write global memories into
a Claude Code global project and point at them from a rules file")."""

from __future__ import annotations

import pathlib

from coffer.domain.memory.hub import CODEX, TYPE_USER, HubEntry, Origin
from coffer.domain.memory.sync_plan import CopyRecord, Target
from coffer.infrastructure.memory.writers.claude_code import (
    GLOBAL_ROOT,
    ClaudeCodeMemoryWriter,
    memory_dir,
)

# A Codex bullet: its title is its first clause, its description all of it.
_BULLET = "keep account knowledge in `shopee-account`; generic knowledge goes in `shopee-platform`."


def _entry(eid: str, title: str, description: str) -> HubEntry:
    return HubEntry(
        id=eid,
        origin=Origin(machine="m", agent=CODEX, source="MEMORY.md::g::User preferences::1"),
        project="",
        type=TYPE_USER,
        title=title,
        description=description,
        body=description,
        created_at="2026-10-16T00:00:00Z",
        updated_at=f"2026-10-16T00:00:0{eid[-1]}Z",
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
