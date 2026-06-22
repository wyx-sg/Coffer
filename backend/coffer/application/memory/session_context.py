"""Rules / SessionStart-context helpers for ``MemoryService`` (spec 007 Slice 6).

Split out of :mod:`coffer.application.memory.service` for the file-size budget.
These are thin free functions the service's ``get_rules`` /
``assemble_session_context`` methods delegate to; the service's public API is
unchanged.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from coffer.application.memory.stores import store_name_for
from coffer.domain.memory.scope import ResolvedScope

_logger = logging.getLogger(__name__)

ResolveStoreFn = Callable[[str], Awaitable[ResolvedScope]]
ResolveRecallScopesFn = Callable[[str | None], Awaitable[list[ResolvedScope]]]
OnChangeFn = Callable[[str], Awaitable[None]]


async def notify_change(on_change: OnChangeFn | None, store_name: str) -> None:
    """Run the post-write change hook; a hook failure must never surface."""
    if on_change is None:
        return
    try:
        await on_change(store_name)
    except Exception:
        # The write succeeded; a post-write hook failure must not surface.
        _logger.warning(
            "memory.on_change.hook_failed",
            extra={"store": store_name},
            exc_info=True,
        )


async def get_rules(*, store_name: str, resolved_store: ResolveStoreFn) -> str | None:
    """Return the rules/rules.md text, or ``None`` if no rules exist yet."""
    from coffer.infrastructure.knowledge.paths import rules_path
    from coffer.infrastructure.memory.rules_files import read_rules

    sd: Path = (await resolved_store(store_name)).store_dir
    return await asyncio.to_thread(read_rules, rules_path(sd))


async def assemble_session_context(
    *,
    cwd: str | None,
    resolve_recall_scopes: ResolveRecallScopesFn,
    get_rules_for: Callable[[str], Awaitable[str | None]],
) -> str:
    """SessionStart rules bundle for an agent at ``cwd`` (Slice 6 FR-049/050).

    Resolves the recall scopes (project + global), concatenates each store's
    rules, and appends the two seeded built-in rules. Never raises — the hook
    must never block the agent. ``get_rules_for`` resolves its own store
    (re-validating), so a missing project store degrades to global + seeded.
    """
    from coffer.application.memory.rules_bundle import RulesBundleAssembler

    async def _get_rules(store_name: str) -> str | None:
        try:
            return await get_rules_for(store_name)
        except Exception:
            return None

    assembler = RulesBundleAssembler(
        resolve_recall_scopes=resolve_recall_scopes,
        get_rules=_get_rules,
        store_name_for=store_name_for,
    )
    return await assembler.assemble_session_context(cwd=cwd)
