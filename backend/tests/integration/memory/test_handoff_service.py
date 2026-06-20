"""Integration: HandoffService set_handoff/resume over a real store + git repo."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_set_then_resume_roundtrip(handoff) -> None:
    res = await handoff.svc.set_handoff(
        cwd=handoff.cwd, body="at step 3\nnext: step 4", actor="agent"
    )
    assert res.branch == "work"  # conftest repo is on branch "work"
    got = await handoff.svc.resume(cwd=handoff.cwd)
    assert got is not None
    assert got.body == "at step 3\nnext: step 4"
    assert got.branch == "work"


async def test_resume_none_when_no_handoff(handoff) -> None:
    assert await handoff.svc.resume(cwd=handoff.cwd) is None


async def test_set_handoff_overwrites_same_branch(handoff) -> None:
    await handoff.svc.set_handoff(cwd=handoff.cwd, body="first", actor="agent")
    await handoff.svc.set_handoff(cwd=handoff.cwd, body="second", actor="agent")
    got = await handoff.svc.resume(cwd=handoff.cwd)
    assert got is not None
    assert got.body == "second"


async def test_resume_none_outside_project(handoff) -> None:
    # cwd not in a git repo → no project scope → no handoff
    assert await handoff.svc.resume(cwd=handoff.non_repo) is None
