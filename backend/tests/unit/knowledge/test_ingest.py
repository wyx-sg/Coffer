"""Document ingestion: convert, describe, and submit what it says as material.

The contract under test (spec knowledge FR-016..FR-019): an upload becomes
**material** for a collection — the same submission, frontmatter and audit
event as an agent's ``coffer__write`` — which a curation pass merges into the
documents. Nothing of the upload itself is kept: not the original bytes, not
the extracted text as a file of its own. With no internal model to merge it,
the material becomes a document as it stands (FR-029). And the whole thing is
all-or-nothing: a refusal leaves nothing behind.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.application.knowledge.ingest import MAX_UPLOAD_BYTES, IngestedDocument, IngestService
from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.domain.errors import ResourceNotFound
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


async def _can_merge() -> bool:
    return True


@pytest.fixture
def knowledge(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    """A ``KnowledgeService`` over an isolated tree with one collection
    (``shopee``) and a model that could merge; ``elsewhere`` is a name no
    collection answers to."""
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))
    fs.create_collection_dir("shopee")
    return KnowledgeService(
        resources=_Resources(["shopee"]), audit=_Audit(), merge_available=_can_merge
    )


@pytest.fixture
def knowledge_without_model(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    """The same tree, with nothing configured to merge material."""
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))
    fs.create_collection_dir("shopee")
    return KnowledgeService(resources=_Resources(["shopee"]), audit=_Audit())


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


def _on_disk(collection: str = "shopee") -> list[str]:
    """Everything actually on disk in the collection, hidden files included.

    Deliberately not ``catalogue.list_level``: that answers what the tree
    SHOWS, and an assertion that nothing landed has to look at the directory
    itself or a stray inbox item or original would slip past it.
    """
    directory = paths.collection_dir(collection)
    if not directory.is_dir():
        return []
    return sorted(str(p.relative_to(directory)) for p in directory.rglob("*") if p.is_file())


# ----- the shape of a successful ingest ---------------------------------


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="an upload is converted and submitted as material, keeping neither file",
)
async def test_an_upload_becomes_material_and_nothing_else(knowledge) -> None:  # type: ignore[no-untyped-def]
    service = _service(knowledge)
    data = b"# Meeting Notes\n\nDiscussed the launch plan and open risks.\n"

    result = await service.ingest(
        collection="shopee", filename="notes.md", data=data, actor="tester"
    )

    assert isinstance(result, IngestedDocument)
    assert result.pending is True
    assert result.path is None
    assert result.title == "Meeting Notes"
    assert result.converter == "passthrough"
    assert result.description == "Discussed the launch plan and open risks."

    # One inbox item, carrying the text; no original and no document beside it.
    assert _on_disk() == [".inbox/meeting-notes.md"]
    material = fs.read_material("shopee", "meeting-notes.md")
    assert material.actor == ACTOR_USER
    assert material.description == result.description
    assert material.body.strip() == data.decode().strip()

    entry = next(c for c in catalogue.list_collections() if c.name == "shopee")
    assert (entry.document_count, entry.pending_count) == (0, 1)


async def test_with_no_model_an_upload_becomes_a_document_as_it_stands(  # type: ignore[no-untyped-def]
    knowledge_without_model,
) -> None:
    service = _service(knowledge_without_model)

    result = await service.ingest(
        collection="shopee",
        filename="notes.md",
        data=b"# Meeting Notes\n\nDiscussed the launch plan.\n",
        actor="tester",
    )

    assert result.pending is False
    assert result.path == "shopee/meeting-notes.md"
    assert _on_disk() == ["meeting-notes.md"]
    assert "Discussed the launch plan." in fs.read_file(result.path).body


async def test_a_non_markdown_upload_is_converted_and_its_original_dropped(knowledge) -> None:  # type: ignore[no-untyped-def]
    service = _service(knowledge)
    data = b"name,role\nAda,engineer\nGrace,engineer\n"

    result = await service.ingest(
        collection="shopee", filename="team.csv", data=data, actor="tester"
    )

    assert result.converter == "csv"
    assert result.title == "team"
    material = fs.read_material("shopee", "team.md")
    assert "| name | role |" in material.body
    assert "| Ada | engineer |" in material.body
    # The `.csv` itself is nowhere: the collection keeps knowledge, not the
    # document it arrived in.
    assert _on_disk() == [".inbox/team.md"]


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
    # Nothing at all: no material, no original (FR-019).
    assert _on_disk() == []


@pytest.mark.acceptance(spec="knowledge", scenario="a document is never stored half-converted")
async def test_a_document_that_converts_to_nothing_is_refused_and_writes_nothing(  # type: ignore[no-untyped-def]
    knowledge,
) -> None:
    """FR-019. The real case is an image-only PDF: MarkItDown extracts no text,
    returns ``""``, and reports no error — it did its job, the document simply
    has no text layer. Stored, that is titled material with an empty body: it
    would be material a curation pass has nothing to fold in from, and with no
    model it would become a document that says nothing.

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
    # Nothing reached the inbox.
    assert _on_disk() == []


async def test_a_whitespace_only_conversion_counts_as_nothing(knowledge) -> None:  # type: ignore[no-untyped-def]
    """A page of blank lines carries as little as an empty one."""
    service = IngestService(
        knowledge=knowledge,
        registry=_EmptyRegistry(markdown="\n   \n\t\n"),
        credential_resolver=lambda ref: "k",
    )

    with pytest.raises(EmptyConversion):
        await service.ingest(collection="shopee", filename="blank.docx", data=b"x", actor="tester")

    assert _on_disk() == []


async def test_oversize_upload_is_refused_naming_the_limit(knowledge) -> None:  # type: ignore[no-untyped-def]
    service = _service(knowledge)
    data = b"x" * (MAX_UPLOAD_BYTES + 1)

    with pytest.raises(UploadTooLarge) as exc_info:
        await service.ingest(collection="shopee", filename="huge.txt", data=data, actor="tester")

    assert str(MAX_UPLOAD_BYTES) in str(exc_info.value)
    assert exc_info.value.limit == MAX_UPLOAD_BYTES
    assert _on_disk() == []


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


# ----- an ingest is a write, and a write names a real collection --------


async def test_ingest_into_a_collection_that_does_not_exist_fails(knowledge) -> None:  # type: ignore[no-untyped-def]
    """Refused before any conversion, and it leaves no directory behind: the
    check is the same one ``submit`` makes, hoisted so an unusable name costs
    nothing."""
    service = _service(knowledge)

    with pytest.raises(CollectionNotFound):
        await service.ingest(
            collection="elsewhere",
            filename="notes.md",
            data=b"# Notes\n\nshould never land\n",
            actor="tester",
        )

    assert not paths.collection_dir("elsewhere").exists()


# ----- deleting (FR-020) ------------------------------------------------


async def test_a_person_may_delete_any_document(knowledge) -> None:  # type: ignore[no-untyped-def]
    written = fs.write_file(
        directory="shopee", title="Curated", description="d", body="b", curated=True
    )

    await knowledge.delete_document(written.path, actor="tester")

    with pytest.raises(KnowledgeFileNotFound):
        fs.read_file(written.path)
    assert _on_disk() == []
