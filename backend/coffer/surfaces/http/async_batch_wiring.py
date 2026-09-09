"""Aggregate start/stop for the async-operation batch workers.

Groups the per-operation batch wirings (KB re-embed, native-memory import)
behind one start/stop pair so the app lifespan stays under the file-size limit.
Each underlying wiring builds its own AsyncOpRunner + registry and registers its
service for the routes.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from coffer.surfaces.http.kb_batch_wiring import start_kb_batch, stop_kb_batch
from coffer.surfaces.http.native_import_batch_wiring import (
    start_native_import_batch,
    stop_native_import_batch,
)


async def start_async_batches(
    app: FastAPI,
    *,
    kb_service: Any,
    import_service: Any,
) -> None:
    """Start every async-operation batch worker (off the request path)."""
    await start_kb_batch(app, kb_service=kb_service)
    await start_native_import_batch(app, import_service=import_service)


async def stop_async_batches(app: FastAPI) -> None:
    """Stop every async-operation batch worker (best-effort)."""
    await stop_kb_batch(app)
    await stop_native_import_batch(app)
