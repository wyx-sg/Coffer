"""The idle arm of ``NotesTidyTrigger``, over the real stack (spec knowledge).

Real ``KnowledgeService`` → real ``ReorgService`` → real ``notes/`` files: the
only stand-in is the agentic port, which here merges the lane by calling the
pass's own tools directly (no LLM, no langgraph). The trigger is wired exactly
as the composition root wires it — ``set_on_change(trigger.on_change)`` — so a
write really does re-arm the idle timer that fires the pass.
"""

from __future__ import annotations

import asyncio
import pathlib
from datetime import UTC, datetime
from typing import Any

from coffer.application.knowledge.reorg import ReorgService
from coffer.application.knowledge.reorg_deps import reorg_collaborators_from_service
from coffer.application.knowledge.tidy_trigger import NotesTidyTrigger
from coffer.domain.knowledge.scope import KnowledgeScope
from coffer.domain.provider.config import Protocol, ProviderConfig, ResolvedConnection
from coffer.infrastructure.knowledge.paths import history_dir, note_path
from coffer.infrastructure.knowledge_scope.note_files import list_notes

MERGED_SLUG = "tidied-notes"


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
    async def get_default(self) -> ResolvedConnection:
        return _model()


class _MergingAgent:
    """AgenticReorgPort that folds every note into one, via the real tools.

    Stands in for the LLM only — the writes, the archiving and the counters are
    all production code, reached through the very handlers the loop would call.
    """

    def __init__(self) -> None:
        self.calls = 0

    async def run(self, *, tools: Any, **_: Any) -> dict[str, Any]:
        self.calls += 1
        by_name = {t.name: t for t in tools}
        listed = await by_name["list_notes"].handler({})
        bodies: list[str] = []
        for note in listed["notes"]:
            if note["slug"] == MERGED_SLUG:
                continue
            read = await by_name["read_note"].handler({"slug": note["slug"]})
            bodies.append(read["body"])
            await by_name["delete_note"].handler({"slug": note["slug"]})
        await by_name["write_note"].handler(
            {
                "slug": MERGED_SLUG,
                "title": "Tidied notes",
                "summary": "everything, merged",
                "markdown": "\n\n".join(bodies),
            }
        )
        return {"messages": []}


def _make_trigger(mem: Any, agent: _MergingAgent, *, idle_delay_seconds: float) -> NotesTidyTrigger:
    deps = reorg_collaborators_from_service(mem.service)
    reorg = ReorgService(
        resolve_store=deps.resolve_store,
        get_config=deps.get_config,
        store_ref=deps.store_ref,
        documents=deps.documents,
        retrieval=deps.retrieval,
        reconciler=deps.reconciler,
        agent=agent,
        models=_Models(),
        audit=mem.audit,
        credential_resolver=lambda ref: "key",
        now=lambda: datetime.now(tz=UTC),
        embedding_resolver=deps.embedding_resolver,
    )

    async def list_scopes() -> list[str]:
        return ["global"]

    trigger = NotesTidyTrigger(
        tidy=reorg,
        list_scopes=list_scopes,
        idle_delay_seconds=idle_delay_seconds,
        # The interval sweep is a separate arm; ``run()`` is never started here,
        # so the only thing that can fire the pass is the idle timer.
        interval_seconds=3600.0,
    )
    mem.service.set_on_change(trigger.on_change)
    return trigger


async def _write_fact(mem: Any, *, title: str, body: str) -> Any:
    return await mem.service.add_fact(
        scope=KnowledgeScope.GLOBAL,
        cwd=None,
        title=title,
        description=body,
        body=body,
        actor="agent",
    )


async def _wait_for(predicate: Any, *, timeout: float = 5.0) -> bool:
    """Poll until ``predicate()`` is true (the timer is wall-clock, not fake)."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return False


async def test_idle_timer_fires_the_tidy_pass_over_the_notes_lane(mem: Any) -> None:
    """A write arms the idle timer; when it fires, the pass really rewrites the
    ``notes/`` lane and archives what it replaced."""
    agent = _MergingAgent()
    trigger = _make_trigger(mem, agent, idle_delay_seconds=0.02)
    try:
        await mem.service.ensure_scope("global")
        store_dir: pathlib.Path = (await mem.service.resolved_scope("global")).store_dir

        await _write_fact(mem, title="deploy", body="Deploy via make release. Marker TIDYME.")
        seeded = list_notes(store_dir)
        assert len(seeded) == 1, "the write must land in notes/ before any tidying"
        fact_slug = seeded[0].slug
        fact_note = note_path(store_dir, fact_slug)

        fired = await _wait_for(lambda: note_path(store_dir, MERGED_SLUG).exists())
        assert fired, "the idle timer should have fired the tidy pass"
        assert agent.calls == 1

        merged = note_path(store_dir, MERGED_SLUG).read_text(encoding="utf-8")
        assert "Marker TIDYME." in merged, "the pass must carry the note's content over"

        # The note it folded away left the lane and is recoverable under .history/.
        assert not fact_note.exists()
        assert [n.slug for n in list_notes(store_dir)] == [MERGED_SLUG]
        archived = sorted(history_dir(store_dir).glob(f"{fact_slug}-*.md"))
        assert len(archived) == 1
        assert "Marker TIDYME." in archived[0].read_text(encoding="utf-8")
    finally:
        await trigger.shutdown()


async def test_shutdown_before_the_timer_leaves_the_notes_lane_untouched(mem: Any) -> None:
    """``shutdown()`` drops a pending idle timer without firing it."""
    agent = _MergingAgent()
    trigger = _make_trigger(mem, agent, idle_delay_seconds=0.5)
    await mem.service.ensure_scope("global")
    store_dir: pathlib.Path = (await mem.service.resolved_scope("global")).store_dir

    await _write_fact(mem, title="deploy", body="Deploy via make release.")
    seeded = [n.slug for n in list_notes(store_dir)]
    assert len(seeded) == 1

    await trigger.shutdown()
    # Well past the idle delay: had the timer survived, the pass would have run.
    await asyncio.sleep(0.7)

    assert agent.calls == 0
    assert not note_path(store_dir, MERGED_SLUG).exists()
    assert [n.slug for n in list_notes(store_dir)] == seeded
    assert not history_dir(store_dir).exists()
