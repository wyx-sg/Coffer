"""OrganizerService — the internal-LLM inbox→topic-doc consolidation (spec 007).

Drains ``knowledge/inbox/`` into coherent topic docs (one LLM call per item) or the
rules lane (``rules/rules.md``) on an explicit trigger. Safety invariants: inbox
items are deleted only after their content is safely written; a parse/LLM failure
skips the item (leaves it in the inbox, never corrupts anything).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from coffer.application.audit_service import AuditService
from coffer.application.knowledge.retrieval import (
    EmbeddingResolver,
    KnowledgeRetrieval,
    no_embedding,
)
from coffer.application.memory.organizer_ports import LlmCompletionPort, ModelSelectorPort
from coffer.application.memory.organizer_prompt import (
    ORGANIZER_SYSTEM,
    OrganizedTopic,
    build_user_prompt,
    parse_organized_topic,
)
from coffer.application.memory.ports import MemoryDocumentRepo
from coffer.application.memory.sync import MemoryReconciler
from coffer.domain.audit import AuditEventType
from coffer.domain.chat.model import ModelConfig
from coffer.domain.knowledge.document import KIND_MEMORY
from coffer.domain.knowledge.retrieval import StoreRef
from coffer.domain.memory.config import MemoryStoreConfig
from coffer.domain.memory.scope import ResolvedScope
from coffer.domain.resource import ResourceRef
from coffer.infrastructure.knowledge.paths import knowledge_dir, rules_path, topic_path
from coffer.infrastructure.memory.files import (
    FactFile,
    delete_fact_file,
    list_inbox_items,
)
from coffer.infrastructure.memory.rules_files import append_rule
from coffer.infrastructure.memory.topic_files import (
    TopicDoc,
    append_changelog,
    list_topic_docs,
    read_topic_doc,
    topic_doc_exists,
    write_index,
    write_topic_doc,
)

logger = logging.getLogger(__name__)

_TOP_K_CANDIDATES = 3

ResolveStoreFn = Callable[[str], Awaitable[ResolvedScope]]
ConfigFn = Callable[[str], Awaitable[MemoryStoreConfig]]
StoreRefFn = Callable[[str, str], StoreRef]
NowFn = Callable[[], datetime]


@dataclass(frozen=True)
class OrganizeResult:
    """The outcome of one ``organize`` run."""

    status: str
    items_processed: int
    topics_created: int
    topics_updated: int
    rules_appended: int
    skipped: int
    model: str | None


class OrganizerService:
    """Orchestrates the explicit inbox→topic-doc consolidation."""

    def __init__(
        self,
        *,
        resolve_store: ResolveStoreFn,
        get_config: ConfigFn,
        store_ref: StoreRefFn,
        documents: MemoryDocumentRepo,
        retrieval: KnowledgeRetrieval,
        reconciler: MemoryReconciler,
        llm: LlmCompletionPort,
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
        self._llm = llm
        self._models = models
        self._credential_resolver = credential_resolver
        self._audit = audit
        self._now = now
        self._resolve_embedding = embedding_resolver

    async def organize(self, *, store_name: str) -> OrganizeResult:
        """Drain ``store_name``'s inbox into topic docs (one LLM call per item).

        Validates the store (404s an unknown name via ``resolve_store``). A
        ``no_model`` / ``empty`` outcome is a clean no-op, not an error."""
        resolved = await self._resolve_store(store_name)
        store_dir = resolved.store_dir
        ref = self._store_ref(store_name, resolved.project_id)

        model = await self._models.get_default()
        if model is None:
            # No internal model → a clean no-op; the inbox is untouched.
            return OrganizeResult("no_model", 0, 0, 0, 0, 0, None)

        items = await asyncio.to_thread(list_inbox_items, store_dir)
        if not items:
            return OrganizeResult("empty", 0, 0, 0, 0, 0, model.display_name)

        config = await self._get_config(store_name)
        # Reconcile once up front so candidate retrieval sees the current lane
        # (inbox items + any existing topic docs) before the first merge.
        embedding = await self._resolve_embedding() if config.vector_enabled else None
        await self._reconciler.reconcile(store=ref, embedding=embedding)

        created = updated = skipped = processed = rules = 0
        for item in items:
            outcome = await self._organize_item(
                item=item, store_dir=store_dir, ref=ref, model=model
            )
            if outcome is None:
                skipped += 1
                continue
            processed += 1
            if outcome == "rule":
                rules += 1
            elif outcome is True:
                updated += 1
            else:
                created += 1

        # Regenerate INDEX from all topic docs, then reconcile (drops the removed
        # inbox rows; (re)indexes the new/updated topic docs so recall returns
        # topic-doc content, not the drained inbox).
        docs = await asyncio.to_thread(list_topic_docs, store_dir)
        await asyncio.to_thread(write_index, store_dir, docs)
        await self._reconciler.reconcile(store=ref, embedding=embedding)

        await self._record_audit(
            store_name=store_name,
            processed=processed,
            created=created,
            updated=updated,
            rules=rules,
            skipped=skipped,
        )
        return OrganizeResult(
            "organized", processed, created, updated, rules, skipped, model.display_name
        )

    # ------------------------------------------------------------------
    # Per-item loop
    # ------------------------------------------------------------------

    async def _organize_item(
        self, *, item: FactFile, store_dir: Path, ref: StoreRef, model: ModelConfig
    ) -> bool | str | None:
        """Process one inbox item: ``"rule"`` (rules lane), ``True`` (merge), ``False``
        (create), or ``None`` (skipped — item stays in inbox)."""
        candidates = await self._retrieve_candidates(ref=ref, store_dir=store_dir, item=item)
        parsed = await self._merge_once(item=item, candidates=candidates, model=model)
        if parsed is None:
            return None
        if parsed.is_rule:
            # Rule path: append to rules/rules.md, drain inbox; skip clobber guard.
            await self._append_rule_and_drain(parsed=parsed, item=item, store_dir=store_dir)
            return "rule"
        parsed = await self._guard_against_clobber(
            parsed=parsed,
            item=item,
            store_dir=store_dir,
            model=model,
            seen_slugs={c.slug for c in candidates},
        )
        if parsed is None:
            return None
        return await self._write_and_drain(parsed=parsed, item=item, store_dir=store_dir)

    async def _append_rule_and_drain(
        self, *, parsed: OrganizedTopic, item: FactFile, store_dir: Path
    ) -> None:
        """Append the rule, drain the inbox item (only after successful append), log."""
        await asyncio.to_thread(append_rule, rules_path(store_dir), parsed.markdown)
        await asyncio.to_thread(delete_fact_file, item.path)
        await asyncio.to_thread(
            append_changelog,
            store_dir,
            f"{self._now().isoformat()} · rule appended ← inbox item '{item.fact.id}'",
        )

    async def _merge_once(
        self, *, item: FactFile, candidates: list[TopicDoc], model: ModelConfig
    ) -> OrganizedTopic | None:
        """One LLM call + parse; ``None`` on failure (item stays in inbox)."""
        try:
            raw = await self._llm.complete(
                system=ORGANIZER_SYSTEM,
                user=build_user_prompt(item_body=item.fact.body, candidates=candidates),
                model=model,
                credential_resolver=self._credential_resolver,
            )
        except Exception:
            logger.warning("organizer.llm_call_failed: item stays in inbox", exc_info=True)
            return None
        return parse_organized_topic(raw)

    async def _guard_against_clobber(
        self,
        *,
        parsed: OrganizedTopic,
        item: FactFile,
        store_dir: Path,
        model: ModelConfig,
        seen_slugs: set[str],
    ) -> OrganizedTopic | None:
        """Enforce the no-clobber invariant in CODE, not just the prompt.

        Best-effort keyword retrieval routinely misses an existing topic doc, so
        the LLM can return a ``topic_slug`` that collides with an on-disk doc it
        was never shown — and a blind overwrite would erase that doc's content
        (a human edit, or a sibling written earlier in this same run). Guard it: if
        the chosen slug names an existing doc the LLM did NOT see, re-merge with
        that doc's real content so it is integrated; if the re-merge still targets
        a *different* unseen doc, disambiguate the slug so a fresh doc is written
        rather than clobbering. Returns ``None`` only if the re-merge itself fails
        — the item then stays in the inbox, never clobbered."""
        existing = await asyncio.to_thread(read_topic_doc, topic_path(store_dir, parsed.topic_slug))
        if existing is None or parsed.topic_slug in seen_slugs:
            # A new doc, or the LLM already saw this doc's content → its markdown
            # IS the merge. Safe to write.
            return parsed
        # The chosen slug names an existing doc the LLM never saw → re-merge with
        # it so its prior content is integrated (never blind-overwritten).
        reparsed = await self._merge_once(item=item, candidates=[existing], model=model)
        if reparsed is None:
            logger.warning(
                "organizer.clobber_guard: slug %r exists but was unseen and the "
                "re-merge failed — skipping item to avoid clobber",
                parsed.topic_slug,
            )
            return None
        target = await asyncio.to_thread(read_topic_doc, topic_path(store_dir, reparsed.topic_slug))
        if target is None or reparsed.topic_slug == existing.slug:
            # New slug (no clobber), or merged into the doc we just showed it → safe.
            return reparsed
        # Pathological: the re-merge chose yet another unseen existing doc.
        # Disambiguate so a fresh doc is written instead of clobbering it.
        safe = await asyncio.to_thread(_unique_slug, store_dir, reparsed.topic_slug)
        logger.warning("organizer.clobber_guard: disambiguated %r -> %r", reparsed.topic_slug, safe)
        return replace(reparsed, topic_slug=safe)

    async def _write_and_drain(
        self, *, parsed: OrganizedTopic, item: FactFile, store_dir: Path
    ) -> bool:
        """Write the merged topic doc, THEN delete the inbox item, THEN log.

        Ordering is the data-loss guard: the inbox item is removed only after the
        topic write succeeds. Returns whether the slug was an existing topic."""
        was_update = await asyncio.to_thread(topic_doc_exists, store_dir, parsed.topic_slug)
        path = topic_path(store_dir, parsed.topic_slug)
        doc = TopicDoc(
            slug=parsed.topic_slug,
            title=parsed.topic_title,
            description=parsed.topic_description,
            body=parsed.markdown,
            updated_at=self._now(),
        )
        await asyncio.to_thread(write_topic_doc, path, doc)
        # Content is now safely in the topic doc → drain the inbox item.
        await asyncio.to_thread(delete_fact_file, item.path)
        action = "merged into" if was_update else "created"
        await asyncio.to_thread(
            append_changelog,
            store_dir,
            f"{self._now().isoformat()} · {action} '{parsed.topic_slug}' "
            f"← inbox item '{item.fact.id}'",
        )
        return was_update

    async def _retrieve_candidates(
        self, *, ref: StoreRef, store_dir: Path, item: FactFile
    ) -> list[TopicDoc]:
        """Top-K most-relevant EXISTING topic docs for an item (no LLM).

        Runs keyword search over the store, then keeps only hits whose document
        is a topic doc (a top-level ``knowledge/*.md`` that is not an inbox item
        and not ``INDEX.md``), reading each via ``read_topic_doc``."""
        try:
            result = await self._retrieval.search(
                ref, item.fact.body, mode="keyword", top_k=_TOP_K_CANDIDATES * 3
            )
        except Exception:
            logger.debug("organizer.candidate_search_failed", exc_info=True)
            return []

        out: list[TopicDoc] = []
        seen: set[str] = set()
        for passage in result.passages:
            doc_row = await self._documents.get_document(
                KIND_MEMORY, ref.resource_name, passage.document_id
            )
            if doc_row is None:
                continue
            path = topic_path_or_none(store_dir, doc_row.path)
            if path is None or path.name in seen:
                continue
            topic = await asyncio.to_thread(read_topic_doc, path)
            if topic is None:
                continue
            seen.add(path.name)
            out.append(topic)
            if len(out) >= _TOP_K_CANDIDATES:
                break
        return out

    async def _record_audit(
        self,
        *,
        store_name: str,
        processed: int,
        created: int,
        updated: int,
        rules: int,
        skipped: int,
    ) -> None:
        await self._audit.record(
            AuditEventType.MEMORY_ORGANIZED.value,
            ref=ResourceRef(KIND_MEMORY, store_name),
            actor="system",
            details={
                "items_processed": processed,
                "topics_created": created,
                "topics_updated": updated,
                "rules_appended": rules,
                "skipped": skipped,
            },
        )


def topic_path_or_none(store_dir: Path, candidate_path: str) -> Path | None:
    """Return the ``Path`` if ``candidate_path`` is a topic doc in this store's
    lane (top-level ``knowledge/*.md``, not an ``inbox/`` item, not ``INDEX.md``),
    else ``None``.

    A document row's ``path`` distinguishes a topic doc from an inbox item: a
    topic doc sits directly under ``knowledge/`` while an inbox item is one level
    deeper under ``knowledge/inbox/``."""
    p = Path(candidate_path)
    lane = knowledge_dir(store_dir).resolve()
    try:
        rp = p.resolve()
    except (OSError, ValueError):  # pragma: no cover - defensive
        return None
    if rp.parent != lane:  # excludes inbox/ (deeper) and the store root
        return None
    if p.name == "INDEX.md" or p.suffix != ".md":
        return None
    return p


def _unique_slug(store_dir: Path, base: str) -> str:
    """A topic slug that does not collide with an existing topic doc (``base``,
    then ``base-2``, ``base-3``, …). Called only when ``base`` is known to collide,
    so a fresh doc is written rather than clobbering an existing one."""
    if not topic_doc_exists(store_dir, base):
        return base
    i = 2
    while topic_doc_exists(store_dir, f"{base}-{i}"):
        i += 1
    return f"{base}-{i}"


__all__ = ["OrganizeResult", "OrganizerService"]
