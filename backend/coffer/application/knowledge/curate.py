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
  what one half-ran over (see "Settle an item only after its pass completes").
* **langgraph stays out.** The loop is reached only through the injected
  :class:`AgenticCurationPort` (import contract 9a), so this module — and the
  whole ``application.knowledge`` package — never imports langchain.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING, Any, Protocol

from coffer.application.engine_ports import ModelSelectorPort
from coffer.application.engine_timeout import TimeoutReader, resolve_timeout
from coffer.application.knowledge import candidates
from coffer.application.knowledge.curate_tools import (
    MAX_WRITES_PER_PASS,
    Counters,
    CurationTool,
    build_tools,
    document_count,
)
from coffer.application.knowledge.service import KnowledgeService
from coffer.domain.audit import AuditEventType
from coffer.domain.knowledge.entry import Pending
from coffer.domain.knowledge.errors import KnowledgeFileNotFound, UnsafeKnowledgePath
from coffer.infrastructure.knowledge import catalogue, fs, paths

if TYPE_CHECKING:
    from coffer.domain.provider.config import ResolvedConnection

logger = logging.getLogger(__name__)

#: How many model turns one pass may take. A pass is never urgent and it
#: rewrites a corpus, so the ceiling is deliberately low.
DEFAULT_CURATION_RECURSION_LIMIT = 24

#: How much of one item to hand the model. Material is what a person wrote or
#: uploaded, so it is bounded by what a person produces; past this the pass
#: reports rather than silently truncating the material it was asked to keep.
MAX_SOURCE_CHARS = 120_000

CURATION_SYSTEM = (
    "You maintain ONE collection of Markdown knowledge documents that a person and you write "
    "together. You are given ONE item: either NEW MATERIAL to fold into the documents, or a "
    "DOCUMENT A PERSON EDITED, whose edit you carry into the rest of the collection.\n\n"
    "RULES, in order of importance:\n"
    "1. LOSE NOTHING. Every fact in new material must end up in a document, and every fact "
    "already in a document you rewrite must survive. Integrate; never regenerate.\n"
    "2. A PERSON'S EDIT IS DELIBERATE. When the item is an edited document, what the person "
    "wrote there is the truth: never revert it or reword it. Carry it outward — correct the "
    "other documents that say otherwise, and move a section that belongs in another document "
    "there — and leave the edited document alone unless it now duplicates another.\n"
    "3. READ BEFORE YOU WRITE. Call read_document on any document you intend to change.\n"
    "4. FIND THE RIGHT HOME. The candidate documents you were shown are a literal-match guess, "
    "not an answer. Call list_documents and read the titles and descriptions: if none of them "
    "owns this subject, create a new document rather than forcing the material somewhere it "
    "does not belong.\n"
    "5. WHEN NEW MATERIAL CONTRADICTS A DOCUMENT, THE NEWER STATEMENT WINS — and say so in the "
    "prose. Keep the superseded statement legible with the date it changed, e.g. '(previously "
    "recorded as X; corrected YYYY-MM-DD)'. Knowledge is about a world that changes, and when "
    "it changed is worth keeping.\n"
    "6. NEVER NAME ANOTHER FILE. Document paths move as the collection is reorganised. Name the "
    "subject in prose. A write that names one of this collection's files is refused.\n"
    "7. ORGANISE BY SUBJECT, NEVER BY PROVENANCE. A reader wants the document to be about the "
    "thing; they do not care which upload told you what. Never add sections like 'From the new "
    "material' — fold it into the section it belongs in, and keep a correction as a sentence "
    "where the corrected fact is, not as a changelog at the bottom.\n"
    "8. Give every document a title and a one-line description saying what QUESTION it answers. "
    "The description is the only thing a future reader chooses by.\n"
    f"9. You may write at most {MAX_WRITES_PER_PASS} files in this pass. Change nothing that "
    "does not need changing, and stop when the item is absorbed."
)


def pending_items(collection: str) -> tuple[Pending, ...]:
    """What a sweep owes one collection: material first, then edits.

    New material first, because until it is merged it is knowledge no agent
    can read; an edited document is already readable as it stands.
    """
    return tuple(Pending(material=name) for name in fs.inbox_items(collection)) + tuple(
        Pending(document=relpath) for relpath in fs.edited_documents(collection)
    )


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
        credential_resolver: Callable[[str], str],
        recursion_limit: int,
        timeout: float | None = None,
    ) -> dict[str, Any]: ...


def _brief(
    collection: str,
    item: Any,
    *,
    edited: bool,
    candidate_bodies: Sequence[Any],
    every_document: Sequence[Any],
) -> str:
    """The one user turn: the item, the candidates, and every title."""
    lines = [f"The collection is {collection!r}.", "", "## Every document that exists"]
    if every_document:
        lines += [f"- {e.path} — {e.title}: {e.description}" for e in every_document]
    else:
        lines.append("(none yet — this collection has no documents)")
    lines += ["", "## Candidate documents, in full"]
    if candidate_bodies:
        for found in candidate_bodies:
            lines += [
                "",
                f"### {found.path} — {found.title}",
                f"_{found.description}_",
                "",
                found.body,
            ]
    else:
        lines.append("(no other document mentions anything in this item)")
    if edited:
        lines += ["", f"## The document a person edited: {item.path}"]
    else:
        lines += ["", "## The new material to absorb"]
    lines += ["", f"### {item.title}", f"_{item.description}_", "", item.body]
    return "\n".join(lines)


def _promote_all(collection: str) -> list[str]:
    """Every inbox item made a document as it stands — the no-model path."""
    return [fs.promote(collection, name).path for name in fs.inbox_items(collection)]


async def run_curation(
    service: KnowledgeService,
    collection_uid: str,
    *,
    item: Pending | None = None,
    actor: str = "system",
    agent: AgenticCurationPort,
    models: ModelSelectorPort,
    credential_resolver: Callable[[str], str],
    recursion_limit: int = DEFAULT_CURATION_RECURSION_LIMIT,
    read_timeout: TimeoutReader | None = None,
) -> dict[str, Any]:
    """Fold one pending item into the documents of one collection.

    The collection is named by its **uid**, resolved once here. A pass takes
    minutes and rewrites a corpus, so the thing it is aimed at has to be the
    thing that cannot change underneath it: the label is read off the row and
    used to build paths, and the row itself is what the audit event is tied to.

    ``status`` is ``no_model`` with no internal connection configured — and then every
    inbox item is promoted to a document as it stands, so material never waits on a
    connection nobody configured (see "Promote material directly when no model is
    configured") — ``up_to_date`` when nothing is pending, ``too_large`` for an item
    past :data:`MAX_SOURCE_CHARS`, ``failed`` when the loop raised, ``truncated``
    when the recursion limit cut it off (reported with the same counters as
    ``ok`` — see "Bound a pass to eight writes"), and ``ok`` otherwise. Only
    ``ok`` settles the item.

    Every outcome carries ``collection`` as the collection's NAME, because the
    dict is what a surface renders and a person reads a pass's report by the
    name they gave the collection, not by its identity.
    """
    # Raises ResourceNotFound for an unknown uid and CollectionNotFound for a
    # disabled row — the two answers the HTTP route turns into a 404.
    row = await service.collection(collection_uid)
    collection = row.name

    model = await models.get_default()
    if model is None:
        promoted = await asyncio.to_thread(_promote_all, collection)
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
        found = await asyncio.to_thread(fs.read_material, collection, item.material or "")
    label = found.path
    if len(found.body) > MAX_SOURCE_CHARS:
        return {
            "status": "too_large",
            "collection": collection,
            "item": label,
            "limit": MAX_SOURCE_CHARS,
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
            user_prompt=_brief(
                collection,
                found,
                edited=edited,
                candidate_bodies=candidate_bodies,
                every_document=every_document,
            ),
            credential_resolver=credential_resolver,
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

    # Cut off by the recursion limit: what it wrote stays, the item stays owed.
    truncated = bool(run.get("truncated"))
    if not truncated:
        await asyncio.to_thread(_settle, collection, item)
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
                )
            },
        )
    return result


def _settle(collection: str, item: Pending) -> None:
    """Mark the item absorbed: material leaves the inbox, a document is
    stamped — unless the pass retired it, in which case there is nothing left
    to stamp."""
    if item.material is not None:
        fs.discard_material(collection, item.material)
        return
    with contextlib.suppress(KnowledgeFileNotFound):
        fs.mark_curated(item.document or "")


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
        credential_resolver: Callable[[str], str],
        recursion_limit: int = DEFAULT_CURATION_RECURSION_LIMIT,
        on_corpus_changed: Callable[[], Awaitable[None]] | None = None,
        read_timeout: TimeoutReader | None = None,
    ) -> None:
        self._read_timeout = read_timeout
        self._agent = agent
        self._models = models
        self._credential_resolver = credential_resolver
        self._recursion_limit = recursion_limit
        # Re-rendering every agent's skill is how a new document becomes reachable
        # (see "Deliver the guide as the shared-master link"), so it hangs off the
        # pass rather than a timer — the corpus changing is the event that matters.
        self._on_corpus_changed = on_corpus_changed

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
            credential_resolver=self._credential_resolver,
            recursion_limit=self._recursion_limit,
            read_timeout=self._read_timeout,
        )
        changed = outcome.get("status") in {"ok", "truncated"} or bool(outcome.get("promoted"))
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
