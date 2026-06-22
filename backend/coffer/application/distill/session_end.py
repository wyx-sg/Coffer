"""On-demand SessionEnd distill (Slice 6 FR-051).

When a managed Claude Code session ends, its hook POSTs to the daemon, which
distills that single session into the journal lane — reusing the exact idempotent
flow of the FR-046 catch-up sweep (``is_distilled`` → ``distill`` →
``mark_distilled``) against the same ``distilled_sessions`` ledger, so a session
distilled here is never re-distilled by the sweep and vice-versa.

All collaborators are injected as plain callables so this application module
imports nothing from infrastructure or surfaces (import-linter compliant). The
only peer import is ``NoModelConfiguredError`` (a no-internal-engine no-op).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from enum import StrEnum

from coffer.application.distill.service import NoModelConfiguredError

_logger = logging.getLogger(__name__)


class SessionEndOutcome(StrEnum):
    """Why a session-end distill ended — all are 2xx-worthy (never an error)."""

    DISTILLED = "distilled"
    ALREADY_DISTILLED = "already_distilled"
    NO_MODEL = "no_model"
    NOT_FOUND = "not_found"  # session id unknown / not a readable transcript
    SKIPPED = "skipped"  # any other tolerated failure (logged, retried by sweep)


class SessionEndDistiller:
    """Distill a single just-ended session, idempotently.

    ``session_sha`` resolves the on-disk transcript path for ``(agent, session)``
    and returns its content sha (or ``None`` if the session can't be located).
    """

    def __init__(
        self,
        *,
        distill: Callable[[str, str], Awaitable[None]],
        is_distilled: Callable[[str, str, str], Awaitable[bool]],
        mark_distilled: Callable[[str, str, str], Awaitable[None]],
        session_sha: Callable[[str, str], Awaitable[str | None]],
    ) -> None:
        self._distill = distill
        self._is_distilled = is_distilled
        self._mark_distilled = mark_distilled
        self._session_sha = session_sha

    async def distill_session(self, *, agent_name: str, session_id: str) -> SessionEndOutcome:
        """Distill ``session_id`` for ``agent_name`` once. Never raises."""
        try:
            sha = await self._session_sha(agent_name, session_id)
        except Exception:
            _logger.debug("session_end.sha.failed", exc_info=True)
            return SessionEndOutcome.NOT_FOUND
        if sha is None:
            return SessionEndOutcome.NOT_FOUND

        try:
            if await self._is_distilled(agent_name, session_id, sha):
                return SessionEndOutcome.ALREADY_DISTILLED
        except Exception:
            _logger.debug("session_end.is_distilled.failed", exc_info=True)
            # Fall through and try to distill; mark guards against duplicates.

        try:
            await self._distill(agent_name, session_id)
        except NoModelConfiguredError:
            _logger.info("session_end.no_model.noop")
            return SessionEndOutcome.NO_MODEL
        except Exception:
            _logger.warning(
                "session_end.distill.failed",
                extra={"agent": agent_name, "session_id": session_id},
                exc_info=True,
            )
            return SessionEndOutcome.SKIPPED

        try:
            await self._mark_distilled(agent_name, session_id, sha)
        except Exception:
            _logger.warning("session_end.mark.failed", exc_info=True)
        return SessionEndOutcome.DISTILLED
