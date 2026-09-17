"""The curation pass: one source, folded into the topic documents.

A person writes into ``sources/``; this is what turns that material into the
``topics/`` lane an agent reads (spec knowledge FR-021). It replaces the tidy
pass, and the difference is not the mechanism but what is at stake: tidy
rewrote the only copy, so it shipped off by default and ran once. Curation
derives a second copy from material it may not touch, so it can run
unattended — and must, because it is now the only path from a source to
something an agent can read.

Four things shape this module:

* **One source per pass.** The context is bounded to that source, at most five
  candidate documents, and the catalogue of titles (FR-023). A sweep with ten
  pending sources runs ten small passes rather than one large one, so a bad
  pass is small and the next source is unaffected by it.
* **The catalogue is always in the prompt.** Candidate selection is literal and
  therefore crude; the catalogue is what lets a model conclude that none of the
  five is the right home and open a new document instead.
* **The watermark is written last.** A pass that raises leaves
  ``coffer_ingested_at`` unset, so the material is curated by a later sweep
  rather than lost to one that half-ran (FR-028).
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
    topic_count,
)
from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.domain.audit import AuditEventType
from coffer.domain.resource import ResourceRef
from coffer.infrastructure.knowledge import catalogue, fs, paths

if TYPE_CHECKING:
    from coffer.domain.provider.config import ResolvedConnection

logger = logging.getLogger(__name__)

#: How many model turns one pass may take. A pass is never urgent and it
#: rewrites a corpus, so the ceiling is deliberately low.
DEFAULT_CURATION_RECURSION_LIMIT = 24

#: How much of one source to hand the model. A source is what a person wrote
#: or uploaded, so it is bounded by what a person produces; past this the pass
#: reports rather than silently truncating the material it was asked to keep.
MAX_SOURCE_CHARS = 120_000

CURATION_SYSTEM = (
    "You maintain ONE collection of curated Markdown knowledge documents. You are given a "
    "single new or changed SOURCE — material a person contributed — and you fold it into the "
    "collection's topic documents.\n\n"
    "RULES, in order of importance:\n"
    "1. LOSE NOTHING. Every fact in the source must end up in a topic document, and every "
    "fact already in a document you rewrite must survive. Integrate; never regenerate.\n"
    "2. READ BEFORE YOU WRITE. Call read_topic on any document you intend to change.\n"
    "3. FIND THE RIGHT HOME. The candidate documents you were shown are a literal-match guess, "
    "not an answer. Call list_topics and read the titles and descriptions: if none of them owns "
    "this subject, create a new document rather than forcing the material somewhere it does not "
    "belong.\n"
    "4. WHEN THE SOURCE CONTRADICTS A DOCUMENT, THE SOURCE WINS — and say so in the prose. "
    "Keep the superseded statement legible with the date it changed, e.g. '(previously recorded "
    "as X; corrected YYYY-MM-DD from <what the source is>)'. Knowledge is about a world that "
    "changes, and when it changed is worth keeping.\n"
    "5. NEVER NAME ANOTHER FILE. Topic paths move as the corpus is reorganised. Name the "
    "subject in prose. A write that names one of this corpus's files is refused.\n"
    "6. ORGANISE BY SUBJECT, NEVER BY PROVENANCE. A reader wants the document to be about the "
    "thing; they do not care which note told you what. Never add sections like 'First read' or "
    "'From the new source' — fold the new material into the section it belongs in, and keep a "
    "correction as a sentence where the corrected fact is, not as a changelog at the bottom.\n"
    "7. Give every document a title and a one-line description saying what QUESTION it answers. "
    "The description is the only thing a future reader chooses by.\n"
    f"8. You may write at most {MAX_WRITES_PER_PASS} files in this pass. Change nothing that "
    "does not need changing, and stop when the source is absorbed."
)


class AgenticCurationPort(Protocol):
    """The agentic loop, seen as a knowledge-local protocol."""

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
    collection: str, source: Any, candidate_bodies: Sequence[Any], every_topic: Sequence[Any]
) -> str:
    """The one user turn: the source, the candidates, and every title."""
    lines = [f"The collection is {collection!r}.", "", "## Every topic document that exists"]
    if every_topic:
        lines += [f"- {e.path} — {e.title}: {e.description}" for e in every_topic]
    else:
        lines.append("(none yet — this collection has no topic documents)")
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
        lines.append("(no document mentions anything in this source)")
    lines += [
        "",
        "## The source to absorb",
        "",
        f"### {source.title}",
        f"_{source.description}_",
        "",
        source.body,
    ]
    return "\n".join(lines)


async def run_curation(
    service: KnowledgeService,
    collection: str,
    *,
    source_relpath: str | None = None,
    actor: str = "system",
    agent: AgenticCurationPort,
    models: ModelSelectorPort,
    credential_resolver: Callable[[str], str],
    recursion_limit: int = DEFAULT_CURATION_RECURSION_LIMIT,
    read_timeout: TimeoutReader | None = None,
) -> dict[str, Any]:
    """Fold one pending source into ``collection``'s topic documents.

    ``status`` is ``no_model`` with no internal connection configured,
    ``up_to_date`` when every source has already been curated, ``too_large``
    for a source past :data:`MAX_SOURCE_CHARS`, ``failed`` when the loop
    raised, and ``ok`` otherwise. Only ``ok`` writes the watermark.
    """
    # Raises CollectionNotFound for a name the caller may not see, which is
    # what the HTTP route turns into a 404.
    await service.require_visible(collection, None)

    model = await models.get_default()
    if model is None:
        return {"status": "no_model", "collection": collection}

    relpath = source_relpath
    if relpath is None:
        pending = await asyncio.to_thread(fs.pending_sources, collection)
        if not pending:
            return {"status": "up_to_date", "collection": collection}
        relpath = pending[0]

    source = await asyncio.to_thread(fs.read_file, relpath)
    if len(source.body) > MAX_SOURCE_CHARS:
        return {
            "status": "too_large",
            "collection": collection,
            "source": relpath,
            "limit": MAX_SOURCE_CHARS,
        }

    chosen = await candidates.select(service, collection, source)
    candidate_bodies = [await asyncio.to_thread(fs.read_file, path) for path in chosen]
    every_topic = await asyncio.to_thread(catalogue.walk_files, paths.topics_dir(collection))

    before = await asyncio.to_thread(topic_count, collection)
    counters = Counters()
    tools = build_tools(service=service, collection=collection, actor=actor, counters=counters)
    try:
        await agent.run(
            model=model,
            tools=tools,
            # The rules go in the system turn and the material in the human
            # turn: the first is identical on every pass and is what a provider
            # caches, the second is tens of kilobytes that differ every time.
            system_prompt=CURATION_SYSTEM,
            user_prompt=_brief(collection, source, candidate_bodies, every_topic),
            credential_resolver=credential_resolver,
            recursion_limit=recursion_limit,
            # Per TURN, not per pass. A curation pass is a conversation of up
            # to ``recursion_limit`` turns and is one ``await`` from here, so a
            # bound wrapped around this call could only stop the whole pass or
            # nothing — and before this it stopped neither, which left a wedged
            # endpoint holding the pass until the daemon restarted.
            timeout=await resolve_timeout(read_timeout),
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        # The watermark stays unset on purpose: a half-run pass must be retried
        # by the next sweep, not treated as having absorbed the material.
        logger.warning(
            "knowledge.curate.loop_failed",
            extra={"collection": collection, "source": relpath},
            exc_info=True,
        )
        return {"status": "failed", "collection": collection, "source": relpath}

    await asyncio.to_thread(fs.mark_ingested, relpath)
    result = {
        "status": "ok",
        "collection": collection,
        "source": relpath,
        "model": model.model,
        "candidates": list(chosen),
        "topics_before": before,
        "topics_after": await asyncio.to_thread(topic_count, collection),
        "written": counters.written,
        "retired": counters.retired,
        "refused": counters.refused,
    }
    # One event per pass, unconditionally: with no review step, the audit log
    # is the only place a person sees that something rewrote the corpus —
    # including a pass that decided to change nothing.
    with contextlib.suppress(Exception):
        await service._audit.record(
            AuditEventType.KNOWLEDGE_CURATED.value,
            ref=ResourceRef(KIND_KNOWLEDGE, collection),
            actor=actor,
            details={
                k: result[k]
                for k in ("source", "model", "topics_before", "topics_after", "written", "retired")
            },
        )
    return result


class CurationPass:
    """``run_curation`` with its ports bound — the callable surfaces register.

    The HTTP route and the background worker both hold one of these and call
    it as ``pass_(service, collection, actor=...)``, so neither has to know
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
        # Re-rendering every agent's skill is how a new document becomes
        # reachable at all (FR-035): until the catalogue is rewritten, the
        # agent has no path to it. So it hangs off the pass rather than off a
        # timer — the corpus changing is exactly the event that matters.
        self._on_corpus_changed = on_corpus_changed

    async def __call__(
        self,
        service: KnowledgeService,
        collection: str,
        *,
        source_relpath: str | None = None,
        actor: str = "system",
    ) -> dict[str, Any]:
        outcome = await run_curation(
            service,
            collection,
            source_relpath=source_relpath,
            actor=actor,
            agent=self._agent,
            models=self._models,
            credential_resolver=self._credential_resolver,
            recursion_limit=self._recursion_limit,
            read_timeout=self._read_timeout,
        )
        if self._on_corpus_changed is not None and outcome.get("status") == "ok":
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
    "run_curation",
]
