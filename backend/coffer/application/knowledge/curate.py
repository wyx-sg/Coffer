"""The curation pass: one piece of new knowledge, folded into the documents.

A collection is one tree of documents a person and Coffer write together (spec knowledge
"Store each collection as one tree of Markdown files"). New knowledge arrives as
**material** in the collection's hidden inbox — an upload's extracted text, an agent's
``coffer__write`` — and this pass is what folds it into the documents, so the collection
grows by integration rather than by accumulating a file per arrival (see "Curate through
a fenced four-tool pass").

The same pass also comes back for a **document someone edited** outside it: the sweep
finds every document whose file changed since curation last stamped it (see "Run
curation on a sweep and on demand"), and hands it here so the edit is carried into the
rest of the collection — a correction made in one document reaching the others that say
the same thing, a new section that belongs in a document of its own moved there.

Four things shape this module:

* **One item per pass.** The context is bounded to that item, at most five candidate
  documents, and the catalogue of titles (see "Assemble a pass from a bounded context").
  A sweep with ten pending items runs ten small passes rather than one large one, so a
  bad pass is small and the next item is unaffected by it.
* **The catalogue is always in the prompt.** Candidate selection is literal and
  therefore crude; the catalogue is what lets a model conclude that none of the
  five is the right home and open a new document instead.
* **The item is settled last.** Material leaves the inbox, and an edited document
  is stamped, only after the loop completes. A pass that raises, or that the recursion
  limit cut off, leaves both as they were, so a later sweep retries rather than losing
  what one half-ran over (see "Settle an item only after its pass completes") — until
  the same item has been cut off three times running, when ``curate_settle`` gives up.
* **langgraph stays out.** The loop is reached only through the injected
  :class:`AgenticCurationPort` (import contract 9a), so this module — and the
  whole ``application.knowledge`` package — never imports langchain.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING, Any, Protocol

from coffer.application.engine_ports import ModelSelectorPort
from coffer.application.engine_timeout import TimeoutReader, resolve_timeout
from coffer.application.knowledge import candidates
from coffer.application.knowledge.curate_prompt import CURATION_SYSTEM, brief
from coffer.application.knowledge.curate_settle import (
    MAX_CONSECUTIVE_TRUNCATIONS,
    TruncationLedger,
    give_up,
    pending_items,
    promote_all,
    settle,
    shelve_oversized,
)
from coffer.application.knowledge.curate_tools import (
    Counters,
    CurationTool,
    build_tools,
    document_count,
)
from coffer.application.knowledge.recording import item_author, recording
from coffer.application.knowledge.service import KnowledgeService
from coffer.domain.audit import AuditEventType
from coffer.domain.knowledge.entry import Pending
from coffer.domain.knowledge.errors import UnsafeKnowledgePath
from coffer.domain.knowledge.history import OP_PASS, WRITER_CURATION, ChangeMeta
from coffer.domain.resource import Resource
from coffer.infrastructure.knowledge import catalogue, fs, inbox, paths
from coffer.infrastructure.knowledge.history import Transaction
from coffer.infrastructure.knowledge.inbox import inbox_path

if TYPE_CHECKING:
    from coffer.domain.provider.config import ResolvedConnection

logger = logging.getLogger(__name__)

#: How many model turns one pass may take. A pass is never urgent and it
#: rewrites a corpus, so the ceiling is deliberately low.
DEFAULT_CURATION_RECURSION_LIMIT = 24

#: How much of one item to hand the model. Material is what a person wrote or
#: uploaded, so it is bounded by what a person produces; past this the pass
#: keeps the item as it stands and reports that, rather than silently
#: truncating the material it was asked to keep.
MAX_SOURCE_CHARS = 120_000


class AgenticCurationPort(Protocol):
    """The agentic loop, seen as a knowledge-local protocol. A result carrying
    ``truncated: True`` means the recursion limit cut the loop off."""

    async def run(
        self,
        *,
        model: ResolvedConnection,
        tools: Sequence[CurationTool],
        system_prompt: str,
        user_prompt: str,
        secret_resolver: Callable[[str], str],
        recursion_limit: int,
        timeout: float | None = None,
    ) -> dict[str, Any]: ...


async def run_curation(
    service: KnowledgeService,
    collection_uid: str,
    *,
    item: Pending | None = None,
    actor: str = "system",
    agent: AgenticCurationPort,
    models: ModelSelectorPort,
    secret_resolver: Callable[[str], str],
    recursion_limit: int = DEFAULT_CURATION_RECURSION_LIMIT,
    read_timeout: TimeoutReader | None = None,
    truncations: TruncationLedger | None = None,
) -> dict[str, Any]:
    """Fold one pending item into the documents of one collection.

    The collection is named by its **uid**, resolved once here: a pass takes
    minutes, so it is aimed at what a rename cannot move. ``status`` is one of
    "Report every pass outcome as a status": ``no_model`` (the inbox promoted
    as it stands), ``up_to_date``, ``too_large`` (never shown to the model;
    ``promoted`` or ``stamped``), ``failed``, ``truncated`` (``gave_up`` on the
    :data:`MAX_CONSECUTIVE_TRUNCATIONS`-th cut-off in a row) or ``ok``. Only
    ``ok`` settles the item. ``collection`` in every outcome is the NAME — the
    dict is what a surface renders.
    """
    # Raises ResourceNotFound for an unknown uid — the answer the HTTP route
    # turns into a 404.
    row = await service.collection(collection_uid)
    collection = row.name
    # One commit for the whole pass, naming Coffer's curation and the item (see
    # "Keep every document's history and undo a pass as a whole"). Opening it
    # first commits any edit made on disk, so the pass's commit holds only the
    # pass — which is what lets it be undone as a whole.
    meta = ChangeMeta(
        WRITER_CURATION, OP_PASS, f"Curate {collection}", actor=actor, collection=collection
    )
    async with recording(service.history, meta) as tx:
        result = await _pass(
            service,
            row,
            collection_uid,
            tx=tx,
            item=item,
            actor=actor,
            agent=agent,
            models=models,
            secret_resolver=secret_resolver,
            recursion_limit=recursion_limit,
            read_timeout=read_timeout,
            truncations=truncations,
        )
        tx.meta = dataclasses.replace(tx.meta, status=str(result["status"]))
    return result


async def _pass(
    service: KnowledgeService,
    row: Resource,
    collection_uid: str,
    *,
    tx: Transaction,
    item: Pending | None,
    actor: str,
    agent: AgenticCurationPort,
    models: ModelSelectorPort,
    secret_resolver: Callable[[str], str],
    recursion_limit: int,
    read_timeout: TimeoutReader | None,
    truncations: TruncationLedger | None,
) -> dict[str, Any]:
    """The pass itself; every path it writes is touched on ``tx``."""
    collection = row.name
    model = await models.get_default()
    if model is None:
        for name in await asyncio.to_thread(inbox.inbox_items, collection):
            tx.touch(inbox_path(collection, name))
        promoted = await asyncio.to_thread(promote_all, collection)
        for path in promoted:
            tx.touch(path)
        tx.meta = dataclasses.replace(tx.meta, summary=f"Add {len(promoted)} items to {collection}")
        return {"status": "no_model", "collection": collection, "promoted": promoted}

    if item is None:
        pending = await asyncio.to_thread(pending_items, collection)
        if not pending:
            return {"status": "up_to_date", "collection": collection}
        item = pending[0]

    edited = item.document is not None
    if item.document is not None:
        # A caller-named document must be THIS collection's: the tools are
        # fenced to it, and the final stamp must land where the pass could reach.
        paths.require_document(item.document)
        if paths.collection_of(item.document) != collection:
            raise UnsafeKnowledgePath(item.document, f"not a document of {collection!r}")
        found = await asyncio.to_thread(fs.read_file, item.document)
    else:
        found = await asyncio.to_thread(inbox.read_material, collection, item.material or "")
    label = found.path
    tx.touch(label)
    tx.meta = dataclasses.replace(
        tx.meta,
        summary=f"Curate {found.title}",
        item=label,
        # Whose item this was: for material, the author its submission's
        # ``knowledge_written`` event names; an edited document is a person's.
        agent=await item_author(service, row, item.material, found.actor)
        if item.material
        else None,
    )
    if len(found.body) > MAX_SOURCE_CHARS:
        # No pass can hold it, so it leaves the queue as it stands rather than
        # being offered to — and refused by — every sweep for ever. Settled,
        # so its cut-off count goes with it.
        shelved = await asyncio.to_thread(shelve_oversized, collection, item)
        for path in shelved.get("promoted", []):
            tx.touch(path)
        if truncations is not None:
            truncations.clear(collection_uid, label)
        return {
            "status": "too_large",
            "collection": collection,
            "item": label,
            "limit": MAX_SOURCE_CHARS,
            **shelved,
        }

    chosen = await candidates.select(service, collection, found)
    candidate_bodies = [await asyncio.to_thread(fs.read_file, path) for path in chosen]
    every_document = await asyncio.to_thread(catalogue.walk_files, paths.collection_dir(collection))

    before = await asyncio.to_thread(document_count, collection)
    counters = Counters()
    tools = build_tools(
        service=service,
        collection=collection,
        actor=actor,
        counters=counters,
        on_touch=tx.touch,
        # The brief carries these in full, so the pass has seen their content.
        shown=[*chosen, *([item.document] if item.document is not None else [])],
    )
    try:
        run = await agent.run(
            model=model,
            tools=tools,
            # Rules in the system turn (identical every pass, what a provider
            # caches); the tens-of-kilobytes brief in the human turn.
            system_prompt=CURATION_SYSTEM,
            user_prompt=brief(
                collection,
                found,
                edited=edited,
                candidate_bodies=candidate_bodies,
                every_document=every_document,
            ),
            secret_resolver=secret_resolver,
            recursion_limit=recursion_limit,
            # Per TURN, not per pass: a bound wrapped around this one ``await``
            # could only stop the whole pass, and a wedged endpoint held it
            # until the daemon restarted.
            timeout=await resolve_timeout(read_timeout),
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        # The item stays as it was: a half-run pass is retried by the next sweep.
        logger.warning(
            "knowledge.curate.loop_failed",
            extra={"collection": collection, "item": label},
            exc_info=True,
        )
        return {"status": "failed", "collection": collection, "item": label}

    # Cut off by the recursion limit: what it wrote stays and the item stays
    # owed, until it has been cut off every time (see ``curate_settle``).
    truncated = bool(run.get("truncated"))
    strikes = truncations.record(collection_uid, label) if truncations and truncated else 0
    gave_up = strikes >= MAX_CONSECUTIVE_TRUNCATIONS
    promoted = await asyncio.to_thread(give_up, collection, item) if gave_up else []
    for path in promoted:
        tx.touch(path)
    if not truncated:
        await asyncio.to_thread(settle, collection, item)
    if truncations is not None and (gave_up or not truncated):
        truncations.clear(collection_uid, label)
    result = {
        "status": "truncated" if truncated else "ok",
        "collection": collection,
        "item": label,
        "model": model.model,
        "candidates": list(chosen),
        "documents_before": before,
        "documents_after": await asyncio.to_thread(document_count, collection),
        "written": counters.written,
        "retired": counters.retired,
        "refused": counters.refused,
        "gave_up": gave_up,
        "promoted": promoted,
    }
    # One event per pass that ran, cut off or not: with no review step, the
    # audit log is the only place a person sees something rewrote the corpus.
    with contextlib.suppress(Exception):
        await service._audit.record(
            AuditEventType.KNOWLEDGE_CURATED.value,
            resource=row,
            actor=actor,
            details={
                k: result[k]
                for k in (
                    "item",
                    "model",
                    "documents_before",
                    "documents_after",
                    "written",
                    "retired",
                    "status",
                    "gave_up",
                )
            },
        )
    return result


class CurationPass:
    """``run_curation`` with its ports bound — the callable surfaces register.

    The HTTP route and the background worker both hold one of these and call
    it as ``pass_(service, collection_uid, actor=...)``, so neither has to know
    that a model port exists.
    """

    def __init__(
        self,
        *,
        agent: AgenticCurationPort,
        models: ModelSelectorPort,
        secret_resolver: Callable[[str], str],
        recursion_limit: int = DEFAULT_CURATION_RECURSION_LIMIT,
        on_corpus_changed: Callable[[], Awaitable[None]] | None = None,
        read_timeout: TimeoutReader | None = None,
    ) -> None:
        self._read_timeout = read_timeout
        self._agent = agent
        self._models = models
        self._secret_resolver = secret_resolver
        self._recursion_limit = recursion_limit
        # Re-rendering every agent's skill is how a new document becomes reachable
        # (see "Deliver the guide as the shared-master link"), so it hangs off the
        # pass rather than a timer — the corpus changing is the event that matters.
        self._on_corpus_changed = on_corpus_changed
        # Shared by the page's button and the sweep, which both call this pass.
        self._truncations = TruncationLedger()

    async def __call__(
        self,
        service: KnowledgeService,
        collection_uid: str,
        *,
        item: Pending | None = None,
        actor: str = "system",
    ) -> dict[str, Any]:
        outcome = await run_curation(
            service,
            collection_uid,
            item=item,
            actor=actor,
            agent=self._agent,
            models=self._models,
            secret_resolver=self._secret_resolver,
            recursion_limit=self._recursion_limit,
            read_timeout=self._read_timeout,
            truncations=self._truncations,
        )
        # A cut-off pass changed the corpus only if it managed a write.
        wrote = outcome.get("written") or outcome.get("retired") or outcome.get("promoted")
        changed = outcome.get("status") == "ok" or bool(wrote)
        if self._on_corpus_changed is not None and changed:
            with contextlib.suppress(Exception):
                await self._on_corpus_changed()
        return outcome


__all__ = [
    "CURATION_SYSTEM",
    "DEFAULT_CURATION_RECURSION_LIMIT",
    "MAX_SOURCE_CHARS",
    "AgenticCurationPort",
    "CurationPass",
    "CurationTool",
    "ModelSelectorPort",
    "Pending",
    "pending_items",
    "run_curation",
]
