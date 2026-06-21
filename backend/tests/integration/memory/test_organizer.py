"""Integration tests for the OrganizerService over the real memory stack.

Extends the ``mem`` harness (real SQLite + real fact files + real ripgrep) with a
fake ``LlmCompletionPort`` (scripted JSON, distill ``_Llm`` pattern) and a fake
``ModelSelectorPort`` — so no real LLM is ever called. The organizer's storage
I/O, reconcile, INDEX, changelog, and the data-loss safety invariants are
exercised end-to-end.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from coffer.application.memory.organizer import OrganizerService
from coffer.domain.audit import AuditEventType
from coffer.domain.memory.scope import MemoryScope
from coffer.domain.provider.config import ProviderConfig, WireFormat
from coffer.infrastructure.knowledge.paths import (
    consolidation_log_path,
    inbox_dir,
    knowledge_index_path,
    rules_path,
    topic_path,
)


def _model() -> ProviderConfig:
    return ProviderConfig(
        wire_format=WireFormat.OLLAMA,
        base_url="http://localhost:11434",
        credential_ref=None,
        model="llama3",
    )


class _Models:
    """Fake ModelSelectorPort. ``model=None`` simulates no internal model."""

    def __init__(self, model: ProviderConfig | None) -> None:
        self._model = model

    async def get_default(self) -> ProviderConfig | None:
        return self._model


class _ScriptedLlm:
    """Fake LlmCompletionPort: returns a queued raw string per call.

    ``responses`` may be JSON strings or already-malformed text; each ``complete``
    pops the next one. Records the user prompts it saw (for merge assertions)."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.user_prompts: list[str] = []

    async def complete(self, *, system: str, user: str, model, credential_resolver) -> str:  # type: ignore[no-untyped-def]
        self.user_prompts.append(user)
        return self._responses.pop(0)


def _topic_json(slug: str, title: str, desc: str, markdown: str) -> str:
    return json.dumps(
        {
            "topic_slug": slug,
            "topic_title": title,
            "topic_description": desc,
            "markdown": markdown,
        }
    )


def _make_organizer(mem, llm: _ScriptedLlm, models: _Models) -> OrganizerService:
    svc = mem.service
    return OrganizerService(
        resolve_store=svc.resolved_store,
        get_config=svc.get_store_config,
        store_ref=svc._recall.store_ref,
        documents=mem.documents,
        retrieval=svc._retrieval,
        reconciler=svc._reconciler,
        llm=llm,
        models=models,
        credential_resolver=lambda ref: "key",
        audit=mem.audit,
        now=lambda: datetime(2026, 6, 21, 12, 0, tzinfo=UTC),
        embedding_resolver=svc._resolve_embedding,
    )


async def _remember(mem, *, body: str, name: str) -> None:
    await mem.service.add_fact(
        scope=MemoryScope.GLOBAL,
        cwd=None,
        name=name,
        description=body[:60],
        body=body,
        actor="agent",
    )


# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="007-memory",
    scenario="the organizer drains the inbox into a topic document",
)
async def test_organizer_drains_inbox_into_topic_doc(mem) -> None:
    await mem.service.ensure_store("global")
    await _remember(mem, body="Deploy via `make release`, never push tags.", name="deploy")
    await _remember(mem, body="Releases are tagged atomically by make release.", name="release")

    llm = _ScriptedLlm(
        [
            # item 1 → creates the topic
            _topic_json(
                "deploy-conventions",
                "Deploy conventions",
                "how we ship",
                "# Deploy\n\nDeploy via `make release`; never push tags directly.",
            ),
            # item 2 FIRST call — item 1's just-written doc isn't indexed mid-run,
            # so retrieval returns no candidate; the LLM never sees item 1's content
            # and (realistically) omits it. A blind write here would clobber item 1.
            _topic_json(
                "deploy-conventions",
                "Deploy conventions",
                "how we ship",
                "# Deploy\n\nReleases are tagged atomically.",
            ),
            # item 2 RE-MERGE — the clobber guard re-runs the merge showing it the
            # existing doc, so item 1's content is integrated rather than erased.
            _topic_json(
                "deploy-conventions",
                "Deploy conventions",
                "how we ship",
                "# Deploy\n\nDeploy via `make release`; never push tags directly.\n"
                "Releases are tagged atomically.",
            ),
        ]
    )
    org = _make_organizer(mem, llm, _Models(_model()))

    result = await org.organize(store_name="global")

    assert result.status == "organized"
    assert result.items_processed == 2
    assert result.skipped == 0
    assert result.model == "llama3"

    store_dir = (await mem.service.resolved_store("global")).store_dir
    # Inbox drained.
    assert list((inbox_dir(store_dir)).glob("*.md")) == []
    # A topic doc exists with the merged content.
    doc = topic_path(store_dir, "deploy-conventions")
    assert doc.exists()
    # BOTH items' content survives — the clobber guard re-merged item 2 against
    # item 1's run-written doc instead of overwriting it.
    doc_text = doc.read_text(encoding="utf-8")
    assert "make release" in doc_text
    assert "tagged atomically" in doc_text
    # INDEX lists it.
    idx = knowledge_index_path(store_dir).read_text(encoding="utf-8")
    assert "deploy-conventions.md" in idx
    # An audit entry was recorded.
    entries = await mem.audit.query(event_type=AuditEventType.MEMORY_ORGANIZED.value)
    assert len(entries) == 1
    # recall returns content from the topic doc, not the (empty) inbox.
    hits, _mode, _fb = await mem.service.recall_in_store(
        store_name="global", query="make release", scope="global"
    )
    assert hits
    # Every hit's source is a topic doc (directly under knowledge/), never the
    # drained inbox subdir.
    assert all("/inbox/" not in h.source for h in hits)
    assert any(h.source.endswith("/knowledge/deploy-conventions.md") for h in hits)


@pytest.mark.acceptance(
    spec="007-memory",
    scenario="organizing merges a note into an existing topic without clobbering it",
)
async def test_organizer_merges_without_clobbering_existing_topic(mem) -> None:
    await mem.service.ensure_store("global")
    store_dir = (await mem.service.resolved_store("global")).store_dir
    # A pre-existing, hand-edited topic doc with content X.
    from coffer.infrastructure.memory.topic_files import TopicDoc, write_topic_doc

    existing_x = "# Testing\n\nX: always run `make verify` before pushing."
    write_topic_doc(
        topic_path(store_dir, "testing"),
        TopicDoc(
            slug="testing",
            title="Testing",
            description="test rules",
            body=existing_x,
            updated_at=datetime(2026, 6, 20, tzinfo=UTC),
        ),
    )
    await _remember(mem, body="Optional engine tests skip locally, run on CI.", name="ci-tests")

    # The LLM returns the existing X plus the new info (a real merge).
    merged = existing_x + "\nOptional engine tests skip locally but run on CI."
    llm = _ScriptedLlm([_topic_json("testing", "Testing", "test rules", merged)])
    org = _make_organizer(mem, llm, _Models(_model()))

    result = await org.organize(store_name="global")

    assert result.status == "organized"
    assert result.topics_updated == 1
    assert result.topics_created == 0
    # The doc STILL contains X (no clobber) AND the new info.
    text = topic_path(store_dir, "testing").read_text(encoding="utf-8")
    assert "always run `make verify`" in text
    assert "run on CI" in text
    # The inbox item is gone.
    assert list((inbox_dir(store_dir)).glob("*.md")) == []
    # The changelog records the merge.
    log = consolidation_log_path(store_dir).read_text(encoding="utf-8")
    assert "merged into 'testing'" in log
    # The LLM was actually given the prior content to merge into.
    assert "always run `make verify`" in llm.user_prompts[0]


@pytest.mark.acceptance(
    spec="007-memory",
    scenario="organize is a no-op when no internal model is configured",
)
async def test_organize_no_model_is_clean_noop(mem) -> None:
    await mem.service.ensure_store("global")
    await _remember(mem, body="Some fact to organize.", name="fact")
    store_dir = (await mem.service.resolved_store("global")).store_dir
    inbox_before = sorted(p.name for p in inbox_dir(store_dir).glob("*.md"))

    llm = _ScriptedLlm([])  # must never be called
    org = _make_organizer(mem, llm, _Models(None))

    result = await org.organize(store_name="global")

    assert result.status == "no_model"
    assert result.model is None
    assert llm.user_prompts == []  # LLM never invoked
    # Inbox untouched; no topic doc written.
    inbox_after = sorted(p.name for p in inbox_dir(store_dir).glob("*.md"))
    assert inbox_after == inbox_before
    from coffer.infrastructure.memory.topic_files import list_topic_docs

    assert list_topic_docs(store_dir) == []


# --- non-acceptance edge cases ---------------------------------------------


async def test_clobber_guard_remerges_against_unretrieved_existing_doc(mem) -> None:
    """Data-loss regression: an existing topic doc that candidate retrieval MISSES
    (the new note shares no terms with it) must NOT be blind-overwritten when the
    LLM coincidentally returns its slug. The clobber guard re-merges with the doc's
    real content so a human edit survives. Without the guard, the first response —
    produced without ever seeing the doc — would erase it."""
    await mem.service.ensure_store("global")
    store_dir = (await mem.service.resolved_store("global")).store_dir
    from coffer.infrastructure.memory.topic_files import TopicDoc, write_topic_doc

    # A hand-edited topic doc whose words are disjoint from the note below, so
    # keyword retrieval deterministically does NOT surface it as a candidate.
    kept = "# Realm\n\nSENTINEL_KEEP_ME umbrella kingdom jupiter zulu."
    write_topic_doc(
        topic_path(store_dir, "realm"),
        TopicDoc(
            slug="realm",
            title="Realm",
            description="kept doc",
            body=kept,
            updated_at=datetime(2026, 6, 20, tzinfo=UTC),
        ),
    )
    await _remember(mem, body="velvet oxygen sandwich nebula.", name="note")

    llm = _ScriptedLlm(
        [
            # First call: no candidate retrieved → the LLM coincidentally returns
            # slug "realm" with markdown that LACKS the sentinel (it never saw it).
            _topic_json("realm", "Realm", "kept doc", "# Realm\n\nvelvet oxygen sandwich."),
            # Re-merge: the guard shows it the real "realm" doc → sentinel preserved.
            _topic_json("realm", "Realm", "kept doc", kept + "\nvelvet oxygen sandwich."),
        ]
    )
    org = _make_organizer(mem, llm, _Models(_model()))

    result = await org.organize(store_name="global")

    assert result.status == "organized"
    # The first call genuinely had NO candidate (retrieval missed) — so the guard
    # path, not a lucky retrieval, is what protected the data.
    assert "no existing topic documents" in llm.user_prompts[0]
    # The re-merge was shown the real doc …
    assert "SENTINEL_KEEP_ME" in llm.user_prompts[1]
    # … and the hand-edited content SURVIVES (no clobber).
    text = topic_path(store_dir, "realm").read_text(encoding="utf-8")
    assert "SENTINEL_KEEP_ME" in text
    assert "velvet oxygen sandwich" in text
    assert list(inbox_dir(store_dir).glob("*.md")) == []


async def test_malformed_llm_output_skips_item_others_organized(mem) -> None:
    await mem.service.ensure_store("global")
    await _remember(mem, body="First good fact about deploys.", name="alpha")
    await _remember(mem, body="Second fact that the LLM mangles.", name="beta")

    # One item parses into a topic; the other returns junk → skipped (stays in
    # the inbox). Items are processed in sorted-filename order, so script the
    # SECOND call as malformed (the exact item it maps to is irrelevant — the
    # invariant is that exactly one is skipped and stays in the inbox).
    responses = [
        _topic_json("deploys", "Deploys", "d", "# Deploys\n\nGood."),
        "this is not json at all {oops",
    ]
    llm = _ScriptedLlm(responses)
    org = _make_organizer(mem, llm, _Models(_model()))

    result = await org.organize(store_name="global")

    assert result.status == "organized"
    assert result.items_processed == 1
    assert result.skipped == 1
    store_dir = (await mem.service.resolved_store("global")).store_dir
    # Exactly one inbox item remains (the one whose response was malformed); its
    # content was NEVER lost.
    remaining = list(inbox_dir(store_dir).glob("*.md"))
    assert len(remaining) == 1
    # The successfully-organized topic doc was written.
    assert topic_path(store_dir, "deploys").exists()


async def test_second_organize_on_empty_inbox_is_noop(mem) -> None:
    await mem.service.ensure_store("global")
    await _remember(mem, body="A fact.", name="fact")
    llm = _ScriptedLlm([_topic_json("facts", "Facts", "f", "# Facts\n\nA fact.")])
    org = _make_organizer(mem, llm, _Models(_model()))
    first = await org.organize(store_name="global")
    assert first.status == "organized"

    # A second run with a now-empty inbox is a clean no-op.
    org2 = _make_organizer(mem, _ScriptedLlm([]), _Models(_model()))
    second = await org2.organize(store_name="global")
    assert second.status == "empty"
    assert second.items_processed == 0


@pytest.mark.acceptance(
    spec="007-memory",
    scenario="a topic document recalls at passage granularity",
)
async def test_topic_doc_recalls_at_passage_granularity(mem) -> None:
    """A multi-section topic doc yields per-passage chunks so recall returns
    the relevant section, not the whole document."""
    await mem.service.ensure_store("global")
    await _remember(mem, body="some note", name="note")

    llm = _ScriptedLlm(
        [
            _topic_json(
                "team-conventions",
                "Team conventions",
                "how the team works",
                "## Alpha process\n\nUse the alphawidget for the alpha flow.\n\n"
                "## Beta process\n\nRun the betagizmo for the beta flow.",
            ),
        ]
    )
    org = _make_organizer(mem, llm, _Models(_model()))
    result = await org.organize(store_name="global")
    assert result.status == "organized"

    hits, _mode, _fb = await mem.service.recall_in_store(
        store_name="global", query="betagizmo", scope="global"
    )
    assert hits
    top = hits[0]
    assert "betagizmo" in top.text  # the Beta passage came back
    assert "alphawidget" not in top.text  # passage granularity: NOT the whole doc
    assert "/inbox/" not in top.source  # recall isolation intact (topic doc, not inbox)


async def test_index_and_changelog_never_surface_in_recall(mem) -> None:
    await mem.service.ensure_store("global")
    await _remember(mem, body="Recallable content marker ZEBRA.", name="zebra")
    llm = _ScriptedLlm(
        [_topic_json("zebra-topic", "Zebra topic", "z", "# Zebra\n\nContent marker ZEBRA.")]
    )
    org = _make_organizer(mem, llm, _Models(_model()))
    await org.organize(store_name="global")

    store_dir = (await mem.service.resolved_store("global")).store_dir
    # INDEX.md and the store-root changelog both exist on disk …
    assert knowledge_index_path(store_dir).exists()
    assert consolidation_log_path(store_dir).exists()

    # … but neither surfaces in recall (grep mode reaches every file under the
    # store dir, so this is the strict check).
    hits, _mode, _fb = await mem.service.recall_in_store(
        store_name="global", query="ZEBRA", scope="global", mode="grep"
    )
    for h in hits:
        assert "INDEX.md" not in h.source
        assert "consolidation-log.md" not in h.source


@pytest.mark.acceptance(
    spec="007-memory",
    scenario="the organizer routes a rule-shaped note into the rules lane",
)
async def test_organizer_routes_rule_into_rules_lane(mem) -> None:
    await mem.service.ensure_store("global")
    # Remember a rule-shaped note and an ordinary deploy note.
    await _remember(mem, body="Always run make verify before pushing to CI.", name="rule-note")
    await _remember(mem, body="Deploy via `make release`; never push tags.", name="deploy-note")

    rule_text = "Always run make verify before pushing to CI."
    rule_json = json.dumps(
        {
            "is_rule": True,
            "topic_slug": "",
            "topic_title": "",
            "topic_description": "",
            "markdown": rule_text,
        }
    )
    topic_response = _topic_json(
        "deploy-conventions",
        "Deploy conventions",
        "how we ship",
        "# Deploy\n\nDeploy via `make release`; never push tags directly.",
    )

    llm = _ScriptedLlm([rule_json, topic_response])
    org = _make_organizer(mem, llm, _Models(_model()))

    result = await org.organize(store_name="global")

    assert result.status == "organized"
    assert result.rules_appended == 1

    store_dir = (await mem.service.resolved_store("global")).store_dir
    rpath = rules_path(store_dir)
    assert rpath.exists(), "rules/rules.md should exist"
    rules_text = rpath.read_text(encoding="utf-8")
    assert rule_text in rules_text

    # The rule text must NOT appear in any knowledge/<topic>.md
    knowledge_lane = store_dir / "knowledge"
    for md_file in knowledge_lane.glob("*.md"):
        if md_file.name == "INDEX.md":
            continue
        content = md_file.read_text(encoding="utf-8")
        assert rule_text not in content, f"rule text leaked into topic doc {md_file.name}"

    # Ordinary item became a topic doc
    assert topic_path(store_dir, "deploy-conventions").exists()

    # Inbox drained (both items processed)
    assert list(inbox_dir(store_dir).glob("*.md")) == []
    assert result.items_processed == 2

    # topics_created counts only non-rule items
    assert result.topics_created == 1

    # Recall does NOT return a hit from rules/
    hits, _mode, _fb = await mem.service.recall_in_store(
        store_name="global", query="make verify", scope="global"
    )
    for h in hits:
        assert "/rules/" not in h.source, f"rules/ path appeared in recall: {h.source}"
