"""The ``skill_link`` reconcile target over a real filesystem and database.

ADR one-level-triggered-reconciler-compares-parameters. Each test induces one
kind of drift with the kind hooks left out (so nothing repairs it early), runs
one pass the way the daemon does, and checks the disk, the binding row and the
audit trail: every repair leaves exactly one audit row, recorded by the
reconciler as ``system``.
"""

from __future__ import annotations

import pathlib
import re
import shutil

import pytest

from coffer.application.skill import drift_view
from coffer.domain.audit import AuditEventType
from coffer.domain.reconcile import Disposition, Outcome, Trigger
from coffer.domain.scope import Scope
from coffer.domain.skill.drift import DriftKind
from coffer.surfaces.http.reconcile_wiring import run_boot_pass
from tests.support.skills import SkillGraph, build_skill_graph, write_skill_folder

pytestmark = pytest.mark.asyncio


async def _delivered(tmp_path: pathlib.Path, name: str = "s1"):
    """A graph with no kind hooks, one agent and one skill delivered to it."""
    graph = await build_skill_graph(tmp_path, hooks=False)
    agent, skill_dir = await graph.register_agent(tmp_path, name="cur")
    skill = await graph.import_skill(tmp_path, name)  # the import asks for a pass
    link = skill_dir / name
    assert link.is_symlink()
    return graph, agent, skill, link


async def _events_after(graph: SkillGraph, seen: set[int]) -> list:
    return [e for e in await graph.audit.query(limit=500) if e.id not in seen]


async def _seen(graph: SkillGraph) -> set[int]:
    return {e.id for e in await graph.audit.query(limit=500)}


def _codes(report) -> dict[str, tuple[Disposition, Outcome]]:
    return {
        r.change.decision.reason_code: (r.change.decision.disposition, r.outcome)
        for r in report.results
    }


async def test_a_missing_link_is_repaired_with_one_audit_row(tmp_path):
    graph, _agent, _skill, link = await _delivered(tmp_path)
    master = graph.store.paths_for("s1").folder
    link.unlink()
    seen = await _seen(graph)

    report = await graph.run(Trigger.BOOT)

    assert _codes(report) == {"missing_link": (Disposition.REPAIR, Outcome.APPLIED)}
    assert link.resolve() == master.resolve()
    [event] = await _events_after(graph, seen)
    assert event.event_type == AuditEventType.SKILL_DRIFT_REMEDIATED.value
    assert (event.actor, event.resource_name) == ("system", "s1")
    assert event.details["kind"] == "missing_link"
    assert event.details["agent"] == "claude-code"
    assert (await graph.run()).results == ()  # converged
    await graph.dispose()


async def test_a_tampered_link_is_backed_up_and_repaired(tmp_path):
    graph, _agent, _skill, link = await _delivered(tmp_path)
    master = graph.store.paths_for("s1").folder
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    link.unlink()
    link.symlink_to(elsewhere, target_is_directory=True)
    seen = await _seen(graph)

    report = await graph.run(Trigger.PERIOD)

    assert _codes(report) == {"tampered_link": (Disposition.REPAIR, Outcome.APPLIED)}
    assert link.resolve() == master.resolve()
    [backup] = list(link.parent.glob("s1.coffer-backup-*"))
    # The spec's ``<path>.coffer-backup-<ts>`` shape: an integer timestamp.
    assert re.match(r".*\.coffer-backup-\d{10,}$", backup.name)
    assert backup.resolve() == elsewhere.resolve(), "the tampered link is kept, not deleted"
    [event] = await _events_after(graph, seen)
    assert event.event_type == AuditEventType.SKILL_DRIFT_REMEDIATED.value
    assert event.actor == "system"
    assert event.details["kind"] == "tampered_link"
    assert event.details["backup"] == str(backup)
    await graph.dispose()


async def test_foreign_content_is_left_untouched_and_reported_blocked(tmp_path):
    graph, _agent, _skill, link = await _delivered(tmp_path)
    link.unlink()
    link.mkdir()
    (link / "mine.txt").write_text("user data", encoding="utf-8")
    seen = await _seen(graph)

    for trigger in (Trigger.BOOT, Trigger.MANUAL):
        report = await graph.run(trigger)
        assert _codes(report) == {"foreign_content": (Disposition.BLOCKED, Outcome.PLANNED)}

    assert (link / "mine.txt").read_text(encoding="utf-8") == "user data"
    assert not link.is_symlink()
    assert await _events_after(graph, seen) == []
    [entry] = (await drift_view.verify(graph.skills, graph.reconciler)).entries
    assert (entry.kind, entry.target_path) == (DriftKind.REPLACED_WITH_REGULAR, str(link))
    await graph.dispose()


@pytest.mark.parametrize("how", ["disabled", "out_of_scope"])
async def test_a_skill_no_longer_granted_is_reclaimed(tmp_path, how):
    graph, agent, skill, link = await _delivered(tmp_path)
    if how == "disabled":
        await graph.rs.set_enabled(skill.uid, False, actor="cli")
    else:
        await graph.rs.update_scope(skill.uid, Scope(agents=["someone-else"]), actor="cli")
    seen = await _seen(graph)

    report = await graph.run(Trigger.HINT)

    assert _codes(report) == {"reclaim": (Disposition.REPAIR, Outcome.APPLIED)}
    assert not link.exists() and not link.is_symlink()
    assert graph.store.paths_for("s1").folder.is_dir(), "a reclaim is not a removal"
    [binding] = await graph.skills.bindings_for(skill.uid)
    assert (binding.enabled, binding.last_link_path) == (False, None)
    [event] = await _events_after(graph, seen)
    assert event.event_type == AuditEventType.SKILL_UNBOUND.value
    assert (event.actor, event.details["agent"]) == ("system", agent.name)
    await graph.dispose()


@pytest.mark.acceptance(
    spec="skill-manager", scenario="moving an agent's config directory moves its deliveries"
)
async def test_a_config_dir_move_relinks(tmp_path):
    graph, agent, skill, old_link = await _delivered(tmp_path)
    new_dir = tmp_path / "moved-cfg"
    new_dir.mkdir()
    await graph.agents.update_config_dir(uid=agent.uid, new_config_dir=str(new_dir), actor="cli")
    seen = await _seen(graph)

    report = await graph.run(Trigger.HINT)

    new_link = new_dir / "skills" / "s1"
    assert _codes(report) == {"link_moved": (Disposition.REPAIR, Outcome.APPLIED)}
    assert not old_link.exists() and not old_link.is_symlink()
    assert new_link.resolve() == graph.store.paths_for("s1").folder.resolve()
    [binding] = await graph.skills.bindings_for(skill.uid)
    assert binding.last_link_path == str(new_link)
    [event] = await _events_after(graph, seen)
    assert event.event_type == AuditEventType.SKILL_RELINKED.value
    assert (event.actor, event.details["link"]) == ("system", str(new_link))
    await graph.dispose()


async def test_an_orphan_master_is_only_reported(tmp_path):
    graph = await build_skill_graph(tmp_path, hooks=False)
    src = write_skill_folder(tmp_path / "orphan-src", name="orphan")
    graph.store.copy_in(src=src, name="orphan", meta={"name": "orphan"})
    seen = await _seen(graph)

    report = await graph.run(Trigger.BOOT)

    assert _codes(report) == {"orphan_master": (Disposition.REPORT, Outcome.PLANNED)}
    assert graph.store.exists("orphan")
    assert await _events_after(graph, seen) == []
    [entry] = (await drift_view.verify(graph.skills, graph.reconciler)).entries
    assert (entry.kind, entry.skill_name, entry.skill_uid) == (
        DriftKind.ORPHAN_MASTER,
        "orphan",
        None,
    )
    await graph.dispose()


async def test_a_correct_unrecorded_link_is_recorded_not_relinked(tmp_path):
    graph = await build_skill_graph(tmp_path, hooks=False)
    await graph.import_skill(tmp_path, "s1")  # no agent yet: nothing delivered
    agent, skill_dir = await graph.register_agent(tmp_path, name="cur")  # no hook: no pass
    master = graph.store.paths_for("s1").folder
    (skill_dir / "s1").symlink_to(master.resolve(), target_is_directory=True)
    inode = (skill_dir / "s1").lstat().st_ino
    seen = await _seen(graph)

    report = await graph.run()

    assert _codes(report) == {"unrecorded_link": (Disposition.REPAIR, Outcome.APPLIED)}
    assert (skill_dir / "s1").lstat().st_ino == inode, "the link on disk is adopted as is"
    assert await graph.delivered(agent) == {"s1"}
    [event] = await _events_after(graph, seen)
    assert event.event_type == AuditEventType.SKILL_BOUND.value
    assert event.details["adopted"] is True
    await graph.dispose()


async def test_a_missing_config_dir_is_not_recreated(tmp_path):
    graph, _agent, _skill, _link = await _delivered(tmp_path)
    shutil.rmtree(tmp_path / "cur-cfg")

    report = await graph.run()

    assert _codes(report) == {"agent_dir_missing": (Disposition.BLOCKED, Outcome.PLANNED)}
    assert not (tmp_path / "cur-cfg").exists()
    await graph.dispose()


async def test_a_dry_run_plan_writes_nothing(tmp_path):
    graph, _agent, skill, link = await _delivered(tmp_path)
    link.unlink()
    seen = await _seen(graph)
    before = await graph.skills.bindings_for(skill.uid)

    plan = await graph.plan()

    assert _codes(plan) == {"missing_link": (Disposition.REPAIR, Outcome.PLANNED)}
    assert not link.exists() and not link.is_symlink()
    assert await graph.skills.bindings_for(skill.uid) == before
    assert await _events_after(graph, seen) == []
    await graph.dispose()


async def test_an_unrecordable_repair_is_undone(tmp_path, monkeypatch):
    """Audit follows the write: when the event cannot be recorded, the
    reconciler runs the target's undo — the backup goes back where it was and
    the row is as it was — and the item fails, to be retried next pass."""
    graph, _agent, skill, link = await _delivered(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    link.unlink()
    link.symlink_to(elsewhere, target_is_directory=True)
    before = await graph.skills.bindings_for(skill.uid)

    async def _refuse(*_a, **_k):
        raise RuntimeError("audit store unavailable")

    monkeypatch.setattr(graph.audit, "record", _refuse)
    report = await graph.run()

    assert _codes(report) == {"tampered_link": (Disposition.REPAIR, Outcome.FAILED)}
    assert link.resolve() == elsewhere.resolve()
    assert list(link.parent.glob("s1.coffer-backup-*")) == []
    assert await graph.skills.bindings_for(skill.uid) == before
    await graph.dispose()


@pytest.mark.acceptance(spec="skill-manager", scenario="a boot heal failure never blocks startup")
async def test_a_failing_skill_target_never_blocks_boot(tmp_path, monkeypatch):
    """A filesystem the target cannot read is reported on the pass and logged;
    the boot pass returns and the daemon comes up."""
    graph, _agent, _skill, link = await _delivered(tmp_path)
    link.unlink()

    def _unreadable(_known):
        raise OSError("disk hiccup")

    monkeypatch.setattr(graph.store, "find_orphans", _unreadable)
    await run_boot_pass(graph.reconciler)  # does not raise

    report = await graph.run(Trigger.BOOT)
    assert [f.target for f in report.failures] == ["skill_link"]
    assert report.results == ()
    await graph.dispose()
