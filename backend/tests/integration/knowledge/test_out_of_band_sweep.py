"""A document edited by hand is curated with no import step.

This is the promise that makes the layer a directory rather than a database
(spec knowledge FR-015): a person edits a Markdown file under
``~/.coffer/knowledge/<collection>/`` in their own editor — or drops a new one
in with Finder — and Coffer carries the edit into the rest of the collection.
Nothing registers it, nothing indexes it and no row is written, so the only
thing that can notice it is the sweep comparing each document's modification
time with its own ``coffer_curated_at`` frontmatter (FR-022, FR-028).

The sweep owes material in the hidden inbox first: until it is merged, it is
knowledge no agent can read, whereas an edited document is readable as it
stands.

Driven through the real ``CurationWorker`` over a real directory, because that
comparison is the whole mechanism and a fake of either side would be testing
the fake. The only thing standing in for the world is the agentic loop: it is
an LLM call, which the tier does not make. It is scripted to write one
document, which is what a model carrying this edit outward would do.
"""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.application.knowledge.curate import CurationPass
from coffer.application.knowledge.curate_worker import CurationWorker
from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.application.upkeep_runs import UpkeepRunRegistry
from coffer.domain.errors import ResourceNotFound
from coffer.domain.resource import Resource
from coffer.infrastructure.knowledge import fs, paths

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
    """A scripted agentic loop: absorbs whatever brief it is given into one new
    document, named after the pass. Records the brief so the test can assert
    which item reached the model."""

    def __init__(self) -> None:
        self.briefs: list[str] = []

    async def run(self, *, tools, user_prompt, **kwargs: Any) -> dict[str, Any]:
        self.briefs.append(user_prompt)
        write = next(t for t in tools if t.name == "write_document")
        await write.handler(
            {
                "title": f"Session cache {len(self.briefs)}",
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


def _drop(name: str, text: str) -> pathlib.Path:
    """A file manager's write: no frontmatter, no registration, no conversion —
    just bytes appearing in the collection."""
    path = paths.collection_dir("shopee") / name
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.acceptance(
    spec="knowledge", scenario="a document edited out-of-band is curated by the next sweep"
)
@pytest.mark.anyio
async def test_a_document_dropped_in_by_hand_is_picked_up_by_the_next_sweep(corpus) -> None:  # type: ignore[no-untyped-def]
    _drop("dropped-by-hand.md", _DROPPED)

    service = KnowledgeService(resources=_Resources(["shopee"]), audit=_Audit())
    loop = _Loop()
    await _worker(service, loop).run_once()

    # It got to the model from THIS file: the brief carried it as a person's edit.
    [brief] = loop.briefs
    assert _DROPPED.strip() in brief
    assert f"The document a person edited: {_DROPPED_RELPATH}" in brief

    # The pass's own write is a document an agent reads, and is stamped so the
    # sweep does not hand it back.
    written = fs.read_file("shopee/session-cache-1.md")
    assert written.curated_at != ""

    # The watermark is written into the person's own file, which is what makes
    # the next sweep a no-op without any state Coffer has to keep (FR-028).
    assert fs.read_file(_DROPPED_RELPATH).curated_at != ""
    assert fs.edited_documents("shopee") == ()


@pytest.mark.anyio
async def test_the_sweep_does_not_rewrite_the_edited_document(corpus) -> None:  # type: ignore[no-untyped-def]
    """It is the person's file. Settling the pass may stamp it and nothing
    else — the body, and any frontmatter they wrote themselves, come through
    untouched (FR-028)."""
    _drop(
        "dropped-by-hand.md",
        "---\ntitle: My own title\ndescription: what I wrote\nactor: user\n"
        f"tags: [cache, redis]\n---\n\n{_DROPPED}",
    )

    service = KnowledgeService(resources=_Resources(["shopee"]), audit=_Audit())
    await _worker(service, _Loop()).run_once()

    after = fs.read_file(_DROPPED_RELPATH)
    assert after.title == "My own title"
    assert after.description == "what I wrote"
    assert after.actor == "user"
    assert after.body.strip() == _DROPPED.strip()
    raw = (paths.collection_dir("shopee") / "dropped-by-hand.md").read_text(encoding="utf-8")
    assert "cache" in raw and "redis" in raw


@pytest.mark.anyio
async def test_a_second_sweep_starts_no_pass_until_the_document_changes(corpus) -> None:  # type: ignore[no-untyped-def]
    """The watermark is what stops a corpus being re-curated every minute."""
    dropped = _drop("dropped-by-hand.md", _DROPPED)

    service = KnowledgeService(resources=_Resources(["shopee"]), audit=_Audit())
    loop = _Loop()
    worker = _worker(service, loop)

    await worker.run_once()
    await worker.run_once()
    assert len(loop.briefs) == 1

    # Edited again in the same editor: owed again, no registration.
    text = dropped.read_text(encoding="utf-8")
    dropped.write_text(f"{text}The cache is Redis.\n", encoding="utf-8")
    await worker.run_once()
    assert len(loop.briefs) == 2
    assert "The cache is Redis." in loop.briefs[1]


@pytest.mark.anyio
async def test_the_inbox_is_drained_before_edited_documents(corpus) -> None:  # type: ignore[no-untyped-def]
    """Material first: until it is merged it is knowledge no agent can read,
    while an edited document is readable as it stands."""
    _drop("dropped-by-hand.md", _DROPPED)
    fs.submit_material(
        "shopee",
        title="Gateway notes",
        description="What the gateway caches",
        body="The gateway also caches tokens.",
    )

    service = KnowledgeService(resources=_Resources(["shopee"]), audit=_Audit())
    loop = _Loop()
    await _worker(service, loop).run_once()

    assert len(loop.briefs) == 2
    assert "## The new material to absorb" in loop.briefs[0]
    assert "The gateway also caches tokens." in loop.briefs[0]
    assert f"The document a person edited: {_DROPPED_RELPATH}" in loop.briefs[1]
    # Material a pass folded in leaves the inbox; nothing is owed any more.
    assert fs.inbox_items("shopee") == ()
    assert fs.edited_documents("shopee") == ()


_DROPPED_RELPATH = "shopee/dropped-by-hand.md"
