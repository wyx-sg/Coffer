"""Aggregate start/stop for the async-operation batch workers.

Groups the per-operation batch wirings (transcript distillation, KB re-embed,
native-memory import) behind one start/stop pair so the app lifespan stays under
the file-size limit. Each underlying wiring builds its own AsyncOpRunner +
registry and registers its service for the routes.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker

from coffer.application.distill.service import TranscriptDistillationService
from coffer.surfaces.http.distill_batch_wiring import start_distill_batch, stop_distill_batch
from coffer.surfaces.http.kb_batch_wiring import start_kb_batch, stop_kb_batch
from coffer.surfaces.http.native_import_batch_wiring import (
    start_native_import_batch,
    stop_native_import_batch,
)


async def start_async_batches(
    app: FastAPI,
    *,
    distill_service: TranscriptDistillationService,
    session_maker: async_sessionmaker,  # type: ignore[type-arg]
    kb_service: Any,
    import_service: Any,
) -> None:
    """Start every async-operation batch worker (off the request path)."""
    await start_distill_batch(app, distill_service=distill_service, session_maker=session_maker)
    await start_kb_batch(app, kb_service=kb_service)
    await start_native_import_batch(app, import_service=import_service)


async def stop_async_batches(app: FastAPI) -> None:
    """Stop every async-operation batch worker (best-effort)."""
    await stop_distill_batch(app)
    await stop_kb_batch(app)
    await stop_native_import_batch(app)
