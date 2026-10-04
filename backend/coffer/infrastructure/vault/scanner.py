"""Finding a person's edits to the vault
(ADR every-vault-write-is-a-validated-commit-naming-its-writer).

Human edits are **found, not intercepted**. File-system events are a hint;
a scan that asks git which working-tree files differ from ``HEAD`` is the
truth. A path is settled only once it has been **quiet**: its content is
fingerprinted on one look and again on a later one at least ``quiet`` seconds
on, and only an unchanged fingerprint is committed — so an editor's
temp-file-and-rename save, or a burst of keystroke saves, is one commit.
Content decides, never a modification time.

The boot scan settles whatever changed while the daemon was down, at once:
nothing is still typing into a file the daemon has never seen.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from pathlib import Path

from coffer.application.runtime.supervisor import spawn
from coffer.domain.vault.writes import CommitResult
from coffer.infrastructure.vault.writer import VaultWriter

logger = logging.getLogger(__name__)

DEFAULT_QUIET_S = 1.0
DEFAULT_INTERVAL_S = 60.0


class VaultScanner:
    """Settles a person's edits once they are quiet."""

    def __init__(
        self,
        writer: VaultWriter,
        *,
        quiet: float = DEFAULT_QUIET_S,
        interval: float = DEFAULT_INTERVAL_S,
        watch: bool = True,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._writer = writer
        self._quiet = quiet
        self._interval = interval
        self._watch = watch
        self._clock = clock
        self._seen: dict[str, tuple[str | None, float]] = {}
        self._wake = asyncio.Event()

    def boot_scan(self) -> CommitResult | None:
        """Settle everything that differs from ``HEAD`` now."""
        self._seen.clear()
        return self._writer.settle()

    def tick(self) -> CommitResult | None:
        """One look: settle the paths whose content has been quiet."""
        now = self._clock()
        pending = self._writer.pending()
        stable: list[str] = []
        for path, fp in pending.items():
            seen = self._seen.get(path)
            if seen is not None and seen[0] == fp and now - seen[1] >= self._quiet:
                stable.append(path)
            elif seen is None or seen[0] != fp:
                self._seen[path] = (fp, now)
        for path in list(self._seen):
            if path not in pending:
                del self._seen[path]
        if not stable:
            return None
        result = self._writer.settle(stable)
        for path in stable:
            self._seen.pop(path, None)
        return result

    def poke(self) -> None:
        """A hint that something changed (a file event, a CLI call)."""
        self._wake.set()

    async def run(self) -> None:
        """Until cancelled: look on every hint (after it has been quiet) and on
        every interval."""
        watcher = spawn(self._watch_files(), name="vault-file-watch") if self._watch else None
        try:
            while True:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._wake.wait(), timeout=self._interval)
                self._wake.clear()
                # Two looks a quiet period apart: the first records, the second settles.
                for _ in range(2):
                    try:
                        await asyncio.to_thread(self.tick)
                    except Exception:
                        logger.warning("vault.scan_failed", exc_info=True)
                    if not self._seen:
                        break
                    await asyncio.sleep(self._quiet)
        finally:
            if watcher is not None:
                watcher.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await watcher

    async def _watch_files(self) -> None:
        try:
            from watchfiles import awatch
        except ImportError:  # pragma: no cover - a declared dependency
            return
        root = self._writer.repo.root

        def outside_git(_change: object, path: str) -> bool:
            return "/.git/" not in path and not path.endswith("/.git")

        while True:
            try:
                if not Path(root).is_dir():
                    await asyncio.sleep(self._interval)
                    continue
                async for _changes in awatch(root, watch_filter=outside_git, debounce=200):
                    self.poke()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("vault.watch_failed", exc_info=True)
                await asyncio.sleep(self._interval)


__all__ = ["DEFAULT_INTERVAL_S", "DEFAULT_QUIET_S", "VaultScanner"]
