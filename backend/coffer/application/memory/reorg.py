"""ReorgService — agentic topic-doc reorganization + 固化 (spec 007).

On an explicit ``reorg`` trigger (REST/CLI; no auto-fire in this PR), runs a
bounded langgraph create_react_agent loop over the store's existing topic docs
AND the episodic journal lane, with 6 internal tools, to consolidate duplicates,
split over-long docs, and CONSOLIDATE (固化) recurring durable journal patterns
into the semantic lane (a knowledge topic, or a rule). Reaches the langgraph
loop ONLY through the injected ``AgenticReorgPort`` (Contract 5e: memory-local
port, NOT ``application.distill`` or ``infrastructure.chat``).

固化 COPIES a recurring pattern into knowledge/rules — it never removes journal
entries (the journal is append-only; one-off events age out by prune, a later
slice). Data-loss invariant: every topic overwrite/supersede first archives the
prior topic doc to the recoverable ``superseded/`` tombstone. There is NO
hard-delete.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from coffer.application.audit_service import AuditService
from coffer.application.knowledge.retrieval import (
    EmbeddingResolver,
    KnowledgeRetrieval,
    no_embedding,
)
from coffer.application.memory.ports import MemoryDocumentRepo
from coffer.application.memory.reorg_journal import (
    REORG_SYSTEM,
    journal_has_entries,
    recent_journal_entries,
)
from coffer.application.memory.reorg_ports import AgenticReorgPort, ModelSelectorPort, ReorgTool
from coffer.application.memory.sync import MemoryReconciler
from coffer.domain.audit import AuditEventType
from coffer.domain.knowledge.document import KIND_MEMORY
from coffer.domain.knowledge.retrieval import StoreRef
from coffer.domain.memory.config import MemoryStoreConfig
from coffer.domain.memory.scope import ResolvedScope
from coffer.domain.resource import ResourceRef
from coffer.infrastructure.knowledge.paths import rules_path, topic_path
from coffer.infrastructure.memory.rules_files import append_rule
from coffer.infrastructure.memory.topic_files import (
    TopicDoc,
    append_changelog,
    archive_topic_doc,
    list_topic_docs,
    read_topic_doc,
    supersede_topic_doc,
    write_index,
    write_topic_doc,
)

logger = logging.getLogger(__name__)

#: ``store_name -> ResolvedScope`` (validates the store exists).
ResolveStoreFn = Callable[[str], Awaitable[ResolvedScope]]
#: ``store_name -> MemoryStoreConfig``.
ConfigFn = Callable[[str], Awaitable[MemoryStoreConfig]]
#: ``store_name, project_id -> StoreRef``.
StoreRefFn = Callable[[str, str], StoreRef]
#: ``() -> datetime`` (injectable clock).
NowFn = Callable[[], datetime]

DEFAULT_REORG_RECURSION_LIMIT = 24


@dataclass(frozen=True)
class ReorgResult:
    """The outcome of one ``reorg`` run.

    ``promoted`` counts 固化 promotions into the rules lane (``append_rule``);
    knowledge-topic promotions are folded into ``topics_written``."""

    status: str  # "reorganized" | "no_model" | "empty"
    topics_before: int
    topics_after: int
    topics_written: int  # create + overwrite (incl. knowledge promotions)
    topics_superseded: int
    promoted: int  # rules promoted from the journal (固化)
    model: str | None  # display name of the internal model used


class _Actions:
    """Mutable accumulator for tool call counts."""

    def __init__(self) -> None:
        self.written: int = 0
        self.superseded: int = 0
        self.promoted: int = 0  # rules promotions (固化)


class ReorgService:
    """Orchestrates the explicit agentic topic-doc reorganization."""

    def __init__(
        self,
        *,
        resolve_store: ResolveStoreFn,
        get_config: ConfigFn,
        store_ref: StoreRefFn,
        documents: MemoryDocumentRepo,
        retrieval: KnowledgeRetrieval,
        reconciler: MemoryReconciler,
        agent: AgenticReorgPort,
        models: ModelSelectorPort,
        credential_resolver: Callable[[str], str],
        audit: AuditService,
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
        self._credential_resolver = credential_resolver
        self._audit = audit
        self._now = now
        self._resolve_embedding = embedding_resolver

    async def reorg(self, *, store_name: str) -> ReorgResult:
        """Run the agentic reorg loop over the store's topic docs.

        Validates the store (404s an unknown name via ``resolve_store``). A
        ``no_model`` / ``empty`` outcome is a clean no-op, not an error."""
        resolved = await self._resolve_store(store_name)
        store_dir = resolved.store_dir
        ref = self._store_ref(store_name, resolved.project_id)

        model = await self._models.get_default()
        if model is None:
            return ReorgResult("no_model", 0, 0, 0, 0, 0, None)

        config = await self._get_config(store_name)
        embedding = await self._resolve_embedding() if config.vector_enabled else None
        await self._reconciler.reconcile(store=ref, embedding=embedding)

        before = await asyncio.to_thread(list_topic_docs, store_dir)
        has_journal = await asyncio.to_thread(journal_has_entries, store_dir)
        # Run the loop when there is anything to work on — topic docs to keep
        # coherent OR journal entries to consolidate (固化). Empty only when both
        # lanes are empty.
        if not before and not has_journal:
            return ReorgResult("empty", 0, 0, 0, 0, 0, model.model)

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
            logger.warning(
                "reorg.agent_loop_failed; finalizing from on-disk state + action counters",
                exc_info=True,
            )

        after = await asyncio.to_thread(list_topic_docs, store_dir)
        await asyncio.to_thread(write_index, store_dir, after)
        await self._reconciler.reconcile(store=ref, embedding=embedding)
        await self._record_audit(
            store_name=store_name,
            topics_before=len(before),
            topics_after=len(after),
            topics_written=acts.written,
            topics_superseded=acts.superseded,
            promoted=acts.promoted,
        )
        return ReorgResult(
            "reorganized",
            len(before),
            len(after),
            acts.written,
            acts.superseded,
            acts.promoted,
            model.model,
        )

    def _build_tools(self, *, store_dir: Path, acts: _Actions) -> list[ReorgTool]:
        now = self._now

        async def _list_topics(args: dict) -> dict:  # type: ignore[type-arg]
            docs = await asyncio.to_thread(list_topic_docs, store_dir)
            return {
                "topics": [
                    {
                        "slug": d.slug,
                        "title": d.title,
                        "description": d.description,
                        "length": len(d.body),
                    }
                    for d in docs
                ]
            }

        async def _read_topic(args: dict) -> dict:  # type: ignore[type-arg]
            slug = args.get("slug", "")
            try:
                path = await asyncio.to_thread(topic_path, store_dir, slug)
            except ValueError as exc:
                return {"error": str(exc)}
            doc = await asyncio.to_thread(read_topic_doc, path)
            if doc is None:
                return {"error": f"no such topic: {slug}"}
            return {"slug": doc.slug, "body": doc.body}

        async def _write_topic(args: dict) -> dict:  # type: ignore[type-arg]
            slug = args.get("slug", "")
            title = args.get("title", "")
            description = args.get("description", "")
            markdown = args.get("markdown", "")
            # Validate slug — topic_path guards via _safe_segment internally.
            try:
                path = await asyncio.to_thread(topic_path, store_dir, slug)
            except ValueError as exc:
                return {"error": str(exc)}
            ts = now()
            # Archive prior version first (data-loss invariant).
            if await asyncio.to_thread(path.exists):
                await asyncio.to_thread(archive_topic_doc, store_dir, slug, when=ts)
            doc = TopicDoc(
                slug=slug,
                title=title,
                description=description,
                body=markdown,
                updated_at=ts,
            )
            await asyncio.to_thread(write_topic_doc, path, doc)
            await asyncio.to_thread(
                append_changelog,
                store_dir,
                f"{ts.isoformat()} · reorg wrote '{slug}'",
            )
            acts.written += 1
            return {"ok": True, "slug": slug}

        async def _supersede_topic(args: dict) -> dict:  # type: ignore[type-arg]
            slug = args.get("slug", "")
            reason = args.get("reason", "")
            ts = now()
            archived = await asyncio.to_thread(supersede_topic_doc, store_dir, slug, when=ts)
            if archived is None:
                return {"error": f"no such topic: {slug}"}
            await asyncio.to_thread(
                append_changelog,
                store_dir,
                f"{ts.isoformat()} · reorg superseded '{slug}': {reason}",
            )
            acts.superseded += 1
            return {"ok": True}

        async def _read_journal(args: dict) -> dict:  # type: ignore[type-arg]
            entries = await asyncio.to_thread(recent_journal_entries, store_dir)
            return {
                "entries": [
                    {"date": e.timestamp.date().isoformat(), "body": e.body} for e in entries
                ]
            }

        async def _append_rule(args: dict) -> dict:  # type: ignore[type-arg]
            rule = str(args.get("rule", "")).strip()
            if not rule:
                return {"error": "rule must be a non-empty string"}
            added = await asyncio.to_thread(append_rule, rules_path(store_dir), rule)
            if not added:
                return {"ok": True, "duplicate": True}
            ts = now()
            await asyncio.to_thread(
                append_changelog,
                store_dir,
                f"{ts.isoformat()} · reorg promoted rule (固化): {rule}",
            )
            acts.promoted += 1
            return {"ok": True}

        return [
            ReorgTool(
                name="list_topics",
                description=(
                    "List all existing topic documents in the store with their "
                    "slug, title, description, and length."
                ),
                input_schema={"type": "object", "properties": {}, "required": []},
                handler=_list_topics,
            ),
            ReorgTool(
                name="read_topic",
                description="Read the full body of a topic document by slug.",
                input_schema={
                    "type": "object",
                    "properties": {"slug": {"type": "string", "description": "The topic slug."}},
                    "required": ["slug"],
                },
                handler=_read_topic,
            ),
            ReorgTool(
                name="write_topic",
                description=(
                    "Create or overwrite a topic document. "
                    "The prior version is archived automatically."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "slug": {"type": "string"},
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "markdown": {"type": "string"},
                    },
                    "required": ["slug", "title", "description", "markdown"],
                },
                handler=_write_topic,
            ),
            ReorgTool(
                name="supersede_topic",
                description=("Retire a topic document to the recoverable superseded/ tombstone."),
                input_schema={
                    "type": "object",
                    "properties": {
                        "slug": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["slug"],
                },
                handler=_supersede_topic,
            ),
            ReorgTool(
                name="read_journal",
                description=(
                    "List recent journal (episodic) entries, newest-first, each with "
                    "its date. Use distinct dates to judge whether a pattern recurs."
                ),
                input_schema={"type": "object", "properties": {}, "required": []},
                handler=_read_journal,
            ),
            ReorgTool(
                name="append_rule",
                description=(
                    "Promote a recurring imperative/behavioural pattern into the rules "
                    "lane (rules/rules.md). The journal entries are NOT removed."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "rule": {
                            "type": "string",
                            "description": "The imperative rule text (e.g. 'always run X').",
                        }
                    },
                    "required": ["rule"],
                },
                handler=_append_rule,
            ),
        ]

    async def _record_audit(
        self,
        *,
        store_name: str,
        topics_before: int,
        topics_after: int,
        topics_written: int,
        topics_superseded: int,
        promoted: int,
    ) -> None:
        await self._audit.record(
            AuditEventType.MEMORY_REORGANIZED.value,
            ref=ResourceRef(KIND_MEMORY, store_name),
            actor="system",
            details={
                "topics_before": topics_before,
                "topics_after": topics_after,
                "topics_written": topics_written,
                "topics_superseded": topics_superseded,
                "promoted": promoted,
            },
        )


__all__ = ["REORG_SYSTEM", "ReorgResult", "ReorgService"]
