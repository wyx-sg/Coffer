"""Joining the two halves of Coffer's own skill.

The text is rendered by the knowledge layer (it carries the catalogue) and
written by the skill layer (it owns the master store and the resource row), and
those two kinds may not import each other — import-linter's cross-kind fences
are explicit about it. A composition root is the one place allowed to bridge
them, so the join lives here and nowhere else, exactly as the agent-skill-dir
resolver does.

That is also why this is a class rather than two calls at the call sites: the
refresh happens at boot AND after every curation pass, and a second call site
reconstructing the same pairing is how the two ends drift apart.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from coffer.application.skill.builtin_seed import BuiltinSkillSeed

_log = logging.getLogger(__name__)

#: Renders the current `SKILL.md` text. Async because the catalogue is a read.
GuideRenderer = Callable[[], Awaitable[str]]


class BuiltinGuide:
    """Coffer's generated skill, kept level with what it describes."""

    def __init__(self, *, name: str, render: GuideRenderer, seed: BuiltinSkillSeed) -> None:
        self._name = name
        self._render = render
        self._seed = seed
        # Three independent triggers can call refresh at once: the boot hook,
        # the curation worker's interval tick, and an HTTP request that created,
        # deleted or switched a collection. ``MasterStore.atomic_replace`` moves
        # the folder aside before swapping the new one in, so two overlapping
        # writes leave the second raising on a folder that is briefly not there
        # — recoverable, since the next trigger retries, but it logs a warning
        # about nothing and opens a window in which drift verification sees a
        # missing master. Serialising costs nothing: the common refresh renders,
        # compares and returns.
        self._lock = asyncio.Lock()

    async def refresh(self) -> bool:
        """Re-render and re-seed; return whether anything changed.

        Never raises. A corpus that cannot be read, or a master folder that
        cannot be written, leaves the previous copy exactly where it was —
        which is the honest outcome, because a half-rendered manual is worse
        than yesterday's. Nothing here may fail a boot or a curation pass.
        """
        async with self._lock:
            try:
                text = await self._render()
            except Exception:
                _log.warning("skill.builtin_guide.render_failed", exc_info=True)
                return False
            return await self._seed.seed(name=self._name, text=text)


async def run_builtin_guide_refresh(guide: BuiltinGuide) -> None:
    """Boot hook, mirroring ``run_skill_drift_boot_heal``.

    Runs after the drift heal, so a link this seed creates is not one the heal
    then has to reason about, and before the background workers, so the row is
    in place by the time the first converge round looks at it.
    """
    if await guide.refresh():
        _log.info("skill.builtin_guide.updated")
