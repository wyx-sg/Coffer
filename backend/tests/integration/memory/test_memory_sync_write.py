"""The memory sync's write half: the hub into each agent's own memory (spec
memory "Write the hub into Claude Code's native memory", "Write global
memories into a Claude Code rules file", "Write the hub into Codex's memory
extension" and the requirements that decide where and when)."""

from __future__ import annotations

import pathlib
import re

import pytest

from coffer.infrastructure.memory.writers.claude_code import BLOCK_BEGIN, BLOCK_END
from coffer.infrastructure.vault.home import config_backups_dir
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


def _resources(codex: pathlib.Path) -> list[pathlib.Path]:
    folder = codex / "memories" / "extensions" / "coffer" / "resources"
    return sorted(folder.glob("*.md")) if folder.is_dir() else []


@pytest.mark.acceptance(spec="memory", scenario="a Codex memory reaches Claude Code")
async def test_a_codex_memory_reaches_claude_code(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a = Machine("machine-a", tmp_path / "a")
    a.codex(
        memory_md=codex_memory(
            [("Payments", str(payments), ["Run uv sync --frozen before tests."])]
        )
    )
    cc = a.claude()
    own = "# Memory index\n\n- [Own](own.md) — something I learned\n"
    memory = cc_project(
        cc, payments, {"MEMORY.md": own, "own.md": cc_file("Own", "mine", "project", "x")}
    )
    await a.sync()

    (copy,) = sorted(memory.glob("coffer_*.md"))
    text = copy.read_text(encoding="utf-8")
    assert "name: Run uv sync --frozen before tests" in text
    assert "type: project" in text
    assert "entry:" in text and "from: codex" in text
    index = (memory / "MEMORY.md").read_text(encoding="utf-8")
    assert index.startswith(own)
    block = index[index.index(BLOCK_BEGIN) : index.index(BLOCK_END)]
    assert f"]({copy.name}) —" in block and "(from Codex)" in block
    backups = list(config_backups_dir().rglob("MEMORY.md.coffer-backup-*"))
    assert backups and backups[0].read_text(encoding="utf-8") == own


@pytest.mark.acceptance(spec="memory", scenario="a Codex profile reaches every Claude Code session")
async def test_a_codex_profile_reaches_every_claude_code_session(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a = Machine("machine-a", tmp_path / "a")
    a.codex(memory_md="", summary_md="## User preferences\n- Prefers replies in Chinese.\n")
    cc = a.claude()
    memory = cc_project(cc, payments, {"MEMORY.md": "# index\n"})
    await a.sync()

    rules = (cc / "rules" / "coffer-memory.md").read_text(encoding="utf-8")
    assert "Coffer writes this file" in rules
    assert "Prefers replies in Chinese" in rules
    assert (memory / "MEMORY.md").read_text(encoding="utf-8") == "# index\n"


@pytest.mark.acceptance(spec="memory", scenario="a Claude Code memory reaches Codex")
async def test_a_claude_code_memory_reaches_codex(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a = Machine("machine-a", tmp_path / "a")
    cc_project(
        a.claude(),
        payments,
        {"p.md": cc_file("Ledger", "Retries", "project", "Retries are idempotent.")},
    )
    codex = a.codex(
        memory_md=codex_memory([("Payments", str(payments), ["Something Codex knows."])])
    )
    await a.sync()

    (resource,) = _resources(codex)
    text = resource.read_text(encoding="utf-8")
    assert f"Applies to: {payments}" in text
    assert "Retries are idempotent." in text
    assert (codex / "memories" / "extensions" / "coffer" / "instructions.md").is_file()
    assert not re.match(r"\d{4}-\d{2}-\d{2}T", resource.name)


@pytest.mark.acceptance(spec="memory", scenario="Codex with memories off is reported, not written")
async def test_codex_with_memories_off_is_reported_not_written(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a = Machine("machine-a", tmp_path / "a")
    cc_project(a.claude(), payments, {"p.md": cc_file("Ledger", "Retries", "project", "x")})
    codex = a.codex(memory_md="", memories_on=False)
    before = sorted(p.relative_to(codex) for p in codex.rglob("*"))
    await a.sync()

    assert sorted(p.relative_to(codex) for p in codex.rglob("*")) == before
    state = await a.view.state()
    (row,) = [r for r in state.agents if r.agent_type == "codex"]
    assert row.writer["state"] == "off"
    assert row.curation.memory == "off"


@pytest.mark.acceptance(spec="memory", scenario="an unrecognised layout is not written into")
async def test_an_unrecognised_layout_is_not_written_into(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a = Machine("machine-a", tmp_path / "a")
    cc_project(a.claude(), payments, {"p.md": cc_file("Ledger", "Retries", "project", "x")})
    codex = a.codex(memory_md="")
    (codex / "memories" / "MEMORY.md").unlink()
    await a.sync()

    assert not (codex / "memories" / "extensions").exists()
    state = await a.view.state()
    (row,) = [r for r in state.agents if r.agent_type == "codex"]
    assert row.writer["state"] == "unrecognised"
    assert row.writer["path"] == str(codex / "memories")


@pytest.mark.acceptance(spec="memory", scenario="a project not checked out here is held back")
async def test_a_project_not_checked_out_here_is_held_back(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a = Machine("machine-a", tmp_path / "a")
    cc_project(a.claude(), payments, {"p.md": cc_file("Ledger", "Retries", "project", "x")})
    await a.sync()

    b = Machine("machine-b", tmp_path / "b")
    b_cc = b.claude()
    await b.sync()
    assert list(b_cc.rglob("coffer_*.md")) == []

    clone = init_repository(tmp_path / "b-src" / "pay", remote="https://github.com/acme/payments")
    cc_project(b_cc, clone, {})
    await b.sync()
    assert len(list(cc_memory_dir(b_cc, clone).glob("coffer_*.md"))) == 1


@pytest.mark.acceptance(
    spec="memory", scenario="a memory returns to its own agent on another machine only"
)
async def test_a_memory_returns_to_its_own_agent_on_another_machine_only(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a = Machine("machine-a", tmp_path / "a")
    a_cc = a.claude()
    cc_project(a_cc, payments, {"p.md": cc_file("Ledger", "Retries", "project", "x")})
    a_codex = a.codex(memory_md=codex_memory([("Payments", str(payments), [])]))
    await a.sync()
    b = Machine("machine-b", tmp_path / "b")
    b_cc = b.claude()
    cc_project(b_cc, payments, {})
    b_codex = b.codex(memory_md=codex_memory([("Payments", str(payments), [])]))
    await b.sync()

    assert list(a_cc.rglob("coffer_*.md")) == []
    assert len(_resources(a_codex)) == 1
    assert len(list(b_cc.rglob("coffer_*.md"))) == 1
    assert len(_resources(b_codex)) == 1


@pytest.mark.acceptance(
    spec="memory",
    scenario="Codex's own import turns the Claude Code to Codex direction off",
)
async def test_codex_own_import_turns_the_claude_code_to_codex_direction_off(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a = Machine("machine-a", tmp_path / "a")
    cc = a.claude()
    cc_project(cc, payments, {"p.md": cc_file("Ledger", "Retries", "project", "x")})
    codex = a.codex(memory_md=codex_memory([("Payments", str(payments), ["Codex fact here."])]))
    await a.service.set_codex_imports_claude(True)
    await a.sync()

    assert _resources(codex) == []
    assert len(list(cc.rglob("coffer_*.md"))) == 1
    state = await a.view.state()
    assert state.codex_imports_claude is True
    rows = await a.view.entries("github.com/acme/payments")
    (row,) = [r for r in rows if r.entry.origin.agent == "claude_code"]
    assert row.copies["codex"] == "deferred"


@pytest.mark.acceptance(spec="memory", scenario="the marked block is capped")
async def test_the_marked_block_is_capped(tmp_path: pathlib.Path, payments: pathlib.Path) -> None:
    a = Machine("machine-a", tmp_path / "a", threshold=100)
    bullets = [f"Fact number {i} about the payments ledger." for i in range(45)]
    a.codex(memory_md=codex_memory([("Payments", str(payments), bullets)]))
    memory = cc_project(a.claude(), payments, {})
    await a.sync()

    index = (memory / "MEMORY.md").read_text(encoding="utf-8")
    lines = index[index.index(BLOCK_BEGIN) : index.index(BLOCK_END)].splitlines()[1:]
    assert len(lines) == 31
    assert lines[-1] == "- …and 15 more Coffer memories in this folder (coffer_*.md)"
