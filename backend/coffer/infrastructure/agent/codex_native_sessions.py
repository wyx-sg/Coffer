"""Codex's own sessions (threads), through a short-lived ``codex app-server``.

Coffer asks Codex, as ``codex_rpc_models`` does for models: spawn the app-server
the turns use, run the ``initialize`` handshake, make one call, tear the
process down. ``thread/list`` answers the listing (the server's own
``nextCursor`` is the continuation token), ``thread/name/set`` renames and
``thread/delete`` deletes. Coffer keeps no copy of any of it.

The listing asks for every interactive source kind (``cli``, ``vscode``,
``exec``, ``appServer``), so the threads Coffer's own channels ran are listed
beside the ones the person started in a terminal. ``searchTerm`` is Codex's own
substring filter and matches the thread's *title* only (not its working
directory); it is passed through rather than re-filtering the returned page by
directory, because filtering a page after the fact would make ``nextCursor``
dishonest (short or empty pages in the middle of a result). The server cannot
count matches cheaply, so ``total`` is ``None``.

The transport is injected: ``infrastructure/agent`` may not import
``infrastructure/chat``, so the composition root hands in the chat package's
production factory (``default_app_server_session``) and tests hand in a fake
peer. The process runs under the agent's own ``CODEX_HOME`` when its config dir
is not the default ``~/.codex``.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import pathlib
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from coffer.application.agent.native_session_service import SourcePage
from coffer.domain.agent.home_env import home_env
from coffer.domain.agent.native_sessions import (
    NativeSession,
    NativeSessionBusy,
    NativeSessionInvalid,
    NativeSessionNotFound,
    scrub_secrets,
)
from coffer.domain.agent.types import AgentType
from coffer.domain.errors import UpstreamTimeout, UpstreamUnavailable
from coffer.domain.pagination import CursorInvalid

#: What Coffer calls itself in the app-server handshake (the turns' value).
_CLIENT_INFO = {"name": "coffer", "title": None, "version": "0"}

#: The thread sources a person can have started: a terminal, an editor, a
#: one-shot ``codex exec`` and an app-server client (Coffer's channels).
_SOURCE_KINDS = ["cli", "vscode", "exec", "appServer"]

#: A wedged CLI must not hold a request open.
_TIMEOUT_SECONDS = 20.0


class _Rpc(Protocol):
    async def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]: ...

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None: ...


class _Session(Protocol):
    @property
    def rpc(self) -> _Rpc: ...

    async def start(self) -> None: ...

    async def close(self) -> None: ...


#: ``(cwd, env) -> session`` — the chat package's ``default_app_server_session``.
SessionFactory = Callable[[str, dict[str, str] | None], _Session]


def _when(seconds: object) -> datetime | None:
    if isinstance(seconds, bool) or not isinstance(seconds, int | float):
        return None
    try:
        return datetime.fromtimestamp(seconds, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _to_session(thread: dict[str, Any]) -> NativeSession | None:
    ident = thread.get("id")
    if not isinstance(ident, str) or not ident:
        return None
    name, preview, cwd = thread.get("name"), thread.get("preview"), thread.get("cwd")
    title = name if isinstance(name, str) and name.strip() else preview
    return NativeSession(
        session_id=ident,
        title=scrub_secrets(title.strip()) if isinstance(title, str) else "",
        cwd=cwd if isinstance(cwd, str) else None,
        created_at=_when(thread.get("createdAt")),
        last_activity_at=_when(thread.get("updatedAt")),
    )


class CodexNativeSessions:
    """``NativeSessionSource`` for Codex."""

    def __init__(self, session_factory: SessionFactory, *, timeout: float = _TIMEOUT_SECONDS):
        self._session_factory = session_factory
        self._timeout = timeout

    async def list(
        self, config_dir: pathlib.Path, *, q: str | None, limit: int, position: list[Any] | None
    ) -> SourcePage:
        params: dict[str, Any] = {
            "limit": limit,
            "sortKey": "updated_at",
            "sourceKinds": _SOURCE_KINDS,
        }
        cursor = _cursor_of(position)
        if cursor is not None:
            params["cursor"] = cursor
        if q:
            params["searchTerm"] = q
        result = await self._call(config_dir, "thread/list", params)
        data = result.get("data")
        rows = data if isinstance(data, list) else []
        items = [s for s in (_to_session(t) for t in rows if isinstance(t, dict)) if s is not None]
        nxt = result.get("nextCursor")
        return SourcePage(
            items=items,
            next_position=[nxt] if isinstance(nxt, str) and nxt else None,
            total=None,
        )

    async def rename(self, config_dir: pathlib.Path, session_id: str, title: str) -> None:
        await self._call(
            config_dir, "thread/name/set", {"threadId": session_id, "name": title}, session_id
        )

    async def delete(self, config_dir: pathlib.Path, session_id: str) -> None:
        await self._call(config_dir, "thread/delete", {"threadId": session_id}, session_id)

    # --- internals -----------------------------------------------------------

    async def _call(
        self,
        config_dir: pathlib.Path,
        method: str,
        params: dict[str, Any],
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Spawn, handshake, one request, tear down; failures become domain errors."""
        try:
            session = self._session_factory(_cwd(config_dir), _env(config_dir))
        except Exception as exc:  # most often: codex is not installed
            raise UpstreamUnavailable(f"codex is not available: {exc}") from exc
        try:
            return await asyncio.wait_for(self._run(session, method, params), self._timeout)
        except TimeoutError as exc:
            raise UpstreamTimeout(f"codex did not answer {method}") from exc
        except Exception as exc:
            raise _domain_error(exc, session_id) from exc
        finally:
            # The process must not outlive the call, even when it was cancelled.
            with contextlib.suppress(Exception):
                await session.close()

    @staticmethod
    async def _run(session: _Session, method: str, params: dict[str, Any]) -> dict[str, Any]:
        await session.start()
        rpc = session.rpc
        # The exact handshake codex_agent runs before any thread call.
        await rpc.request("initialize", {"clientInfo": _CLIENT_INFO, "capabilities": None})
        await rpc.notify("initialized")
        return await rpc.request(method, params)


def _cursor_of(position: list[Any] | None) -> str | None:
    """The server's own cursor a decoded position carries."""
    if position is None:
        return None
    if len(position) != 1 or not isinstance(position[0], str):
        raise CursorInvalid("its position does not fit this list")
    return position[0]


def _domain_error(exc: Exception, session_id: str | None) -> Exception:
    """An RPC refusal about a missing thread is a 404, one about a thread another
    process is writing to (a Codex App window, a terminal) is a 409; anything
    else is codex being unavailable. Duck-typed on ``rpc_message`` so this module need not
    import the chat package's ``CodexRpcError``."""
    message = getattr(exc, "rpc_message", None)
    if isinstance(message, str):
        lowered = message.lower()
        if session_id is not None and ("not found" in lowered or "no thread" in lowered):
            return NativeSessionNotFound(session_id)
        if session_id is not None and "active writer" in lowered:
            return NativeSessionBusy(message)
        if "invalid" in lowered and session_id is not None:
            return NativeSessionInvalid(message)
    return UpstreamUnavailable(f"codex app-server failed: {exc}")


def _env(config_dir: pathlib.Path) -> dict[str, str] | None:
    """The daemon's environment plus ``CODEX_HOME`` for a non-default config dir
    (the spawn REPLACES the environment, so overrides are merged); ``None``
    inherits unchanged."""
    overrides = home_env(AgentType.CODEX, config_dir)
    return {**os.environ, **overrides} if overrides else None


def _cwd(config_dir: pathlib.Path) -> str:
    """The process must start somewhere that exists; the thread calls need no
    project context."""
    with contextlib.suppress(OSError):
        if config_dir.is_dir():
            return str(config_dir)
    return str(pathlib.Path.home())


__all__ = ["CodexNativeSessions", "SessionFactory"]
