"""The text Coffer writes into Claude Code: a project's ``MEMORY.md`` block
(spec memory "Write the hub into Claude Code as text it loads")."""

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
)

_PREFERENCE = "memories/memory_summary.md::profile::User preferences::1"
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


_ROOT = "/work/payments"


def _block(tmp_path: pathlib.Path, entries: list[HubEntry]) -> str:
    """The block written into the payments project's ``MEMORY.md``."""
    project = [
        HubEntry(**{**e.__dict__, "project": _PROJECT}) if not e.project else e for e in entries
    ]
    return _aux(tmp_path, project, root=_ROOT)[str(memory_dir(str(tmp_path), _ROOT) / "MEMORY.md")]


def test_no_memory_is_written_as_a_file_of_its_own() -> None:
    entry = _entry("a1", "Reply in Chinese", "Reply in Chinese", project=_PROJECT)
    assert not ClaudeCodeMemoryWriter().wants(Target(entry, _ROOT, entry.body))


def test_the_block_holds_each_memory_s_text_newest_first(tmp_path: pathlib.Path) -> None:
    block = _block(
        tmp_path,
        [
            _entry("a1", "Sessions", "Session TTL is 30 minutes."),
            _entry("a2", "Reply in Chinese", "Reply in Chinese, keep code identifiers in English."),
        ],
    )
    lines = [line for line in block.splitlines() if line.startswith("- ")]
    assert "Reply in Chinese, keep code identifiers in English. (from Codex)" in lines[0]
    assert "Session TTL is 30 minutes." in lines[1]
    assert "coffer_" not in block


def test_a_title_that_opens_its_text_is_not_repeated(tmp_path: pathlib.Path) -> None:
    block = _block(tmp_path, [_entry("a1", "keep account knowledge in `shopee-account`", _BULLET)])
    assert f"- {_BULLET} (from Codex)" in block


def test_a_title_the_text_does_not_open_with_leads_in_bold(tmp_path: pathlib.Path) -> None:
    block = _block(
        tmp_path,
        [_entry("a1", "Testing", "Integration tests hit a real database.", agent=CLAUDE_CODE)],
    )
    assert "- **Testing**: Integration tests hit a real database. (from Claude Code)" in block


def test_one_memory_s_text_is_bounded(tmp_path: pathlib.Path) -> None:
    block = _block(tmp_path, [_entry("a1", "Long", "word " * 1000)])
    line = next(line for line in block.splitlines() if line.startswith("- "))
    assert len(line) <= MEMORY_TEXT_MAX + len("- ") + len(" (from Codex)")


@pytest.mark.acceptance(spec="memory", scenario="an earlier build's global rules file is deleted")
def test_an_earlier_build_s_global_rules_file_is_deleted(tmp_path: pathlib.Path) -> None:
    rules = tmp_path / "rules" / "coffer-memory.md"
    rules.parent.mkdir(parents=True)
    rules.write_text("# Memories from your other agents\n\n- Reply in Chinese\n")
    writes = ClaudeCodeMemoryWriter().aux(str(tmp_path), {}, {}, [])
    assert [(w.path, w.content) for w in writes] == [(str(rules), None)]


@pytest.mark.acceptance(spec="memory", scenario="a project's memories reach only that project")
def test_project_memories_go_into_that_project_s_block_not_the_rules_file(
    tmp_path: pathlib.Path,
) -> None:
    root = _ROOT
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
    root = _ROOT
    entries = [_entry(f"p{i:02d}", f"Note {i}", "y" * 400, project=_PROJECT) for i in range(30)]
    block = next(iter(_aux(tmp_path, entries, root=root).values()))
    inner = block.split(BLOCK_BEGIN, 1)[1].split(BLOCK_END, 1)[0]
    assert len(inner.encode("utf-8")) <= BLOCK_MAX_BYTES + 2
    assert f"`coffer memory entries --project {_PROJECT}`" in inner


def test_an_earlier_build_s_global_folder_block_is_emptied(tmp_path: pathlib.Path) -> None:
    folder = memory_dir(str(tmp_path), GLOBAL_ROOT)
    folder.mkdir(parents=True)
    (folder / "MEMORY.md").write_text(f"{BLOCK_BEGIN}\n- old line\n{BLOCK_END}\n")
    writes = _aux(tmp_path, [])
    assert writes[str(folder / "MEMORY.md")] == ""
