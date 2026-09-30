"""What each agent session has already been given (spec memory "Retrieve the
notes a prompt names", "Guard a known trap once per session").

Two promises rest on it: a note retrieved for one prompt is not retrieved again
in the same session, and a trigger holds a command at most once per session.
Both are keyed on the ``session_id`` the agent hands its hook — never on a
process id, which every session of one Codex app-server shares — or, for a
turn Coffer drives from a channel, on the conversation.

Held in memory, bounded to the most recent sessions, and **rebuilt after a
daemon restart** from the one durable record of what was given: every fire
that delivered something is already an audit event naming its session, its
notes and its trigger (spec memory "Audit every delivery fire"). So the ledger
adds no table (spec memory "Add no table of its own"): ``restore`` reads those
events back once, before the first question is answered
(``ledger_restore.restore_from_audit``). A restore that fails is logged and
leaves the ledger empty — the cheaper failure is giving a note once more.
"""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

#: How many sessions the ledger remembers before forgetting the oldest.
MAX_SESSIONS = 2048


@dataclass
class _Session:
    delivered: set[str] = field(default_factory=set)
    fired: set[str] = field(default_factory=set)


class SessionLedger:
    """Per-session sets of delivered notes and fired triggers."""

    def __init__(
        self,
        max_sessions: int = MAX_SESSIONS,
        *,
        restore: Callable[[SessionLedger], Awaitable[object]] | None = None,
    ) -> None:
        self._sessions: OrderedDict[str, _Session] = OrderedDict()
        self._max = max_sessions
        self._restore = restore
        self._lock = asyncio.Lock()

    async def ready(self) -> None:
        """Restore what earlier daemons gave, once, before the first answer."""
        if self._restore is None:
            return
        async with self._lock:
            restore, self._restore = self._restore, None
            if restore is None:
                return
            try:
                await restore(self)
            except Exception:
                logger.exception("memory.session_ledger.restore_failed")

    def _session(self, session_id: str) -> _Session:
        found = self._sessions.get(session_id)
        if found is None:
            found = _Session()
            self._sessions[session_id] = found
            while len(self._sessions) > self._max:
                self._sessions.popitem(last=False)
        else:
            self._sessions.move_to_end(session_id)
        return found

    def delivered(self, session_id: str) -> frozenset[str]:
        """The note keys already delivered in this session."""
        found = self._sessions.get(session_id)
        return frozenset(found.delivered) if found else frozenset()

    def mark_delivered(self, session_id: str, keys: list[str]) -> None:
        self._session(session_id).delivered.update(keys)

    def has_fired(self, session_id: str, trigger_id: str) -> bool:
        found = self._sessions.get(session_id)
        return bool(found and trigger_id in found.fired)

    def mark_fired(self, session_id: str, trigger_id: str) -> None:
        self._session(session_id).fired.add(trigger_id)


__all__ = ["MAX_SESSIONS", "SessionLedger"]
