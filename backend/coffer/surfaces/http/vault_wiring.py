"""Finding a person's edits to the vault, wired for the app lifespan
(ADR every-vault-write-is-a-validated-commit-naming-its-writer; spec
vault-storage "Keep the last valid version when a hand edit is invalid").

Human edits are found, not intercepted. At startup this settles whatever was
edited while the daemon was down (the boot scan), then keeps
:class:`~coffer.infrastructure.vault.scanner.VaultScanner` running — the file
watcher as a hint, a periodic scan as the truth — until shutdown. Each
``disk`` commit a settle makes is audited as ``vault_file_edited`` with actor
``human``, one row per file, after the commit: the commit is itself the
durable record of the change, so an audit write that fails is logged and the
commit stands. A hand edit validation refuses stays on disk, uncommitted, and
reaches the Overview through the ``vault`` attention source this returns.

Called once from the lifespan, after :func:`build_vault_stores` has set the
validator and the resource store is listening, so a boot-scan commit refreshes
the stores like any other.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any, Protocol

from coffer.application.runtime.supervisor import spawn
from coffer.application.vault.attention import VaultAttentionSource
from coffer.domain.audit import AuditEventType
from coffer.domain.audit_diff import commit_change
from coffer.domain.vault.writers import WRITER_DISK
from coffer.domain.vault.writes import CommitResult
from coffer.infrastructure.vault.git import GitMissing
from coffer.infrastructure.vault.instance import vault_writer
from coffer.infrastructure.vault.scanner import (
    DEFAULT_INTERVAL_S,
    DEFAULT_QUIET_S,
    VaultScanner,
)

_log = logging.getLogger(__name__)

#: The audit actor of an edit found on disk: nobody Coffer can name did it.
HUMAN = "human"


class _Audit(Protocol):
    def record(
        self,
        event_type: str,
        *,
        actor: str = ...,
        details: dict[str, Any] | None = ...,
    ) -> Coroutine[Any, Any, None]: ...


@dataclass
class VaultScanning:
    """The running scanner, its attention source, and the audit rows in flight."""

    scanner: VaultScanner
    attention: VaultAttentionSource
    _audit: _Audit
    _loop: asyncio.AbstractEventLoop
    #: ``(ref, path) -> bytes``, to say what each edit changed; ``None`` records
    #: only the path and version.
    _read: Callable[[str, str], bytes | None] | None = None
    task: asyncio.Task[None] | None = None
    _pending: set[asyncio.Task[None]] = field(default_factory=set)
    _stopped: bool = False

    def on_commit(self, result: CommitResult) -> None:
        """Writer listener: audit a ``disk`` commit. Called from whichever
        thread committed, so the rows are written on the loop."""
        if self._stopped or result.meta.writer != WRITER_DISK:
            return
        try:
            self._loop.call_soon_threadsafe(self._spawn, result)
        except RuntimeError:  # the loop is closed: the commit stands regardless
            _log.warning("vault.edit_audit_skipped", extra={"version": result.version})

    def _spawn(self, result: CommitResult) -> None:
        task = spawn(self._record(result), name="vault-edit-audit")
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def _record(self, result: CommitResult) -> None:
        for path in result.paths:
            try:
                details: dict[str, Any] = {"path": path, "version": result.version}
                if self._read is not None:
                    # Added, deleted or modified, and the diff of a knowledge
                    # or skill text file (never of config, which may hold env).
                    details.update(
                        await asyncio.to_thread(commit_change, self._read, result.version, [path])
                    )
                await self._audit.record(
                    AuditEventType.VAULT_FILE_EDITED.value, actor=HUMAN, details=details
                )
            except Exception:
                _log.warning(
                    "vault.edit_audit_failed",
                    extra={"path": path, "version": result.version},
                    exc_info=True,
                )

    async def drain(self) -> None:
        """Wait for the audit rows already scheduled."""
        await asyncio.sleep(0)  # let a call_soon_threadsafe land
        while self._pending:
            await asyncio.gather(*list(self._pending), return_exceptions=True)

    async def stop(self) -> None:
        """Stop scanning; the audit rows already scheduled are still written."""
        self._stopped = True
        if self.task is not None:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task
        await self.drain()


async def start_vault_scanning(
    audit: _Audit,
    *,
    watch: bool = True,
    quiet: float = DEFAULT_QUIET_S,
    interval: float = DEFAULT_INTERVAL_S,
    run: bool = True,
) -> VaultScanning:
    """Ensure the vault repository, settle the boot scan, start scanning.

    A missing ``git`` is a startup error naming how to install it. ``run``
    false skips the background loop (a test drives ``scanner.tick()``).
    """
    writer = vault_writer()
    try:
        await asyncio.to_thread(writer.repo.ensure)
    except GitMissing as exc:
        raise RuntimeError(str(exc)) from exc
    scanner = VaultScanner(writer, quiet=quiet, interval=interval, watch=watch)
    scanning = VaultScanning(
        scanner=scanner,
        attention=VaultAttentionSource(writer),
        _audit=audit,
        _loop=asyncio.get_running_loop(),
        _read=writer.repo.read,
    )
    writer.add_listener(scanning.on_commit)
    try:
        await asyncio.to_thread(scanner.boot_scan)
    except Exception:
        # A scan that cannot run now runs again on the next interval; startup
        # never waits on a person's half-finished edit.
        _log.warning("vault.boot_scan_failed", exc_info=True)
    if run:
        scanning.task = spawn(scanner.run(), name="vault-scanner")
    return scanning


__all__ = ["HUMAN", "VaultScanning", "start_vault_scanning"]
