"""The cross-kind attention list: feature filtering, failure isolation,
ordering and counts; and the reconciler-drift source's items and actions."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.application.attention import (
    AttentionAction,
    AttentionItem,
    AttentionService,
    Severity,
)
from coffer.application.audit_service import AuditService
from coffer.application.reconcile.attention_source import APPLY_PATH, DriftAttentionSource
from coffer.application.reconcile.ports import Applied
from coffer.application.reconcile.reconciler import Reconciler
from coffer.domain.audit import AuditEntry
from coffer.domain.reconcile import (
    Decision,
    Difference,
    Disposition,
    Item,
    PlannedChange,
    Subject,
    Trigger,
)


def _item(kind: str, severity: Severity, title: str = "x") -> AttentionItem:
    return AttentionItem(
        kind=kind,
        uid="u",
        title=title,
        reason_code=f"{kind}_code",
        reason="Because.",
        severity=severity,
        action=AttentionAction("check", "GET", f"/api/v1/{kind}"),
    )


class _Source:
    def __init__(self, name: str, items: list[AttentionItem], feature: str | None = None) -> None:
        self.name = name
        self.feature = feature
        self._items = items
        self.asked = 0

    async def items(self) -> Sequence[AttentionItem]:
        self.asked += 1
        return list(self._items)


class _Broken(_Source):
    async def items(self) -> Sequence[AttentionItem]:
        raise ConnectionError("store is gone")


@pytest.mark.acceptance(
    spec="resource-framework", scenario="each item carries one action from its kind's own page"
)
async def test_items_sort_by_severity_and_are_counted_per_kind() -> None:
    svc = AttentionService(
        [
            _Source("agent", [_item("agent", Severity.WARNING)]),
            _Source(
                "mcp", [_item("mcp_server", Severity.ERROR), _item("mcp_server", Severity.INFO)]
            ),
        ],
        feature_enabled=lambda _k: True,
    )
    report = await svc.report()
    assert [(i.kind, i.severity) for i in report.items] == [
        ("mcp_server", Severity.ERROR),
        ("agent", Severity.WARNING),
        ("mcp_server", Severity.INFO),
    ]
    assert report.counts_by_kind == {"mcp_server": 2, "agent": 1}
    assert report.errors == ()


@pytest.mark.acceptance(
    spec="resource-framework", scenario="a failing source does not hide the others"
)
async def test_a_failing_source_is_reported_beside_the_others() -> None:
    svc = AttentionService(
        [_Broken("sync", []), _Source("agent", [_item("agent", Severity.WARNING)])],
        feature_enabled=lambda _k: True,
    )
    report = await svc.report()
    assert [i.kind for i in report.items] == ["agent"]
    assert [(e.source, "store is gone" in e.error) for e in report.errors] == [("sync", True)]


@pytest.mark.acceptance(
    spec="resource-framework", scenario="a switched-off feature's signals are left out"
)
@pytest.mark.acceptance(
    spec="experimental-features", scenario="a switched-off feature's attention source is not asked"
)
async def test_a_switched_off_features_source_is_not_asked() -> None:
    gated = _Source("fake", [_item("fake", Severity.ERROR)], feature="fake_feature")
    svc = AttentionService([gated], feature_enabled=lambda key: key != "fake_feature")
    report = await svc.report()
    assert report.items == () and gated.asked == 0
    svc_on = AttentionService([gated], feature_enabled=lambda _k: True)
    assert len((await svc_on.report()).items) == 1


async def test_every_item_carries_a_handoff_the_source_may_leave_to_the_service() -> None:
    own = AttentionItem(
        kind="cli",
        uid="u",
        title="jq",
        reason_code="cli_missing",
        reason="Missing.",
        severity=Severity.WARNING,
        action=AttentionAction("check", "GET", "/api/v1/cli"),
        handoff="install jq",
    )
    bare = _item("sync", Severity.ERROR, title="Backup")
    svc = AttentionService([_Source("a", [own, bare])], feature_enabled=lambda _k: True)
    items = {i.kind: i for i in (await svc.report()).items}
    assert items["cli"].handoff == "install jq"
    fallback = items["sync"].handoff
    assert fallback is not None
    assert "Backup" in fallback and "Because." in fallback and "GET /api/v1/sync" in fallback


# --- the drift source ----------------------------------------------------------


class _Audit:
    async def insert(self, entry: AuditEntry) -> None:
        return None

    async def query(self, **_: Any) -> list[AuditEntry]:
        return []


class _Target:
    """``fixable`` repairs on any trigger (but its write fails), ``foreign``
    only on a person's request, ``stuck`` never."""

    name = "t"
    kinds = frozenset({"agent"})

    async def desired(self) -> Sequence[Item]:
        return [
            Item(k, Subject("agent", f"uid-{k}", f"Agent {k}"), {"v": 1}, f"/f/{k}")
            for k in ("fixable", "foreign", "stuck")
        ]

    async def observe(self) -> Sequence[Item]:
        return []

    def decide(self, differences: Sequence[Difference], trigger: Trigger) -> Sequence[Decision]:
        out = []
        for d in differences:
            if d.key == "fixable":
                out.append(Decision(Disposition.REPAIR, "stale", "Out of date."))
            elif d.key == "foreign" and trigger is not Trigger.MANUAL:
                out.append(Decision(Disposition.REPORT, "unclaimed", "Not claimed."))
            elif d.key == "foreign":
                out.append(Decision(Disposition.REPAIR, "unclaimed", "Not claimed."))
            else:
                out.append(Decision(Disposition.BLOCKED, "missing_launcher", "No launcher."))
        return out

    async def apply(self, change: PlannedChange) -> Applied:
        raise PermissionError("read-only")


async def test_drift_lists_what_a_pass_could_not_fix_with_honest_actions() -> None:
    rec = Reconciler(audit=AuditService(_Audit()))
    rec.register(_Target())
    source = DriftAttentionSource(rec)
    # Before any writing pass: the repairable item is left to the next pass.
    assert {i.reason_code for i in await source.items()} == {"unclaimed", "missing_launcher"}

    before = datetime.now(tz=UTC)
    await rec.run(trigger=Trigger.PERIOD)  # the repair of "fixable" fails
    items = {i.uid: i for i in await source.items()}
    assert set(items) == {"uid-fixable", "uid-foreign", "uid-stuck"}
    assert items["uid-fixable"].action == AttentionAction(
        "repair", "POST", APPLY_PATH, {"ids": ["t:fixable"]}
    )
    # Reported now, but a person's request would repair it.
    assert items["uid-foreign"].action.verb == "repair"
    assert items["uid-foreign"].severity is Severity.WARNING
    # Blocked: nothing to write until the cause is gone.
    assert items["uid-stuck"].action == AttentionAction(
        "review", "GET", "/api/v1/reconcile/plan?target=t"
    )
    assert items["uid-stuck"].severity is Severity.ERROR
    assert all(i.since is not None and i.since >= before for i in items.values())
    assert items["uid-stuck"].title == "Agent stuck" and items["uid-stuck"].kind == "agent"


async def test_a_failing_target_becomes_an_item() -> None:
    class _Raising(_Target):
        async def desired(self) -> Sequence[Item]:
            raise OSError("unreadable")

    rec = Reconciler(audit=AuditService(_Audit()))
    rec.register(_Raising())
    (item,) = await DriftAttentionSource(rec).items()
    assert (item.kind, item.reason_code, item.severity) == (
        "reconcile",
        "target_failed",
        Severity.ERROR,
    )
    assert "unreadable" in item.reason


class _Gated(_Source):
    """Waits for every gated source to be asked before any answers — only
    possible if the sources are asked concurrently."""

    def __init__(self, name: str, items: list[AttentionItem], gate: Any) -> None:
        super().__init__(name, items)
        self._gate = gate

    async def items(self) -> Sequence[AttentionItem]:
        self._gate.arrived += 1
        if self._gate.arrived == self._gate.total:
            self._gate.event.set()
        await self._gate.event.wait()
        return await super().items()


class _Gate:
    def __init__(self, total: int) -> None:
        import asyncio

        self.total = total
        self.arrived = 0
        self.event = asyncio.Event()


@pytest.mark.asyncio
async def test_sources_are_asked_concurrently_and_errors_keep_source_order() -> None:
    import asyncio

    gate = _Gate(2)
    sources = [
        _Gated("a", [_item("agent", Severity.INFO)], gate),
        _Broken("b", []),
        _Gated("c", [_item("mcp", Severity.ERROR)], gate),
        _Broken("d", []),
    ]
    service = AttentionService(sources, feature_enabled=lambda _f: True)

    report = await asyncio.wait_for(service.report(), timeout=2)

    assert [i.kind for i in report.items] == ["mcp", "agent"]  # severity order, not source order
    assert [e.source for e in report.errors] == ["b", "d"]  # source order
