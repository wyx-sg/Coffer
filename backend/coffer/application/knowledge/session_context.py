"""Rules-lane helpers for ``KnowledgeService`` (spec 007).

Split out of :mod:`coffer.application.knowledge.service` for the file-size
budget. These are thin free functions the service's ``get_rules`` method
delegates to; the service's public API is unchanged.

The rules lane once had a second job: assembling a SessionStart bundle for the
shell hook Coffer installed into each agent. That delivery channel is gone
(spec 004 FR-043…FR-048 removed), so what remains here is the read side — the
lane's content is still written by ``organize`` and still readable through
``coffer knowledge rules``; nothing pushes it into an agent session any more.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from coffer.domain.knowledge.scope import ResolvedScope

_logger = logging.getLogger(__name__)

ResolveStoreFn = Callable[[str], Awaitable[ResolvedScope]]
OnChangeFn = Callable[[str], Awaitable[None]]


async def notify_change(on_change: OnChangeFn | None, scope_name: str) -> None:
    """Run the post-write change hook; a hook failure must never surface."""
    if on_change is None:
        return
    try:
        await on_change(scope_name)
    except Exception:
        # The write succeeded; a post-write hook failure must not surface.
        _logger.warning(
            "memory.on_change.hook_failed",
            extra={"store": scope_name},
            exc_info=True,
        )


async def get_rules(*, scope_name: str, resolved_scope: ResolveStoreFn) -> str | None:
    """Return the store's rules text — every ``rules/*.md`` file concatenated (so
    the autonomous split's per-topic files are all included), or
    ``None`` if no rules exist yet."""
    from coffer.infrastructure.knowledge.paths import rules_dir
    from coffer.infrastructure.knowledge_scope.rules_files import read_all_rules

    sd: Path = (await resolved_scope(scope_name)).store_dir
    return await asyncio.to_thread(read_all_rules, rules_dir(sd))
