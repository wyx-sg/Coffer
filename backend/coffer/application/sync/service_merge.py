"""The agent-merge half of ``SyncService`` (spec vault-sync "Hand conflicting files to
an agent").

Handing files to an agent records the hand-off and writes each file's
marked-up copy outside the vault; the prompt names where the agent writes its
merge. The status then reads the copy to say whether the agent has merged it.
Nothing here answers a file or writes into the vault: marking the merge
resolved is the ``edited`` answer, and going back to two choices forgets the
copy.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from coffer.application.sync import round_answers
from coffer.application.sync.views import HandoffResult
from coffer.domain.sync.handoffs import (
    MergeFile,
    agent_mergeable,
    conflict_merge_handoff,
    is_secret_file,
)
from coffer.domain.sync.stops import ConflictFile, StopKind

if TYPE_CHECKING:  # pragma: no cover - typing only
    from coffer.application.sync.round_engine import RoundEngine
    from coffer.application.sync.service_ports import HostMachinePort


class MergeMixin:
    """Declares what it borrows from ``SyncService``, which assigns each."""

    _engine: RoundEngine
    _machine: HostMachinePort
    _vault_path: Callable[[], Path]

    async def _locked(self, fn: Callable[[], Any]) -> Any:
        raise NotImplementedError  # pragma: no cover - provided by SyncService

    async def hand_off(
        self,
        paths: list[str] | None,
        *,
        join: bool = False,
        agent: str | None = None,
        conversation: str | None = None,
    ) -> HandoffResult:
        """Record ``paths`` (every file an agent may merge when ``None``) as
        handed to an agent, and the prompt that asks for the merge."""

        def apply() -> HandoffResult:
            handed = round_answers.hand_off(
                self._engine, paths, join=join, agent=agent, conversation=conversation
            )
            prompt = self._merge_prompt(handed, join=join)
            assert prompt is not None  # hand_off refuses an empty list
            return HandoffResult(prompt=prompt, paths=handed)

        result: HandoffResult = await self._locked(apply)
        return result

    async def conflict_handoff(self) -> str | None:
        """The prompt for every file of the stopped round an agent may merge,
        recording nothing (the Overview's item)."""

        def build() -> str | None:
            d = self._engine.d
            stop = d.state.stop()
            if stop is None or stop.kind is not StopKind.CONFLICTS:
                return None
            handed = tuple(c.path for c in stop.conflicts if agent_mergeable(c))
            for path in handed:
                round_answers.editor_copy(self._engine, path)
            return self._merge_prompt(handed, join=False)

        found: str | None = await self._locked(build)
        return found

    async def discard_copy(self, path: str, *, join: bool = False) -> None:
        """Back to two choices for ``path``."""
        await self._locked(lambda: round_answers.discard_copy(self._engine, path, join=join))

    def _merge_prompt(self, paths: tuple[str, ...], *, join: bool) -> str | None:
        d = self._engine.d
        stop = d.state.stop()
        pool: tuple[ConflictFile, ...] = (
            d.state.join_choices() if join else (stop.conflicts if stop else ())
        )
        by_path = {c.path: c for c in pool}
        files = [
            MergeFile(by_path[p], copy=d.scratch.where(p) or "")
            for p in paths
            if p in by_path and d.scratch is not None
        ]
        return conflict_merge_handoff(
            vault=str(self._vault_path()),
            machine=self._machine.label(),
            files=files,
            secret_files=sum(1 for c in pool if c.answer is None and is_secret_file(c.path)),
            joining=join,
        )


__all__ = ["MergeMixin"]
