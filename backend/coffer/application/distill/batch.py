"""Async batch distillation — runs the FR-045 distill path off the request path.

Wraps distillation + the FR-046 ``distilled_sessions`` ledger with the shared
:class:`AsyncOpRunner` so the UI can fire single / batch / select-all
distillation without blocking and poll per-session status. Skip-unchanged
reuses the ledger: a session whose current content sha is already distilled is
not re-enqueued.

All collaborators are injected as plain callables / protocols so this
application module imports nothing from infrastructure or surfaces.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from coffer.application.async_ops.registry import AsyncOpRegistry, InflightEntry, OpState
from coffer.application.async_ops.runner import AsyncOpRunner
from coffer.domain.distill.session import TranscriptSession

#: Operation type key in the shared registry.
OP_TYPE = "distill"
_SEP = "\x00"  # agent / session_id separator in registry keys (neither contains NUL)

#: Derived list statuses — cheap (ledger-only). In-flight states (queued /
#: running / error) are overlaid from the registry by the surface layer.
STATUS_DONE = "done"
STATUS_NEVER = "never"


class SessionLister(Protocol):
    """Fetches an agent's transcript sessions with the list view's filters."""

    async def __call__(
        self,
        agent: str,
        *,
        limit: int,
        query: str | None = None,
        project: str | None = None,
        started_after: datetime | None = None,
        started_before: datetime | None = None,
    ) -> list[TranscriptSession]: ...


@dataclass(frozen=True)
class EnqueueResult:
    """Outcome of a batch enqueue."""

    queued: int  # newly enqueued
    skipped: int  # already distilled at current sha (skip-unchanged)
    total: int  # candidates considered


class DistillBatchService:
    """Enqueues distillation work and reports per-session status."""

    def __init__(
        self,
        *,
        runner: AsyncOpRunner,
        registry: AsyncOpRegistry,
        list_sessions: SessionLister,
        distilled_ids: Callable[[str], Awaitable[set[str]]],
        distill: Callable[[str, str], Awaitable[None]],
        is_distilled: Callable[[str, str, str], Awaitable[bool]],
        mark_distilled: Callable[[str, str, str], Awaitable[None]],
        session_sha: Callable[[str], str],
        max_select_all: int = 1000,
    ) -> None:
        self._runner = runner
        self._registry = registry
        self._list_sessions = list_sessions
        self._distilled_ids = distilled_ids
        self._distill = distill
        self._is_distilled = is_distilled
        self._mark_distilled = mark_distilled
        self._session_sha = session_sha
        self._max_select_all = max_select_all

    @staticmethod
    def _key(agent: str, session_id: str) -> str:
        return f"{agent}{_SEP}{session_id}"

    def inflight(self, agent: str) -> dict[str, InflightEntry]:
        """In-flight entries for *agent*, keyed by session_id."""
        prefix = f"{agent}{_SEP}"
        snap = self._registry.snapshot(OP_TYPE, prefix=prefix)
        return {key[len(prefix) :]: entry for key, entry in snap.items()}

    async def derived_statuses(self, agent: str, session_ids: list[str]) -> dict[str, str]:
        """Map each session_id to ``done`` (in the ledger) or ``never``."""
        done = await self._distilled_ids(agent)
        return {sid: (STATUS_DONE if sid in done else STATUS_NEVER) for sid in session_ids}

    async def enqueue_sessions(self, agent: str, session_ids: list[str]) -> EnqueueResult:
        """Enqueue an explicit set of sessions (skip already-distilled)."""
        sessions = await self._list_sessions(agent, limit=self._max_select_all)
        wanted = set(session_ids)
        chosen = [s for s in sessions if s.session_id in wanted]
        return await self._enqueue(agent, chosen)

    async def enqueue_all(
        self,
        agent: str,
        *,
        query: str | None = None,
        project: str | None = None,
        started_after: datetime | None = None,
        started_before: datetime | None = None,
    ) -> EnqueueResult:
        """Enqueue every session matching the current list filters (select-all)."""
        sessions = await self._list_sessions(
            agent,
            limit=self._max_select_all,
            query=query,
            project=project,
            started_after=started_after,
            started_before=started_before,
        )
        return await self._enqueue(agent, sessions)

    async def _enqueue(self, agent: str, sessions: list[TranscriptSession]) -> EnqueueResult:
        queued = 0
        skipped = 0
        for session in sessions:
            try:
                sha = self._session_sha(session.source_path)
            except OSError:
                continue  # unreadable transcript — skip silently (mirrors the sweep)
            if await self._is_distilled(agent, session.session_id, sha):
                skipped += 1
                continue
            key = self._key(agent, session.session_id)
            existing = self._registry.get(OP_TYPE, key)
            if existing is not None and existing.state in (OpState.queued, OpState.running):
                continue  # already in flight — don't double-enqueue
            self._runner.enqueue(OP_TYPE, key, self._factory(agent, session.session_id, sha))
            queued += 1
        return EnqueueResult(queued=queued, skipped=skipped, total=len(sessions))

    def _factory(self, agent: str, session_id: str, sha: str) -> Callable[[], Awaitable[None]]:
        async def _run() -> None:
            await self._distill(agent, session_id)
            await self._mark_distilled(agent, session_id, sha)

        return _run
