"""Claude Code's own sessions, through the Claude Agent SDK.

``claude_agent_sdk.list_sessions`` reads each session file's head and tail (no
parse of the conversation) and returns what a list needs; ``rename_session`` and
``delete_session`` change the agent's own store. Coffer keeps no copy and no
cache of any of it.

The SDK locates sessions through ``CLAUDE_CONFIG_DIR`` in ``os.environ``. A
registered agent whose config directory is not ``~/.claude`` therefore gets the
variable set around the call, under one module lock (the environment is process
wide) and restored afterwards. The SDK calls block on disk, so each runs in a
worker thread.

The SDK has no search, no cursor and no count: the whole listing is fetched,
filtered (case-insensitive, over title and working directory), ordered newest
activity first with the session id as the tie-break, and cut to the page here.
The continuation is a keyset over that order — the last row's activity time and
session id — and not an offset, so a session written between two reads neither
repeats nor skips a row (spec agent-registry/claude-code "List Claude Code
sessions through the Agent SDK").
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import claude_agent_sdk

from coffer.application.agent.native_session_service import SourcePage
from coffer.domain.agent.home_env import home_env
from coffer.domain.agent.native_sessions import (
    NativeSession,
    NativeSessionInvalid,
    NativeSessionNotFound,
    scrub_secrets,
)
from coffer.domain.agent.types import AgentType
from coffer.domain.pagination import position_of, time_and_id

#: Serialises every SDK call that needs a non-default ``CLAUDE_CONFIG_DIR``:
#: ``os.environ`` is shared by the whole daemon.
_ENV_LOCK = threading.Lock()


@contextmanager
def _config_dir_env(config_dir: pathlib.Path) -> Iterator[None]:
    """Point ``CLAUDE_CONFIG_DIR`` at *config_dir* for the block, then restore."""
    overrides = home_env(AgentType.CLAUDE_CODE, config_dir)
    if not overrides:
        yield
        return
    with _ENV_LOCK:
        saved = {name: os.environ.get(name) for name in overrides}
        os.environ.update(overrides)
        try:
            yield
        finally:
            for name, value in saved.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


def _when(ms: int | None) -> datetime | None:
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _to_session(info: Any) -> NativeSession:
    title = info.custom_title or info.summary or info.first_prompt or ""
    return NativeSession(
        session_id=info.session_id,
        title=scrub_secrets(title),
        cwd=info.cwd,
        created_at=_when(info.created_at),
        last_activity_at=_when(info.last_modified),
    )


def _matches(session: NativeSession, needle: str) -> bool:
    return needle in session.title.lower() or needle in (session.cwd or "").lower()


_FLOOR = datetime.min.replace(tzinfo=UTC)


def _order_key(session: NativeSession) -> tuple[datetime, str]:
    """Where the session sits in the listing: newest activity first, then the id
    descending (a session with no known activity sorts last)."""
    return (session.last_activity_at or _FLOOR, session.session_id)


class ClaudeNativeSessions:
    """``NativeSessionSource`` for Claude Code.

    The SDK functions are looked up on the SDK module at call time, so a test
    replaces them with ``monkeypatch.setattr(claude_agent_sdk, ...)``.
    """

    async def list(
        self, config_dir: pathlib.Path, *, q: str | None, limit: int, position: list[Any] | None
    ) -> SourcePage:
        after = time_and_id(position, str)

        def work() -> list[Any]:
            with _config_dir_env(config_dir):
                return list(claude_agent_sdk.list_sessions())

        infos = await asyncio.to_thread(work)
        sessions = [_to_session(info) for info in infos]
        if q:
            needle = q.lower()
            sessions = [s for s in sessions if _matches(s, needle)]
        sessions.sort(key=_order_key, reverse=True)
        total = len(sessions)
        if after is not None:
            sessions = [s for s in sessions if _order_key(s) < after]
        window = sessions[:limit]
        more = len(sessions) > limit
        return SourcePage(
            items=window,
            next_position=position_of(*_order_key(window[-1])) if more else None,
            total=total,
        )

    async def rename(self, config_dir: pathlib.Path, session_id: str, title: str) -> None:
        await asyncio.to_thread(
            self._call, claude_agent_sdk.rename_session, config_dir, session_id, title
        )

    async def delete(self, config_dir: pathlib.Path, session_id: str) -> None:
        await asyncio.to_thread(self._call, claude_agent_sdk.delete_session, config_dir, session_id)

    @staticmethod
    def _call(fn: Callable[..., None], config_dir: pathlib.Path, *args: str) -> None:
        try:
            with _config_dir_env(config_dir):
                fn(*args)
        except FileNotFoundError as exc:
            raise NativeSessionNotFound(args[0]) from exc
        except ValueError as exc:
            raise NativeSessionInvalid(str(exc)) from exc


__all__ = ["ClaudeNativeSessions"]
