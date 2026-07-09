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
from typing import TYPE_CHECKING, Any

from coffer.application.memory.stores import store_name_for
from coffer.domain.errors import ScopeUnresolved
from coffer.domain.memory.scope import MemoryScope, ResolvedScope

if TYPE_CHECKING:
    from coffer.domain.memory.fact import MemoryFact
    from coffer.domain.memory.journal import JournalEntry

_logger = logging.getLogger(__name__)

ResolveStoreFn = Callable[[str], Awaitable[ResolvedScope]]
ResolveRecallScopesFn = Callable[[str | None], Awaitable[list[ResolvedScope]]]
OnChangeFn = Callable[[str], Awaitable[None]]

#: How much of the project store to surface in the session-start digest. It is
#: an INDEX, not the memory itself: knowledge is a title-only list and only a
#: few recent journal lines are shown, so the injection stays light — the agent
#: calls ``recall`` for any bodies it actually needs.
_DIGEST_FACTS = 25
_DIGEST_JOURNAL = 3
_DIGEST_HEADER = "## Project memory (via Coffer)"


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
    """Return the store's rules text — every ``rules/*.md`` file concatenated (so
    the autonomous split's per-topic files all reach session-start injection), or
    ``None`` if no rules exist yet."""
    from coffer.infrastructure.knowledge.paths import rules_dir
    from coffer.infrastructure.memory.rules_files import read_all_rules

    sd: Path = (await resolved_store(store_name)).store_dir
    return await asyncio.to_thread(read_all_rules, rules_dir(sd))


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


def _one_line(text: str | None, limit: int) -> str:
    """Collapse whitespace/newlines and hard-cap to ``limit`` chars for a digest
    bullet (so a multi-line fact body never breaks the markdown list)."""
    flat = " ".join((text or "").split())
    return flat[:limit]


def render_memory_digest(
    facts: list[MemoryFact], journal_entries: list[JournalEntry], *, max_chars: int
) -> str:
    """Render the SessionStart project-memory **index** (FR-055): a title-only
    list of known topics + a few recent journal lines — an orientation pointer,
    not the memory itself, so the agent knows what exists and calls ``recall``
    for detail. Pure. Returns ``""`` when there is nothing to surface or no
    budget remains (``max_chars <= 0``), and truncates to ``max_chars``."""
    if max_chars <= 0:
        return ""
    sections: list[str] = []
    if facts:
        lines = "\n".join(f"- {_one_line(f.title, 100)}" for f in facts)
        sections.append("### Known topics\n" + lines)
    if journal_entries:
        lines = "\n".join(
            f"- {e.timestamp.date().isoformat()}: {_one_line(e.body, 120)}" for e in journal_entries
        )
        sections.append("### Recent activity\n" + lines)
    if not sections:
        return ""
    intro = "Index of this project's stored memory; call `coffer__recall <query>` for any detail."
    body = "\n\n".join([_DIGEST_HEADER, intro, *sections])
    return body[:max_chars]


async def assemble_memory_digest(
    *, cwd: str | None, memory: Any, journal: Any, max_chars: int
) -> str:
    """Fetch and render the project-memory digest for ``cwd`` (FR-055). Never
    raises — a failure yields ``""`` so the session-start hook is never blocked.

    ``memory`` / ``journal`` are the MemoryService / JournalService (duck-typed
    to avoid an import cycle through this module, which the service imports)."""
    if cwd is None or max_chars <= 0:
        return ""
    try:
        resolved = await memory.resolve_scope(scope=MemoryScope.PROJECT, cwd=cwd)
    except ScopeUnresolved:
        return ""  # not inside a git project → no project digest
    except Exception:
        _logger.debug("memory_digest.resolve.failed", exc_info=True)
        return ""
    try:
        facts, _total = await memory.list_facts(
            store_name=store_name_for(resolved), limit=_DIGEST_FACTS
        )
        entries = await journal.read_recent(cwd=cwd, limit=_DIGEST_JOURNAL)
    except Exception:
        _logger.debug("memory_digest.fetch.failed", exc_info=True)
        return ""
    return render_memory_digest(facts, entries, max_chars=max_chars)
