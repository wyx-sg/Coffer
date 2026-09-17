"""Document ingestion: convert, describe, write both files into the sources lane.

The contract under test (spec knowledge FR-016..FR-019): an upload becomes an
ordinary **source** — same frontmatter, same scope enforcement, same audit
event as a file a person typed — with the original kept beside it as a
visible file in the same lane, and the whole thing all-or-nothing: nothing
lands unless everything does.

What changed, and what these tests now pin that the previous ones could not:
the original is no longer hidden under ``.raw/``. Hiding it only ever bought
keeping it out of a ranked retrieval index, and there is no retrieval surface
left to pollute (FR-033) — so the original is a file in ``sources/`` that a
person browsing their own lane can see, delete and re-upload on its own. That
also means deleting the extracted Markdown no longer deletes anything else:
two files, two lifetimes.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.application.knowledge.ingest import MAX_UPLOAD_BYTES, IngestedDocument, IngestService
from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.domain.knowledge.converter import (
    Conversion,
    EmptyConversion,
    UnsupportedDocument,
)
from coffer.domain.knowledge.entry import ACTOR_USER
from coffer.domain.knowledge.errors import CollectionNotFound, KnowledgeFileNotFound, UploadTooLarge
from coffer.domain.provider.config import ProviderConfig, ResolvedConnection
from coffer.domain.resource import Resource
from coffer.infrastructure.knowledge import catalogue, fs, paths
from coffer.infrastructure.knowledge.converters.registry import default_registry


class _Resources:
    """A fake ``ResourceService``: just enough for ``enabled_collections``."""

    def __init__(self, names: list[str]) -> None:
        now = datetime.now(tz=UTC)
        self._rows = [
            Resource(
                id=i,
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

    async def list(self, kind=None, enabled=None):  # type: ignore[no-untyped-def]
        return list(self._rows)


class _Audit:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def record(self, event_type, **kwargs):  # type: ignore[no-untyped-def]
        self.events.append(event_type)


class _Model:
    def __init__(self, connection) -> None:  # type: ignore[no-untyped-def]
        self._connection = connection

    async def get_default(self):  # type: ignore[no-untyped-def]
        return self._connection


class _Completion:
    """Records what it was called with; answers a fixed text or raises."""

    def __init__(self, text: str | None = None, *, raises: bool = False) -> None:
        self._text = text
        self._raises = raises
        self.calls: list[tuple[str, str]] = []

    async def complete(self, *, system, user, model, credential_resolver, timeout=None):  # type: ignore[no-untyped-def]
        self.calls.append((system, user))
        self.timeout = timeout
        if self._raises:
            raise RuntimeError("the internal connection is unreachable")
        assert credential_resolver("provider/test") == "k"
        return self._text or ""


@pytest.fixture
def fake_connection() -> ResolvedConnection:
    return ResolvedConnection(
        config=ProviderConfig(
            protocol="openai",
            base_url="https://example.invalid/v1",
            credential_ref="provider/test",
        ),
        model="agnes-2.0-flash",
    )


@pytest.fixture
def knowledge(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    """A ``KnowledgeService`` over an isolated tree with one collection
    (``shopee``); ``elsewhere`` is a name no collection answers to."""
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))
    fs.create_collection_dir("shopee")
    resources = _Resources(["shopee"])
    return KnowledgeService(
        resources=resources,
        audit=_Audit(),
    )


class _EmptyRegistry:
    """A converter registry whose converter succeeds and produces no text.

    Stands in for MarkItDown on an image-only PDF, which returns ``""`` and
    raises nothing.
    """

    def __init__(self, markdown: str = "") -> None:
        self._markdown = markdown

    async def convert(self, data: bytes, filename: str) -> Conversion:
        return Conversion(markdown=self._markdown, title="Scan", converter="markitdown")


def _service(knowledge, *, models=None, completion=None, credential_resolver=None):  # type: ignore[no-untyped-def]
    return IngestService(
        knowledge=knowledge,
        registry=default_registry(),
        models=models,
        completion=completion,
        credential_resolver=credential_resolver or (lambda ref: "k"),
    )


def _sources(collection: str = "shopee") -> list[str]:
    """Everything actually on disk in the lane — Markdown or not.

    Deliberately not ``fs.list_level``: that answers what the tree SHOWS, and
    an assertion that nothing landed has to look at the directory itself or a
    stray original would slip past it.
    """
    directory = paths.sources_dir(collection)
    if not directory.is_dir():
        return []
    return sorted(p.name for p in directory.iterdir())


# ----- the shape of a successful ingest ---------------------------------


@pytest.mark.acceptance(
    spec="knowledge", scenario="an upload lands both the original and its text in sources"
)
async def test_a_markdown_upload_is_stored_once(knowledge) -> None:  # type: ignore[no-untyped-def]
    service = _service(knowledge)
    data = b"# Meeting Notes\n\nDiscussed the launch plan and open risks.\n"

    result = await service.ingest(
        collection="shopee", filename="notes.md", data=data, actor="tester"
    )

    assert isinstance(result, IngestedDocument)
    # The lane segment is the layer's, never the caller's (FR-013): the call
    # named only the collection.
    assert result.path == "shopee/sources/meeting-notes.md"
    assert result.title == "Meeting Notes"
    assert result.converter == "passthrough"
    assert result.description == "Discussed the launch plan and open risks."

    written = fs.read_file(result.path)
    assert written.actor == ACTOR_USER
    assert written.description == result.description
    assert written.body.strip() == data.decode().strip()

    # Markdown converts by passthrough, so "the original" would be the bytes
    # already in the file just written. Keeping a second copy would put one
    # document in the lane twice and hand curation the same facts as two
    # independent sources — two model calls to discover they agree.
    assert result.original_path == result.path
    assert [f.path for f in catalogue.walk_files(paths.sources_dir("shopee"))] == [result.path]
    assert fs.pending_sources("shopee") == (result.path,)
    assert not any(p.name.startswith(".") for p in paths.collection_dir("shopee").iterdir())

    # It is a source, and it is counted as one; nothing reached the other lane.
    entry = next(c for c in catalogue.list_collections() if c.name == "shopee")
    assert entry.topic_count == 0


async def test_a_non_markdown_upload_converts_before_it_is_written(knowledge) -> None:  # type: ignore[no-untyped-def]
    service = _service(knowledge)
    data = b"name,role\nAda,engineer\nGrace,engineer\n"

    result = await service.ingest(
        collection="shopee", filename="team.csv", data=data, actor="tester"
    )

    assert result.converter == "csv"
    assert result.title == "team"
    written = fs.read_file(result.path)
    assert "| name | role |" in written.body
    assert "| Ada | engineer |" in written.body

    # The `.csv` keeps its own extension: the original is what was sent, not a
    # renamed copy of it.
    assert result.original_path == "shopee/sources/team.csv"
    assert paths.resolve(result.original_path).read_bytes() == data


async def test_a_folder_is_a_subdirectory_of_the_lane_not_beside_it(knowledge) -> None:  # type: ignore[no-untyped-def]
    """``folder`` is nesting INSIDE ``sources/`` (FR-004), so no entrance can
    aim an upload at ``topics/`` by spelling a path."""
    service = _service(knowledge)

    result = await service.ingest(
        collection="shopee",
        filename="notes.md",
        data=b"# Notes\n\nSome prose.\n",
        folder="runbooks",
        actor="tester",
    )

    assert result.path == "shopee/sources/runbooks/notes.md"


@pytest.mark.acceptance(
    spec="knowledge", scenario="an upload of an unsupported type is refused with its reason"
)
async def test_an_unsupported_type_is_refused_and_writes_nothing(knowledge) -> None:  # type: ignore[no-untyped-def]
    service = _service(knowledge)

    with pytest.raises(UnsupportedDocument) as exc_info:
        await service.ingest(
            collection="shopee", filename="archive.bin", data=b"whatever", actor="tester"
        )

    assert exc_info.value.doc_type == "bin"
    # Not "no Markdown": nothing at all, original included (FR-019).
    assert _sources() == []


@pytest.mark.acceptance(spec="knowledge", scenario="a document is never stored half-converted")
async def test_a_document_that_converts_to_nothing_is_refused_and_writes_nothing(  # type: ignore[no-untyped-def]
    knowledge,
) -> None:
    """FR-019. The real case is an image-only PDF: MarkItDown extracts no text,
    returns ``""``, and reports no error — it did its job, the document simply
    has no text layer. Stored, that is a titled source with an empty body: it
    would be handed to a curation pass that has nothing to fold in, and the
    catalogue would carry a document that says nothing.

    Driven through a converter that returns empty markdown rather than through
    a real scanned PDF, because the rule is about ANY converter producing
    nothing, and a fixture PDF would only prove the one format.
    """
    service = IngestService(
        knowledge=knowledge,
        registry=_EmptyRegistry(),
        credential_resolver=lambda ref: "k",
    )

    with pytest.raises(EmptyConversion) as exc_info:
        await service.ingest(
            collection="shopee", filename="scan.pdf", data=b"%PDF-1.7 image only", actor="tester"
        )

    assert exc_info.value.doc_type == "pdf"
    # Neither the extracted Markdown NOR the original: refusing the text but
    # keeping the bytes would leave a file in the lane with no way to read it.
    assert _sources() == []


async def test_a_whitespace_only_conversion_counts_as_nothing(knowledge) -> None:  # type: ignore[no-untyped-def]
    """A page of blank lines carries as little as an empty one."""
    service = IngestService(
        knowledge=knowledge,
        registry=_EmptyRegistry(markdown="\n   \n\t\n"),
        credential_resolver=lambda ref: "k",
    )

    with pytest.raises(EmptyConversion):
        await service.ingest(collection="shopee", filename="blank.docx", data=b"x", actor="tester")

    assert _sources() == []


async def test_oversize_upload_is_refused_naming_the_limit(knowledge) -> None:  # type: ignore[no-untyped-def]
    service = _service(knowledge)
    data = b"x" * (MAX_UPLOAD_BYTES + 1)

    with pytest.raises(UploadTooLarge) as exc_info:
        await service.ingest(collection="shopee", filename="huge.txt", data=data, actor="tester")

    assert str(MAX_UPLOAD_BYTES) in str(exc_info.value)
    assert exc_info.value.limit == MAX_UPLOAD_BYTES
    assert _sources() == []


# ----- the description: model when available, prose otherwise ----------


async def test_description_comes_from_the_model_when_one_is_configured(  # type: ignore[no-untyped-def]
    knowledge, fake_connection
) -> None:
    completion = _Completion(text="  A recap of the launch plan and its risks.  \n")
    service = _service(knowledge, models=_Model(fake_connection), completion=completion)

    result = await service.ingest(
        collection="shopee",
        filename="notes.md",
        data=b"# Notes\n\nSome opening prose that the model will ignore.\n",
        actor="tester",
    )

    assert result.description == "A recap of the launch plan and its risks."
    assert len(completion.calls) == 1


async def test_description_falls_back_to_opening_prose_with_no_model_configured(  # type: ignore[no-untyped-def]
    knowledge,
) -> None:
    service = _service(knowledge, models=None, completion=None)

    result = await service.ingest(
        collection="shopee",
        filename="notes.md",
        data=b"# Notes\n\nThe fallback text this test expects to see.\n",
        actor="tester",
    )

    assert result.description == "The fallback text this test expects to see."


async def test_description_falls_back_to_opening_prose_when_the_model_call_raises(  # type: ignore[no-untyped-def]
    knowledge, fake_connection
) -> None:
    completion = _Completion(raises=True)
    service = _service(knowledge, models=_Model(fake_connection), completion=completion)

    result = await service.ingest(
        collection="shopee",
        filename="notes.md",
        data=b"# Notes\n\nStill readable even though the model failed.\n",
        actor="tester",
    )

    assert result.description == "Still readable even though the model failed."
    assert len(completion.calls) == 1


async def test_description_falls_back_to_the_title_when_there_is_no_prose_at_all(  # type: ignore[no-untyped-def]
    knowledge,
) -> None:
    """A document can convert to real content and still contain no PROSE — a
    file that is nothing but a heading is the case. ``_fallback_description``
    skips heading lines, so there is no paragraph left, and FR-003 makes the
    description required: the title is the only thing left to use.

    This used to be driven with a completely EMPTY CSV. That is no longer a
    stored document at all — a conversion that produces nothing is refused
    (``EmptyConversion``, FR-019) — so the vehicle has to be a document that
    converts to something and still yields no prose.
    """
    service = _service(knowledge)

    result = await service.ingest(
        collection="shopee", filename="team.md", data=b"# Team\n", actor="t"
    )

    assert result.description == result.title == "Team"


# ----- atomicity: nothing half-lands (FR-019) ---------------------------


async def test_a_failure_keeping_the_original_takes_the_markdown_back(
    knowledge, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    """The Markdown must not outlive the original it was meant to stand beside.

    The two writes cannot both be made to fail by arranging the directory any
    more — ``write_original`` picks a free name rather than colliding — so the
    second write is failed at the filesystem boundary itself. The unit under
    test is the rollback in ``IngestService``, not ``fs``.
    """
    service = _service(knowledge)

    def _boom(collection: str, filename: str, data: bytes) -> str:
        raise OSError("no space left on device")

    monkeypatch.setattr(fs, "write_original", _boom)

    # A CSV, so the conversion genuinely differs from the upload and an
    # original is actually kept — a Markdown or plain-text upload short
    # circuits before `write_original` is ever reached.
    with pytest.raises(OSError):
        await service.ingest(
            collection="shopee",
            filename="table.csv",
            data=b"name,owner\nsession,account\n",
            actor="tester",
        )

    # Not "the original is missing" — the Markdown that DID land is gone too.
    assert _sources() == []


# ----- an ingest is a write, and a write names a real collection --------


async def test_ingest_into_a_collection_that_does_not_exist_fails(knowledge) -> None:  # type: ignore[no-untyped-def]
    """Refused before any conversion, and it leaves no directory behind: the
    check is the same one ``write_source`` makes, hoisted so an unusable name
    costs nothing."""
    service = _service(knowledge)

    with pytest.raises(CollectionNotFound):
        await service.ingest(
            collection="elsewhere",
            filename="notes.md",
            data=b"# Notes\n\nshould never land\n",
            actor="tester",
        )

    assert not paths.collection_dir("elsewhere").exists()


# ----- two files, two lifetimes (FR-016, FR-020) -----------------------


async def test_deleting_the_extracted_markdown_leaves_the_original_alone(knowledge) -> None:  # type: ignore[no-untyped-def]
    """The symmetry the ``.raw/`` design needed is gone with it.

    An original under ``.raw/`` was an invisible appendage of the Markdown, so
    deleting one had to delete the other or it became unreachable litter. In
    ``sources/`` it is an ordinary file a person can see, so it outlives the
    conversion and is deleted on its own — which is also what makes
    re-converting a bad extraction possible after deleting the bad one.
    """
    service = _service(knowledge)
    result = await service.ingest(
        collection="shopee",
        filename="table.csv",
        data=b"name,owner\nsession,account\n",
        actor="tester",
    )
    assert result.original_path != result.path

    await knowledge.delete_source(result.path, actor="tester")

    with pytest.raises(KnowledgeFileNotFound):
        fs.read_file(result.path)
    assert paths.resolve(result.original_path).is_file()

    # And the original goes the same way, by its own path.
    await knowledge.delete_source(result.original_path, actor="tester")
    assert _sources() == []


async def test_deleting_a_hand_written_source_is_a_clean_delete(knowledge) -> None:  # type: ignore[no-untyped-def]
    written = fs.write_file(
        directory="shopee/sources", title="Hand Written", description="d", body="b"
    )

    await knowledge.delete_source(written.path, actor="tester")

    with pytest.raises(KnowledgeFileNotFound):
        fs.read_file(written.path)
