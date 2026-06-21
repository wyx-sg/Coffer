"""Integration test: _JournalInsightSink writes distilled insights to the journal.

Verifies that the sink appends to the project journal (returning the entry's iso
timestamp marker), skips when there is no project path, and skips when the path
does not resolve to a git project (``ScopeUnresolved`` → there is no global journal).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.domain.distill.session import DistilledInsight
from coffer.domain.errors import ScopeUnresolved

pytestmark = pytest.mark.asyncio

_TS = datetime(2026, 6, 21, 9, 0, tzinfo=UTC)


class _Entry:
    def __init__(self, ts: datetime) -> None:
        self.timestamp = ts


class _FakeJournalService:
    """Records append calls and returns an entry with a fixed timestamp."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def append(self, *, cwd, body, actor) -> _Entry:
        self.calls.append({"cwd": cwd, "body": body, "actor": actor})
        return _Entry(_TS)


class _RaisingJournalService:
    """Always raises ScopeUnresolved (path not inside a git project)."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def append(self, *, cwd, body, actor) -> _Entry:
        self.calls.append({"cwd": cwd, "body": body, "actor": actor})
        raise ScopeUnresolved(cwd or "unknown")


def _insight() -> DistilledInsight:
    return DistilledInsight(
        name="test-insight",
        description="A test",
        body="Body text",
    )


async def test_journal_sink_appends_and_returns_marker() -> None:
    """A project_path appends to the journal and record() returns the iso timestamp."""
    from coffer.surfaces.http.distill_wiring import _JournalInsightSink

    svc = _FakeJournalService()
    sink = _JournalInsightSink(svc)  # type: ignore[arg-type]

    marker = await sink.record(
        project_path="/repo",
        insight=_insight(),
        origin_session_id="sess-abc",
    )

    assert marker == _TS.isoformat()
    assert len(svc.calls) == 1
    assert svc.calls[0]["cwd"] == "/repo"
    assert svc.calls[0]["actor"] == "agent"
    # Body joins the non-empty pieces of name/description/body.
    assert svc.calls[0]["body"] == "test-insight\n\nA test\n\nBody text"


async def test_journal_sink_skips_when_no_project_path() -> None:
    """project_path=None returns None and does NOT call append (no global journal)."""
    from coffer.surfaces.http.distill_wiring import _JournalInsightSink

    svc = _FakeJournalService()
    sink = _JournalInsightSink(svc)  # type: ignore[arg-type]

    marker = await sink.record(
        project_path=None,
        insight=_insight(),
        origin_session_id="sess-xyz",
    )

    assert marker is None
    assert svc.calls == []


async def test_journal_sink_skips_when_scope_unresolved() -> None:
    """A project_path that raises ScopeUnresolved returns None (path not in a git project)."""
    from coffer.surfaces.http.distill_wiring import _JournalInsightSink

    svc = _RaisingJournalService()
    sink = _JournalInsightSink(svc)  # type: ignore[arg-type]

    marker = await sink.record(
        project_path="/not/a/git/root",
        insight=_insight(),
        origin_session_id="sess-abc",
    )

    assert marker is None
    assert len(svc.calls) == 1
