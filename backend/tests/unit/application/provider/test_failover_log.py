"""The failover log is idempotent (spec provider-switching "Log every failover
in Activity"): a spool file ingested again hands its failovers over again, and
one the log already holds is not written twice."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from coffer.application.provider.usage_lookup import ProviderUsageLookup
from coffer.application.usage.ports import FailoverEvent

_AT = datetime(2026, 10, 2, 9, 30, tzinfo=UTC)


class _Audit:
    """Just enough of ``AuditService``: ``record`` stores, ``query`` reads back."""

    def __init__(self) -> None:
        self.rows: list[SimpleNamespace] = []

    async def record(self, event_type: str, *, details: dict[str, Any], **_: Any) -> None:
        self.rows.append(SimpleNamespace(event_type=event_type, details=details))

    async def query(self, *, event_type: str, **_: Any) -> list[SimpleNamespace]:
        return [r for r in self.rows if r.event_type == event_type]


class _Providers:
    async def get(self, uid: str) -> Any:
        raise LookupError(uid)


def _event(**over: Any) -> FailoverEvent:
    base: dict[str, Any] = {
        "at": _AT,
        "agent_uid": "agent-1",
        "agent_type": "claude_code",
        "model": "m",
        "from_uid": "conn-a",
        "from_name": "Primary",
        "reason": "status 503",
    }
    return FailoverEvent(**{**base, **over})


@pytest.fixture
def lookup() -> tuple[ProviderUsageLookup, _Audit]:
    audit = _Audit()
    return ProviderUsageLookup(_Providers(), None, audit), audit  # type: ignore[arg-type]


async def test_a_failover_is_logged_once(lookup: tuple[ProviderUsageLookup, _Audit]) -> None:
    log, audit = lookup
    await log.failed_over(_event())
    await log.failed_over(_event())  # the same spool file, ingested again
    assert len(audit.rows) == 1


async def test_a_different_failover_is_its_own_row(
    lookup: tuple[ProviderUsageLookup, _Audit],
) -> None:
    log, audit = lookup
    await log.failed_over(_event())
    await log.failed_over(_event(from_uid="conn-b"))
    await log.failed_over(_event(at=_AT.replace(second=5)))
    assert len(audit.rows) == 3
