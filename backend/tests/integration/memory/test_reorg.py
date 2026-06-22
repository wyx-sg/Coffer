"""Integration tests for ReorgService over the real memory stack (spec 007).

Extends the ``mem`` harness (real SQLite + real fact files + real ripgrep) with a
fake ``AgenticReorgPort`` that drives ``run_agentic_reorg`` directly (via a
``GenericFakeChatModel`` with scripted AIMessages), so no real LLM is ever called.

The acceptance tests cover:
1. Duplicate consolidation (list → read a → read b → write merged → supersede b).
2. Data-loss invariant: a superseded doc stays recoverable under ``superseded/``.
3. No-op when no internal model is configured (``status == "no_model"``).
4. 固化 (FR-047): a recurring journal pattern is promoted to a knowledge topic.
5. 固化 (FR-047): an imperative pattern is promoted to the rules lane.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.application.memory.reorg import ReorgService
from coffer.domain.audit import AuditEventType
from coffer.domain.provider.config import Protocol, ProviderConfig, ResolvedConnection
from coffer.infrastructure.knowledge.paths import (
    consolidation_log_path,
    journal_path,
    rules_path,
    superseded_dir,
    topic_path,
)
from coffer.infrastructure.memory.journal_files import append_entry
from coffer.infrastructure.memory.topic_files import TopicDoc, write_topic_doc


def _model() -> ResolvedConnection:
    return ResolvedConnection(
        config=ProviderConfig(
            protocol=Protocol.OLLAMA,
            base_url="http://localhost:11434",
            credential_ref=None,
        ),
        model="llama3",
    )


class _Models:
    """Fake ModelSelectorPort. ``model=None`` simulates no internal model."""

    def __init__(self, model: ResolvedConnection | None) -> None:
        self._model = model

    async def get_default(self) -> ResolvedConnection | None:
        return self._model


def _fake_chat_model(scripted: list[Any]) -> Any:
    """A GenericFakeChatModel whose bind_tools is a no-op (returns self)."""
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

    class _Model(GenericFakeChatModel):  # type: ignore[misc]
        def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
            return self

    return _Model(messages=iter(scripted))


class _FakeAgent:
    """AgenticReorgPort that runs the real reorg loop with a scripted fake model."""

    def __init__(self, scripted: list[Any]) -> None:
        self._scripted = scripted

    async def run(
        self,
        *,
        model: ResolvedConnection,
        tools: Any,
        system_prompt: str,
        credential_resolver: Any,
        recursion_limit: int,
    ) -> dict[str, Any]:
        from coffer.infrastructure.chat.agentic_reorg import run_agentic_reorg

        lc_model = _fake_chat_model(self._scripted)
        return await run_agentic_reorg(
            lc_model=lc_model,
            tools=tools,
            system_prompt=system_prompt,
            recursion_limit=recursion_limit,
        )


def _make_reorg(mem: Any, agent: _FakeAgent, models: _Models) -> ReorgService:
    svc = mem.service
    return ReorgService(
        resolve_store=svc.resolved_store,
        get_config=svc.get_store_config,
        store_ref=svc._recall.store_ref,
        documents=mem.documents,
        retrieval=svc._retrieval,
        reconciler=svc._reconciler,
        agent=agent,
        models=models,
        credential_resolver=lambda ref: "key",
        audit=mem.audit,
        now=lambda: datetime(2026, 6, 21, 12, 0, tzinfo=UTC),
        embedding_resolver=svc._resolve_embedding,
    )


def _seed_topic(store_dir: Any, slug: str, title: str, body: str) -> None:
    """Write a topic doc directly (not via the organizer) for test setup."""
    write_topic_doc(
        topic_path(store_dir, slug),
        TopicDoc(
            slug=slug,
            title=title,
            description=title,
            body=body,
            updated_at=datetime(2026, 6, 20, tzinfo=UTC),
        ),
    )


def _seed_journal(store_dir: Any, entries: list[tuple[datetime, str]]) -> None:
    """Append episodic journal entries directly into ``journal/<period>.md``.

    Each ``(timestamp, body)`` lands in the month-partitioned file for its date,
    mirroring what the distill path would have written."""
    for ts, body in entries:
        append_entry(journal_path(store_dir, ts.strftime("%Y-%m")), timestamp=ts, body=body)


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="007-memory",
    scenario="the reorg pass consolidates duplicate topic documents",
)
async def test_reorg_consolidates_duplicate_topics(mem: Any) -> None:
    """Seed two overlapping topics; the agent merges them and supersedes one."""
    from langchain_core.messages import AIMessage

    await mem.service.ensure_store("global")
    store_dir = (await mem.service.resolved_store("global")).store_dir

    _seed_topic(store_dir, "deploy-a", "Deploy A", "# Deploy A\n\nDeploy via make release.")
    _seed_topic(store_dir, "deploy-b", "Deploy B", "# Deploy B\n\nReleases tagged atomically.")

    scripted = [
        # list_topics → agent sees both docs
        AIMessage(
            content="",
            tool_calls=[{"id": "c1", "name": "list_topics", "args": {}, "type": "tool_call"}],
        ),
        # read deploy-a
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "c2",
                    "name": "read_topic",
                    "args": {"slug": "deploy-a"},
                    "type": "tool_call",
                }
            ],
        ),
        # read deploy-b
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "c3",
                    "name": "read_topic",
                    "args": {"slug": "deploy-b"},
                    "type": "tool_call",
                }
            ],
        ),
        # write merged content into deploy-a
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "c4",
                    "name": "write_topic",
                    "args": {
                        "slug": "deploy-a",
                        "title": "Deploy conventions",
                        "description": "How we ship",
                        "markdown": (
                            "# Deploy\n\nDeploy via make release.\nReleases tagged atomically."
                        ),
                    },
                    "type": "tool_call",
                }
            ],
        ),
        # supersede deploy-b
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "c5",
                    "name": "supersede_topic",
                    "args": {"slug": "deploy-b", "reason": "merged into deploy-a"},
                    "type": "tool_call",
                }
            ],
        ),
        # done
        AIMessage(content="Consolidation complete."),
    ]

    reorg_svc = _make_reorg(mem, _FakeAgent(scripted), _Models(_model()))
    result = await reorg_svc.reorg(store_name="global")

    assert result.status == "reorganized"
    assert result.topics_before == 2
    assert result.topics_written == 1
    assert result.topics_superseded == 1
    assert result.model == "llama3"

    # deploy-a is now the merged doc
    merged = topic_path(store_dir, "deploy-a").read_text(encoding="utf-8")
    assert "make release" in merged
    assert "tagged atomically" in merged

    # deploy-b is gone from the live lane
    assert not topic_path(store_dir, "deploy-b").exists()

    # Audit recorded
    entries = await mem.audit.query(event_type=AuditEventType.MEMORY_REORGANIZED.value)
    assert len(entries) == 1


@pytest.mark.acceptance(
    spec="007-memory",
    scenario="reorg never destroys content — a superseded topic stays recoverable",
)
async def test_reorg_superseded_topic_stays_recoverable(mem: Any) -> None:
    """Overwriting a topic archives the prior version to superseded/; superseding
    archives + removes from the lane. Both prior versions must be readable."""
    from langchain_core.messages import AIMessage

    await mem.service.ensure_store("global")
    store_dir = (await mem.service.resolved_store("global")).store_dir

    original_body = "# Alpha\n\nOriginal content SENTINEL_KEEP_ME."
    _seed_topic(store_dir, "alpha", "Alpha", original_body)

    scripted = [
        AIMessage(
            content="",
            tool_calls=[{"id": "c1", "name": "list_topics", "args": {}, "type": "tool_call"}],
        ),
        AIMessage(
            content="",
            tool_calls=[
                {"id": "c2", "name": "read_topic", "args": {"slug": "alpha"}, "type": "tool_call"}
            ],
        ),
        # Overwrite alpha with updated content (prior version should be archived)
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "c3",
                    "name": "write_topic",
                    "args": {
                        "slug": "alpha",
                        "title": "Alpha",
                        "description": "Alpha topic",
                        "markdown": (
                            "# Alpha\n\nUpdated content Y. Plus SENTINEL_KEEP_ME preserved."
                        ),
                    },
                    "type": "tool_call",
                }
            ],
        ),
        AIMessage(content="Done."),
    ]

    reorg_svc = _make_reorg(mem, _FakeAgent(scripted), _Models(_model()))
    result = await reorg_svc.reorg(store_name="global")

    assert result.status == "reorganized"
    assert result.topics_written == 1

    # Live doc has the new content
    live = topic_path(store_dir, "alpha").read_text(encoding="utf-8")
    assert "Updated content Y" in live

    # Prior version is in superseded/
    sup_dir = superseded_dir(store_dir)
    archived = list(sup_dir.glob("alpha-*.md"))
    assert archived, "prior version should have been archived to superseded/"
    # The archived copy has the original content
    archived_text = archived[0].read_text(encoding="utf-8")
    assert "SENTINEL_KEEP_ME" in archived_text
    assert "Original content" in archived_text


@pytest.mark.acceptance(
    spec="007-memory",
    scenario="reorg is a no-op when no internal model is configured",
)
async def test_reorg_no_model_is_clean_noop(mem: Any) -> None:
    """When no model is configured the service returns status='no_model' and the
    agent loop is never called; on-disk state is untouched."""
    await mem.service.ensure_store("global")
    store_dir = (await mem.service.resolved_store("global")).store_dir

    _seed_topic(store_dir, "existing", "Existing", "# Existing\n\nShould survive.")

    # _FakeAgent with empty scripted list — if called at all, it would fail
    class _NeverCalledAgent:
        async def run(self, **_: Any) -> dict[str, Any]:
            raise AssertionError("agent loop must not be called when no model is configured")

    reorg_svc = _make_reorg(mem, _NeverCalledAgent(), _Models(None))  # type: ignore[arg-type]
    result = await reorg_svc.reorg(store_name="global")

    assert result.status == "no_model"
    assert result.model is None
    assert result.topics_written == 0
    assert result.topics_superseded == 0

    # On-disk state is untouched
    assert topic_path(store_dir, "existing").exists()
    text = topic_path(store_dir, "existing").read_text(encoding="utf-8")
    assert "Should survive" in text
    # superseded/ was NOT created
    assert not superseded_dir(store_dir).exists()


# ---------------------------------------------------------------------------
# Non-acceptance edge cases
# ---------------------------------------------------------------------------


async def test_read_topic_missing_slug_returns_error_dict(mem: Any) -> None:
    """read_topic on a missing slug returns an error dict, no raise."""
    from langchain_core.messages import AIMessage

    await mem.service.ensure_store("global")
    store_dir = (await mem.service.resolved_store("global")).store_dir
    _seed_topic(store_dir, "real", "Real", "# Real\n\nExists.")

    scripted = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "c1",
                    "name": "read_topic",
                    "args": {"slug": "nonexistent"},
                    "type": "tool_call",
                }
            ],
        ),
        AIMessage(content="Topic not found; nothing to do."),
    ]

    reorg_svc = _make_reorg(mem, _FakeAgent(scripted), _Models(_model()))
    # Must not raise; tool error is handled by ToolNode
    result = await reorg_svc.reorg(store_name="global")
    assert result.status == "reorganized"
    assert result.topics_written == 0
    assert result.topics_superseded == 0


async def test_write_topic_bad_slug_rejected_no_write(mem: Any) -> None:
    """A write_topic call with a traversal slug is rejected without any write."""
    from langchain_core.messages import AIMessage

    await mem.service.ensure_store("global")
    store_dir = (await mem.service.resolved_store("global")).store_dir
    _seed_topic(store_dir, "safe", "Safe", "# Safe\n\nContent.")

    scripted = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "c1",
                    "name": "write_topic",
                    "args": {
                        "slug": "../evil",
                        "title": "Evil",
                        "description": "bad",
                        "markdown": "# Evil",
                    },
                    "type": "tool_call",
                }
            ],
        ),
        AIMessage(content="Got an error; aborting."),
    ]

    reorg_svc = _make_reorg(mem, _FakeAgent(scripted), _Models(_model()))
    result = await reorg_svc.reorg(store_name="global")
    assert result.status == "reorganized"
    assert result.topics_written == 0
    # The safe topic is untouched
    assert "Content." in topic_path(store_dir, "safe").read_text(encoding="utf-8")


async def test_recursion_limit_still_finalizes_index_and_audit(mem: Any) -> None:
    """GraphRecursionError mid-loop still finalizes INDEX/reconcile/audit."""
    from langchain_core.messages import AIMessage

    from coffer.infrastructure.knowledge.paths import knowledge_index_path

    await mem.service.ensure_store("global")
    store_dir = (await mem.service.resolved_store("global")).store_dir
    _seed_topic(store_dir, "topic-a", "Topic A", "# A\n\nContent A.")
    _seed_topic(store_dir, "topic-b", "Topic B", "# B\n\nContent B.")

    # Script 13 list_topics calls — DEFAULT_REORG_RECURSION_LIMIT=24 steps
    # means 12 tool calls fit; 13 will overflow.
    scripted = [
        AIMessage(
            content="",
            tool_calls=[{"id": f"c{i}", "name": "list_topics", "args": {}, "type": "tool_call"}],
        )
        for i in range(13)
    ]

    reorg_svc = _make_reorg(mem, _FakeAgent(scripted), _Models(_model()))
    result = await reorg_svc.reorg(store_name="global")

    assert result.status == "reorganized"
    # INDEX was regenerated despite the truncated loop
    assert knowledge_index_path(store_dir).exists()
    # Audit was recorded
    entries = await mem.audit.query(event_type=AuditEventType.MEMORY_REORGANIZED.value)
    assert len(entries) == 1


# ---------------------------------------------------------------------------
# 固化 (consolidation) — FR-047
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="007-memory",
    scenario="固化 promotes a recurring journal pattern into a knowledge topic",
)
async def test_consolidation_promotes_recurring_journal_to_topic(mem: Any) -> None:
    """A recurring durable pattern (≥3 entries across ≥2 days, no prior topics) is
    copied into a new knowledge topic via write_topic; the journal is untouched."""
    from langchain_core.messages import AIMessage

    await mem.service.ensure_store("global")
    store_dir = (await mem.service.resolved_store("global")).store_dir

    # Recurring pattern: deploys keep failing on the migration step (4 entries, 3 days).
    journal_entries = [
        (datetime(2026, 6, 18, 9, tzinfo=UTC), "deploy failed: migration step timed out"),
        (datetime(2026, 6, 19, 11, tzinfo=UTC), "deploy failed again on the migration step"),
        (datetime(2026, 6, 19, 16, tzinfo=UTC), "another deploy failed at migration"),
        (datetime(2026, 6, 20, 10, tzinfo=UTC), "deploy migration step failed once more"),
    ]
    _seed_journal(store_dir, journal_entries)
    journal_md = journal_path(store_dir, "2026-06")
    journal_before = journal_md.read_text(encoding="utf-8")

    scripted = [
        # read_journal → agent sees the recurring pattern
        AIMessage(
            content="",
            tool_calls=[{"id": "c1", "name": "read_journal", "args": {}, "type": "tool_call"}],
        ),
        # promote it to a new knowledge topic
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "c2",
                    "name": "write_topic",
                    "args": {
                        "slug": "deploy-migration-failures",
                        "title": "Deploy migration failures",
                        "description": "Recurring deploy failures at the migration step",
                        "markdown": (
                            "# Deploy migration failures\n\nDeploys repeatedly fail at the "
                            "migration step (timeouts). Investigate the migration timeout."
                        ),
                    },
                    "type": "tool_call",
                }
            ],
        ),
        AIMessage(content="Consolidation complete."),
    ]

    reorg_svc = _make_reorg(mem, _FakeAgent(scripted), _Models(_model()))
    result = await reorg_svc.reorg(store_name="global")

    # The loop ran despite NO prior topic docs (journal alone is enough).
    assert result.status == "reorganized"
    assert result.topics_before == 0
    assert result.topics_written == 1

    # The promoted topic exists on disk + is recalled.
    promoted = topic_path(store_dir, "deploy-migration-failures")
    assert promoted.exists()
    assert "migration step" in promoted.read_text(encoding="utf-8")
    hits, _fb = await mem.service.recall(cwd=None, query="deploy migration failures", top_k=10)
    assert any("migration" in h.text for h in hits), [h.text for h in hits]

    # The consolidation log recorded the write (固化 copy).
    log = consolidation_log_path(store_dir).read_text(encoding="utf-8")
    assert "deploy-migration-failures" in log

    # Promotion COPIES — the journal is NOT modified.
    assert journal_md.read_text(encoding="utf-8") == journal_before


@pytest.mark.acceptance(
    spec="007-memory",
    scenario="固化 promotes a recurring imperative pattern into the rules lane",
)
async def test_consolidation_promotes_imperative_to_rules(mem: Any) -> None:
    """A clearly imperative recurring pattern is promoted to rules/rules.md via
    append_rule; the changelog logs it and the result/audit promoted count is 1."""
    from langchain_core.messages import AIMessage

    await mem.service.ensure_store("global")
    store_dir = (await mem.service.resolved_store("global")).store_dir

    _seed_journal(
        store_dir,
        [
            (datetime(2026, 6, 18, 9, tzinfo=UTC), "forgot to run the linter before pushing again"),
            (datetime(2026, 6, 19, 9, tzinfo=UTC), "CI failed because the linter wasn't run"),
            (datetime(2026, 6, 20, 9, tzinfo=UTC), "had to re-push after the linter caught issues"),
        ],
    )
    journal_md = journal_path(store_dir, "2026-06")
    journal_before = journal_md.read_text(encoding="utf-8")

    rule_text = "Always run the linter before pushing."
    scripted = [
        AIMessage(
            content="",
            tool_calls=[{"id": "c1", "name": "read_journal", "args": {}, "type": "tool_call"}],
        ),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "c2",
                    "name": "append_rule",
                    "args": {"rule": rule_text},
                    "type": "tool_call",
                }
            ],
        ),
        AIMessage(content="Promoted a rule."),
    ]

    reorg_svc = _make_reorg(mem, _FakeAgent(scripted), _Models(_model()))
    result = await reorg_svc.reorg(store_name="global")

    assert result.status == "reorganized"
    assert result.promoted == 1
    assert result.topics_written == 0

    # The rule is in rules/rules.md.
    rules = rules_path(store_dir).read_text(encoding="utf-8")
    assert rule_text in rules

    # The changelog logged the promotion.
    log = consolidation_log_path(store_dir).read_text(encoding="utf-8")
    assert rule_text in log
    assert "固化" in log

    # The audit details report promoted=1.
    entries = await mem.audit.query(event_type=AuditEventType.MEMORY_REORGANIZED.value)
    assert len(entries) == 1
    assert entries[0].details["promoted"] == 1

    # The journal is unchanged (固化 copies).
    assert journal_md.read_text(encoding="utf-8") == journal_before


async def test_read_journal_returns_entries_with_dates(mem: Any) -> None:
    """The read_journal tool surfaces journal entries newest-first, each with its
    YYYY-MM-DD date — the distinct-days signal the loop uses to judge recurrence."""
    await mem.service.ensure_store("global")
    store_dir = (await mem.service.resolved_store("global")).store_dir
    _seed_journal(
        store_dir,
        [
            (datetime(2026, 6, 18, 9, tzinfo=UTC), "older event about gizmos"),
            (datetime(2026, 6, 20, 9, tzinfo=UTC), "newer event about gizmos"),
        ],
    )

    # Build the tools directly and invoke the read_journal handler.
    reorg_svc = _make_reorg(mem, _FakeAgent([]), _Models(_model()))
    from coffer.application.memory.reorg import _Actions

    tools = reorg_svc._build_tools(store_dir=store_dir, acts=_Actions())
    read_journal = next(t for t in tools if t.name == "read_journal")
    out = await read_journal.handler({})

    dates = [e["date"] for e in out["entries"]]
    bodies = [e["body"] for e in out["entries"]]
    # Newest-first ordering, ISO dates.
    assert dates == ["2026-06-20", "2026-06-18"]
    assert bodies[0] == "newer event about gizmos"
    assert bodies[1] == "older event about gizmos"


async def test_empty_guard_no_topics_no_journal(mem: Any) -> None:
    """A store with NEITHER topic docs NOR journal entries returns status='empty'
    and never calls the agent loop."""

    class _NeverCalledAgent:
        async def run(self, **_: Any) -> dict[str, Any]:
            raise AssertionError("agent loop must not run when both lanes are empty")

    await mem.service.ensure_store("global")

    reorg_svc = _make_reorg(mem, _NeverCalledAgent(), _Models(_model()))  # type: ignore[arg-type]
    result = await reorg_svc.reorg(store_name="global")

    assert result.status == "empty"
    assert result.topics_written == 0
    assert result.promoted == 0
    assert result.model == "llama3"
