"""The ``coffer-seatalk-bridge`` executable.

1. Move the protocol off fd 1: the real stdout is duplicated onto a private
   descriptor that only the emitter writes to, and fd 1 is pointed at
   /dev/null, so a stray ``print()`` in the SDK can neither corrupt the
   protocol nor leak a message body anywhere.
2. Read the one config line from stdin.
3. Import the SDK and hold one connection on a worker thread.
4. Exit when the connection ends, when stdin reaches EOF (the daemon closed it
   or died), or on SIGTERM — closing the client first, and leaving after a
   short grace period even if the SDK does not let go.
"""

from __future__ import annotations

import contextlib
import functools
import os
import signal
import sys
import threading
from typing import Any

from coffer.infrastructure.channel.seatalk_bridge.protocol import Emitter, decode_config
from coffer.infrastructure.channel.seatalk_bridge.session import import_sdk, open_session

_CLOSE_GRACE_SECONDS = 5.0
_POLL_SECONDS = 0.2


def _private_stdout() -> int:
    """Return a descriptor for the real stdout, and point fd 1 at /dev/null."""
    out_fd = os.dup(1)
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull, 1)
    finally:
        os.close(devnull)
    return out_fd


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        view = view[written:]


def main() -> int:
    out_fd = _private_stdout()
    line = sys.stdin.buffer.readline()
    try:
        config = decode_config(line)
    except ValueError as e:
        print(f"coffer-seatalk-bridge: {e}", file=sys.stderr)
        return 2

    emitter = Emitter(functools.partial(_write_all, out_fd), secret=config.app_secret)
    session = open_session(functools.partial(import_sdk, config.sdk_dir), config, emitter)
    if session is None:
        return 0

    stop = threading.Event()
    finished = threading.Event()
    emitter.on_broken = stop.set

    def _run() -> None:
        try:
            session.run()
        finally:
            finished.set()

    def _watch_stdin() -> None:
        with contextlib.suppress(Exception):
            while sys.stdin.buffer.readline():
                pass  # nothing else is ever sent; EOF is the message
        stop.set()

    def _on_sigterm(_signum: int, _frame: Any) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, _on_sigterm)
    threading.Thread(target=_watch_stdin, name="bridge-stdin", daemon=True).start()
    threading.Thread(target=_run, name="bridge-session", daemon=True).start()

    while not finished.wait(_POLL_SECONDS):
        if stop.is_set():
            session.close()
            finished.wait(_CLOSE_GRACE_SECONDS)
            break
    return 0


def run() -> None:
    """Entry point: run, then leave without waiting on threads the SDK started."""
    code = main()
    with contextlib.suppress(Exception):
        sys.stderr.flush()
    os._exit(code)
