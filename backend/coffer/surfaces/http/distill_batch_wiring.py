"""Composition helper for async batch distillation.

``start_distill_batch`` builds the shared :class:`AsyncOpRunner` + registry,
wires a :class:`DistillBatchService` against the live distill service and the
``distilled_sessions`` ledger (same idempotency key as the FR-046 sweep), starts
the worker pool, and registers the service for the transcript routes.
``stop_distill_batch`` tears the pool down. Both run from the app lifespan so
``app.py`` stays under the file-size budget.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
from datetime import UTC, datetime

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker

from coffer.application.async_ops.registry import AsyncOpRegistry
from coffer.application.async_ops.runner import AsyncOpRunner
from coffer.application.distill.batch import DistillBatchService
from coffer.application.distill.service import TranscriptDistillationService
from coffer.domain.distill.session import TranscriptSession
from coffer.infrastructure.persistence.distilled_session_repo import DistilledSessionRepo
from coffer.surfaces.http.distill.state import set_distill_batch_service

_DEFAULT_CONCURRENCY = 2
_MAX_SELECT_ALL = 1000


def _concurrency() -> int:
    try:
        return max(1, int(os.environ.get("COFFER_DISTILL_BATCH_CONCURRENCY", _DEFAULT_CONCURRENCY)))
    except (TypeError, ValueError):
        return _DEFAULT_CONCURRENCY


async def start_distill_batch(
    app: FastAPI,
    *,
    distill_service: TranscriptDistillationService,
    session_maker: async_sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Wire and start the async batch-distillation worker pool."""
    repo = DistilledSessionRepo(session_maker)
    registry = AsyncOpRegistry()
    runner = AsyncOpRunner(registry, concurrency=_concurrency())
    await runner.start()

    async def list_sessions(
        agent: str,
        *,
        limit: int,
        query: str | None = None,
        project: str | None = None,
        started_after: datetime | None = None,
        started_before: datetime | None = None,
    ) -> list[TranscriptSession]:
        _total, page = await distill_service.list_sessions(
            agent,
            limit=limit,
            offset=0,
            query=query,
            project=project,
            started_after=started_after,
            started_before=started_before,
        )
        return page

    async def distill(agent: str, session_id: str) -> None:
        await distill_service.distill(agent_name=agent, session_id=session_id, dry_run=False)

    async def mark_distilled(agent: str, session_id: str, sha: str) -> None:
        await repo.mark_distilled(agent, session_id, sha, datetime.now(tz=UTC))

    # Memoize the content hash by (path, mtime_ns, size) so the list view's
    # staleness check (which hashes every distilled session, possibly several MB,
    # on each 2s poll) re-reads a transcript only when it has actually changed.
    sha_cache: dict[str, tuple[int, int, str]] = {}

    def session_sha(path: str) -> str:
        st = os.stat(path)
        cached = sha_cache.get(path)
        if cached is not None and cached[0] == st.st_mtime_ns and cached[1] == st.st_size:
            return cached[2]
        sha = hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
        sha_cache[path] = (st.st_mtime_ns, st.st_size, sha)
        return sha

    svc = DistillBatchService(
        runner=runner,
        registry=registry,
        list_sessions=list_sessions,
        distilled_shas=repo.distilled_session_shas,
        distill=distill,
        is_distilled=repo.is_distilled,
        mark_distilled=mark_distilled,
        session_sha=session_sha,
        max_select_all=_MAX_SELECT_ALL,
    )
    set_distill_batch_service(svc)
    app.state.distill_batch_runner = runner


async def stop_distill_batch(app: FastAPI) -> None:
    """Stop the batch-distillation worker pool if it was started."""
    runner = getattr(app.state, "distill_batch_runner", None)
    if runner is not None:
        await runner.stop()
