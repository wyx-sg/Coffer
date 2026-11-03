"""Codex's two memory versions (spec memory "Write the hub into Codex's
memory extension", "Read Codex's v2 memory").

Codex keeps v1 memory in ``memories/`` and v2 memory in ``memories_v2/``, and
Codex Desktop picks one per thread, so Coffer writes its extension into each
folder that is there and reads both."""

from __future__ import annotations

import pathlib

import pytest

from tests.integration.memory._sync_harness import (
    Machine,
    cc_file,
    cc_memory_dir,
    cc_project,
    codex_memory,
)
from tests.integration.memory.conftest import init_repository


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
    codex = a.codex(memory_md=codex_memory([("Payments", str(payments), [])]), v2_summary_md="v1\n")
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
    codex = a.codex(v1=False, v2_summary_md="v1\n")
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
    codex = a.codex(memory_md=codex_memory([("Payments", str(payments), [])]), v2_summary_md="v1\n")
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


@pytest.mark.acceptance(
    spec="memory", scenario="a Codex v2 topic reaches Claude Code once sorted into memory"
)
async def test_a_codex_v2_topic_reaches_claude_code(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a = Machine("machine-a", tmp_path / "a")
    a.codex(
        v1=False,
        v2_summary_md=V2_SUMMARY,
        rollouts={"ab12-ledger.md": str(payments)},
    )
    claude = a.claude()
    await a.sync()

    rules = (claude / "rules" / "coffer-memory.md").read_text(encoding="utf-8")
    assert "Lead with the point" in rules
    assert "Separate evidence from hypotheses" in rules
    index = cc_memory_dir(claude, payments) / "MEMORY.md"
    assert not index.exists()
    (topic,) = await a.view.to_sort()

    await a.view.mark_sorted([topic.id], "memory", "", "agent")
    await a.sync()

    text = index.read_text(encoding="utf-8")
    assert "Ledger retries are idempotent" in text
    assert "PR: payments!42 merged." in text
    assert list(claude.rglob("coffer_*.md")) == []


async def test_undo_removes_coffers_copies_from_every_codex_memory_folder(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a = Machine("machine-a", tmp_path / "a")
    cc_project(a.claude(), payments, {"p.md": cc_file("Ledger", "Retries", "project", "Retry.")})
    codex = a.codex(memory_md=codex_memory([("Payments", str(payments), [])]), v2_summary_md="v1\n")
    await a.sync()
    await a.service.undo("user")

    for folder in ("memories", "memories_v2"):
        assert not (codex / folder / "extensions" / "coffer").exists()
    ledger = a.service.ledger.load()
    assert all(not copies for copies in ledger.copies.values())
