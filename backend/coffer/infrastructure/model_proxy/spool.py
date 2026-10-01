"""Append usage records to spool files the daemon ingests.

The proxy never opens the database — the daemon is its only writer (ADR
usage-is-metered-at-the-proxy-and-subscriptions-show-only-official-quota). It
appends one JSON object per line to ``<spool dir>/<pid>-<seq>.jsonl.part`` and
renames the file to ``.jsonl`` once it will not grow: when it holds records and
either two seconds have passed since its first record or it reached 500, and
at shutdown. The rename is atomic, so the daemon only ever reads whole files.

Appending never blocks a relay: :meth:`UsageSpool.append` only enqueues, and
one writer task does the file I/O in a worker thread. A crash can lose at most
the records still in the queue, and leaves a ``.part`` file behind; the next
proxy to start finalizes every ``.part`` whose writer pid is no longer alive,
so those records are ingested rather than stranded (a torn last line is the
ingest's to skip).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
from pathlib import Path

from coffer.application.runtime.supervisor import spawn
from coffer.domain.usage.records import (
    PART_SUFFIX,
    SPOOL_DIR_ENV,
    SPOOL_SUFFIX,
    UsageRecord,
)
from coffer.infrastructure.vault.home import proxy_usage_dir

_logger = logging.getLogger(__name__)

MAX_AGE_SECONDS = 2.0
MAX_RECORDS = 500


def spool_dir() -> Path:
    """``COFFER_PROXY_SPOOL_DIR``, else ``~/.coffer/proxy-usage``."""
    override = os.environ.get(SPOOL_DIR_ENV)
    return Path(override) if override else proxy_usage_dir()


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def finalize_orphans(directory: Path, own_pid: int) -> int:
    """Rename every ``.part`` left by a writer that is gone; returns the count."""
    count = 0
    for part in directory.glob(f"*{PART_SUFFIX}"):
        head = part.name.split("-", 1)[0]
        if not head.isdigit() or int(head) == own_pid or _pid_alive(int(head)):
            continue
        if part.stat().st_size == 0:
            part.unlink(missing_ok=True)
            continue
        os.replace(part, part.with_name(part.name[: -len(PART_SUFFIX)] + SPOOL_SUFFIX))
        count += 1
    return count


class _Flush:
    def __init__(self) -> None:
        self.done = asyncio.get_running_loop().create_future()


class UsageSpool:
    """One writer of ``<pid>-<seq>.jsonl`` files in :func:`spool_dir`."""

    def __init__(
        self,
        directory: Path | None = None,
        *,
        max_age: float = MAX_AGE_SECONDS,
        max_records: int = MAX_RECORDS,
        pid: int | None = None,
    ) -> None:
        self.directory = directory or spool_dir()
        self._max_age = max_age
        self._max_records = max_records
        self._pid = os.getpid() if pid is None else pid
        self._seq = 0
        self._queue: asyncio.Queue[UsageRecord | _Flush | None] | None = None
        self._task: asyncio.Task[None] | None = None
        # The open part file (written only from the worker thread).
        self._part: Path | None = None
        self._count = 0
        self._opened_at = 0.0

    # --- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        await asyncio.to_thread(self._prepare)
        self._queue = asyncio.Queue()
        self._task = spawn(self._run(), name="model-proxy-spool")

    def _prepare(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with contextlib.suppress(OSError):
            found = finalize_orphans(self.directory, self._pid)
            if found:
                _logger.info("model_proxy.spool_orphans_finalized count=%s", found)

    async def close(self) -> None:
        """Write everything queued, finalize the open file, stop the writer."""
        if self._queue is None or self._task is None:
            return
        self._queue.put_nowait(None)
        with contextlib.suppress(Exception):
            await self._task
        self._queue, self._task = None, None

    # --- producer side ---------------------------------------------------------

    def append(self, record: UsageRecord) -> None:
        """Enqueue a record; never blocks and never raises into the relay."""
        if self._queue is None:
            _logger.warning("model_proxy.spool_not_running; usage record dropped")
            return
        self._queue.put_nowait(record)

    async def flush(self) -> None:
        """Wait until every record appended so far sits in a finalized file."""
        if self._queue is None:
            return
        marker = _Flush()
        self._queue.put_nowait(marker)
        await marker.done

    # --- writer ----------------------------------------------------------------

    async def _run(self) -> None:
        assert self._queue is not None
        queue = self._queue
        while True:
            timeout = None
            if self._part is not None:
                timeout = max(0.0, self._opened_at + self._max_age - time.monotonic())
            try:
                item = await asyncio.wait_for(queue.get(), timeout)
            except TimeoutError:
                await self._finalize()
                continue
            batch: list[UsageRecord] = []
            control: list[_Flush | None] = []
            while True:
                if isinstance(item, UsageRecord):
                    batch.append(item)
                else:
                    control.append(item)
                    break
                if queue.empty():
                    break
                item = queue.get_nowait()
            if batch:
                await self._write(batch)
            if control or (
                self._part is not None
                and (
                    self._count >= self._max_records
                    or time.monotonic() - self._opened_at >= self._max_age
                )
            ):
                await self._finalize()
            for marker in control:
                if marker is None:
                    return
                if not marker.done.done():
                    marker.done.set_result(None)

    async def _write(self, batch: list[UsageRecord]) -> None:
        lines = "".join(r.model_dump_json() + "\n" for r in batch)
        try:
            await asyncio.to_thread(self._append_lines, lines, len(batch))
        except OSError:
            _logger.warning("model_proxy.spool_write_failed records=%s", len(batch), exc_info=True)

    def _append_lines(self, lines: str, n: int) -> None:
        if self._part is None:
            self._seq += 1
            self._part = self.directory / f"{self._pid}-{self._seq:06d}{PART_SUFFIX}"
            self._count = 0
            self._opened_at = time.monotonic()
        fd = os.open(self._part, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            handle.write(lines)
        self._count += n
        if self._count >= self._max_records:
            self._rename()

    async def _finalize(self) -> None:
        try:
            await asyncio.to_thread(self._rename)
        except OSError:
            _logger.warning("model_proxy.spool_finalize_failed", exc_info=True)

    def _rename(self) -> None:
        part, self._part = self._part, None
        if part is None:
            return
        done = part.with_name(part.name[: -len(PART_SUFFIX)] + SPOOL_SUFFIX)
        os.replace(part, done)
        self._count = 0


__all__ = ["MAX_AGE_SECONDS", "MAX_RECORDS", "UsageSpool", "finalize_orphans", "spool_dir"]
