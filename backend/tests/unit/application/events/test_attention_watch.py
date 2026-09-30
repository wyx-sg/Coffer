"""AttentionWatcher: one ``attention`` envelope per change in what the list reports."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from coffer.application.attention import (
    AttentionAction,
    AttentionItem,
    AttentionReport,
    Severity,
    SourceError,
)
from coffer.application.events.attention_watch import AttentionWatcher, fingerprint
from coffer.application.events.broker import Envelope, EventBroker
from coffer.domain.reconcile import Changed, PassReport, Trigger

_ACTION = AttentionAction("test", "POST", "/api/v1/resources/mcp_server/u1/test")


def _item(uid: str = "u1", *, reason: str = "mcp_failing", title: str = "A") -> AttentionItem:
    return AttentionItem(
        kind="mcp_server",
        uid=uid,
        title=title,
        reason_code=reason,
        reason="It fails.",
        severity=Severity.ERROR,
        action=_ACTION,
    )


class _Reports:
    """A scripted attention service: returns ``current`` on every call."""

    def __init__(self, current: AttentionReport) -> None:
        self.current = current
        self.calls = 0

    async def report(self) -> AttentionReport:
        self.calls += 1
        return self.current


def _attention_envelopes(broker: EventBroker) -> list[Envelope]:
    return [e for e in broker.buffered if e.kind == "attention"]


async def test_the_first_check_is_only_the_baseline() -> None:
    broker = EventBroker()
    watcher = AttentionWatcher(broker)
    reports = _Reports(AttentionReport((_item(),)))
    assert await watcher.check(reports.report) is False
    assert broker.head == 0


async def test_a_new_item_publishes_one_attention_envelope_without_id_or_rev() -> None:
    broker = EventBroker()
    watcher = AttentionWatcher(broker)
    reports = _Reports(AttentionReport(()))
    await watcher.check(reports.report)
    reports.current = AttentionReport((_item(),))
    assert await watcher.check(reports.report) is True
    assert broker.buffered == (Envelope(1, "attention", None, None, "upsert"),)
    # Unchanged since: nothing more.
    assert await watcher.check(reports.report) is False
    assert broker.head == 1


async def test_wording_and_titles_do_not_count_as_a_change() -> None:
    before = AttentionReport((_item(title="A"),), (SourceError("sync", "boom 1"),))
    after = AttentionReport((_item(title="Renamed"),), (SourceError("sync", "boom 2"),))
    assert fingerprint(before) == fingerprint(after)


def test_reason_severity_and_failing_sources_do_count() -> None:
    base = AttentionReport((_item(),))
    assert fingerprint(base) != fingerprint(AttentionReport((_item(reason="mcp_missing_secret"),)))
    assert fingerprint(base) != fingerprint(AttentionReport((_item("u2"),)))
    assert fingerprint(base) != fingerprint(
        AttentionReport((_item(),), (SourceError("sync", "x"),))
    )


async def test_a_resource_write_or_a_pass_prompts_a_settled_recompute() -> None:
    broker = EventBroker()
    watcher = AttentionWatcher(broker, settle_seconds=0.01, period_seconds=60)
    reports = _Reports(AttentionReport(()))
    task = asyncio.ensure_future(watcher.serve(reports.report))
    try:
        await asyncio.sleep(0.02)
        assert reports.calls == 1  # the baseline
        reports.current = AttentionReport((_item(),))
        watcher.on_changed(Changed("mcp_server", "u1", 2))
        watcher.on_changed(Changed("mcp_server", "u1", 3))  # settles into one recompute
        await asyncio.sleep(0.05)
        assert reports.calls == 2
        assert len(_attention_envelopes(broker)) == 1

        reports.current = AttentionReport(())
        now = datetime.now(tz=UTC)
        watcher.on_pass(PassReport(Trigger.PERIOD, False, now, now, ()))
        await asyncio.sleep(0.05)
        assert reports.calls == 3
        assert len(_attention_envelopes(broker)) == 2
    finally:
        task.cancel()


async def test_the_period_recomputes_with_nothing_prompting_it() -> None:
    broker = EventBroker()
    watcher = AttentionWatcher(broker, settle_seconds=0, period_seconds=0.01)
    reports = _Reports(AttentionReport(()))
    await watcher.prime(reports.report)
    task = asyncio.ensure_future(watcher.serve(reports.report))
    try:
        reports.current = AttentionReport((_item(),))
        await asyncio.sleep(0.05)
        assert len(_attention_envelopes(broker)) == 1
    finally:
        task.cancel()


async def test_a_failing_report_is_logged_and_the_loop_carries_on() -> None:
    broker = EventBroker()
    watcher = AttentionWatcher(broker, settle_seconds=0, period_seconds=0.01)
    calls = 0

    async def flaky() -> AttentionReport:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("source gone")
        return AttentionReport(() if calls == 1 else (_item(),))

    await watcher.prime(flaky)
    task = asyncio.ensure_future(watcher.serve(flaky))
    try:
        # Wait for the loop to get past the failure rather than a fixed time,
        # so a loaded machine cannot starve it of turns.
        async with asyncio.timeout(5):
            while calls < 3 or not _attention_envelopes(broker):
                await asyncio.sleep(0.01)
        assert len(_attention_envelopes(broker)) == 1
    finally:
        task.cancel()
