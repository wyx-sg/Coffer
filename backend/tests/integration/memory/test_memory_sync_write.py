"""The memory sync's write half: the hub into each agent's own memory (spec
memory "Write the hub into Claude Code as text it loads", "Write the hub into
Codex's memory extension" and the requirements that decide where and when)."""

from __future__ import annotations

import os
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
    codex_topics,
    hub_files,
)
from tests.integration.memory.conftest import init_repository


@pytest.fixture
def payments(tmp_path: pathlib.Path) -> pathlib.Path:
    return init_repository(tmp_path / "src" / "payments", remote="git@github.com:acme/payments.git")


def _resources(codex: pathlib.Path) -> list[pathlib.Path]:
    folder = codex / "memories" / "extensions" / "coffer" / "resources"
    return sorted(folder.glob("*.md")) if folder.is_dir() else []


def _block(memory: pathlib.Path) -> str:
    index = (memory / "MEMORY.md").read_text(encoding="utf-8")
    return index[index.index(BLOCK_BEGIN) : index.index(BLOCK_END)]


@pytest.mark.acceptance(spec="memory", scenario="a project's memories reach only that project")
async def test_a_project_s_memories_reach_only_that_project(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a = Machine("machine-a", tmp_path / "a")
    a.codex(
        memory=codex_topics([("Payments", str(payments), ["Run uv sync --frozen before tests."])])
    )
    cc = a.claude()
    own = "# Memory index\n\n- [Own](own.md) — something I learned\n"
    memory = cc_project(
        cc, payments, {"MEMORY.md": own, "own.md": cc_file("Own", "mine", "project", "x")}
    )
    other = init_repository(tmp_path / "src" / "other", remote="git@github.com:acme/other.git")
    elsewhere = cc_project(cc, other, {"MEMORY.md": "# other\n"})
    await a.sync()

    index = (memory / "MEMORY.md").read_text(encoding="utf-8")
    assert index.startswith(own)
    assert "- Run uv sync --frozen before tests. (from Codex)" in _block(memory)
    assert (elsewhere / "MEMORY.md").read_text(encoding="utf-8") == "# other\n"
    assert not (cc / "rules").exists()
    assert list(cc.rglob("coffer_*.md")) == []
    backups = list(config_backups_dir().rglob("MEMORY.md.coffer-backup-*"))
    assert backups and backups[0].read_text(encoding="utf-8") == own


@pytest.mark.acceptance(
    spec="memory", scenario="a memory learned outside any repository is not synced"
)
async def test_a_memory_learned_outside_any_repository_is_not_synced(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    scratch = tmp_path / "Documents" / "notes"
    scratch.mkdir(parents=True)
    a = Machine("machine-a", tmp_path / "a")
    codex = a.codex(memory=codex_topics([("Payments", str(payments), [])]))
    cc = a.claude()
    cc_project(cc, scratch, {"lang.md": cc_file("Chinese", "Replies", "user", "Reply in Chinese.")})
    cc_project(cc, payments, {})
    await a.sync()

    assert hub_files(pathlib.Path(os.environ["HOME"]) / ".coffer" / "vault") == []
    assert _resources(codex) == []


@pytest.mark.acceptance(spec="memory", scenario="a reference memory syncs like any project memory")
async def test_a_reference_memory_syncs_like_any_project_memory(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a = Machine("machine-a", tmp_path / "a")
    codex = a.codex(memory=codex_topics([("IA sheet", str(payments), ["Remarks go in column F."])]))
    cc = a.claude()
    memory = cc_project(
        cc,
        payments,
        {"r.md": cc_file("Dashboards", "Where", "reference", "Grafana board payments-p99.")},
    )
    await a.sync()

    assert "Remarks go in column F." in _block(memory)
    (copy,) = _resources(codex)
    assert "Grafana board payments-p99." in copy.read_text(encoding="utf-8")


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
    codex = a.codex(memory=codex_topics([("Payments", str(payments), ["Something Codex knows."])]))
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
    codex = a.codex(memories_on=False)
    before = sorted(p.relative_to(codex) for p in codex.rglob("*"))
    await a.sync()

    assert sorted(p.relative_to(codex) for p in codex.rglob("*")) == before
    state = await a.view.state()
    (row,) = [r for r in state.agents if r.agent_type == "codex"]
    assert row.writer["state"] == "off"


@pytest.mark.acceptance(spec="memory", scenario="an unrecognised layout is not written into")
async def test_an_unrecognised_layout_is_not_written_into(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a = Machine("machine-a", tmp_path / "a")
    cc_project(a.claude(), payments, {"p.md": cc_file("Ledger", "Retries", "project", "x")})
    codex = a.codex()
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
    assert not b_cc.joinpath("projects").exists() or not list(b_cc.rglob("MEMORY.md"))

    clone = init_repository(tmp_path / "b-src" / "pay", remote="https://github.com/acme/payments")
    cc_project(b_cc, clone, {})
    await b.sync()
    assert "- **Ledger**: x (from Claude Code)" in _block(cc_memory_dir(b_cc, clone))


@pytest.mark.acceptance(
    spec="memory", scenario="a memory returns to its own agent on another machine only"
)
async def test_a_memory_returns_to_its_own_agent_on_another_machine_only(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a = Machine("machine-a", tmp_path / "a")
    a_cc = a.claude()
    cc_project(a_cc, payments, {"p.md": cc_file("Ledger", "Retries", "project", "x")})
    a_codex = a.codex(memory=codex_topics([("Payments", str(payments), [])]))
    await a.sync()
    b = Machine("machine-b", tmp_path / "b")
    b_cc = b.claude()
    cc_project(b_cc, payments, {})
    b_codex = b.codex(memory=codex_topics([("Payments", str(payments), [])]))
    await b.sync()

    assert not (cc_memory_dir(a_cc, payments) / "MEMORY.md").exists()
    assert len(_resources(a_codex)) == 1
    assert "(from Claude Code)" in _block(cc_memory_dir(b_cc, payments))
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
    codex = a.codex(memory=codex_topics([("Payments", str(payments), ["Codex fact here."])]))
    await a.service.set_codex_imports_claude(True)
    await a.sync()

    assert _resources(codex) == []
    state = await a.view.state()
    assert state.codex_imports_claude is True
    rows = await a.view.entries("github.com/acme/payments")
    (row,) = [r for r in rows if r.entry.origin.agent == "claude_code"]
    assert row.copies["codex"] == "deferred"


@pytest.mark.acceptance(spec="memory", scenario="the marked block is bounded")
async def test_the_marked_block_is_bounded(tmp_path: pathlib.Path, payments: pathlib.Path) -> None:
    a = Machine("machine-a", tmp_path / "a", threshold=100)
    bullets = [f"Fact number {i} about the payments ledger, " + "x" * 200 for i in range(45)]
    a.codex(memory=codex_topics([("Payments", str(payments), bullets)]))
    memory = cc_project(a.claude(), payments, {})
    await a.sync()

    lines = _block(memory).splitlines()[1:]
    assert 0 < len(lines) < 45
    assert lines[-1].startswith("- …and ")
    assert lines[-1].endswith("`coffer memory entries --project github.com/acme/payments`")


@pytest.mark.acceptance(spec="memory", scenario="a memory left out of a full block says so")
async def test_a_memory_left_out_of_a_full_block_says_so(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a = Machine("machine-a", tmp_path / "a", threshold=100)
    topics = [f"Fact number {i} about the payments ledger, " + "x" * 200 for i in range(45)]
    a.codex(memory=codex_topics([("Payments", str(payments), topics)]))
    memory = cc_project(a.claude(), payments, {})
    await a.sync()

    rows = await a.view.entries("github.com/acme/payments")
    states = [r.copies["claude_code"] for r in rows]
    held = len(_block(memory).splitlines()) - 2
    assert states.count("block") == held
    assert states.count("over_limit") == 45 - held
    block = _block(memory)
    for row in rows:
        assert (row.entry.body in block) == (row.copies["claude_code"] == "block")
