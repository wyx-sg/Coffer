"""The lifespan's first decision: open the vault, or wait for git (spec daemon
"Wait in a setup state when git is missing or too old").

Wraps the composition root's lifespan. Before anything else it looks for a
usable git (:func:`~coffer.infrastructure.vault.git_requirement.check_git`, the
daemon's ``PATH`` then the login shell's). With one, the full lifespan runs as
it always has — on the login shell's git, put first on ``PATH``, when that is
where it was found. Without one, nothing of the composition runs: no
migrations, no vault, no kinds, no workers. The daemon publishes its token and
port so the page and the CLI can talk to it, enters the setup state
(:mod:`coffer.surfaces.http.setup_state`) and serves until it is restarted.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI

from coffer.infrastructure.vault import git_requirement
from coffer.surfaces.http.daemon_identity import publish_daemon_identity
from coffer.surfaces.http.setup_state import enter_setup

_log = logging.getLogger(__name__)

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def guarded(lifespan: Lifespan) -> Lifespan:
    """``lifespan``, run only once git is there; the setup state otherwise."""

    @asynccontextmanager
    async def _guarded(app: FastAPI) -> AsyncIterator[None]:
        check = await asyncio.to_thread(git_requirement.check_git)
        if not check.ok:
            setup = enter_setup(check)
            publish_daemon_identity()
            _log.warning(
                "daemon.waiting_for_git",
                extra={"reason": setup.reason, "found": setup.found, "needed": setup.needed},
            )
            yield
            return
        git_requirement.use_git_dir(check)
        async with lifespan(app):
            yield

    return _guarded


__all__ = ["guarded"]
