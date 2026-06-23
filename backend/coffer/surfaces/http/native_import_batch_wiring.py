"""Composition helper for async batch native-memory import.

``start_native_import_batch`` builds the shared :class:`AsyncOpRunner` + registry,
wires a :class:`NativeImportBatchService` against the live
:class:`AgentMemoryImportService` (the existing FR-041 adoption slice), starts the
worker pool, and registers the service for the native-memory routes.
``stop_native_import_batch`` tears the pool down. Both run from the app lifespan so
``app.py`` stays under the file-size budget.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI

from coffer.application.agent.native_import_batch import NativeImportBatchService
from coffer.application.async_ops.registry import AsyncOpRegistry
from coffer.application.async_ops.runner import AsyncOpRunner
from coffer.surfaces.http.dependencies import set_native_import_batch_service

_DEFAULT_CONCURRENCY = 2


def _concurrency() -> int:
    try:
        return max(
            1, int(os.environ.get("COFFER_NATIVE_IMPORT_BATCH_CONCURRENCY", _DEFAULT_CONCURRENCY))
        )
    except (TypeError, ValueError):
        return _DEFAULT_CONCURRENCY


async def start_native_import_batch(app: FastAPI, *, import_service: Any) -> None:
    """Wire and start the async batch native-memory import worker pool.

    ``import_service`` is the live :class:`AgentMemoryImportService` (already
    registered by ``wire_native_memory_import``)."""
    registry = AsyncOpRegistry()
    runner = AsyncOpRunner(registry, concurrency=_concurrency())
    await runner.start()

    async def import_store(agent: str, memory_dir: str) -> None:
        await import_service.import_store(name=agent, memory_dir=memory_dir)

    svc = NativeImportBatchService(
        runner=runner,
        registry=registry,
        import_store=import_store,
    )
    set_native_import_batch_service(svc)
    app.state.native_import_batch_runner = runner


async def stop_native_import_batch(app: FastAPI) -> None:
    """Stop the batch native-memory import worker pool if it was started."""
    runner = getattr(app.state, "native_import_batch_runner", None)
    if runner is not None:
        await runner.stop()
