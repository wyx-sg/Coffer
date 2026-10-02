"""The reconciler loop over in-memory targets: repair only what the policy
allows, audit after the write and undo when the audit fails, dry-run writes
nothing, a raising target is skipped, hints bring a pass forward."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest

from coffer.application.audit_service import AuditService
from coffer.application.reconcile.ports import Applied, AuditEvent
from coffer.application.reconcile.reconciler import Reconciler
from coffer.domain.audit import AuditEntry
from coffer.domain.reconcile import (
    Changed,
    Decision,
    Difference,
    Disposition,
    Item,
    Op,
    Outcome,
    PlannedChange,
    Subject,
    Trigger,
)


class _AuditRepo:
    def __init__(self, *, fail: bool = False) -> None:
        self.rows: list[AuditEntry] = []
        self.fail = fail

    async def insert(self, entry: AuditEntry) -> None:
        if self.fail:
            raise RuntimeError("audit store is gone")
        self.rows.append(entry)

    async def query(self, **_: Any) -> list[AuditEntry]:
        return list(self.rows)


@dataclass
class _Target:
    """An in-memory 'file': ``actual`` is what is there, ``wanted`` what
    Coffer wants. Keys starting with ``foreign`` are only reported."""

    name: str = "fake"
    kinds: frozenset[str] = frozenset({"agent"})
    wanted: dict[str, dict[str, Any]] = field(default_factory=dict)
    actual: dict[str, dict[str, Any]] = field(default_factory=dict)
    applied: list[str] = field(default_factory=list)
    triggers: list[Trigger] = field(default_factory=list)
    raise_on_desired: bool = False
    on_apply: Any = None

    def _items(self, src: dict[str, dict[str, Any]]) -> list[Item]:
        return [Item(k, Subject("agent", k, k.title()), dict(v), f"/f/{k}") for k, v in src.items()]

    async def desired(self) -> Sequence[Item]:
        if self.raise_on_desired:
            raise OSError("cannot read")
        return self._items(self.wanted)

    async def observe(self) -> Sequence[Item]:
        return self._items(self.actual)

    def decide(self, differences: Sequence[Difference], trigger: Trigger) -> Sequence[Decision]:
        self.triggers.append(trigger)
        out = []
        for d in differences:
            if d.key.startswith("foreign") and trigger is not Trigger.MANUAL:
                out.append(Decision(Disposition.REPORT, "foreign", "Not ours to change."))
            else:
                out.append(Decision(Disposition.REPAIR, "stale", "Out of date."))
        return out

    async def apply(self, change: PlannedChange) -> Applied:
        d = change.difference
        before = self.actual.get(d.key)
        if self.on_apply is not None:
            await self.on_apply()
        if d.op is Op.REMOVE:
            del self.actual[d.key]
        else:
            self.actual[d.key] = dict(self.wanted[d.key])
        self.applied.append(d.key)

        async def _undo() -> None:
            if before is None:
                self.actual.pop(d.key, None)
            else:
                self.actual[d.key] = before

        return Applied(AuditEvent("thing_repaired", None, {"key": d.key}), undo=_undo)


def _reconciler(repo: _AuditRepo | None = None, **kw: Any) -> tuple[Reconciler, _AuditRepo]:
    repo = repo or _AuditRepo()
    return Reconciler(audit=AuditService(repo), **kw), repo


async def test_a_pass_repairs_what_the_policy_allows_and_reports_the_rest() -> None:
    rec, repo = _reconciler()
    t = _Target(
        wanted={"a": {"command": "new"}, "b": {"command": "x"}},
        actual={"a": {"command": "old"}, "foreign1": {"command": "theirs"}},
    )
    rec.register(t)
    report = await rec.run(trigger=Trigger.PERIOD)
    outcomes = {r.change.id: r.outcome for r in report.results}
    assert outcomes == {
        "fake:a": Outcome.APPLIED,
        "fake:b": Outcome.APPLIED,
        "fake:foreign1": Outcome.PLANNED,
    }
    assert t.actual == {
        "a": {"command": "new"},
        "b": {"command": "x"},
        "foreign1": {"command": "theirs"},
    }
    assert [r.event_type for r in repo.rows] == ["thing_repaired", "thing_repaired"]
    assert {r.actor for r in repo.rows} == {"system"}
    assert all(r.details["reconcile"] == "period" for r in repo.rows)
    # The report-only difference is still open, and has a first-seen time.
    assert rec.first_seen("fake:foreign1") is not None
    assert rec.first_seen("fake:a") is None
    assert rec.last_pass is report


async def test_dry_run_writes_nothing_and_remembers_nothing() -> None:
    rec, repo = _reconciler()
    t = _Target(wanted={"a": {"command": "new"}}, actual={"a": {"command": "old"}})
    rec.register(t)
    report = await rec.plan()
    assert report.dry_run is True
    (only,) = report.results
    assert only.outcome is Outcome.PLANNED
    assert only.change.difference.changed_params == ("command",)
    assert t.actual == {"a": {"command": "old"}} and t.applied == []
    assert repo.rows == []
    assert rec.first_seen("fake:a") is None
    assert rec.last_pass is None
    assert not rec.pending_hints


async def test_a_failed_audit_restores_the_write_and_fails_the_item() -> None:
    rec, _repo = _reconciler(_AuditRepo(fail=True))
    t = _Target(wanted={"a": {"command": "new"}}, actual={"a": {"command": "old"}})
    rec.register(t)
    report = await rec.run(trigger=Trigger.PERIOD)
    (only,) = report.results
    assert only.outcome is Outcome.FAILED
    assert only.error is not None and "audit not recorded" in only.error
    assert t.applied == ["a"]  # it was written ...
    assert t.actual == {"a": {"command": "old"}}  # ... and put back
    # Still open, so the next pass retries it.
    assert rec.first_seen("fake:a") is not None


@pytest.mark.acceptance(
    spec="resource-framework", scenario="a target that fails is reported and the pass goes on"
)
async def test_a_raising_target_is_reported_and_the_pass_goes_on() -> None:
    rec, _ = _reconciler()
    broken = _Target(name="broken", raise_on_desired=True)
    fine = _Target(name="fine", wanted={"a": {"v": 1}})
    rec.register(broken)
    rec.register(fine)
    report = await rec.run(trigger=Trigger.BOOT)
    assert [f.target for f in report.failures] == ["broken"]
    assert "cannot read" in report.failures[0].error
    assert fine.actual == {"a": {"v": 1}}


async def test_a_raising_write_fails_only_that_item() -> None:
    rec, repo = _reconciler()
    t = _Target(wanted={"a": {"v": 1}})

    async def _boom() -> None:
        raise PermissionError("read-only")

    t.on_apply = _boom
    rec.register(t)
    (only,) = (await rec.run(trigger=Trigger.PERIOD)).results
    assert only.outcome is Outcome.FAILED and "read-only" in (only.error or "")
    assert repo.rows == []


async def test_manual_apply_writes_only_the_named_items_as_the_caller() -> None:
    rec, repo = _reconciler()
    t = _Target(
        wanted={"a": {"v": 1}, "b": {"v": 2}},
        actual={"foreign1": {"v": 0}},
    )
    rec.register(t)
    report = await rec.apply(["fake:foreign1", "fake:b", "nope:x"], actor="cli")
    assert {r.change.id for r in report.results} == {"fake:foreign1", "fake:b"}
    assert t.triggers == [Trigger.MANUAL]
    assert "a" not in t.actual and t.actual == {"b": {"v": 2}}
    assert {r.actor for r in repo.rows} == {"cli"}


async def test_the_import_and_switch_triggers_record_their_own_actor() -> None:
    rec, repo = _reconciler()
    rec.register(_Target(wanted={"a": {"v": 1}}))
    await rec.run(trigger=Trigger.IMPORT)
    rec.register(_Target(name="other", wanted={"b": {"v": 1}}))
    await rec.run(targets=["other"], trigger=Trigger.SWITCH)
    assert [r.actor for r in repo.rows] == ["sync", "system:features"]


async def test_unknown_targets_are_refused_and_duplicates_too() -> None:
    rec, _ = _reconciler()
    rec.register(_Target())
    with pytest.raises(ValueError, match="twice"):
        rec.register(_Target())
    with pytest.raises(KeyError, match="nope"):
        await rec.run(targets=["nope"], trigger=Trigger.CHANGE)
    assert rec.target_names == ("fake",)
    assert rec.target_kinds("fake") == frozenset({"agent"})
    assert rec.target_kinds("nope") == frozenset()


async def test_a_pass_asked_for_inside_a_pass_becomes_a_hint() -> None:
    """A repair whose write set off a kind hook that asks for a pass must not
    wait on the lock it is itself holding."""
    rec, _ = _reconciler()
    t = _Target(wanted={"a": {"v": 1}})
    inner: list[Any] = []

    async def _nested() -> None:
        inner.append(await rec.run(targets=["fake"], trigger=Trigger.CHANGE))

    t.on_apply = _nested
    rec.register(t)
    await asyncio.wait_for(rec.run(trigger=Trigger.PERIOD), timeout=2)
    assert inner[0].results == ()
    assert ("target", "fake") in rec.pending_hints


@pytest.mark.acceptance(spec="resource-framework", scenario="a write brings the next pass forward")
async def test_a_hint_brings_a_pass_forward_for_the_kinds_targets_only() -> None:
    rec, _ = _reconciler(period_seconds=3600, settle_seconds=0.01)
    agent_t = _Target(name="agent_t", kinds=frozenset({"agent"}), wanted={"a": {"v": 1}})
    skill_t = _Target(name="skill_t", kinds=frozenset({"skill"}), wanted={"s": {"v": 1}})
    rec.register(agent_t)
    rec.register(skill_t)
    loop = asyncio.create_task(rec.serve())
    try:
        rec.hint(Changed("agent", "u1"))
        rec.hint(Changed("agent", "u1"))  # a repeated hint is one pending pass
        assert rec.pending_hints == {("agent", "u1")}
        for _ in range(200):
            if agent_t.applied:
                break
            await asyncio.sleep(0.01)
    finally:
        loop.cancel()
        with pytest.raises(asyncio.CancelledError):
            await loop
    assert agent_t.applied == ["a"]
    assert skill_t.applied == []
    assert agent_t.triggers == [Trigger.HINT]


async def test_the_period_runs_every_target() -> None:
    rec, _ = _reconciler(period_seconds=0.01)
    t = _Target(wanted={"a": {"v": 1}})
    rec.register(t)
    loop = asyncio.create_task(rec.serve())
    try:
        for _ in range(200):
            if t.applied:
                break
            await asyncio.sleep(0.01)
    finally:
        loop.cancel()
        with pytest.raises(asyncio.CancelledError):
            await loop
    assert t.applied == ["a"]
    assert t.triggers[0] is Trigger.PERIOD


async def test_hold_keeps_other_passes_out_until_released() -> None:
    rec, _ = _reconciler()
    t = _Target(wanted={"a": {"v": 1}})
    rec.register(t)
    async with rec.hold():
        waiting = asyncio.create_task(rec.run(trigger=Trigger.PERIOD))
        await asyncio.sleep(0.05)
        assert not waiting.done() and t.applied == []
        # The holder's own pass runs inside the hold.
        await rec.run(targets=["fake"], trigger=Trigger.IMPORT)
        assert t.applied == ["a"]
    await asyncio.wait_for(waiting, timeout=2)


async def test_a_decision_count_mismatch_is_a_target_failure() -> None:
    rec, _ = _reconciler()

    class _Short(_Target):
        def decide(self, differences: Sequence[Difference], trigger: Trigger) -> Sequence[Decision]:
            return []

    rec.register(_Short(wanted={"a": {"v": 1}}))
    report = await rec.run(trigger=Trigger.PERIOD)
    assert report.results == ()
    assert "decided 0 of 1" in report.failures[0].error


async def test_pass_listeners_hear_every_writing_pass_and_never_a_dry_run() -> None:
    rec, _ = _reconciler()
    rec.register(_Target(wanted={"a": {"command": "new"}}))
    heard: list[Trigger] = []

    def _boom(_: object) -> None:
        raise RuntimeError("listener gone")

    rec.add_pass_listener(_boom)  # a raising listener fails neither the pass nor the next one
    rec.add_pass_listener(lambda report: heard.append(report.trigger))
    await rec.plan(trigger=Trigger.PERIOD)
    assert heard == []
    report = await rec.run(trigger=Trigger.PERIOD)
    assert heard == [Trigger.PERIOD]
    assert report.count(Outcome.APPLIED) == 1
