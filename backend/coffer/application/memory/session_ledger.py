"""What each agent session has already been given (spec memory "Retrieve the
notes a prompt names", "Guard a known trap once per session").

Two promises rest on it: a note retrieved for one prompt is not retrieved again
in the same session, and a trigger holds a command at most once per session.
Both are keyed on the ``session_id`` the agent hands its hook — never on a
process id, which every session of one Codex app-server shares.

Per-daemon and in memory, bounded to the most recent sessions. A daemon
restart forgets it, so after one a session may be given a note again or have a
trigger hold one more command; that is the cheaper failure, and the ledger adds
no table (spec memory "Add no table of its own").
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field

#: How many sessions the ledger remembers before forgetting the oldest.
MAX_SESSIONS = 2048


@dataclass
class _Session:
    delivered: set[str] = field(default_factory=set)
    fired: set[str] = field(default_factory=set)


class SessionLedger:
    """Per-session sets of delivered notes and fired triggers."""

    def __init__(self, max_sessions: int = MAX_SESSIONS) -> None:
        self._sessions: OrderedDict[str, _Session] = OrderedDict()
        self._max = max_sessions

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
