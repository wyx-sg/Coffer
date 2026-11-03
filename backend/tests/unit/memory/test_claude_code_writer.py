"""The text Coffer writes into Claude Code: a project's ``MEMORY.md`` block and
``rules/coffer-memory.md`` (spec memory "Write the hub into Claude Code as text
it loads")."""

from __future__ import annotations

import pathlib

import pytest

from coffer.domain.memory.hub import CLAUDE_CODE, CODEX, TYPE_USER, HubEntry, Origin
from coffer.domain.memory.sync_plan import CopyRecord, Target
from coffer.infrastructure.memory.writers.claude_code import (
    BLOCK_BEGIN,
    BLOCK_END,
    GLOBAL_ROOT,
    ClaudeCodeMemoryWriter,
    memory_dir,
)
from coffer.infrastructure.memory.writers.claude_code_lines import (
    BLOCK_MAX_BYTES,
    MEMORY_TEXT_MAX,
    RULES_MAX_BYTES,
)

_PREFERENCE = "memories/memory_summary.md::profile::User preferences::1"
_PROFILE = "memories/memory_summary.md::profile::user-profile"
_PROJECT = "github.com/acme/payments"

# A Codex bullet: its title is its first clause, its description all of it.
_BULLET = "keep account knowledge in `shopee-account`; generic knowledge goes in `shopee-platform`."


def _entry(
    eid: str,
    title: str,
    body: str,
    *,
    source: str = _PREFERENCE,
    agent: str = CODEX,
    project: str = "",
    updated: str = "",
) -> HubEntry:
    return HubEntry(
        id=eid,
        origin=Origin(machine="m", agent=agent, source=source),
        project=project,
        type=TYPE_USER,
        title=title,
        description=body,
        body=body,
        created_at="2026-10-16T00:00:00Z",
        updated_at=updated or f"2026-10-16T00:00:0{eid[-1]}Z",
    )


def _aux(
    tmp_path: pathlib.Path,
    entries: list[HubEntry],
    root: str | None = None,
    copies: dict[str, CopyRecord] | None = None,
) -> dict[str, str]:
    config_dir = str(tmp_path)
    targets = [Target(e, root if e.project else None, e.body) for e in entries]
    writes = ClaudeCodeMemoryWriter().aux(
        config_dir, copies or {}, {t.entry.id: t for t in targets}, targets
    )
    return {w.path: w.content or "" for w in writes}


def _rules(tmp_path: pathlib.Path) -> str:
    return str(tmp_path / "rules" / "coffer-memory.md")


def test_no_memory_is_written_as_a_file_of_its_own() -> None:
    entry = _entry("a1", "Reply in Chinese", "Reply in Chinese")
    assert not ClaudeCodeMemoryWriter().wants(Target(entry, None, entry.body))


@pytest.mark.acceptance(spec="memory", scenario="a Codex profile reaches every Claude Code session")
def test_the_rules_file_holds_each_global_memory_s_text_profile_first(
    tmp_path: pathlib.Path,
) -> None:
    rules = _aux(
        tmp_path,
        [
            _entry("a2", "Reply in Chinese", "Reply in Chinese, keep code identifiers in English."),
            _entry(
                "a1",
                "User Profile",
                "A backend engineer who works on Shopee accounts.",
                source=_PROFILE,
            ),
        ],
    )[_rules(tmp_path)]
    body = rules.split("\n\n", 3)[-1]
    lines = [line for line in body.splitlines() if line.startswith("- ")]
    assert "A backend engineer who works on Shopee accounts." in lines[0]
    assert "Reply in Chinese, keep code identifiers in English. (from Codex)" in lines[1]
    assert "coffer_" not in rules


def test_a_title_that_opens_its_text_is_not_repeated(tmp_path: pathlib.Path) -> None:
    rules = _aux(tmp_path, [_entry("a1", "keep account knowledge in `shopee-account`", _BULLET)])
    assert f"- {_BULLET} (from Codex)" in rules[_rules(tmp_path)]


def test_a_title_the_text_does_not_open_with_leads_in_bold(tmp_path: pathlib.Path) -> None:
    rules = _aux(
        tmp_path,
        [_entry("a1", "Testing", "Integration tests hit a real database.", agent=CLAUDE_CODE)],
    )
    assert (
        "- **Testing**: Integration tests hit a real database. (from Claude Code)"
        in rules[_rules(tmp_path)]
    )


def test_one_memory_s_text_is_bounded(tmp_path: pathlib.Path) -> None:
    rules = _aux(tmp_path, [_entry("a1", "Long", "word " * 1000)])[_rules(tmp_path)]
    line = next(line for line in rules.splitlines() if line.startswith("- "))
    assert len(line) <= MEMORY_TEXT_MAX + len("- ") + len(" (from Codex)")


@pytest.mark.acceptance(spec="memory", scenario="the rules file stays bounded")
def test_the_rules_file_is_bounded_and_names_the_rest(tmp_path: pathlib.Path) -> None:
    entries = [_entry(f"b{i:02d}", f"Preference {i}", "x" * 400) for i in range(40)]
    rules = _aux(tmp_path, entries)[_rules(tmp_path)]
    assert len(rules.encode("utf-8")) <= RULES_MAX_BYTES
    assert "more: `coffer memory entries --project global` lists them." in rules


@pytest.mark.acceptance(spec="memory", scenario="a project's memories reach only that project")
def test_project_memories_go_into_that_project_s_block_not_the_rules_file(
    tmp_path: pathlib.Path,
) -> None:
    root = "/work/payments"
    writes = _aux(
        tmp_path,
        [_entry("p1", "Sessions", "Session TTL is 30 minutes.", project=_PROJECT)],
        root=root,
    )
    index = str(memory_dir(str(tmp_path), root) / "MEMORY.md")
    assert set(writes) == {index}
    block = writes[index]
    assert block.startswith(BLOCK_BEGIN)
    assert "- **Sessions**: Session TTL is 30 minutes. (from Codex)" in block
    assert block.rstrip().endswith(BLOCK_END)


def test_a_project_block_is_bounded(tmp_path: pathlib.Path) -> None:
    root = "/work/payments"
    entries = [_entry(f"p{i:02d}", f"Note {i}", "y" * 400, project=_PROJECT) for i in range(30)]
    block = next(iter(_aux(tmp_path, entries, root=root).values()))
    inner = block.split(BLOCK_BEGIN, 1)[1].split(BLOCK_END, 1)[0]
    assert len(inner.encode("utf-8")) <= BLOCK_MAX_BYTES + 2
    assert f"`coffer memory entries --project {_PROJECT}`" in inner


def test_an_earlier_build_s_global_folder_block_is_emptied(tmp_path: pathlib.Path) -> None:
    folder = memory_dir(str(tmp_path), GLOBAL_ROOT)
    folder.mkdir(parents=True)
    (folder / "MEMORY.md").write_text(f"{BLOCK_BEGIN}\n- old line\n{BLOCK_END}\n")
    writes = _aux(tmp_path, [_entry("a1", "Reply in Chinese", "Reply in Chinese")])
    assert writes[str(folder / "MEMORY.md")] == ""
