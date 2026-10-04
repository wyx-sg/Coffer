"""Acceptance scenarios of the knowledge spec that the filesystem layer and the
sweep can observe on their own.

The knowledge root resolves from the fresh ``HOME`` every test gets
(``backend/tests/conftest.py``), never the developer's real vault.
"""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime

import pytest

from coffer.application.knowledge.guide_render import render_catalogue
from coffer.application.knowledge.ingest import IngestService
from coffer.application.knowledge.intake import adopt_dropped_files
from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.domain.errors import ResourceNotFound
from coffer.domain.resource import Resource
from coffer.infrastructure.knowledge import catalogue, fs, paths
from coffer.infrastructure.knowledge.converters.registry import default_registry
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter
from coffer.infrastructure.knowledge.paths import knowledge_root as _knowledge_root


class _Resources:
    """A fake ``ResourceService`` holding collections by name."""

    def __init__(self, names: list[str]) -> None:
        now = datetime.now(tz=UTC)
        self._rows = [
            Resource(
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
    knowledge = _knowledge_root()
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
    document = fs.write_file(directory="shopee", title="Gateway", description="d", body="b").path
    paths.readme_path("shopee").write_text("# shopee\n\nEdited later.\n", encoding="utf-8")

    level = catalogue.list_level("shopee")
    assert [f.path for f in level.files] == [document]
    [entry] = catalogue.list_collections()
    assert entry.document_count == 1


# ----- presented as files --------------------------------------------------


@pytest.mark.acceptance(
    spec="knowledge", scenario="the guide hands over files to read with the agent's own tools"
)
def test_the_catalogue_says_read_the_files_with_your_own_tool(root: pathlib.Path) -> None:
    fs.write_file(directory="shopee", title="Gateway", description="d", body="b")
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
    spec="knowledge",
    scenario="leave a file under a scope name uncatalogued instead of resolving it",
)
@pytest.mark.anyio
async def test_a_file_under_global_is_left_alone_and_provisions_nothing(
    root: pathlib.Path,
) -> None:
    note = root / "global" / ".inbox" / "note.md"
    note.parent.mkdir(parents=True)
    note.write_text("an agent's note\n", encoding="utf-8")
    service = _service("shopee")

    assert await adopt_dropped_files(service) == []

    # Left exactly where it is, with no frontmatter added, and not a collection.
    assert note.read_text(encoding="utf-8") == "an agent's note\n"
    assert [c.name for c in await service.list_collections()] == ["shopee"]
    assert await service.collection_names() == ["shopee"]
    assert not (root / "project-1").exists()


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
