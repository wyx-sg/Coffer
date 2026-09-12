"""The tidy pass: a bounded agentic rewrite of one collection's files.

A collection accumulates the way notes do — the same fact written twice from
two sessions, one file that grew until it covers four subjects. Nothing about
that is wrong at write time, which is why ``coffer__write`` stays dumb: an
agent should never have to think about filing. The tidying is deferred to
here, where a model can read what is already on disk and merge or split it.

Three things shape this module (ADR knowledge-is-plain-files):

* **There is no index.** Nothing is reconciled before or after the pass; a
  file moves and the next ``grep`` sees it. The old pass bracketed itself with
  two reindex calls, and both are gone rather than kept as no-ops.
* **``.history/`` is the entire safety net.** The pass rewrites a jointly
  managed artifact with no review step (spec knowledge FR-050), so every tool
  that can overwrite or retire a file calls :func:`fs.archive` first. That is
  the one invariant in here worth defending.
* **langgraph stays out.** The loop is reached only through the injected
  :class:`AgenticTidyPort` (import contract 9a), so this module — and the
  whole ``application.knowledge`` package — never imports langchain.

``no_model`` and ``empty`` are clean no-ops rather than errors: an
installation with no internal model connection configured simply never tidies.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable, Sequence
from typing import Any, Protocol

from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.application.knowledge.tidy_tools import (
    Counters,
    TidyTool,
    build_tools,
    file_count,
)
from coffer.domain.audit import AuditEventType
from coffer.domain.provider.config import ResolvedConnection
from coffer.domain.resource import ResourceRef

logger = logging.getLogger(__name__)

#: How many model turns one pass may take. A tidy is never urgent and a
#: runaway loop rewrites a human's files, so the ceiling is deliberately low.
DEFAULT_TIDY_RECURSION_LIMIT = 24

TIDY_SYSTEM = (
    "You keep ONE collection of Markdown knowledge files coherent. Work only "
    "inside the collection you are given.\n"
    "FIRST call list_files to see what is there, then read_file on anything "
    "you may change — never rewrite a file you have not read.\n"
    "Merge duplicates: write the combined content into ONE file with "
    "write_file, preserving ALL existing information and any human edits, then "
    "delete_file the file whose content now lives elsewhere. Split a file that "
    "covers several unrelated subjects into focused files. Give every file a "
    "title and a one-line description that says what question it answers — "
    "that description is the only thing a future reader has to choose by.\n"
    "NEVER regenerate a file from scratch; integrate. Prefer minimal, careful "
    "edits, and change nothing when the collection is already coherent. Every "
    "prior revision is archived automatically, but that is a safety net, not "
    "a licence. When there is nothing left to do, stop."
)


class AgenticTidyPort(Protocol):
    """The agentic loop, seen as a knowledge-local protocol."""

    async def run(
        self,
        *,
        model: ResolvedConnection,
        tools: Sequence[TidyTool],
        system_prompt: str,
        credential_resolver: Callable[[str], str],
        recursion_limit: int,
    ) -> dict[str, Any]: ...


class ModelSelectorPort(Protocol):
    """Resolves Coffer's internal-engine connection (the internal-default one)."""

    async def get_default(self) -> ResolvedConnection | None: ...


async def run_tidy(
    service: KnowledgeService,
    collection: str,
    *,
    actor: str = "system",
    agent: AgenticTidyPort,
    models: ModelSelectorPort,
    credential_resolver: Callable[[str], str],
    recursion_limit: int = DEFAULT_TIDY_RECURSION_LIMIT,
) -> dict[str, Any]:
    """Tidy one collection, returning what the pass did.

    ``status`` is ``no_model`` when no internal connection is configured,
    ``empty`` when the collection holds no files, and ``ok`` otherwise. The
    first two are clean no-ops, not errors — the caller (a route, the CLI, the
    background worker) treats all three the same way.
    """
    # Raises CollectionNotFound for a name the caller may not see, which is
    # what the HTTP route turns into a 404.
    await service.require_visible(collection, None)

    model = await models.get_default()
    if model is None:
        return {"status": "no_model", "collection": collection}

    before = await asyncio.to_thread(file_count, collection)
    if not before:
        return {"status": "empty", "collection": collection, "model": model.model}

    counters = Counters()
    tools = build_tools(service=service, collection=collection, actor=actor, counters=counters)
    try:
        await agent.run(
            model=model,
            tools=tools,
            system_prompt=f"{TIDY_SYSTEM}\n\nThe collection is {collection!r}.",
            credential_resolver=credential_resolver,
            recursion_limit=recursion_limit,
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        # A half-finished loop still moved files. Report from what is on disk
        # rather than raising: the pass is best-effort, and whatever armed it
        # must not be handed an exception for a partial tidy.
        logger.warning(
            "knowledge.tidy.loop_failed; reporting from on-disk state",
            extra={"collection": collection},
            exc_info=True,
        )

    result = {
        "status": "ok",
        "collection": collection,
        "model": model.model,
        "files_before": before,
        "files_after": await asyncio.to_thread(file_count, collection),
        "rewritten": counters.rewritten,
        "merged": counters.merged,
        "archived": counters.archived,
    }
    # One event per pass, unconditionally: with no review step and no index,
    # the audit log is the only place a human can see that something rewrote
    # their files — including a pass that decided to change nothing.
    with contextlib.suppress(Exception):
        await service._audit.record(
            AuditEventType.KNOWLEDGE_TIDIED.value,
            ref=ResourceRef(KIND_KNOWLEDGE, collection),
            actor=actor,
            details={
                k: result[k]
                for k in ("model", "files_before", "files_after", "rewritten", "merged")
            },
        )
    return result


class TidyPass:
    """``run_tidy`` with its ports bound — the callable the surfaces register.

    The HTTP route and the background worker both hold one of these and call
    it as ``pass_(service, collection, actor=...)``, so neither has to know
    that a model port exists.
    """

    def __init__(
        self,
        *,
        agent: AgenticTidyPort,
        models: ModelSelectorPort,
        credential_resolver: Callable[[str], str],
        recursion_limit: int = DEFAULT_TIDY_RECURSION_LIMIT,
    ) -> None:
        self._agent = agent
        self._models = models
        self._credential_resolver = credential_resolver
        self._recursion_limit = recursion_limit

    async def __call__(
        self,
        service: KnowledgeService,
        collection: str,
        *,
        actor: str = "system",
    ) -> dict[str, Any]:
        return await run_tidy(
            service,
            collection,
            actor=actor,
            agent=self._agent,
            models=self._models,
            credential_resolver=self._credential_resolver,
            recursion_limit=self._recursion_limit,
        )


__all__ = [
    "DEFAULT_TIDY_RECURSION_LIMIT",
    "TIDY_SYSTEM",
    "AgenticTidyPort",
    "ModelSelectorPort",
    "TidyPass",
    "TidyTool",
    "run_tidy",
]
