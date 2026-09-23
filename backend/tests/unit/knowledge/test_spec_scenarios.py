"""Acceptance scenarios of the knowledge spec that the filesystem layer, the
curation tools and the worker can observe on their own.

Every test pins ``COFFER_KNOWLEDGE_ROOT`` into ``tmp_path``: an unset root
falls back to the developer's real ``~/.coffer/knowledge``.
"""

from __future__ import annotations

import asyncio
import pathlib
from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.knowledge.builtin_tools import register_knowledge_builtin_tools
from coffer.application.knowledge.curate import pending_items
from coffer.application.knowledge.curate_tools import Counters, build_tools
from coffer.application.knowledge.curate_worker import CurationWorker
from coffer.application.knowledge.guide_render import render_catalogue
from coffer.application.knowledge.ingest import IngestService
from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.application.upkeep_runs import UpkeepRunRegistry
from coffer.domain.errors import ResourceNotFound
from coffer.domain.internal_engine_config import GlobalInternalEngineConfig
from coffer.domain.resource import Resource
from coffer.infrastructure.knowledge import catalogue, fs, paths
from coffer.infrastructure.knowledge.converters.registry import default_registry
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter


class _Resources:
    """A fake ``ResourceService`` holding enabled collections by name."""

    def __init__(self, names: list[str]) -> None:
        now = datetime.now(tz=UTC)
        self._rows = [
            Resource(
                id=i,
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

    async def list(self, kind=None, enabled=None):  # type: ignore[no-untyped-def]
        return list(self._rows)


class _Audit:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def record(self, event_type, **kwargs):  # type: ignore[no-untyped-def]
        self.events.append(event_type)


@pytest.fixture
def root(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    knowledge = tmp_path / "knowledge"
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(knowledge))
    fs.create_collection_dir("shopee")
    return knowledge


def _service(*names: str) -> KnowledgeService:
    return KnowledgeService(resources=_Resources(list(names)), audit=_Audit())


def _files_under(directory: pathlib.Path) -> list[str]:
    return sorted(str(p.relative_to(directory)) for p in directory.rglob("*") if p.is_file())


# ----- storage -------------------------------------------------------------


@pytest.mark.acceptance(spec="knowledge", scenario="keep no index beside the documents")
@pytest.mark.anyio
async def test_no_index_is_kept_and_a_hand_edit_is_read_back(root: pathlib.Path) -> None:
    written = fs.write_file(
        directory="shopee", title="Session", description="d", body="first", actor="agent"
    )

    # The document is the only thing on disk: nothing Coffer derived beside it,
    # in the collection or anywhere under the knowledge root.
    assert _files_under(root) == ["shopee/session.md"]

    on_disk = pathlib.Path(written.file_path)
    frontmatter, _ = split_frontmatter(on_disk.read_text(encoding="utf-8"))
    on_disk.write_text(
        on_disk.read_text(encoding="utf-8").replace("first", "rewritten by hand"),
        encoding="utf-8",
    )

    read = await _service("shopee").read(written.path)
    assert read.body.strip() == "rewritten by hand"
    assert frontmatter["title"] == "Session"
    assert _files_under(root) == ["shopee/session.md"]


@pytest.mark.acceptance(
    spec="knowledge", scenario="list and catalogue a nested document at its own path"
)
def test_a_nested_document_is_listed_and_catalogued_where_it_was_filed(
    root: pathlib.Path,
) -> None:
    deep = root / "shopee" / "a" / "b" / "deep.md"
    deep.parent.mkdir(parents=True)
    deep.write_text(
        "---\ntitle: Deep\ndescription: filed by a person\nactor: user\n"
        "created_at: '2026-09-17T00:00:00+00:00'\nupdated_at: '2026-09-17T00:00:00+00:00'\n"
        "---\n\nbody\n",
        encoding="utf-8",
    )

    level = catalogue.list_level("shopee/a/b")
    assert [f.path for f in level.files] == ["shopee/a/b/deep.md"]

    walked = catalogue.walk_files(paths.collection_dir("shopee"))
    assert [f.path for f in walked] == ["shopee/a/b/deep.md"]
    # Nothing was required or renamed around it.
    assert _files_under(root) == ["shopee/a/b/deep.md"]


@pytest.mark.acceptance(
    spec="knowledge", scenario="keep the README out of listings, counts and curation"
)
def test_the_readme_is_never_a_document(root: pathlib.Path) -> None:
    document = fs.write_file(
        directory="shopee", title="Gateway", description="d", body="b", curated=True
    ).path
    # Edited after creation, so its mtime is newer than anything — a sweep that
    # treated it as a document would owe it a pass.
    paths.readme_path("shopee").write_text("# shopee\n\nEdited later.\n", encoding="utf-8")

    level = catalogue.list_level("shopee")
    assert [f.path for f in level.files] == [document]
    [entry] = catalogue.list_collections()
    assert entry.document_count == 1
    assert pending_items("shopee") == ()


# ----- presented as files --------------------------------------------------


@pytest.mark.acceptance(
    spec="knowledge", scenario="the guide hands over files to read with the agent's own tools"
)
def test_the_catalogue_says_read_the_files_with_your_own_tool(root: pathlib.Path) -> None:
    fs.write_file(directory="shopee", title="Gateway", description="d", body="b", curated=True)
    catalogue_ = [
        (entry, catalogue.walk_files(paths.collection_dir(entry.name)))
        for entry in catalogue.list_collections()
    ]

    text = render_catalogue("~/.coffer/knowledge", catalogue_)

    assert "Read one at `~/.coffer/knowledge/<collection>/<path>` with your own file tool" in text
    assert "Files live under `~/.coffer/knowledge/shopee/`" in text
    assert "coffer__" not in text


# ----- no scope axis -------------------------------------------------------


@pytest.mark.acceptance(
    spec="knowledge", scenario="refuse a write to a scope name instead of resolving it"
)
@pytest.mark.anyio
async def test_a_write_to_global_is_refused_and_provisions_nothing(root: pathlib.Path) -> None:
    registry = BuiltinToolRegistry()
    register_knowledge_builtin_tools(registry, knowledge_service=_service("shopee"))
    write = {t.name: t for t in registry.list()}["write"].handler

    with pytest.raises(ValueError) as raised:
        await write({"agent": "codex", "collection": "global", "title": "t", "description": "d"})

    assert "shopee" in str(raised.value)
    assert sorted(p.name for p in root.iterdir()) == ["shopee"]


# ----- converted material --------------------------------------------------


@pytest.mark.acceptance(
    spec="knowledge", scenario="title an upload from its file name when it has no heading"
)
@pytest.mark.anyio
async def test_an_upload_with_no_heading_is_titled_from_its_file_name(
    root: pathlib.Path,
) -> None:
    ingest = IngestService(knowledge=_service("shopee"), registry=default_registry())

    result = await ingest.ingest(
        collection="shopee",
        filename="release-notes.txt",
        data=b"The release ships the new gateway on Monday.\n\nMore detail follows.\n",
        actor="user",
    )

    assert result.title == "release-notes"
    assert result.path is not None
    frontmatter, _ = split_frontmatter((root / result.path).read_text(encoding="utf-8"))
    assert frontmatter["title"] == "release-notes"
    assert frontmatter["description"] == "The release ships the new gateway on Monday."


# ----- curation ------------------------------------------------------------


def _tools(collection: str) -> dict[str, Any]:
    tools = build_tools(
        service=_service("shopee", "personal"),
        collection=collection,
        actor="system",
        counters=Counters(),
    )
    return {tool.name: tool for tool in tools}


@pytest.mark.acceptance(
    spec="knowledge", scenario="hand a pass exactly four tools over one collection"
)
@pytest.mark.anyio
async def test_a_pass_gets_four_tools_fenced_to_its_collection(root: pathlib.Path) -> None:
    fs.create_collection_dir("personal")
    fs.write_file(directory="shopee", title="Mine", description="d", body="b", curated=True)
    fs.write_file(directory="personal", title="Other", description="d", body="b", curated=True)
    before = _files_under(root / "personal")

    tools = _tools("shopee")
    assert set(tools) == {"list_documents", "read_document", "write_document", "retire_document"}

    answer = await tools["write_document"].handler(
        {"path": "personal/intruder.md", "title": "t", "description": "d", "body": "b"}
    )
    assert "error" in answer
    assert _files_under(root / "personal") == before


def _held_worker(lock: asyncio.Lock, curated: list[Any]) -> CurationWorker:
    async def curate(service, uid, *, item, actor):  # type: ignore[no-untyped-def]
        curated.append(item)
        return {"status": "curated"}

    async def enabled() -> bool:
        return True

    async def collections() -> list[str]:
        return ["uid-1"]

    return CurationWorker(
        service=_service("shopee"),
        curate=curate,
        deliver=None,
        is_enabled=enabled,
        list_collections=collections,
        lock=lock,
        runs=UpkeepRunRegistry(),
    )


@pytest.mark.acceptance(spec="knowledge", scenario="wait for the vault lock before sweeping")
@pytest.mark.anyio
async def test_the_sweep_waits_for_a_converge_round_to_release_the_lock(
    root: pathlib.Path,
) -> None:
    fs.submit_material("shopee", title="Waiting", description="d", body="b", actor="agent")
    lock = asyncio.Lock()
    curated: list[Any] = []
    worker = _held_worker(lock, curated)

    await lock.acquire()  # a converge round is writing the vault
    tick = asyncio.create_task(worker.run_once())
    await asyncio.sleep(0.05)
    assert curated == []
    assert not tick.done()

    lock.release()
    await asyncio.wait_for(tick, timeout=5)
    assert len(curated) == 1
    assert curated[0].material == "waiting.md"


@pytest.mark.acceptance(
    spec="knowledge", scenario="curate only where the owner machine is this one"
)
def test_curation_runs_only_on_the_owner_machine() -> None:
    now = datetime.now(tz=UTC)
    default = GlobalInternalEngineConfig(model=None, updated_at=now)
    assert default.auto_curate_enabled is True

    elsewhere = GlobalInternalEngineConfig(
        model=None, updated_at=now, curate_owner_machine_id="machine-b"
    )
    here = GlobalInternalEngineConfig(
        model=None, updated_at=now, curate_owner_machine_id="machine-a"
    )
    assert elsewhere.curate_runs_on("machine-a") is False
    assert here.curate_runs_on("machine-a") is True
    # A single-machine vault never named an owner, and curates where it is.
    assert default.curate_runs_on("machine-a") is True


@pytest.mark.anyio
async def test_a_truncated_item_neither_stops_the_sweep_nor_is_retried_within_it(
    root: pathlib.Path,
) -> None:
    # A pass cut off by the recursion limit leaves its item pending (spec
    # knowledge "Settle an item only after its pass completes"). The sweep
    # moves on to the next item rather than stopping — the item that truncated
    # is first in line every sweep, so stopping on it would starve the rest —
    # and does not hand the same item back to a second pass in this sweep.
    fs.submit_material("shopee", title="Huge", description="d", body="b", actor="agent")
    fs.submit_material("shopee", title="Small", description="d", body="b", actor="agent")
    curated: list[Any] = []

    async def curate(service, uid, *, item, actor):  # type: ignore[no-untyped-def]
        curated.append(item.material)
        return {"status": "truncated" if item.material == "huge.md" else "ok"}

    async def enabled() -> bool:
        return True

    async def collections() -> list[str]:
        return ["uid-1"]

    worker = CurationWorker(
        service=_service("shopee"),
        curate=curate,
        deliver=None,
        is_enabled=enabled,
        list_collections=collections,
        runs=UpkeepRunRegistry(),
    )
    await worker.run_once()

    assert curated == ["huge.md", "small.md"]
