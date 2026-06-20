"""Optional periodic auto-backup worker.

When enabled (via env vars), writes a full vault ``.tar.gz`` snapshot on a
fixed interval and prunes old snapshots so at most ``keep`` backups are
retained (rolling retention, oldest-first).

The worker receives its dependencies via constructor injection so this
application-layer module has no direct dependency on the infrastructure or
surfaces layers (import-linter compliant).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

_logger = logging.getLogger(__name__)


class BackupWorker:
    """Periodically writes a vault snapshot and prunes the oldest files.

    Runs immediately on start (catch-up), then every ``interval_seconds``.
    A failing backup is logged but never kills the worker.
    """

    def __init__(
        self,
        *,
        create_backup: Callable[..., object],
        backup_dir: Path,
        keep: int,
        interval_seconds: float,
    ) -> None:
        self._create_backup = create_backup
        self._backup_dir = backup_dir
        self._keep = keep
        self._interval = interval_seconds
        self._stop = asyncio.Event()

    def stop(self) -> None:
        """Signal the run loop to exit cleanly."""
        self._stop.set()

    async def run(self) -> None:
        """Run until stop() is called."""
        while not self._stop.is_set():
            await self._run_once()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
            except TimeoutError:
                continue

    async def _run_once(self) -> None:
        """Write one snapshot and prune old backups. Never raises."""
        try:
            self._backup_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
            # Use the "auto-coffer-" prefix so the worker's own snapshots are
            # distinct from manual "coffer-<ts>.tar.gz" backups written by
            # ``POST /vault/backup`` and the ``coffer backup`` CLI.  This
            # prevents _prune() from accidentally deleting user-created backups.
            dest = self._backup_dir / f"auto-coffer-{ts}.tar.gz"
            await asyncio.to_thread(self._create_backup, dest, include_master_key=False)
            _logger.info(
                "backup_worker.snapshot.written",
                extra={"dest": str(dest)},
            )
            self._prune()
        except Exception:
            _logger.exception("backup_worker.snapshot.failed")

    def _prune(self) -> None:
        """Delete all but the ``keep`` newest auto-snapshots in backup_dir.

        Only globs ``auto-coffer-*.tar.gz`` — the worker's own prefix — so
        manual ``coffer-*.tar.gz`` backups (written by the CLI or HTTP route)
        are never touched.

        Defensive guard: if ``self._keep`` is somehow <= 0 (should not happen
        after the env-clamp in backup_wiring, but belt-and-suspenders), treat
        it as keep=1 so a bad value can never wipe everything.
        """
        keep = max(1, self._keep)
        files = sorted(
            self._backup_dir.glob("auto-coffer-*.tar.gz"),
            key=lambda p: p.stat().st_mtime,
        )
        to_delete = files[: max(0, len(files) - keep)]
        for f in to_delete:
            try:
                f.unlink()
                _logger.debug("backup_worker.pruned", extra={"file": str(f)})
            except OSError:
                _logger.exception("backup_worker.prune.failed", extra={"file": str(f)})
