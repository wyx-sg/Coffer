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
import shutil
from collections.abc import Callable, Sequence
from typing import Protocol

from coffer.infrastructure.chat.codex_jsonrpc import CodexRpcClient


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
            stderr=asyncio.subprocess.DEVNULL,
        )
        assert proc.stdin is not None and proc.stdout is not None
        self._proc = proc
        self._rpc = CodexRpcClient(proc.stdout, proc.stdin)
        self._rpc.start()

    async def close(self) -> None:
        if self._rpc is not None:
            await self._rpc.close()
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
