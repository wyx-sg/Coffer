"""FallbackSessionSource — an agent's own sessions, or Coffer's when its store
cannot be read.

OpenCode, DeepSeek Harness and Cursor keep their sessions in stores they do not
document for other programs, so a new version may change what Coffer reads.
When the primary source raises one of ``unreadable``, the list answers with
the fallback (the conversations Coffer ran on the agent) instead of failing;
the reason is logged once per failure. Rename and delete always go to the
primary source. The fallback's positions are one cursor and the primary's a
time and an id, so a later page goes back to the source that issued it.
"""

from __future__ import annotations

import logging
import pathlib
from typing import Any

from coffer.application.agent.native_session_service import NativeSessionSource, SourcePage

_log = logging.getLogger(__name__)


class FallbackSessionSource:
    def __init__(
        self,
        primary: NativeSessionSource,
        fallback: NativeSessionSource,
        *,
        unreadable: tuple[type[Exception], ...],
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._unreadable = unreadable

    def bind(self, chat: object) -> None:
        for source in (self._primary, self._fallback):
            bind = getattr(source, "bind", None)
            if callable(bind):
                bind(chat)

    async def list(
        self, config_dir: pathlib.Path, *, q: str | None, limit: int, position: list[Any] | None
    ) -> SourcePage:
        if position is not None and len(position) == 1:
            # A later page of the fallback's list (its positions are one
            # cursor; the primary's are a time and an id).
            return await self._fallback.list(config_dir, q=q, limit=limit, position=position)
        try:
            return await self._primary.list(config_dir, q=q, limit=limit, position=position)
        except self._unreadable as exc:
            _log.warning("agent session store unreadable, listing Coffer's sessions: %s", exc)
            if position is not None:
                # A later page of the primary's list: its position does not
                # fit the fallback, so the list ends here.
                return SourcePage(items=[], next_position=None, total=None)
            return await self._fallback.list(config_dir, q=q, limit=limit, position=None)

    async def rename(self, config_dir: pathlib.Path, session_id: str, title: str) -> None:
        await self._primary.rename(config_dir, session_id, title)

    async def delete(self, config_dir: pathlib.Path, session_id: str) -> None:
        await self._primary.delete(config_dir, session_id)


__all__ = ["FallbackSessionSource"]
