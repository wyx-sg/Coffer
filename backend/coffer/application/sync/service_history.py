"""The run-history half of ``ConvergeService`` (spec vault-sync).

Split out for the file-size tier, the same way ``service_machines.py`` was, and
along a real seam: the rest of the service decides *when* a round may run and
what a held one means, while this reads back what already ran.

Reading the history takes no lock and records nothing. A round is appended by
``record_run`` as part of storing it, so there is no second write to keep in
step — and a history that audited its own reads would grow a row every time the
page was opened.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coffer.domain.sync.convergence import ConvergeStatus, RunRecord

if TYPE_CHECKING:  # pragma: no cover - typing only
    from coffer.application.sync.ports import ConvergenceStatePort, SyncRemoteRepoPort

#: What one read returns, newest first. The surface searches, filters and pages
#: in the browser over what it is handed, so this is the window a user can look
#: back through — generous enough to cover weeks of rounds, small enough to stay
#: one query.
DEFAULT_RUN_LIMIT = 500


class HistoryMixin:
    """Declares what it borrows from the service it is mixed into.

    The annotation below is the contract, not state: ``ConvergeService``
    assigns it in its constructor. Spelling it here is what lets this half be
    type-checked on its own.
    """

    _remotes: SyncRemoteRepoPort
    _state: ConvergenceStatePort

    async def not_applicable(self) -> list[str]:
        """Every path recorded as not applicable on this machine."""
        _retry, not_applicable = await self._state.held_paths()
        return sorted(not_applicable)

    async def runs(self, limit: int = DEFAULT_RUN_LIMIT) -> list[RunRecord]:
        """Every round this vault has run against its remote, newest first.

        Not filtered by status: a round that changed nothing is the majority of
        them and is exactly what makes a *gap* visible — a history that only
        kept the eventful rounds would read as though the vault had been idle
        rather than failing.
        """
        return await self._remotes.list_runs(limit)

    async def divergence_outstanding(self) -> bool:
        """Whether a round left something the user has not yet answered.

        Either a confirmation held at the deletion guard, or a last round that
        stopped on a conflict — which holds nothing (the vault is untouched and
        the pointer has not moved), so only the recorded round says it is
        there. An unattended rewriter consults this before it runs (spec
        vault-sync "Never overlap a tidy pass and a round"): a rewrite piled
        onto an unresolved divergence changes the very documents the user is
        about to decide between.
        """
        if await self._state.pending() is not None:
            return True
        last = await self._remotes.last_run()
        return last is not None and last.status is ConvergeStatus.CONFLICT
