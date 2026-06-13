"""Integration test: _MemoryInsightSink scope fallback.

Verifies that when project_path is not inside a git work-tree,
_MemoryInsightSink.record falls back to GLOBAL scope and returns a fact id.
"""

from __future__ import annotations

import pytest

from coffer.domain.distill.session import DistilledInsight, InsightType
from coffer.domain.errors import ScopeUnresolved
from coffer.domain.memory.scope import MemoryScope

pytestmark = pytest.mark.asyncio


class _FakeMemoryService:
    """Minimal fake: raises ScopeUnresolved for PROJECT, succeeds for GLOBAL."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def add_fact(self, *, scope: MemoryScope, cwd, **kwargs) -> object:
        self.calls.append({"scope": scope, "cwd": cwd, **kwargs})
        if scope == MemoryScope.PROJECT:
            raise ScopeUnresolved(cwd or "unknown")

        class _Fact:
            id = "global-fact-id"

        return _Fact()


async def test_memory_sink_falls_back_to_global_when_scope_unresolved() -> None:
    """project_path that triggers ScopeUnresolved retries with GLOBAL scope."""
    from coffer.surfaces.http.distill_wiring import _MemoryInsightSink

    svc = _FakeMemoryService()
    sink = _MemoryInsightSink(svc)  # type: ignore[arg-type]

    insight = DistilledInsight(
        name="test-insight",
        description="A test",
        body="Body text",
        type=InsightType.DECISION,
    )
    fact_id = await sink.record(
        project_path="/not/a/git/root",
        insight=insight,
        origin_session_id="sess-abc",
    )

    assert fact_id == "global-fact-id"
    # First call was PROJECT (which raised); second was GLOBAL
    assert len(svc.calls) == 2
    assert svc.calls[0]["scope"] == MemoryScope.PROJECT
    assert svc.calls[1]["scope"] == MemoryScope.GLOBAL
    assert svc.calls[1]["cwd"] is None


async def test_memory_sink_uses_global_directly_when_no_project_path() -> None:
    """When project_path is None, GLOBAL scope is used directly (no fallback needed)."""
    from coffer.surfaces.http.distill_wiring import _MemoryInsightSink

    class _DirectFake:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def add_fact(self, *, scope: MemoryScope, cwd, **kwargs) -> object:
            self.calls.append({"scope": scope, "cwd": cwd})

            class _Fact:
                id = "global-only-id"

            return _Fact()

    svc = _DirectFake()
    sink = _MemoryInsightSink(svc)  # type: ignore[arg-type]
    insight = DistilledInsight(
        name="global-insight",
        description="Global",
        body="Body",
        type=InsightType.DECISION,
    )
    fact_id = await sink.record(
        project_path=None,
        insight=insight,
        origin_session_id="sess-xyz",
    )

    assert fact_id == "global-only-id"
    assert len(svc.calls) == 1
    assert svc.calls[0]["scope"] == MemoryScope.GLOBAL
    assert svc.calls[0]["cwd"] is None
