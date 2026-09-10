"""The tidy pass: a bounded agentic loop that keeps ``notes/`` coherent.

A scope's notes accumulate the way notes do — the same thing written twice from
two sessions, one note that grew until it covers four subjects. Nothing about
that is wrong at write time, which is why the write path stays dumb: an agent
should never have to think about filing. The tidying is deferred to here, where
an LLM can read what is already on disk and merge or split it.

The loop reaches langgraph ONLY through the injected ``AgenticReorgPort``, so
the knowledge kind never imports ``infrastructure.llm`` (the layered import
contract). Four tools — list, read, write, delete — over one lane; there is no
tombstone verb, because ``note_files`` archives every replaced revision into
``.history/`` on its own. The loop cannot lose text even if it decides to.

:meth:`ReorgService.reorg` is the whole surface: the periodic trigger, the REST
route and the CLI all call exactly that, and ``no_model`` / ``empty`` are clean
no-ops rather than errors — a vault with no internal engine configured simply
never tidies.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from coffer.application.audit_service import AuditService
from coffer.application.knowledge.ports import KnowledgeDocumentRepo
from coffer.application.knowledge.reorg_ports import AgenticReorgPort, ModelSelectorPort, ReorgTool
from coffer.application.knowledge.retrieval import (
    EmbeddingResolver,
    KnowledgeRetrieval,
    no_embedding,
)
from coffer.application.knowledge.sync import KnowledgeReconciler
from coffer.domain.audit import AuditEventType
from coffer.domain.knowledge.document import KIND_KNOWLEDGE
from coffer.domain.knowledge.retrieval import StoreRef
from coffer.domain.knowledge.scope import ResolvedScope
from coffer.domain.knowledge.scope_config import KnowledgeConfig
from coffer.domain.resource import ResourceRef
from coffer.infrastructure.knowledge_scope.note_files import (
    delete_note,
    list_notes,
    read_note,
    write_note,
)

logger = logging.getLogger(__name__)

REORG_SYSTEM = (
    "You keep a small set of coherent notes tidy. FIRST call list_notes to see "
    "what exists, then read_note for any note you may change. Consolidate "
    "duplicates: write the merged content (preserving ALL existing info + human "
    "edits — never drop content) into ONE note, then delete the now-redundant "
    "duplicate. Split an over-long note into focused notes. NEVER regenerate "
    "from scratch; integrate. The system archives every prior version "
    "automatically, but still prefer minimal, careful edits. When done, stop."
)

#: ``scope_name -> ResolvedScope`` (validates the store exists).
ResolveStoreFn = Callable[[str], Awaitable[ResolvedScope]]
#: ``scope_name -> KnowledgeConfig``.
ConfigFn = Callable[[str], Awaitable[KnowledgeConfig]]
#: ``scope_name, project_id -> StoreRef``.
StoreRefFn = Callable[[str, str], StoreRef]
#: ``() -> datetime`` (injectable clock).
NowFn = Callable[[], datetime]

DEFAULT_REORG_RECURSION_LIMIT = 24


@dataclass(frozen=True)
class ReorgResult:
    """The outcome of one tidy pass."""

    status: str  # "reorganized" | "no_model" | "empty"
    notes_before: int
    notes_after: int
    notes_written: int  # create + overwrite
    notes_archived: int  # notes retired into .history/
    model: str | None  # display name of the internal model used


class _Actions:
    """Mutable accumulator for tool call counts."""

    def __init__(self) -> None:
        self.written: int = 0
        self.archived: int = 0


class ReorgService:
    """Runs the tidy pass over one scope's ``notes/`` lane."""

    def __init__(
        self,
        *,
        resolve_store: ResolveStoreFn,
        get_config: ConfigFn,
        store_ref: StoreRefFn,
        documents: KnowledgeDocumentRepo,
        retrieval: KnowledgeRetrieval,
        reconciler: KnowledgeReconciler,
        agent: AgenticReorgPort,
        models: ModelSelectorPort,
        audit: AuditService,
        credential_resolver: Callable[[str], str],
        now: NowFn,
        embedding_resolver: EmbeddingResolver = no_embedding,
    ) -> None:
        self._resolve_store = resolve_store
        self._get_config = get_config
        self._store_ref = store_ref
        self._documents = documents
        self._retrieval = retrieval
        self._reconciler = reconciler
        self._agent = agent
        self._models = models
        self._audit = audit
        self._credential_resolver = credential_resolver
        self._now = now
        self._resolve_embedding = embedding_resolver

    async def reorg(self, *, scope_name: str) -> ReorgResult:
        """Tidy one scope's notes.

        Validates the store (404s an unknown name via ``resolve_store``). A
        ``no_model`` / ``empty`` outcome is a clean no-op, not an error."""
        resolved = await self._resolve_store(scope_name)
        store_dir = resolved.store_dir
        ref = self._store_ref(scope_name, resolved.project_id)

        model = await self._models.get_default()
        if model is None:
            return ReorgResult("no_model", 0, 0, 0, 0, None)

        config = await self._get_config(scope_name)
        embedding = await self._resolve_embedding() if config.vector_enabled else None
        await self._reconciler.reconcile(store=ref, embedding=embedding)

        before = await asyncio.to_thread(list_notes, store_dir)
        # Nothing to keep coherent → a clean no-op.
        if not before:
            return ReorgResult("empty", 0, 0, 0, 0, model.model)

        acts = _Actions()
        tools = self._build_tools(store_dir=store_dir, acts=acts)

        try:
            await self._agent.run(
                model=model,
                tools=tools,
                system_prompt=REORG_SYSTEM,
                credential_resolver=self._credential_resolver,
                recursion_limit=DEFAULT_REORG_RECURSION_LIMIT,
            )
        except Exception:
            # A half-finished loop still moved files. Finalize from what is on
            # disk rather than raising: the pass is best-effort, and the trigger
            # that armed it must not be handed an exception for a partial tidy.
            logger.warning(
                "knowledge.tidy.agent_loop_failed; finalizing from on-disk state",
                exc_info=True,
            )

        after = await asyncio.to_thread(list_notes, store_dir)
        await self._reconciler.reconcile(store=ref, embedding=embedding)
        result = ReorgResult(
            "reorganized",
            len(before),
            len(after),
            acts.written,
            acts.archived,
            model.model,
        )
        await self._audit_pass(scope_name, result)
        return result

    async def _audit_pass(self, scope_name: str, result: ReorgResult) -> None:
        """Record a pass that actually rewrote something.

        The audit log records changes someone or something made, not that a
        timer fired — and this pass revisits every scope on an interval, so
        auditing every run would bury the changes it is supposed to make
        legible. A pass that wrote and deleted nothing left the notes exactly
        as it found them, and has nothing to report."""
        if not result.notes_written and not result.notes_archived:
            return
        await self._audit.record(
            AuditEventType.KNOWLEDGE_TIDIED.value,
            ref=ResourceRef(KIND_KNOWLEDGE, scope_name),
            actor="system",
            details={
                "notes_before": result.notes_before,
                "notes_after": result.notes_after,
                "notes_written": result.notes_written,
                "notes_archived": result.notes_archived,
                "model": result.model,
            },
        )

    def _build_tools(self, *, store_dir: Path, acts: _Actions) -> list[ReorgTool]:
        now = self._now

        async def _list_notes(args: dict) -> dict:  # type: ignore[type-arg]
            docs = await asyncio.to_thread(list_notes, store_dir)
            return {
                "notes": [
                    {
                        "slug": d.slug,
                        "title": d.title,
                        "summary": d.summary,
                        "length": len(d.body),
                    }
                    for d in docs
                ]
            }

        async def _read_note(args: dict) -> dict:  # type: ignore[type-arg]
            slug = args.get("slug", "")
            try:
                doc = await asyncio.to_thread(read_note, store_dir, slug)
            except ValueError as exc:  # unsafe slug — never a path, always an error
                return {"error": str(exc)}
            if doc is None:
                return {"error": f"no such note: {slug}"}
            return {"slug": doc.slug, "body": doc.body}

        async def _write_note(args: dict) -> dict:  # type: ignore[type-arg]
            slug = args.get("slug", "")
            try:
                await asyncio.to_thread(
                    write_note,
                    store_dir,
                    slug,
                    title=args.get("title", ""),
                    summary=args.get("summary", ""),
                    body=args.get("markdown", ""),
                    now=now(),
                )
            except ValueError as exc:
                return {"error": str(exc)}
            acts.written += 1
            return {"ok": True, "slug": slug}

        async def _delete_note(args: dict) -> dict:  # type: ignore[type-arg]
            slug = args.get("slug", "")
            try:
                removed = await asyncio.to_thread(delete_note, store_dir, slug)
            except ValueError as exc:
                return {"error": str(exc)}
            if not removed:
                return {"error": f"no such note: {slug}"}
            acts.archived += 1
            return {"ok": True}

        return [
            ReorgTool(
                name="list_notes",
                description=(
                    "List every note in the scope with its slug, title, summary and length."
                ),
                input_schema={"type": "object", "properties": {}, "required": []},
                handler=_list_notes,
            ),
            ReorgTool(
                name="read_note",
                description="Read the full body of one note by slug.",
                input_schema={
                    "type": "object",
                    "properties": {"slug": {"type": "string", "description": "The note slug."}},
                    "required": ["slug"],
                },
                handler=_read_note,
            ),
            ReorgTool(
                name="write_note",
                description=(
                    "Create or overwrite a note. The prior revision is archived automatically."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "slug": {"type": "string"},
                        "title": {"type": "string"},
                        "summary": {"type": "string"},
                        "markdown": {"type": "string"},
                    },
                    "required": ["slug", "title", "summary", "markdown"],
                },
                handler=_write_note,
            ),
            ReorgTool(
                name="delete_note",
                description=(
                    "Remove a note whose content now lives elsewhere. The "
                    "removed revision is archived automatically."
                ),
                input_schema={
                    "type": "object",
                    "properties": {"slug": {"type": "string"}},
                    "required": ["slug"],
                },
                handler=_delete_note,
            ),
        ]


__all__ = ["REORG_SYSTEM", "ReorgResult", "ReorgService"]
