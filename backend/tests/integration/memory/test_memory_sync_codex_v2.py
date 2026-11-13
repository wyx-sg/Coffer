"""Codex's two memory folders (spec memory "Write the hub into Codex's
memory extension", "Read Codex's memory from its v2 summary").

Codex keeps v1 memory in ``memories/`` and v2 memory in ``memories_v2/``, and
Codex Desktop picks one per thread, so Coffer writes its extension into each
folder that is there. It reads the v2 summary only."""

from __future__ import annotations

import os
import pathlib

import pytest

from coffer.infrastructure.memory.hub_store import parse_entry
from tests.integration.memory._sync_harness import (
    CodexMemory,
    Machine,
    cc_file,
    cc_memory_dir,
    cc_project,
    codex_topics,
    hub_files,
)
from tests.integration.memory.conftest import init_repository


def _entries() -> list:  # type: ignore[type-arg]
    vault = pathlib.Path(os.environ["HOME"]) / ".coffer" / "vault"
    return [parse_entry(p.read_text(encoding="utf-8")) for p in hub_files(vault)]


@pytest.fixture
def payments(tmp_path: pathlib.Path) -> pathlib.Path:
    return init_repository(tmp_path / "src" / "payments", remote="git@github.com:acme/payments.git")


def _resources(codex: pathlib.Path, folder: str) -> list[pathlib.Path]:
    resources = codex / folder / "extensions" / "coffer" / "resources"
    return sorted(resources.glob("*.md")) if resources.is_dir() else []


V2_SUMMARY = """v1

## User Profile

The user runs payments operations.

## User preferences

- Lead with the point.

## General Tips

Separate evidence from hypotheses.

## What's in Memory

### Payments ledger
#### 2026-11-02
- rollout_summaries/ab12-ledger.md — Ledger retries are idempotent; thread_id=t-1
  - PR: payments!42 merged.
"""


@pytest.mark.acceptance(spec="memory", scenario="a memory reaches every Codex memory folder")
async def test_a_memory_reaches_every_codex_memory_folder(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a = Machine("machine-a", tmp_path / "a")
    cc_project(a.claude(), payments, {"p.md": cc_file("Ledger", "Retries", "project", "Retry.")})
    codex = a.codex(memory=codex_topics([("Payments", str(payments), [])]), v2=True)
    await a.sync()

    (v1,) = _resources(codex, "memories")
    (v2,) = _resources(codex, "memories_v2")
    assert v1.name == v2.name
    assert v1.read_text(encoding="utf-8") == v2.read_text(encoding="utf-8")
    assert (codex / "memories_v2" / "extensions" / "coffer" / "instructions.md").is_file()

    state = await a.view.state()
    (row,) = [r for r in state.agents if r.agent_type == "codex"]
    assert [(loc.name, loc.writer["state"]) for loc in row.locations] == [
        ("", "ok"),
        ("memories_v2", "ok"),
    ]
    assert [loc.copies for loc in row.locations] == [{"written": 1}, {"written": 1}]
    assert row.copies == {"written": 2}


async def test_a_codex_with_only_v2_memory_is_written_into_v2(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a = Machine("machine-a", tmp_path / "a")
    cc_project(a.claude(), payments, {"p.md": cc_file("Ledger", "Retries", "project", "Retry.")})
    codex = a.codex(v1=False, v2=True)
    await a.sync()

    assert not (codex / "memories").exists()
    assert len(_resources(codex, "memories_v2")) == 1


@pytest.mark.acceptance(
    spec="memory", scenario="a newer Codex memory folder is reported, not written"
)
async def test_a_newer_codex_memory_folder_is_reported_not_written(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a = Machine("machine-a", tmp_path / "a")
    cc_project(a.claude(), payments, {"p.md": cc_file("Ledger", "Retries", "project", "Retry.")})
    codex = a.codex(memory=codex_topics([("Payments", str(payments), [])]), v2=True)
    (codex / "memories_v3").mkdir()
    await a.sync()

    assert len(_resources(codex, "memories")) == 1
    assert len(_resources(codex, "memories_v2")) == 1
    assert not (codex / "memories_v3" / "extensions").exists()
    state = await a.view.state()
    (row,) = [r for r in state.agents if r.agent_type == "codex"]
    assert row.locations[-1].name == "memories_v3"
    assert row.locations[-1].writer["state"] == "unrecognised"
    assert row.writer["state"] == "unrecognised"
    assert row.writer["path"] == str(codex / "memories_v3")


@pytest.mark.acceptance(spec="memory", scenario="a Codex v2 topic reaches Claude Code")
async def test_a_codex_v2_topic_reaches_claude_code(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a = Machine("machine-a", tmp_path / "a")
    a.codex(v1=False, memory=CodexMemory(V2_SUMMARY, {"ab12-ledger.md": str(payments)}))
    claude = a.claude()
    await a.sync()

    index = cc_memory_dir(claude, payments) / "MEMORY.md"
    text = index.read_text(encoding="utf-8")
    assert "Ledger retries are idempotent" in text
    assert "PR: payments!42 merged." in text
    assert "rollout_summaries/" not in text and "thread_id" not in text
    assert "Lead with the point" not in text and "Separate evidence" not in text
    assert [e.title for e in _entries()] == ["Ledger retries are idempotent"]


@pytest.mark.acceptance(spec="memory", scenario="Codex's v1 task groups are not read")
async def test_codex_v1_task_groups_are_not_read(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a = Machine("machine-a", tmp_path / "a")
    codex = a.codex()
    (codex / "memories" / "MEMORY.md").write_text(
        f"# Task Group: Payments\napplies_to: cwd={payments}\n\n"
        "## Reusable knowledge\n- Use uv sync --frozen.\n",
        encoding="utf-8",
    )
    (codex / "memories" / "memory_summary.md").write_text(
        "## User preferences\n- Prefers replies in Chinese.\n", encoding="utf-8"
    )
    a.claude()
    await a.sync()

    assert _entries() == []
    assert not [p for p in a.service.ledger.load().sources if "/memories/" in p]


async def test_undo_removes_coffers_copies_from_every_codex_memory_folder(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a = Machine("machine-a", tmp_path / "a")
    cc_project(a.claude(), payments, {"p.md": cc_file("Ledger", "Retries", "project", "Retry.")})
    codex = a.codex(memory=codex_topics([("Payments", str(payments), [])]), v2=True)
    await a.sync()
    await a.service.undo("user")

    for folder in ("memories", "memories_v2"):
        assert not (codex / folder / "extensions" / "coffer").exists()
    ledger = a.service.ledger.load()
    assert all(not copies for copies in ledger.copies.values())
