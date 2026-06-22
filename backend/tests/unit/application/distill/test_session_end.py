"""SessionEndDistiller — on-demand single-session distill (Slice 6 FR-051)."""

from __future__ import annotations

import pytest

from coffer.application.distill.service import NoModelConfiguredError
from coffer.application.distill.session_end import (
    SessionEndDistiller,
    SessionEndOutcome,
)

pytestmark = pytest.mark.asyncio


def _distiller(*, sha="abc", distilled_shas=None, distill_raises=None):
    distilled = set(distilled_shas or [])
    calls = {"distill": 0, "mark": []}

    async def session_sha(agent, sid):
        return sha

    async def is_distilled(agent, sid, s):
        return s in distilled

    async def distill(agent, sid):
        calls["distill"] += 1
        if distill_raises is not None:
            raise distill_raises

    async def mark(agent, sid, s):
        calls["mark"].append(s)
        distilled.add(s)

    d = SessionEndDistiller(
        distill=distill, is_distilled=is_distilled, mark_distilled=mark, session_sha=session_sha
    )
    return d, calls


@pytest.mark.acceptance(
    spec="007-memory", scenario="session-end distils the closed session into the journal"
)
async def test_distills_and_marks_a_new_session():
    d, calls = _distiller()
    out = await d.distill_session(agent_name="cc", session_id="s1")
    assert out is SessionEndOutcome.DISTILLED
    assert calls["distill"] == 1
    assert calls["mark"] == ["abc"]


async def test_already_distilled_is_noop():
    d, calls = _distiller(distilled_shas=["abc"])
    out = await d.distill_session(agent_name="cc", session_id="s1")
    assert out is SessionEndOutcome.ALREADY_DISTILLED
    assert calls["distill"] == 0


async def test_no_model_is_noop():
    d, calls = _distiller(distill_raises=NoModelConfiguredError("none"))
    out = await d.distill_session(agent_name="cc", session_id="s1")
    assert out is SessionEndOutcome.NO_MODEL
    assert calls["mark"] == []


async def test_missing_session_returns_not_found():
    d, _calls = _distiller(sha=None)
    out = await d.distill_session(agent_name="cc", session_id="missing")
    assert out is SessionEndOutcome.NOT_FOUND


async def test_distill_failure_is_skipped_not_marked():
    d, calls = _distiller(distill_raises=RuntimeError("boom"))
    out = await d.distill_session(agent_name="cc", session_id="s1")
    assert out is SessionEndOutcome.SKIPPED
    assert calls["mark"] == []  # left unmarked → sweep retries
