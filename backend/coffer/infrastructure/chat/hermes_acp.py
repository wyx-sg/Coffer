"""Subprocess transport seam for ``hermes acp`` (the Agent Client Protocol).

Wraps a long-lived ``hermes acp`` process behind the :class:`HermesAcpSession`
protocol so the adapter drives a
:class:`~coffer.infrastructure.chat.codex_jsonrpc.CodexRpcClient` (a generic
NDJSON JSON-RPC client) without knowing whether it is talking to a real
subprocess or a fake JSON-RPC peer. Mirrors ``codex_app_server.py``.

ACP is JSON-RPC 2.0 over stdio — one JSON object per line, in both directions —
so the same :class:`CodexRpcClient` transport used for ``codex app-server`` drives
it verbatim; Coffer hand-rolls the client and adds no ``acp`` pip dependency.

The production factory :func:`default_hermes_acp_session` resolves the ``hermes``
binary on ``PATH`` via ``shutil.which`` and spawns ``hermes acp --accept-hooks``
(``--accept-hooks`` pre-consents shell hooks so an unattended turn is never
blocked). Two robustness details, learned from the opencode adapter review:

* **stderr is drained concurrently** in a background task — hermes logs to
  stderr, and an undrained stderr pipe blocks the subprocess once it fills.
* the subprocess ``StreamReader`` ``limit`` is raised to 16 MiB (ACP lines —
  a tool call's raw output — routinely exceed asyncio's 64 KiB default).

Only stdlib ``asyncio`` + ``shutil`` are used (no new dependency).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import shutil
from collections.abc import Callable, Sequence
from typing import Protocol

from coffer.infrastructure.chat.codex_jsonrpc import CodexRpcClient

_logger = logging.getLogger(__name__)

#: StreamReader line-buffer limit for the subprocess pipes. ACP frames — a tool
#: call's ``rawOutput`` (a file read or verbose command output) — routinely
#: exceed asyncio's 64 KiB default, which would raise ``ValueError`` mid-stream.
#: 16 MiB covers realistic frames; beyond it the RPC read loop ends gracefully
#: (the adapter then synthesises a terminal) rather than crashing.
STREAM_LIMIT = 16 * 1024 * 1024


class HermesAcpSession(Protocol):
    """The slice of a ``hermes acp`` process the adapter drives, behind a seam.

    ``start()`` launches the transport and begins the RPC read loop; ``rpc``
    exposes the bidirectional JSON-RPC client; ``close()`` tears the process
    (and read loop) down. Injected via :data:`AcpSessionFactory` so turns are
    testable with a fake peer (mirrors ``CodexAppServerSession``).
    """

    @property
    def rpc(self) -> CodexRpcClient: ...

    async def start(self) -> None: ...

    async def close(self) -> None: ...


#: Build one ACP session from its spawn config: ``(cwd, env) -> session``.
AcpSessionFactory = Callable[[str, "dict[str, str] | None"], HermesAcpSession]


class HermesSubprocessSession:
    """A :class:`HermesAcpSession` backed by a real ``hermes acp`` process.

    Kept deliberately thin — the only place the concrete subprocess is touched —
    so the adapter stays unit-testable behind the protocol.
    """

    def __init__(self, argv: Sequence[str], cwd: str, env: dict[str, str] | None) -> None:
        self._argv = list(argv)
        self._cwd = cwd
        self._env = env
        self._proc: asyncio.subprocess.Process | None = None
        self._rpc: CodexRpcClient | None = None
        self._stderr_task: asyncio.Task[None] | None = None

    @property
    def rpc(self) -> CodexRpcClient:
        if self._rpc is None:
            raise RuntimeError("session not started")
        return self._rpc

    async def start(self) -> None:
        proc = await asyncio.create_subprocess_exec(
            *self._argv,
            cwd=self._cwd,
            env=self._env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=STREAM_LIMIT,
        )
        if proc.stdin is None or proc.stdout is None:
            raise RuntimeError("hermes acp subprocess has no stdin/stdout pipe")
        self._proc = proc
        # Drain stderr concurrently: hermes logs to stderr, and an undrained
        # stderr pipe blocks the subprocess once the OS pipe buffer fills. The
        # drain also forwards the lines to the daemon log so an install/startup
        # failure ("hermes rpc stream ended") shows its actual cause.
        if proc.stderr is not None:
            self._stderr_task = asyncio.create_task(self._drain_stderr(proc.stderr))
        self._rpc = CodexRpcClient(proc.stdout, proc.stdin)
        self._rpc.start()

    @staticmethod
    async def _drain_stderr(stream: asyncio.StreamReader) -> None:
        """Forward the hermes subprocess's stderr to the daemon log, line by line.

        Robust to an over-long line: rather than let ``readline`` raise (which
        would end the drain and re-expose the deadlock), the offending buffer is
        discarded and draining continues.
        """
        while True:
            try:
                line = await stream.readline()
            except (ValueError, asyncio.LimitOverrunError):
                # Over-limit line: consume the buffered chunk so the pipe keeps
                # draining, then continue.
                with contextlib.suppress(Exception):
                    await stream.read(STREAM_LIMIT)
                continue
            except Exception:
                break
            if not line:
                break
            text = line.decode("utf-8", "replace").rstrip()
            if text:
                _logger.warning("hermes acp stderr: %s", text)

    async def close(self) -> None:
        """Kill and reap the subprocess (no zombie) and stop the read + drain loops."""
        if self._rpc is not None:
            await self._rpc.close()
        if self._stderr_task is not None:
            self._stderr_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._stderr_task
            self._stderr_task = None
        proc = self._proc
        if proc is not None and proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            with contextlib.suppress(Exception):
                await proc.wait()


def default_hermes_acp_session(cwd: str, env: dict[str, str] | None) -> HermesAcpSession:
    """Build a real ``hermes acp`` session (production seam).

    Resolves the ``hermes`` binary on ``PATH`` at call time so the adapter never
    hard-codes a path. ``--accept-hooks`` pre-consents shell hooks so a turn is
    never blocked. Raises ``RuntimeError`` if ``hermes`` is not installed.
    """
    binary = shutil.which("hermes")
    if binary is None:
        raise RuntimeError("hermes binary not found on PATH")
    return HermesSubprocessSession([binary, "acp", "--accept-hooks"], cwd, env)


__all__ = [
    "STREAM_LIMIT",
    "AcpSessionFactory",
    "HermesAcpSession",
    "HermesSubprocessSession",
    "default_hermes_acp_session",
]
