"""A file dropped into ``sources/`` by hand is curated with no import step.

This is the promise that makes the layer a directory rather than a database
(spec knowledge FR-015): a person drags a Markdown file into
``~/.coffer/knowledge/<collection>/sources/`` in Finder and Coffer picks it up.
Nothing registers it, nothing indexes it and no row is written, so the only
thing that can notice it is the sweep comparing each file's modification time
with its own ``coffer_ingested_at`` frontmatter (FR-022, FR-028).

Driven through the real ``CurationWorker`` over a real directory, because that
comparison is the whole mechanism and a fake of either side would be testing
the fake. The only thing standing in for the world is the agentic loop: it is
an LLM call, which the tier does not make. It is scripted to write one topic
document, which is what a model absorbing this source would do.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.application.knowledge.curate import CurationPass
from coffer.application.knowledge.curate_worker import CurationWorker
from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.application.upkeep_runs import UpkeepRunRegistry
from coffer.domain.errors import ResourceNotFound
from coffer.domain.resource import Resource
from coffer.infrastructure.knowledge import catalogue, fs, paths

_DROPPED = "The account gateway owns the session cache.\n"


class _Resources:
    """Just enough ``ResourceService`` for ``enabled_collections``."""

    def __init__(self, names: list[str]) -> None:
        now = datetime.now(tz=UTC)
        self._rows = [
            Resource(
                id=i,
                # A uid a test can spell, and deliberately not the name: a
                # lookup that worked because the two matched would prove
                # nothing about addressing a collection by identity.
                uid=f"uid-{i}",
                kind=KIND_KNOWLEDGE,
                name=name,
                description=None,
                config={},
                enabled=True,
                created_at=now,
                updated_at=now,
                scope=None,
            )
            for i, name in enumerate(names, start=1)
        ]

    async def get(self, uid):  # type: ignore[no-untyped-def]
        for row in self._rows:
            if row.uid == uid:
                return row
        raise ResourceNotFound(uid)

    def uid_of(self, name: str) -> str:
        """The uid a test knows the collection by its name — the resolution a
        person's CLI or the web page does before anything inside the daemon
        is handed an identity."""
        return next(r.uid for r in self._rows if r.name == name)

    async def list(self, kind=None, enabled=None):  # type: ignore[no-untyped-def]
        return list(self._rows)


class _Audit:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def record(self, event_type, **kwargs):  # type: ignore[no-untyped-def]
        self.events.append(event_type)


class _Models:
    async def get_default(self):  # type: ignore[no-untyped-def]
        return type("C", (), {"model": "fake-model"})()


class _Loop:
    """A scripted agentic loop: absorbs whatever brief it is given into one
    topic document. Records the brief so the test can assert the dropped file
    is what reached the model."""

    def __init__(self) -> None:
        self.briefs: list[str] = []

    async def run(self, *, tools, user_prompt, **kwargs: Any) -> dict[str, Any]:
        self.briefs.append(user_prompt)
        write = next(t for t in tools if t.name == "write_topic")
        await write.handler(
            {
                "title": "Session cache",
                "description": "Which service owns the session cache",
                "body": _DROPPED.strip(),
            }
        )
        return {}


@pytest.fixture
def corpus(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    root = tmp_path / "knowledge"
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(root))
    fs.create_collection_dir("shopee")
    return root


def _worker(service: KnowledgeService, loop: _Loop) -> CurationWorker:
    async def _collections() -> list[str]:
        # Uids, as the composition root's own lister yields: the sweep claims
        # and curates by identity, never by the directory's name.
        return ["uid-1"]

    async def _enabled() -> bool:
        return True

    return CurationWorker(
        service=service,
        curate=CurationPass(agent=loop, models=_Models(), credential_resolver=lambda ref: "key"),
        is_enabled=_enabled,
        deliver=None,
        list_collections=_collections,
        runs=UpkeepRunRegistry(),
    )


@pytest.mark.acceptance(
    spec="knowledge", scenario="a source added out-of-band is curated by the next sweep"
)
@pytest.mark.anyio
async def test_a_file_dropped_into_sources_is_picked_up_by_the_next_sweep(corpus) -> None:  # type: ignore[no-untyped-def]
    # A file manager's write: no frontmatter, no registration, no conversion —
    # just bytes appearing in the lane.
    dropped = paths.sources_dir("shopee") / "dropped-by-hand.md"
    dropped.write_text(_DROPPED, encoding="utf-8")

    service = KnowledgeService(resources=_Resources(["shopee"]), audit=_Audit())
    loop = _Loop()
    await _worker(service, loop).run_once()

    # The fact the file stated is now in the lane an agent reads.
    [topic] = catalogue.walk_files(paths.topics_dir("shopee"))
    assert topic.path == "shopee/topics/session-cache.md"
    assert "session cache" in fs.read_file(topic.path).body

    # And it got there from THIS file: the brief the model saw carried it.
    assert _DROPPED.strip() in loop.briefs[0]

    # The watermark is written into the person's own file, which is what makes
    # the next sweep a no-op without any state Coffer has to keep (FR-028).
    assert fs.read_file(dropped_relpath()).ingested_at != ""
    assert fs.pending_sources("shopee") == ()


@pytest.mark.anyio
async def test_the_sweep_does_not_rewrite_the_dropped_file(corpus) -> None:  # type: ignore[no-untyped-def]
    """It is the person's file. Curation may stamp it and nothing else — the
    body, and any frontmatter they wrote themselves, come through untouched
    (FR-013, FR-028)."""
    dropped = paths.sources_dir("shopee") / "dropped-by-hand.md"
    dropped.write_text(
        f"---\ntitle: My own title\ndescription: what I wrote\nactor: user\n---\n\n{_DROPPED}",
        encoding="utf-8",
    )

    service = KnowledgeService(resources=_Resources(["shopee"]), audit=_Audit())
    await _worker(service, _Loop()).run_once()

    after = fs.read_file(dropped_relpath())
    assert after.title == "My own title"
    assert after.description == "what I wrote"
    assert after.actor == "user"
    assert after.body.strip() == _DROPPED.strip()


@pytest.mark.anyio
async def test_a_second_sweep_starts_no_pass_until_the_file_changes(corpus) -> None:  # type: ignore[no-untyped-def]
    """The watermark is what stops a corpus being re-curated every minute."""
    dropped = paths.sources_dir("shopee") / "dropped-by-hand.md"
    dropped.write_text(_DROPPED, encoding="utf-8")

    service = KnowledgeService(resources=_Resources(["shopee"]), audit=_Audit())
    loop = _Loop()
    worker = _worker(service, loop)

    await worker.run_once()
    await worker.run_once()
    assert len(loop.briefs) == 1

    # Edited in the same editor it arrived from: owed again, no registration.
    dropped.write_text(f"{_DROPPED}The cache is Redis.\n", encoding="utf-8")
    await worker.run_once()
    assert len(loop.briefs) == 2
    assert "The cache is Redis." in loop.briefs[1]


def dropped_relpath() -> str:
    return "shopee/sources/dropped-by-hand.md"
