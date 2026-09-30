"""``restore_from_audit`` and ``SessionLedger.ready`` — the ledger rebuilt from
the delivery fires in the audit log (spec memory "Remember what a session was
given across daemon restarts")."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from coffer.application.memory.ledger_restore import RESTORE_WINDOW, restore_from_audit
from coffer.application.memory.session_ledger import SessionLedger
from coffer.domain.audit import AuditEntry, AuditEventType

_NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


def _fire(details: dict[str, Any], minutes_ago: int = 1) -> AuditEntry:
    return AuditEntry(
        id=None,
        timestamp=_NOW - timedelta(minutes=minutes_ago),
        event_type=AuditEventType.MEMORY_DELIVERY_FIRED.value,
        actor="claude-code",
        details=details,
    )


class _Audit:
    def __init__(self, entries: list[AuditEntry]) -> None:
        self.entries = entries
        self.asked: list[dict[str, Any]] = []

    async def query(self, **kw: Any) -> list[AuditEntry]:
        self.asked.append(kw)
        return [e for e in self.entries if e.timestamp >= kw["since"]]


@pytest.mark.asyncio
async def test_prompt_and_trigger_fires_are_replayed_per_session() -> None:
    audit = _Audit(
        [
            _fire({"moment": "guard", "session_id": "s1", "trigger": "t1", "notes": ["p/a"]}),
            _fire({"moment": "prompt", "session_id": "s1", "notes": ["p/a", "global/b"]}),
            _fire({"moment": "error", "session_id": "s2", "trigger": "t2", "notes": ["p/a"]}),
            _fire({"moment": "session_start", "session_id": "s3"}),
            _fire({"moment": "prompt", "notes": ["p/c"]}),  # no session: nothing to key on
            _fire({"moment": "prompt", "session_id": "old", "notes": ["p/d"]}, minutes_ago=10**6),
        ]
    )
    ledger = SessionLedger()

    applied = await restore_from_audit(ledger, audit, now=_NOW)

    assert applied == 3
    assert ledger.delivered("s1") == {"p/a", "global/b"}
    assert ledger.has_fired("s1", "t1") and ledger.has_fired("s2", "t2")
    assert ledger.delivered("s3") == frozenset() and ledger.delivered("old") == frozenset()
    assert audit.asked[0]["event_type"] == "memory_delivery_fired"
    assert audit.asked[0]["since"] == _NOW - RESTORE_WINDOW


@pytest.mark.asyncio
async def test_ready_restores_once_and_a_failure_leaves_the_ledger_empty() -> None:
    calls: list[int] = []

    async def restore(ledger: SessionLedger) -> None:
        calls.append(1)
        ledger.mark_delivered("s1", ["p/a"])

    ledger = SessionLedger(restore=restore)
    await ledger.ready()
    await ledger.ready()
    assert calls == [1] and ledger.delivered("s1") == {"p/a"}

    async def broken(_ledger: SessionLedger) -> None:
        raise RuntimeError("audit log unreadable")

    failing = SessionLedger(restore=broken)
    await failing.ready()
    assert failing.delivered("s1") == frozenset()
