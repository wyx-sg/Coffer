"""Fixtures for the workflow persistence tests.

The first one is not a convenience, it is a guard. ``paths.workflow_root()``
falls back to ``$HOME/.coffer/workflows`` when ``COFFER_WORKFLOW_ROOT`` is
unset, and this layer creates, writes into and copies out of that tree — so a
test that forgot to pin it would operate on the developer's real runs. It is
``autouse`` for exactly that reason: pinning it must not be something a new
test file can forget to do. The knowledge and memory layers carry the same
fixture after one of them once rewrote a real tree.
"""

from __future__ import annotations

import pathlib
from collections.abc import AsyncIterator

import pytest

from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.workflow.approvals_repo import WorkflowApprovalRepo
from coffer.infrastructure.workflow.repository import (
    WorkflowAttemptRepo,
    WorkflowEventRepo,
    WorkflowRunRepo,
)


@pytest.fixture(autouse=True)
def isolated_workflow_root(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    """Give every test its own run tree, far away from the real vault."""
    root = tmp_path / "workflow-root"
    monkeypatch.setenv("COFFER_WORKFLOW_ROOT", str(root))
    return root


class Repos:
    """The four repositories, over one throwaway database."""

    def __init__(
        self,
        runs: WorkflowRunRepo,
        events: WorkflowEventRepo,
        attempts: WorkflowAttemptRepo,
        approvals: WorkflowApprovalRepo,
    ) -> None:
        self.runs = runs
        self.events = events
        self.attempts = attempts
        self.approvals = approvals


@pytest.fixture
async def repos(tmp_path: pathlib.Path) -> AsyncIterator[Repos]:
    """A real SQLite file with the four tables on it.

    ``create_all`` from the ORM metadata rather than the Alembic chain: that
    the migration produces this same schema is the roundtrip suite's job, and
    replaying 85 revisions per test would buy nothing here.
    """
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'workflow.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    yield Repos(
        WorkflowRunRepo(sm),
        WorkflowEventRepo(sm),
        WorkflowAttemptRepo(sm),
        WorkflowApprovalRepo(sm),
    )
    await engine.dispose()
