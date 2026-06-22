"""Composition helper for the auto-distill catch-up sweep worker (007 FR-046).

``start_auto_distill`` wires the application-layer sweep (whose collaborators are
all injected ports) against the live distill service, agent service, and the
SQLite idempotency ledger, then starts it as a background task.
``stop_auto_distill`` tears it down gracefully. Both are called from the app
lifespan so app.py stays under the file-size budget.

The sweep is **default-ON** (it is the memory write guarantee); the
``COFFER_AUTO_DISTILL`` env var only DISABLES it (explicit falsy value).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import pathlib
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker

from coffer.application.distill.auto_distill import (
    AutoDistillSweep,
    AutoDistillSweepWorker,
)
from coffer.application.distill.service import TranscriptDistillationService
from coffer.domain.distill.session import TranscriptSession
from coffer.infrastructure.persistence.distilled_session_repo import (
    DistilledSessionRepo,
)

_logger = logging.getLogger(__name__)

_FALSY = {"0", "false", "no", "off"}

# Read at most this many sessions per agent per pass — the catch-up net only
# cares about recent sessions, and the recency window discards the rest.
_LIST_SESSIONS_LIMIT = 500

_DEFAULT_SETTLE_SECONDS = 900.0
_DEFAULT_RECENCY_SECONDS = 604800.0  # 7 days
_DEFAULT_MAX_PER_SWEEP = 20
_DEFAULT_INTERVAL_SECONDS = 3600.0
_MIN_INTERVAL_SECONDS = 60.0


def auto_distill_enabled() -> bool:
    """Default-ON: enabled unless ``COFFER_AUTO_DISTILL`` is explicitly falsy."""
    return os.environ.get("COFFER_AUTO_DISTILL", "").strip().lower() not in _FALSY


def _float_env(name: str, default: float, *, minimum: float = 0.0) -> float:
    try:
        value = float(os.environ.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, value)


def _int_env(name: str, default: int, *, minimum: int = 1) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, value)


def start_auto_distill(
    app: FastAPI,
    *,
    distill_service: TranscriptDistillationService,
    agent_service: Any,
    session_maker: async_sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Wire and start the auto-distill catch-up sweep worker (default-ON)."""
    if not auto_distill_enabled():
        app.state.auto_distill_worker = None
        app.state.auto_distill_task = None
        return

    repo = DistilledSessionRepo(session_maker)

    async def list_agent_names() -> list[str]:
        return [r.name for r in await agent_service.list()]

    async def list_sessions(name: str) -> list[TranscriptSession]:
        _total, page = await distill_service.list_sessions(
            name, limit=_LIST_SESSIONS_LIMIT, offset=0
        )
        return page

    async def distill(name: str, session_id: str) -> None:
        await distill_service.distill(agent_name=name, session_id=session_id, dry_run=False)

    def now() -> datetime:
        return datetime.now(tz=UTC)

    async def mark_distilled(name: str, session_id: str, sha: str) -> None:
        await repo.mark_distilled(name, session_id, sha, now())

    def session_sha(path: str) -> str:
        return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

    settle = _float_env("COFFER_AUTO_DISTILL_SETTLE_SECONDS", _DEFAULT_SETTLE_SECONDS)
    recency = _float_env("COFFER_AUTO_DISTILL_RECENCY_SECONDS", _DEFAULT_RECENCY_SECONDS)
    max_per_sweep = _int_env("COFFER_AUTO_DISTILL_MAX_PER_SWEEP", _DEFAULT_MAX_PER_SWEEP)
    interval = _float_env(
        "COFFER_AUTO_DISTILL_INTERVAL_SECONDS",
        _DEFAULT_INTERVAL_SECONDS,
        minimum=_MIN_INTERVAL_SECONDS,
    )

    sweep = AutoDistillSweep(
        list_agent_names=list_agent_names,
        list_sessions=list_sessions,
        distill=distill,
        is_distilled=repo.is_distilled,
        mark_distilled=mark_distilled,
        session_sha=session_sha,
        now=now,
        settle_seconds=settle,
        recency_seconds=recency,
        max_per_sweep=max_per_sweep,
    )
    worker = AutoDistillSweepWorker(sweep=sweep.run_once, interval_seconds=interval)
    task = asyncio.create_task(worker.run())
    app.state.auto_distill_worker = worker
    app.state.auto_distill_task = task
    _logger.info(
        "auto_distill.started",
        extra={
            "settle_seconds": settle,
            "recency_seconds": recency,
            "max_per_sweep": max_per_sweep,
            "interval_seconds": interval,
        },
    )


def wire_session_end_distiller(
    *,
    distill_service: TranscriptDistillationService,
    session_maker: async_sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Construct + register the on-demand SessionEnd distiller (Slice 6 FR-051).

    Reuses the same ``distilled_sessions`` ledger as the catch-up sweep so a
    session distilled at session-end is never re-distilled by the sweep (and
    vice-versa). The session sha is resolved from the agent's listed sessions
    (matched by id) so the idempotency key matches the sweep's exactly.
    """
    from coffer.application.distill.session_end import SessionEndDistiller
    from coffer.surfaces.http.dependencies import set_session_end_distiller

    repo = DistilledSessionRepo(session_maker)

    async def distill(name: str, session_id: str) -> None:
        await distill_service.distill(agent_name=name, session_id=session_id, dry_run=False)

    def now() -> datetime:
        return datetime.now(tz=UTC)

    async def mark_distilled(name: str, session_id: str, sha: str) -> None:
        await repo.mark_distilled(name, session_id, sha, now())

    async def session_sha(name: str, session_id: str) -> str | None:
        # Match the session by id among the agent's transcripts, then hash its
        # on-disk source so the key is identical to the catch-up sweep's.
        _total, page = await distill_service.list_sessions(
            name, limit=_LIST_SESSIONS_LIMIT, offset=0
        )
        for session in page:
            if session.session_id == session_id and session.source_path:
                return hashlib.sha256(pathlib.Path(session.source_path).read_bytes()).hexdigest()
        return None

    distiller = SessionEndDistiller(
        distill=distill,
        is_distilled=repo.is_distilled,
        mark_distilled=mark_distilled,
        session_sha=session_sha,
    )
    set_session_end_distiller(distiller)


async def stop_auto_distill(app: FastAPI) -> None:
    """Gracefully stop the auto-distill worker if it was started."""
    worker = getattr(app.state, "auto_distill_worker", None)
    task = getattr(app.state, "auto_distill_task", None)
    if worker is None:
        return
    worker.stop()
    if task is not None:
        try:
            await asyncio.wait_for(task, timeout=2.0)
        except (TimeoutError, asyncio.CancelledError):
            task.cancel()
