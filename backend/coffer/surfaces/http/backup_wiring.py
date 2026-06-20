"""Composition helper for the optional auto-backup worker.

Mirrors the style of :mod:`coffer.surfaces.http.sync_wiring`:
``start_backup_worker`` wires and starts the worker; ``stop_backup_worker``
tears it down gracefully.  Both functions are called from the app lifespan so
that app.py stays under the 400-line guideline.
"""

from __future__ import annotations

import asyncio
import logging
import os

from fastapi import FastAPI

_logger = logging.getLogger(__name__)


def start_backup_worker(app: FastAPI) -> None:
    """Wire and start the optional periodic auto-backup worker.

    Reads configuration from environment variables:

    * ``COFFER_AUTO_BACKUP_ENABLED`` - set to ``"1"`` or ``"true"`` to enable.
    * ``COFFER_AUTO_BACKUP_INTERVAL_HOURS`` - how often to snapshot (default 24).
    * ``COFFER_AUTO_BACKUP_KEEP`` - rolling retention count (default 7).

    When enabled, constructs a :class:`~coffer.application.backup_worker.BackupWorker`,
    starts it as an asyncio task, and stores both on ``app.state``.
    When disabled, both ``app.state`` attributes are set to ``None``.
    """
    enabled = os.environ.get("COFFER_AUTO_BACKUP_ENABLED", "").lower() in ("1", "true")
    if not enabled:
        app.state.backup_worker = None
        app.state.backup_worker_task = None
        return

    # Lazy imports kept here (surfaces layer may import infra/application).
    from coffer.application.backup_worker import BackupWorker
    from coffer.infrastructure.vault.backup import create_backup, vault_root

    try:
        interval_hours = int(os.environ.get("COFFER_AUTO_BACKUP_INTERVAL_HOURS", "24"))
    except ValueError:
        interval_hours = 24
    interval_hours = max(1, interval_hours)  # prevent busy-loop if set to 0 or negative

    try:
        keep = int(os.environ.get("COFFER_AUTO_BACKUP_KEEP", "7"))
    except ValueError:
        keep = 7
    keep = max(1, keep)  # prevent wiping all snapshots if set to 0 or negative

    worker = BackupWorker(
        create_backup=create_backup,
        backup_dir=vault_root() / "backups",
        keep=keep,
        interval_seconds=interval_hours * 3600,
    )
    task = asyncio.create_task(worker.run())
    app.state.backup_worker = worker
    app.state.backup_worker_task = task
    _logger.info(
        "backup_worker.started",
        extra={"interval_hours": interval_hours, "keep": keep},
    )


async def stop_backup_worker(app: FastAPI) -> None:
    """Gracefully stop the auto-backup worker if it was started.

    Mirrors the teardown logic previously inlined in app.py's lifespan
    ``finally`` block.
    """
    worker = getattr(app.state, "backup_worker", None)
    task = getattr(app.state, "backup_worker_task", None)
    if worker is None:
        return
    worker.stop()
    if task is not None:
        try:
            await asyncio.wait_for(task, timeout=2.0)
        except (TimeoutError, asyncio.CancelledError):
            task.cancel()
