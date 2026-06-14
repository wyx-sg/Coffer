"""Subprocess transport seam for ``codex app-server`` (spec 008, T2).

Wraps the long-lived ``codex app-server`` process behind the
:class:`CodexAppServerSession` protocol so the adapter drives a
:class:`~coffer.infrastructure.chat.codex_jsonrpc.CodexRpcClient` without knowing
whether it is talking to a real subprocess or a fake JSON-RPC peer. Mirrors
``cli_agent.default_spawner`` / ``claude_sdk_agent.default_session_factory``.

The production factory :func:`default_app_server_session` resolves the ``codex``
binary on ``PATH`` via ``shutil.which`` (production machines ship a working npm
wrapper; the adapter never hard-codes a path) and spawns it with stdin/stdout
pipes, which become the NDJSON reader/writer the RPC client reads/writes.

Only stdlib ``asyncio`` + ``shutil`` are used (Contract 9 — no new dependency).
The real-subprocess factory is covered by an integration test that skips when
``codex`` is absent; it is never exercised in the unit tier.
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


class CodexAppServerSession(Protocol):
    """The slice of a ``codex app-server`` process the adapter drives, behind a seam.

    ``start()`` launches the transport and begins the RPC read loop; ``rpc``
    exposes the bidirectional JSON-RPC client; ``close()`` tears the process
    (and read loop) down. Injected via :data:`AppServerSessionFactory` so turns
    are testable with a fake peer (mirrors ``ClaudeSdkSession``).
    """

    @property
    def rpc(self) -> CodexRpcClient: ...

    async def start(self) -> None: ...

    async def close(self) -> None: ...


#: Build one app-server session from its spawn config: ``(cwd, env) -> session``.
AppServerSessionFactory = Callable[[str, dict[str, str] | None], CodexAppServerSession]


class CodexSubprocessSession:
    """A :class:`CodexAppServerSession` backed by a real ``codex app-server`` process.

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
        # Capture stderr (was DEVNULL) and forward it to the daemon log. When
        # codex exits during the handshake the RPC layer only sees the stream
        # end ("codex rpc stream ended"); the actual cause (e.g. a broken codex
        # install: "Missing optional dependency @openai/codex-…") is on stderr,
        # so surfacing it here turns an opaque failure into an actionable log.
        proc = await asyncio.create_subprocess_exec(
            *self._argv,
            cwd=self._cwd,
            env=self._env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        if proc.stdin is None or proc.stdout is None:
            raise RuntimeError("codex app-server subprocess has no stdin/stdout pipe")
        self._proc = proc
        if proc.stderr is not None:
            self._stderr_task = asyncio.create_task(self._drain_stderr(proc.stderr))
        self._rpc = CodexRpcClient(proc.stdout, proc.stdin)
        self._rpc.start()

    @staticmethod
    async def _drain_stderr(stream: asyncio.StreamReader) -> None:
        """Forward the codex subprocess's stderr to the daemon log, line by line."""
        with contextlib.suppress(Exception):
            while True:
                line = await stream.readline()
                if not line:
                    break
                text = line.decode("utf-8", "replace").rstrip()
                if text:
                    _logger.warning("codex app-server stderr: %s", text)

    async def close(self) -> None:
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
                proc.terminate()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(proc.wait(), timeout=5.0)


def default_app_server_session(cwd: str, env: dict[str, str] | None) -> CodexAppServerSession:
    """Build a real ``codex app-server`` session (production seam).

    Resolves the ``codex`` binary on ``PATH`` at call time so the adapter never
    hard-codes a path. Raises ``RuntimeError`` if ``codex`` is not installed.
    """
    binary = shutil.which("codex")
    if binary is None:
        raise RuntimeError("codex binary not found on PATH")
    return CodexSubprocessSession([binary, "app-server"], cwd, env)


__all__ = [
    "AppServerSessionFactory",
    "CodexAppServerSession",
    "CodexSubprocessSession",
    "default_app_server_session",
]
