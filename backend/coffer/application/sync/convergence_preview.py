"""A join, described before it is performed (spec vault-sync "Report a join
before applying it").

Step 0 of a round decides whether this machine is joining and, if so, as what.
The surfaces owe the user that answer — the case, the day this machine last
converged, how much the remote changed since, how much this vault holds —
*before* the round acts on it. This asks step 0's question the same way the
round does and stops there.

Nothing here touches the vault or the pointer. It fetches, which the round would
do first anyway, and it serializes the vault into the working tree to count it.
The tree is a serialization target that the next round rewrites from the vault
(or resets to the recovered base, for a returning machine) before it compares
anything, so a preview leaves nothing behind that a round could read as a
change.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from coffer.application.sync.convergence_ops import diff_between, remote_tip
from coffer.application.sync.joining import JoinPreview, JoinResolver
from coffer.domain.sync.convergence import JoinKind
from coffer.domain.sync.errors import SyncJoinAmbiguous

_logger = logging.getLogger("coffer.application.sync.convergence")

#: Unreachable pointers already reported in this process.
_REPORTED_UNREACHABLE: set[str] = set()

if TYPE_CHECKING:  # pragma: no cover - typing only
    from coffer.application.sync.ports import ConvergenceStatePort, GitMirrorPort
    from coffer.domain.sync.models import ExportSummary


class PreviewMixin:
    """``preview_join``, mixed into ``ConvergeRound``.

    The members below are borrowed from the round; declaring them lets this
    half be type-checked on its own.
    """

    _mirror: GitMirrorPort
    _state: ConvergenceStatePort
    _joining: JoinResolver
    _serialize: Callable[[], Awaitable[ExportSummary]]
    _branch: str

    async def _reachable(self, commit: str) -> bool:
        raise NotImplementedError  # pragma: no cover - provided by ConvergeRound

    async def is_joining(self) -> bool:
        """No pointer, or one that no longer resolves: the next round joins.

        The one predicate for "has this machine joined?" — the round, the
        preview and the status surface all ask this, so they cannot disagree.
        The empty tree a new machine joins from counts as joined
        (``ConvergeRound._reachable``).
        """
        pointer = await self._state.pointer()
        if pointer is None:
            return True
        if await self._reachable(pointer):
            return False
        if pointer not in _REPORTED_UNREACHABLE:
            # Once per pointer, not every tick: the Sync page and ``coffer sync
            # status`` carry the state; the log only has to say why.
            _REPORTED_UNREACHABLE.add(pointer)
            _logger.info(
                "converge: pointer %s is unreachable (working tree deleted or moved); "
                "this machine re-joins on 'coffer sync adopt'",
                pointer[:12],
            )
        return True

    async def preview_join(self, *, token: str | None, choice: str | None = None) -> JoinPreview:
        """What step 0 would decide, with the counts the surfaces report.

        Mirrors ``ConvergeRound._base``: a pointer that is missing, or that no
        longer resolves, means this machine is joining. The reachability check
        runs before the fetch for the same reason it does there.
        """
        if not await self.is_joining():
            return JoinPreview(joining=False)
        await self._mirror.fetch(token=token)
        vault_documents = await self._count_vault()
        try:
            join = await self._joining.resolve(self._mirror, choice=choice)
        except SyncJoinAmbiguous:
            return JoinPreview(
                joining=True,
                ambiguous=True,
                last_converged_on=await self._joining.last_converged_on(self._mirror),
                vault_documents=vault_documents,
            )
        tip = await remote_tip(self._mirror, self._branch)
        changed = (
            0
            if tip is None
            else len((await diff_between(self._mirror, join.pointer, tip)).vault_changes)
        )
        return JoinPreview(
            joining=True,
            kind=join.kind,
            base=join.pointer if join.kind is JoinKind.RETURNING else None,
            last_converged_on=join.last_converged_on,
            remote_changed=changed,
            vault_documents=vault_documents,
        )

    async def _count_vault(self) -> int:
        """Every document this vault would publish, area by area.

        ``machines/`` is the registry, not the vault, and it only exists in the
        tree once a descriptor has been written there — so counting it would
        make the same vault report a different number from one round to the
        next.
        """
        summary = await self._serialize()
        return sum(area.count for area in summary.areas if area.area != "machines")
