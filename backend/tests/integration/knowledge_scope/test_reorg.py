"""Integration tests for the notes tidy pass over the real stack (spec knowledge).

Extends the ``mem`` harness (real SQLite + real note files + real ripgrep) with
a fake ``AgenticReorgPort`` that drives the REAL ``run_agentic_reorg`` loop (a
``GenericFakeChatModel`` emitting scripted tool calls), so the langgraph tool
plumbing is exercised without ever reaching an LLM.

One lane, four tools — ``list_notes`` / ``read_note`` / ``write_note`` /
``delete_note`` — and one hidden archive: every revision the pass replaces (or
deletes) lands in ``<scope>/.history/``, which is dot-prefixed so neither the
lane scan nor ripgrep can hand it back as a live result.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.application.knowledge.reorg import ReorgService
from coffer.application.knowledge.reorg_deps import reorg_collaborators_from_service
from coffer.domain.knowledge.document import KIND_KNOWLEDGE, LANE_NOTES
from coffer.domain.provider.config import Protocol, ProviderConfig, ResolvedConnection
from coffer.infrastructure.knowledge.paths import history_dir, note_path
from coffer.infrastructure.knowledge_scope.note_files import write_note

NOW = datetime(2026, 6, 21, 12, 0, tzinfo=UTC)


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


class _CountingScript:
    """The scripted turns, counting how many the loop actually consumed."""

    def __init__(self, scripted: list[Any]) -> None:
        self.total = len(scripted)
        self.consumed = 0
        self._it = iter(scripted)

    def __iter__(self) -> _CountingScript:
        return self

    def __next__(self) -> Any:
        turn = next(self._it)
        self.consumed += 1
        return turn


def _fake_chat_model(script: _CountingScript) -> Any:
    """A GenericFakeChatModel whose bind_tools is a no-op (returns self)."""
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

    class _Model(GenericFakeChatModel):
        def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
            return self

    return _Model(messages=script)


class _FakeAgent:
    """AgenticReorgPort that runs the real reorg loop with a scripted model."""

    def __init__(self, scripted: list[Any]) -> None:
        self.script = _CountingScript(scripted)
        self.calls = 0

    async def run(
        self,
        *,
        model: ResolvedConnection,
        tools: Any,
        system_prompt: str,
        credential_resolver: Any,
        recursion_limit: int,
    ) -> dict[str, Any]:
        from coffer.infrastructure.llm.agentic_reorg import run_agentic_reorg

        self.calls += 1
        return await run_agentic_reorg(
            lc_model=_fake_chat_model(self.script),
            tools=tools,
            system_prompt=system_prompt,
            recursion_limit=recursion_limit,
        )


class _NeverCalledAgent:
    """AgenticReorgPort that fails the test if the loop is armed at all."""

    def __init__(self, why: str) -> None:
        self._why = why

    async def run(self, **_: Any) -> dict[str, Any]:
        raise AssertionError(f"agent loop must not run {self._why}")


def _tool_call(call_id: str, name: str, args: dict[str, Any]) -> Any:
    from langchain_core.messages import AIMessage

    return AIMessage(
        content="",
        tool_calls=[{"id": call_id, "name": name, "args": args, "type": "tool_call"}],
    )


def _done(text: str = "Done.") -> Any:
    from langchain_core.messages import AIMessage

    return AIMessage(content=text)


def _make_reorg(mem: Any, agent: Any, models: _Models) -> ReorgService:
    deps = reorg_collaborators_from_service(mem.service)
    return ReorgService(
        resolve_store=deps.resolve_store,
        get_config=deps.get_config,
        store_ref=deps.store_ref,
        documents=deps.documents,
        retrieval=deps.retrieval,
        reconciler=deps.reconciler,
        agent=agent,
        models=models,
        audit=mem.audit,
        credential_resolver=lambda ref: "key",
        now=lambda: NOW,
        embedding_resolver=deps.embedding_resolver,
    )


def _seed_note(store_dir: Any, slug: str, title: str, body: str) -> None:
    """Seed one note directly on disk (the tidy pass's input)."""
    write_note(
        store_dir,
        slug,
        title=title,
        summary=title,
        body=body,
        now=datetime(2026, 6, 20, tzinfo=UTC),
    )


async def _store_dir(mem: Any) -> Any:
    await mem.service.ensure_scope("global")
    return (await mem.service.resolved_scope("global")).store_dir


async def _tidy_events(mem: Any) -> Any:
    """Every ``knowledge_tidied`` audit entry recorded for the global scope."""
    return await mem.audit.query(kind=KIND_KNOWLEDGE, name="global", event_type="knowledge_tidied")


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="the reorg pass consolidates duplicate topic documents",
)
async def test_reorg_consolidates_duplicate_notes(mem: Any) -> None:
    """Two overlapping notes are merged into one; the redundant one is removed
    from the lane, the merged text is what search returns, and the pass is
    audited."""
    store_dir = await _store_dir(mem)

    _seed_note(store_dir, "deploy-a", "Deploy A", "# Deploy A\n\nDeploy via make release.")
    _seed_note(store_dir, "deploy-b", "Deploy B", "# Deploy B\n\nReleases are tagged atomically.")

    scripted = [
        _tool_call("c1", "list_notes", {}),
        _tool_call("c2", "read_note", {"slug": "deploy-a"}),
        _tool_call("c3", "read_note", {"slug": "deploy-b"}),
        _tool_call(
            "c4",
            "write_note",
            {
                "slug": "deploy-a",
                "title": "Deploy conventions",
                "summary": "How we ship",
                "markdown": (
                    "# Deploy\n\nDeploy via make release.\nReleases are tagged atomically."
                ),
            },
        ),
        _tool_call("c5", "delete_note", {"slug": "deploy-b"}),
        _done("Consolidation complete."),
    ]

    result = await _make_reorg(mem, _FakeAgent(scripted), _Models(_model())).reorg(
        scope_name="global"
    )

    assert result.status == "reorganized"
    assert result.notes_before == 2
    assert result.notes_after == 1
    assert result.notes_written == 1
    assert result.notes_archived == 1
    assert result.model == "llama3"

    merged = note_path(store_dir, "deploy-a").read_text(encoding="utf-8")
    assert "make release" in merged
    assert "tagged atomically" in merged
    assert not note_path(store_dir, "deploy-b").exists()

    # The merged content is what a subsequent search returns, and it comes from
    # the surviving note — the redundant one is gone from the index too.
    hits, _mode, _fb = await mem.service.recall_in_scope(
        scope_name="global", query="atomically", scope="global"
    )
    assert hits, "the merged note must be searchable"
    assert all("deploy-b" not in h.source for h in hits)
    assert any("deploy-a" in h.source and "tagged atomically" in h.text for h in hits)

    # The pass is recorded in the audit log with what it actually changed.
    events = await _tidy_events(mem)
    assert len(events) == 1
    assert events[0].details["notes_written"] == 1
    assert events[0].details["notes_archived"] == 1
    assert events[0].details["model"] == "llama3"


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="reorg never destroys content — a superseded topic stays recoverable",
)
async def test_reorg_replaced_revision_stays_in_history(mem: Any) -> None:
    """The revision the pass overwrites lands in ``.history/`` holding the OLD
    text — the live note no longer has it, the archive does."""
    store_dir = await _store_dir(mem)

    _seed_note(store_dir, "alpha", "Alpha", "# Alpha\n\nOriginal wording SENTINEL_ONLY_OLD.")

    scripted = [
        _tool_call("c1", "list_notes", {}),
        _tool_call("c2", "read_note", {"slug": "alpha"}),
        _tool_call(
            "c3",
            "write_note",
            {
                "slug": "alpha",
                "title": "Alpha",
                "summary": "Alpha note",
                "markdown": "# Alpha\n\nRewritten wording SENTINEL_ONLY_NEW.",
            },
        ),
        _done(),
    ]

    result = await _make_reorg(mem, _FakeAgent(scripted), _Models(_model())).reorg(
        scope_name="global"
    )

    assert result.status == "reorganized"
    assert result.notes_written == 1

    live = note_path(store_dir, "alpha").read_text(encoding="utf-8")
    assert "SENTINEL_ONLY_NEW" in live
    assert "SENTINEL_ONLY_OLD" not in live

    archived = sorted(history_dir(store_dir).glob("alpha-*.md"))
    assert len(archived) == 1, "the replaced revision must be archived under .history/"
    archived_text = archived[0].read_text(encoding="utf-8")
    assert "SENTINEL_ONLY_OLD" in archived_text
    assert "SENTINEL_ONLY_NEW" not in archived_text

    # The archive is a sibling of the lane, not a note: it never re-enters the
    # index as a duplicate of the note it supersedes.
    docs = await mem.documents.list_documents(KIND_KNOWLEDGE, "global", lane=LANE_NOTES)
    assert [d.id for d in docs] == ["alpha"]

    events = await _tidy_events(mem)
    assert len(events) == 1


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="reorg is a no-op when no internal model is configured",
)
async def test_reorg_no_model_is_clean_noop(mem: Any) -> None:
    """No internal model → ``status='no_model'``, the loop is never armed, and
    nothing on disk moves (not even a ``.history/`` dir)."""
    store_dir = await _store_dir(mem)
    _seed_note(store_dir, "existing", "Existing", "# Existing\n\nShould survive.")

    agent = _NeverCalledAgent("when no model is configured")
    result = await _make_reorg(mem, agent, _Models(None)).reorg(scope_name="global")

    assert result.status == "no_model"
    assert result.model is None
    assert result.notes_before == 0
    assert result.notes_after == 0
    assert result.notes_written == 0
    assert result.notes_archived == 0

    text = note_path(store_dir, "existing").read_text(encoding="utf-8")
    assert "Should survive" in text
    assert not history_dir(store_dir).exists()
    assert await _tidy_events(mem) == []


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="a topic document recalls at passage granularity",
)
async def test_tidied_note_recalls_at_passage_granularity(mem: Any) -> None:
    """A multi-section note the tidy pass wrote is chunked per passage, so a
    query hitting the second section gets that section — not the whole note."""
    store_dir = await _store_dir(mem)
    _seed_note(store_dir, "scratch", "Scratch", "# Scratch\n\nUnsorted notes about processes.")

    scripted = [
        _tool_call("c1", "list_notes", {}),
        _tool_call(
            "c2",
            "write_note",
            {
                "slug": "team-conventions",
                "title": "Team conventions",
                "summary": "how the team works",
                "markdown": (
                    "## Alpha process\n\nUse the alphawidget for the alpha flow.\n\n"
                    "## Beta process\n\nRun the betagizmo for the beta flow."
                ),
            },
        ),
        _tool_call("c3", "delete_note", {"slug": "scratch"}),
        _done(),
    ]

    result = await _make_reorg(mem, _FakeAgent(scripted), _Models(_model())).reorg(
        scope_name="global"
    )
    assert result.status == "reorganized"

    hits, _mode, _fb = await mem.service.recall_in_scope(
        scope_name="global", query="betagizmo", scope="global"
    )
    assert hits, "the tidied note must be searchable"
    top = hits[0]
    assert "betagizmo" in top.text  # the Beta passage came back
    assert "alphawidget" not in top.text  # …as a passage, not the whole note
    assert "team-conventions" in top.source


# ---------------------------------------------------------------------------
# The archive stays invisible to retrieval
# ---------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("rg") is None, reason="grep mode needs the rg binary")
async def test_history_copy_never_surfaces_in_grep_recall(mem: Any) -> None:
    """Grep reaches every file under the scope dir, so this is the strict check
    that ``.history/`` is excluded: the marker is in BOTH the live note and its
    archived revision, and only the live one may come back."""
    store_dir = await _store_dir(mem)
    _seed_note(store_dir, "zebra", "Zebra", "# Zebra\n\nContent marker ZEBRAMARK, first draft.")

    scripted = [
        _tool_call("c1", "list_notes", {}),
        _tool_call(
            "c2",
            "write_note",
            {
                "slug": "zebra",
                "title": "Zebra",
                "summary": "zebra",
                "markdown": "# Zebra\n\nContent marker ZEBRAMARK, rewritten.",
            },
        ),
        _done(),
    ]
    await _make_reorg(mem, _FakeAgent(scripted), _Models(_model())).reorg(scope_name="global")

    # Both copies carry the marker on disk …
    archived = sorted(history_dir(store_dir).glob("zebra-*.md"))
    assert len(archived) == 1
    assert "ZEBRAMARK" in archived[0].read_text(encoding="utf-8")

    # … but only the live note is reachable.
    hits, mode, _fb = await mem.service.recall_in_scope(
        scope_name="global", query="ZEBRAMARK", scope="global", mode="grep"
    )
    assert mode == "grep"
    assert hits, "the live note must still be grep-able"
    assert all(".history" not in h.source for h in hits)
    assert any("notes/zebra.md" in h.source for h in hits)


# ---------------------------------------------------------------------------
# The pass finalizes from on-disk state whatever the loop does
# ---------------------------------------------------------------------------


async def test_raising_agent_loop_still_finalizes_from_disk(mem: Any) -> None:
    """A loop that dies mid-way (a dead model connection) must not propagate:
    the pass finalizes from what the tools actually landed."""
    store_dir = await _store_dir(mem)
    _seed_note(store_dir, "keep", "Keep", "# Keep\n\nKeep this.")
    _seed_note(store_dir, "drop", "Drop", "# Drop\n\nFold this away.")

    class _RaisingAgent:
        async def run(self, *, tools: Any, **_: Any) -> dict[str, Any]:
            by_name = {t.name: t for t in tools}
            await by_name["write_note"].handler(
                {
                    "slug": "keep",
                    "title": "Keep",
                    "summary": "merged",
                    "markdown": "# Keep\n\nKeep this. Fold this away.",
                }
            )
            await by_name["delete_note"].handler({"slug": "drop"})
            raise RuntimeError("the model connection died mid-loop")

    result = await _make_reorg(mem, _RaisingAgent(), _Models(_model())).reorg(scope_name="global")

    assert result.status == "reorganized"
    assert result.notes_before == 2
    assert result.notes_after == 1  # counted from disk after the raise
    assert result.notes_written == 1
    assert result.notes_archived == 1

    merged = note_path(store_dir, "keep").read_text(encoding="utf-8")
    assert "Fold this away." in merged
    assert not note_path(store_dir, "drop").exists()

    # The final reconcile still ran: the index reflects the post-raise lane.
    docs = await mem.documents.list_documents(KIND_KNOWLEDGE, "global", lane=LANE_NOTES)
    assert [d.id for d in docs] == ["keep"]


async def test_recursion_overflow_still_finalizes_from_disk(mem: Any) -> None:
    """A loop that overruns its recursion limit finalizes the same way: the
    counters report the tool calls that landed before the overflow."""
    store_dir = await _store_dir(mem)
    _seed_note(store_dir, "note-a", "Note A", "# A\n\nContent A.")
    _seed_note(store_dir, "note-b", "Note B", "# B\n\nContent B.")

    scripted = [
        _tool_call(
            "c1",
            "write_note",
            {
                "slug": "note-a",
                "title": "Note A",
                "summary": "merged",
                "markdown": "# A\n\nContent A. Content B.",
            },
        ),
        _tool_call("c2", "delete_note", {"slug": "note-b"}),
    ]
    # DEFAULT_REORG_RECURSION_LIMIT is 24 steps; far more list_notes turns than
    # can fit, so the loop is guaranteed to overrun rather than run dry.
    scripted += [_tool_call(f"c{i}", "list_notes", {}) for i in range(3, 60)]

    agent = _FakeAgent(scripted)
    result = await _make_reorg(mem, agent, _Models(_model())).reorg(scope_name="global")

    # The loop really was cut short — it never reached the end of the script.
    assert agent.script.consumed < agent.script.total

    assert result.status == "reorganized"
    assert result.notes_before == 2
    assert result.notes_after == 1
    assert result.notes_written == 1
    assert result.notes_archived == 1

    assert "Content B." in note_path(store_dir, "note-a").read_text(encoding="utf-8")
    assert not note_path(store_dir, "note-b").exists()

    docs = await mem.documents.list_documents(KIND_KNOWLEDGE, "global", lane=LANE_NOTES)
    assert [d.id for d in docs] == ["note-a"]


async def test_empty_lane_is_clean_noop(mem: Any) -> None:
    """A scope with no notes short-circuits before the loop and touches
    nothing."""
    store_dir = await _store_dir(mem)

    agent = _NeverCalledAgent("when the lane is empty")
    result = await _make_reorg(mem, agent, _Models(_model())).reorg(scope_name="global")

    assert result.status == "empty"
    assert result.notes_before == 0
    assert result.notes_after == 0
    assert result.notes_written == 0
    assert result.notes_archived == 0
    assert result.model == "llama3"

    assert not history_dir(store_dir).exists()
    assert await _tidy_events(mem) == []


# ---------------------------------------------------------------------------
# Tool-level error handling
# ---------------------------------------------------------------------------


async def test_read_note_missing_slug_returns_error_not_raise(mem: Any) -> None:
    """``read_note`` on a slug that isn't there answers with an error dict, so
    the loop keeps going and the pass still finalizes."""
    store_dir = await _store_dir(mem)
    _seed_note(store_dir, "real", "Real", "# Real\n\nExists.")

    scripted = [
        _tool_call("c1", "read_note", {"slug": "nonexistent"}),
        _done("Note not found; nothing to do."),
    ]

    result = await _make_reorg(mem, _FakeAgent(scripted), _Models(_model())).reorg(
        scope_name="global"
    )

    assert result.status == "reorganized"
    assert result.notes_before == 1
    assert result.notes_after == 1
    assert result.notes_written == 0
    assert result.notes_archived == 0
    assert not history_dir(store_dir).exists()


async def test_write_note_traversal_slug_rejected_without_writing(mem: Any) -> None:
    """A traversal slug is refused by the path guard: no file is created, the
    counters stay at zero, and the existing note is untouched."""
    store_dir = await _store_dir(mem)
    _seed_note(store_dir, "safe", "Safe", "# Safe\n\nContent.")

    scripted = [
        _tool_call(
            "c1",
            "write_note",
            {
                "slug": "../evil",
                "title": "Evil",
                "summary": "bad",
                "markdown": "# Evil",
            },
        ),
        _done("Got an error; aborting."),
    ]

    result = await _make_reorg(mem, _FakeAgent(scripted), _Models(_model())).reorg(
        scope_name="global"
    )

    assert result.status == "reorganized"
    assert result.notes_written == 0
    assert result.notes_after == 1
    assert "Content." in note_path(store_dir, "safe").read_text(encoding="utf-8")
    assert not (store_dir.parent / "evil.md").exists()


async def test_delete_note_missing_slug_does_not_count_as_archived(mem: Any) -> None:
    """Deleting a note that isn't there is an error dict, not an archive."""
    store_dir = await _store_dir(mem)
    _seed_note(store_dir, "only", "Only", "# Only\n\nStill here.")

    scripted = [
        _tool_call("c1", "delete_note", {"slug": "ghost"}),
        _done(),
    ]

    result = await _make_reorg(mem, _FakeAgent(scripted), _Models(_model())).reorg(
        scope_name="global"
    )

    assert result.status == "reorganized"
    assert result.notes_archived == 0
    assert result.notes_after == 1
    assert note_path(store_dir, "only").exists()
    assert not history_dir(store_dir).exists()
