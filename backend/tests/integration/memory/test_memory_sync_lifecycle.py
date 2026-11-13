"""The memory sync over time: copies read back, curated, edited and removed by
the agents, the preview, the Activity record, undo and failures (spec
memory)."""

from __future__ import annotations

import asyncio
import os
import pathlib

import pytest

from coffer.domain.memory.errors import MemorySyncRunning
from tests.integration.memory._sync_harness import (
    Machine,
    cc_file,
    cc_memory_dir,
    cc_project,
    codex_topics,
    hub_files,
    resources,
)
from tests.integration.memory.conftest import init_repository


def _vault() -> pathlib.Path:
    return pathlib.Path(os.environ["HOME"]) / ".coffer" / "vault"


@pytest.fixture
def payments(tmp_path: pathlib.Path) -> pathlib.Path:
    return init_repository(tmp_path / "src" / "payments", remote="git@github.com:acme/payments.git")


async def _claude_to_codex(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> tuple[Machine, pathlib.Path]:
    """A Claude Code project memory copied into Codex; answers the copy."""
    a = Machine("machine-a", tmp_path / "a")
    codex = a.codex(memory=codex_topics([("Payments", str(payments), [])]))
    cc_project(
        a.claude(), payments, {"p.md": cc_file("Ledger", "Retries", "project", "Idempotent.")}
    )
    await a.sync()
    (copy,) = resources(codex)
    return a, copy


@pytest.mark.acceptance(spec="memory", scenario="a copy read back is not published")
async def test_a_copy_read_back_is_not_published(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a = Machine("machine-a", tmp_path / "a")
    a.codex(
        memory=codex_topics(
            [
                (
                    "Payments",
                    str(payments),
                    ["Own Codex fact about ledgers.", "Derived [via Coffer] fact."],
                )
            ]
        )
    )
    cc_project(a.claude(), payments, {})
    await a.sync()
    await a.sync()
    titles = sorted(p.read_text(encoding="utf-8") for p in hub_files(_vault()))
    assert len(titles) == 1
    assert "Own Codex fact" in titles[0]


@pytest.mark.acceptance(spec="memory", scenario="an absorbed copy does not circulate")
async def test_an_absorbed_copy_does_not_circulate(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a = Machine("machine-a", tmp_path / "a")
    a.codex(memory=codex_topics([("Payments", str(payments), ["Prefers replies in Chinese."])]))
    cc = a.claude()
    memory = cc_project(cc, payments, {})
    await a.sync()
    assert "Prefers replies in Chinese." in (memory / "MEMORY.md").read_text()
    before = sorted(p.read_bytes() for p in hub_files(_vault()))
    # Claude Code's curation folds the line it was given into a memory of its own.
    (memory / "own.md").write_text(
        cc_file("Language", "replies", "user", "Prefers replies in Chinese."), encoding="utf-8"
    )
    await a.sync()
    assert sorted(p.read_bytes() for p in hub_files(_vault())) == before


@pytest.mark.acceptance(spec="memory", scenario="a copy Auto Dream merged away is not brought back")
async def test_a_copy_auto_dream_merged_away_is_not_brought_back(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a, copy = await _claude_to_codex(tmp_path, payments)
    copy.unlink()
    await a.sync()
    assert not copy.exists()
    assert len(hub_files(_vault())) == 1


@pytest.mark.acceptance(spec="memory", scenario="a copy the agent edited is not overwritten")
async def test_a_copy_the_agent_edited_is_not_overwritten(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a, copy = await _claude_to_codex(tmp_path, payments)
    edited = copy.read_text(encoding="utf-8") + "\nThe agent's own addition.\n"
    copy.write_text(edited, encoding="utf-8")
    await a.sync()
    assert copy.read_text(encoding="utf-8") == edited


@pytest.mark.acceptance(
    spec="memory", scenario="an agent's own files are byte-identical after a sync"
)
async def test_an_agents_own_files_are_byte_identical_after_a_sync(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a = Machine("machine-a", tmp_path / "a")
    codex = a.codex(
        memory=codex_topics([("Payments", str(payments), ["Codex fact one here."])]),
    )
    cc = a.claude()
    cc_project(cc, payments, {"own.md": cc_file("Own", "mine", "project", "Mine.")})
    snap = {
        p: (p.read_bytes(), p.stat().st_mtime_ns)
        for root in (cc, codex)
        for p in root.rglob("*")
        if p.is_file()
    }
    await a.sync()
    for path, (data, mtime) in snap.items():
        assert path.read_bytes() == data, path
        assert path.stat().st_mtime_ns == mtime, path
    new = {p for root in (cc, codex) for p in root.rglob("*") if p.is_file()} - set(snap)
    for path in new:
        rel = str(path)
        assert path.name == "MEMORY.md" or "/extensions/coffer/" in rel, rel
    assert cc_memory_dir(cc, payments) / "MEMORY.md" in new
    assert not (cc / "rules").exists()
    assert not [p for p in new if p.name.startswith("coffer_")]


@pytest.mark.acceptance(spec="memory", scenario="the first sync waits for the person")
async def test_the_first_sync_waits_for_the_person(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a = Machine("machine-a", tmp_path / "a")
    codex = a.codex(
        memory=codex_topics([("Payments", str(payments), ["Prefers replies in Chinese."])])
    )
    cc = a.claude()
    memory = cc_project(cc, payments, {"p.md": cc_file("Ledger", "Retries", "project", "x")})
    await a.service.sync("user")

    assert len(hub_files(_vault())) == 2
    assert not (memory / "MEMORY.md").exists()
    assert not (codex / "memories" / "extensions").exists()
    state = await a.view.state()
    assert state.preview is not None
    listed = {(r["agent"], r["write"]) for r in state.preview["rows"]}
    # One memory, into each of Codex's two memory folders.
    assert ("codex", 2) in listed

    await a.service.write_preview("user")
    assert "Prefers replies in Chinese." in (memory / "MEMORY.md").read_text()
    assert len(resources(codex)) == 1
    assert (await a.view.state()).preview is None


@pytest.mark.acceptance(spec="memory", scenario="a sync lists what it wrote")
async def test_a_sync_lists_what_it_wrote(tmp_path: pathlib.Path, payments: pathlib.Path) -> None:
    a = Machine("machine-a", tmp_path / "a")
    cc = a.claude()
    cc_project(cc, payments, {"p.md": cc_file("Ledger", "Retries", "project", "x")})
    a.codex(memory=codex_topics([("Payments", str(payments), [])]))
    await a.sync()
    a.codex("cx2", memory=codex_topics([("Payments", str(payments), [])]))
    a.audit.events.clear()
    cc_project(cc, payments, {"q.md": cc_file("Fees", "Fees", "project", "Fees round down.")})
    await a.service.sync("user")
    ((event, actor, details),) = a.audit.events
    assert (event, actor) == ("memory_synced", "user")
    assert [c["title"] for c in details["hub"]["created"]] == ["Fees"]
    # The new memory into both Codex agents, and the first into the new one,
    # each into Codex's two memory folders.
    assert len(details["copies"]["codex"]["written"]) == 6


@pytest.mark.acceptance(spec="memory", scenario="undo removes Coffer's copies and nothing else")
async def test_undo_removes_coffers_copies_and_nothing_else(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a = Machine("machine-a", tmp_path / "a")
    codex = a.codex(memory=codex_topics([("Payments", str(payments), ["A Codex fact."])]))
    cc = a.claude()
    memory = cc_project(
        cc,
        payments,
        {
            "MEMORY.md": "# mine\n",
            "p.md": cc_file("Ledger", "Retries", "project", "x"),
            "q.md": cc_file("Fees", "Fees", "project", "y"),
        },
    )
    await a.sync()
    one, two = resources(codex)
    two.write_text(two.read_text(encoding="utf-8") + "edited\n", encoding="utf-8")
    hub_before = sorted(p.read_bytes() for p in hub_files(_vault()))
    stopped: list[str] = []

    async def _stop(actor: str) -> None:
        stopped.append(actor)

    a.service._stop_automatic = _stop
    await a.service.undo("user")

    assert not one.exists() and two.exists()
    assert (memory / "MEMORY.md").read_text(encoding="utf-8") == "# mine\n"
    assert (memory / "p.md").exists()
    assert sorted(p.read_bytes() for p in hub_files(_vault())) == hub_before
    assert stopped == ["user"]
    assert a.audit.events[-1][0] == "memory_sync_undone"


@pytest.mark.acceptance(spec="memory", scenario="an agent's tab shows what Coffer wrote into it")
async def test_an_agents_row_carries_what_coffer_wrote_into_it(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a = Machine("machine-a", tmp_path / "a")
    cc_project(
        a.claude(),
        payments,
        {
            "p.md": cc_file("Ledger", "Retries", "project", "x"),
            "q.md": cc_file("Fees", "Fees", "project", "y"),
        },
    )
    a.codex(memory=codex_topics([("Payments", str(payments), ["A Codex fact."])]))
    await a.sync()
    state = await a.view.state()
    rows = {r.agent_type: r for r in state.agents}
    assert rows["codex"].writer["state"] == "ok"
    # Two memories, into each of Codex's two memory folders.
    assert rows["codex"].copies == {"written": 4}
    # Claude Code gets text in a block, no copies to count.
    assert rows["claude_code"].writer["state"] == "ok"
    assert rows["claude_code"].copies == {}
    assert not hasattr(rows["claude_code"], "curation")


@pytest.mark.acceptance(
    spec="memory", scenario="an agent whose native memory shape is unreadable degrades loudly"
)
async def test_an_unreadable_agent_degrades_loudly(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a = Machine("machine-a", tmp_path / "a")
    memory = cc_project(
        a.claude(), payments, {"p.md": cc_file("Ledger", "Retries", "project", "x")}
    )
    a.codex(memory=codex_topics([("Payments", str(payments), ["Codex fact one here."])]))
    await a.sync()
    (memory / "p.md").write_text("---\nname: [unterminated\n", encoding="utf-8")
    report = await a.service.sync("user")
    assert [f["path"] for f in report.failures] == [str(memory / "p.md")]  # type: ignore[attr-defined]
    assert len(hub_files(_vault())) == 2


@pytest.mark.acceptance(spec="memory", scenario="a sync runs at start and on demand")
async def test_one_sync_at_a_time(tmp_path: pathlib.Path) -> None:
    a = Machine("machine-a", tmp_path / "a")
    a.claude()
    async with a.service._lock:
        with pytest.raises(MemorySyncRunning):
            await a.service.sync("user")
    await asyncio.wait_for(a.service.sync("user"), timeout=10)
