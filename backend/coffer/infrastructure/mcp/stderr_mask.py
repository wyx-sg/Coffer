"""Masking the values Coffer injected into a stdio child out of its stderr file.

Spec secret "Hold plaintext only in memory at the moment of use". A stdio
upstream is handed its materialised secrets in its environment; if it prints
one on stderr, the SDK would write it straight into the upstream's log file
(the child holds the file's descriptor itself), where the server page's log
read, the diagnosis hand-off and ``coffer log`` quote it. So when there is
anything to mask, the child's stderr is an OS pipe instead, and its read end is
pumped by the event loop through :class:`StreamMasker` into the real sink —
the masking happens before a byte reaches disk, not when the file is read.

Only the exact values injected into THIS child are masked (the secret overlay,
not the server's static env, and nothing on stdout, which is the JSON-RPC
channel). Matching is on the UTF-8 bytes, with the last ``longest - 1`` bytes
held back between reads so a value split across two writes is still caught.
The policy is the one the one-off server test already applies to the same
stream, its stderr tail (``domain.mcp.probe``): the same marker, ``••••••``,
and the same floor — a value shorter than four characters is not masked,
because rewriting every "1" or "on" in a log protects nothing and makes it
unreadable. (The HTTP custom tools mask with ``***`` and no floor, over a
bounded response body rather than a debugging log; here a test's stderr tail
and the server's log file should read alike.)

Coffer's own lines written into the same file (start / stop / error) go
through :meth:`MaskedSink.write`, masked whole, so they cannot carry a value
either.
"""

from __future__ import annotations

import asyncio
import codecs
import contextlib
import os
import re
import sys
import threading
from collections.abc import Iterable
from typing import TextIO

from coffer.domain.mcp.probe import REDACTED, secret_values

#: What a masked value reads as in the log file.
MASK = REDACTED

#: How long closing waits for the child's last stderr bytes (end of file on the
#: pipe) once its process is gone, before draining what is buffered and closing.
#: A grandchild that inherited stderr and outlived the server is why it can end
#: without end of file.
DRAIN_SECONDS = 2.0
_READ_SIZE = 64 * 1024


class StreamMasker:
    """Replace every injected value in a byte stream with :data:`MASK`."""

    def __init__(self, values: Iterable[str]) -> None:
        # Longest first: the regex takes the first alternative that matches at
        # a position, so a value containing another is replaced whole.
        patterns = [v.encode() for v in secret_values(values)]
        self._re = re.compile(b"|".join(re.escape(p) for p in patterns)) if patterns else None
        self._hold = max((len(p) for p in patterns), default=1) - 1
        self._carry = b""

    @property
    def active(self) -> bool:
        return self._re is not None

    def feed(self, data: bytes) -> bytes:
        """The masked bytes that can be decided now; the rest waits for more."""
        if self._re is None:
            return data
        buf = self._carry + data
        # A match starting at or after here could still grow into a longer
        # value (or begin one) once the next chunk arrives.
        keep_from = max(0, len(buf) - self._hold)
        out: list[bytes] = []
        pos = 0
        for m in self._re.finditer(buf):
            if m.start() >= keep_from:
                break
            out += [buf[pos : m.start()], MASK.encode()]
            pos = m.end()
        end = max(pos, keep_from)
        out.append(buf[pos:end])
        self._carry = buf[end:]
        return b"".join(out)

    def finish(self) -> bytes:
        """Everything still held back, masked: the stream has ended."""
        rest, self._carry = self._carry, b""
        return self.mask_bytes(rest)

    def mask_bytes(self, data: bytes) -> bytes:
        return data if self._re is None else self._re.sub(MASK.encode(), data)

    def mask_text(self, text: str) -> str:
        if self._re is None:
            return text
        return self.mask_bytes(text.encode()).decode("utf-8", errors="replace")


class MaskedSink:
    """A stdio child's stderr destination with the injected values masked out.

    ``write`` / ``flush`` make it a line sink for Coffer's own lines
    (``files.write_coffer_line``); :meth:`open_pipe` gives the SDK a file
    whose descriptor becomes the child's stderr, and :meth:`aclose` ends the
    pump once the child is gone. The target is not owned: whoever opened it
    closes it, after this.
    """

    def __init__(self, target: TextIO, values: Iterable[str]) -> None:
        self._target = target
        self._masker = StreamMasker(values)
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        # The loop's reader callback and Coffer's lines both write to the
        # target; the fallback reader thread (no ``add_reader``) does too.
        self._lock = threading.Lock()
        self._fd: int | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ended = asyncio.Event()

    @property
    def active(self) -> bool:
        """Whether any injected value is long enough to be masked."""
        return self._masker.active

    # -- Coffer's own lines ---------------------------------------------------
    def write(self, text: str, /) -> int:
        with self._lock:
            return self._target.write(self._masker.mask_text(text))

    def flush(self) -> None:
        with self._lock:
            self._target.flush()

    # -- the child's stderr ---------------------------------------------------
    def open_pipe(self) -> TextIO:
        """Start pumping a new pipe; return its write end for the SDK.

        The caller closes the returned file once the child has been started
        (the child holds its own copy), so the pipe ends when the child and
        anything it forked have exited.
        """
        read_fd, write_fd = os.pipe()  # both non-inheritable (PEP 446)
        self._fd = read_fd
        self._loop = loop = asyncio.get_running_loop()
        try:
            os.set_blocking(read_fd, False)
            loop.add_reader(read_fd, self._on_readable)
        except (NotImplementedError, AttributeError):  # pragma: no cover - Windows proactor
            os.set_blocking(read_fd, True)
            self._thread = threading.Thread(
                target=self._read_blocking, name="coffer-stderr-mask", daemon=True
            )
            self._thread.start()
        return os.fdopen(write_fd, "w", encoding="utf-8", errors="replace")

    def _on_readable(self) -> None:
        fd = self._fd
        if fd is None:
            return
        try:
            data = os.read(fd, _READ_SIZE)
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            data = b""
        if data:
            self._emit(self._masker.feed(data))
        else:
            self._end()

    def _read_blocking(self) -> None:  # pragma: no cover - Windows proactor
        fd = self._fd
        while fd is not None:
            try:
                data = os.read(fd, _READ_SIZE)
            except OSError:
                data = b""
            if not data:
                break
            self._emit(self._masker.feed(data))
        self._end()

    def _emit(self, data: bytes, *, final: bool = False) -> None:
        text = self._decoder.decode(data, final=final)
        if not text:
            return
        with self._lock:
            try:
                self._target.write(text)
                self._target.flush()
            except (OSError, ValueError):
                return

    def _end(self) -> None:
        """Stop reading, write the held-back tail, close the read end. Idempotent."""
        fd, self._fd = self._fd, None
        if fd is None:
            return
        if self._thread is None and self._loop is not None:
            with contextlib.suppress(Exception):
                self._loop.remove_reader(fd)
            # Whatever the child wrote before it was stopped is still buffered
            # in the pipe when the end comes from closing rather than from EOF.
            while True:
                try:
                    data = os.read(fd, _READ_SIZE)
                except OSError:
                    break
                if not data:
                    break
                self._emit(self._masker.feed(data))
        with contextlib.suppress(OSError):
            os.close(fd)
        self._emit(self._masker.finish(), final=True)
        if self._thread is None:
            self._ended.set()
        elif self._loop is not None:  # pragma: no cover - Windows proactor
            with contextlib.suppress(RuntimeError):
                self._loop.call_soon_threadsafe(self._ended.set)

    async def aclose(self) -> None:
        """Wait (bounded) for the child's stderr to end, then end the pump.

        Runs during teardown, after the SDK has stopped the child; cancellation
        or the time limit still drains, flushes and closes on the way out.
        """
        try:
            if self._loop is not None and not self._ended.is_set():
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._ended.wait(), DRAIN_SECONDS)
        finally:
            # A blocking reader thread cannot be interrupted; it ends with the
            # pipe's last writer and closes the read end itself.
            if self._thread is None:
                self._end()


def masked_sink(target: TextIO | None, values: Iterable[str]) -> MaskedSink | None:
    """A :class:`MaskedSink` over ``target`` (the daemon's stderr when there is
    none), or ``None`` when no injected value is long enough to mask."""
    sink = MaskedSink(target if target is not None else sys.stderr, values)
    return sink if sink.active else None


__all__ = ["DRAIN_SECONDS", "MASK", "MaskedSink", "StreamMasker", "masked_sink"]
