"""Starting a stdio upstream's child process, and learning its pid exactly.

``StdioUpstreamConnection`` owns the child in a lifetime task; this module is
the part of starting it that needs the child's pid, which the SDK's
``stdio_client`` does not expose: the pid files that let a leaked child be
reaped later are written under it. The pid is read from the process object the
SDK creates, never inferred from a before/after diff of the daemon's children —
any other child the daemon starts in that window (a codex, a git, a
skill-source clone) would be recorded as this server's process and killed with
it.
"""

from __future__ import annotations

import asyncio
import contextlib
import weakref
from collections.abc import Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

import mcp.client.stdio as _sdk_stdio
import psutil
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client

from coffer.infrastructure.daemon.orphan_sweep import record_spawn
from coffer.infrastructure.logging.files import open_upstream_errlog, write_coffer_line


def leaf_exception(exc: BaseException) -> BaseException:
    """Unwrap single-member exception groups so the real error is named."""
    while isinstance(exc, BaseExceptionGroup) and len(exc.exceptions) == 1:
        exc = exc.exceptions[0]
    return exc


# Serialise the window in which the SDK's process factory is wrapped, across
# the whole process: the wrapper records the pid of the NEXT process the SDK
# creates, so two concurrent spawns must not overlap. One lock per event loop:
# an ``asyncio.Lock`` binds to the loop of its first contended acquire, so a
# single module-level lock would refuse every later loop (a test's, or the
# daemon's after a restart in-process). The daemon runs one loop, so it has
# exactly one lock.
_SPAWN_LOCKS: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = (
    weakref.WeakKeyDictionary()
)


def _spawn_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _SPAWN_LOCKS.get(loop)
    if lock is None:
        lock = _SPAWN_LOCKS[loop] = asyncio.Lock()
    return lock


@dataclass
class StartedChild:
    """What opening the child produced besides its two streams."""

    read: Any
    write: Any
    errlog: TextIO | None = None
    pid_files: list[Path] = field(default_factory=list)
    child_pids: list[int] = field(default_factory=list)


async def open_child(
    exit_stack: AsyncExitStack,
    params: StdioServerParameters,
    *,
    server_name: str,
    server_uid: str,
    stderr_sink: TextIO | None,
    command_line: str,
    on_stop: Callable[[TextIO], None],
) -> StartedChild:
    """Start the child inside ``exit_stack`` and record its pid file."""
    async with _spawn_lock():
        # Give this upstream its own stderr file. The SDK's default is the
        # daemon's stderr, which lands in daemon.log and drowns Coffer's own
        # lines there (see logging/files.py).
        errlog = None if stderr_sink is not None else open_upstream_errlog(server_name)
        if errlog is not None:
            exit_stack.callback(errlog.close)
            # LIFO: this runs after the client's teardown, before close.
            exit_stack.callback(on_stop, errlog)
            write_coffer_line(errlog, f"start {command_line}")
        sink = errlog if errlog is not None else stderr_sink
        client = stdio_client(params) if sink is None else stdio_client(params, errlog=sink)

        original = _sdk_stdio._create_platform_compatible_process
        pids: list[int] = []

        async def _recording(*args: Any, **kwargs: Any) -> Any:
            process = await original(*args, **kwargs)
            pids.append(process.pid)
            return process

        _sdk_stdio._create_platform_compatible_process = _recording
        try:
            read, write = await exit_stack.enter_async_context(client)
        finally:
            _sdk_stdio._create_platform_compatible_process = original

    started = StartedChild(read, write, errlog, child_pids=sorted(pids))
    # The SDK starts the child in a new session, so its pid is also its process
    # group's id. The pid file keeps the child's actual cmdline, so a later
    # sweep can still guard against PID recycling.
    for pid in pids:
        with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
            started.pid_files.append(record_spawn(server_uid, pid, psutil.Process(pid).cmdline()))
    return started
