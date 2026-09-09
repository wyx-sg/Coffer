"""Integration: HandoffService set_handoff/resume over a real store + git repo."""

from __future__ import annotations

import pathlib

import pytest

from coffer.domain.audit import AuditEventType

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


async def test_handoff_is_per_branch_independent(handoff) -> None:
    """The (project x branch) anti-clobber guarantee (SHOULD 1): a handoff saved
    on branch ``work`` is invisible after switching to a fresh branch, and each
    branch reads only its own scene (same project store, different branch file)."""
    repo = pathlib.Path(handoff.repo)
    await handoff.svc.set_handoff(cwd=handoff.cwd, body="WORK_BODY", actor="agent")

    # Switch to a brand-new branch in the SAME repo (same project store).
    handoff.git(["checkout", "-q", "-b", "other"], repo)
    # Fresh branch has no scene of its own yet.
    assert await handoff.svc.resume(cwd=handoff.cwd) is None
    # Give it its own scene; it must not see / clobber "work".
    await handoff.svc.set_handoff(cwd=handoff.cwd, body="OTHER_BODY", actor="agent")
    got_other = await handoff.svc.resume(cwd=handoff.cwd)
    assert got_other is not None
    assert got_other.branch == "other"
    assert got_other.body == "OTHER_BODY"

    # Back on "work": its original scene is intact, untouched by "other".
    handoff.git(["checkout", "-q", "work"], repo)
    got_work = await handoff.svc.resume(cwd=handoff.cwd)
    assert got_work is not None
    assert got_work.branch == "work"
    assert got_work.body == "WORK_BODY"


async def test_handoff_set_audit_has_no_body_payload(handoff) -> None:
    """The ``handoff_set`` audit entry records branch + char_size only — never
    the body text (SHOULD 3). Audit is metadata, not a copy of the scene."""
    secret = "SECRET_BODY_TEXT"
    await handoff.svc.set_handoff(cwd=handoff.cwd, body=f"{secret} step 4", actor="agent")

    entries = await handoff.audit.query(event_type=AuditEventType.HANDOFF_SET.value)
    assert len(entries) == 1
    details = entries[0].details
    assert details["branch"] == "work"
    assert details["char_size"] == len(f"{secret} step 4")
    assert secret not in str(details)
