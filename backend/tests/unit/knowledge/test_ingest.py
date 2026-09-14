"""Document ingestion: convert, describe, write, keep the original.

The contract under test (spec knowledge FR-032..FR-037): an upload becomes an
ordinary knowledge file — same frontmatter, same scope enforcement, same audit
event as a hand-written one — with its original bytes kept under ``.raw/``,
and the whole thing is all-or-nothing: nothing lands unless everything does.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.application.knowledge.ingest import MAX_UPLOAD_BYTES, IngestedDocument, IngestService
from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.domain.knowledge.converter import UnsupportedDocument
from coffer.domain.knowledge.entry import ACTOR_USER
from coffer.domain.knowledge.errors import CollectionNotFound, KnowledgeFileNotFound, UploadTooLarge
from coffer.domain.provider.config import ProviderConfig, ResolvedConnection
from coffer.domain.resource import Resource
from coffer.domain.scope import Scope
from coffer.infrastructure.knowledge import fs, paths
from coffer.infrastructure.knowledge.converters.registry import default_registry


class _Resources:
    """A fake ``ResourceService``: just enough for ``visible_collections``."""

    def __init__(self, entries: list[tuple[str, Scope | None]]) -> None:
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
                scope=scope,
            )
            for i, (name, scope) in enumerate(entries, start=1)
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

    async def complete(self, *, system, user, model, credential_resolver):  # type: ignore[no-untyped-def]
        self.calls.append((system, user))
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
    """A ``KnowledgeService`` over an isolated tree with one open collection
    (``shopee``) and one an unrelated agent may not see (``restricted``)."""
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))
    fs.create_collection_dir("shopee")
    resources = _Resources([("shopee", None), ("restricted", Scope(agents=["only-agent"]))])
    return KnowledgeService(
        resources=resources,
        audit=_Audit(),
    )


def _service(knowledge, *, models=None, completion=None, credential_resolver=None):  # type: ignore[no-untyped-def]
    return IngestService(
        knowledge=knowledge,
        registry=default_registry(),
        models=models,
        completion=completion,
        credential_resolver=credential_resolver or (lambda ref: "k"),
    )


# ----- the shape of a successful ingest ---------------------------------


@pytest.mark.acceptance(
    spec="knowledge", scenario="an uploaded document lands as markdown with frontmatter"
)
async def test_a_markdown_upload_lands_with_frontmatter_and_its_original_kept(knowledge) -> None:  # type: ignore[no-untyped-def]
    service = _service(knowledge)
    data = b"# Meeting Notes\n\nDiscussed the launch plan and open risks.\n"

    result = await service.ingest(
        collection="shopee", filename="notes.md", data=data, actor="tester"
    )

    assert isinstance(result, IngestedDocument)
    assert result.path == "shopee/meeting-notes.md"
    assert result.title == "Meeting Notes"
    assert result.converter == "passthrough"
    assert result.description == "Discussed the launch plan and open risks."

    written = fs.read_file(result.path)
    assert written.actor == ACTOR_USER
    assert written.description == result.description
    assert written.body.strip() == data.decode().strip()

    raw = paths.raw_dir("shopee") / "meeting-notes.md"
    assert str(raw) == result.raw_path
    assert raw.is_file()
    assert raw.read_bytes() == data

    # The original stays out of the catalogue and its count (FR-035).
    assert fs.list_collections()[0].file_count == 1


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

    raw_path = paths.raw_dir("shopee") / "team.csv"
    assert raw_path.is_file()
    assert raw_path.read_bytes() == data


@pytest.mark.acceptance(
    spec="knowledge", scenario="an upload of an unsupported type is refused with its reason"
)
async def test_an_unsupported_type_is_refused_and_writes_nothing(knowledge) -> None:  # type: ignore[no-untyped-def]
    service = _service(knowledge)

    with pytest.raises(UnsupportedDocument):
        await service.ingest(
            collection="shopee", filename="archive.bin", data=b"whatever", actor="tester"
        )

    assert fs.list_level("shopee").files == ()
    assert not paths.raw_dir("shopee").exists()


async def test_oversize_upload_is_refused_naming_the_limit(knowledge) -> None:  # type: ignore[no-untyped-def]
    service = _service(knowledge)
    data = b"x" * (MAX_UPLOAD_BYTES + 1)

    with pytest.raises(UploadTooLarge) as exc_info:
        await service.ingest(collection="shopee", filename="huge.txt", data=data, actor="tester")

    assert str(MAX_UPLOAD_BYTES) in str(exc_info.value)
    assert exc_info.value.limit == MAX_UPLOAD_BYTES
    assert fs.list_level("shopee").files == ()


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
    """An empty CSV converts to an empty document — no paragraph to fall back
    to at all — so the description must still be non-empty (FR-003 makes it
    required); the title is the only thing left to fall back to."""
    service = _service(knowledge)

    result = await service.ingest(collection="shopee", filename="team.csv", data=b"", actor="t")

    assert result.description == result.title == "team"


# ----- atomicity: nothing half-lands (FR-037) ---------------------------


async def test_a_write_failure_leaves_no_partial_file_and_no_orphan_original(knowledge) -> None:  # type: ignore[no-untyped-def]
    service = _service(knowledge)

    # "report.txt" converts (passthrough) to a file that would be named
    # "report.md" and whose original would be kept at ".raw/report.txt" — pre-
    # occupy that exact spot with a directory so the raw-copy step fails after
    # the Markdown file already exists, forcing the rollback path.
    raw_dir = paths.raw_dir("shopee")
    raw_dir.mkdir(parents=True)
    (raw_dir / "report.txt").mkdir()

    with pytest.raises(OSError):
        await service.ingest(
            collection="shopee", filename="report.txt", data=b"hello world", actor="tester"
        )

    assert fs.list_level("shopee").files == ()
    assert not (paths.collection_dir("shopee") / "report.md").exists()
    # The pre-existing directory is untouched — the failure came from trying
    # to write a file where one couldn't go, not from us clobbering it.
    assert (raw_dir / "report.txt").is_dir()


# ----- scope: an ingest is a write, and a write is enforced -------------


async def test_ingest_into_a_collection_the_caller_may_not_see_fails(knowledge) -> None:  # type: ignore[no-untyped-def]
    service = _service(knowledge)

    with pytest.raises(CollectionNotFound):
        await service.ingest(
            collection="restricted",
            filename="notes.md",
            data=b"# Notes\n\nshould never land\n",
            actor="tester",
            agent="someone-else",
        )

    assert not paths.collection_dir("restricted").exists()


# ----- deletion symmetry (FR-035), exercised through KnowledgeService ---


async def test_deleting_an_ingested_file_removes_its_raw_original(knowledge) -> None:  # type: ignore[no-untyped-def]
    service = _service(knowledge)
    result = await service.ingest(
        collection="shopee", filename="notes.md", data=b"# Notes\n\nbody\n", actor="tester"
    )
    raw = paths.raw_dir("shopee") / "notes.md"
    assert raw.is_file()

    await knowledge.delete(result.path, actor="tester")

    with pytest.raises(KnowledgeFileNotFound):
        fs.read_file(result.path)
    assert not raw.exists()


async def test_deleting_a_hand_written_file_with_no_original_is_a_clean_noop(knowledge) -> None:  # type: ignore[no-untyped-def]
    written = fs.write_file(directory="shopee", title="Hand Written", description="d", body="b")

    # Must not raise even though no ".raw/" directory exists at all.
    await knowledge.delete(written.path, actor="tester")

    with pytest.raises(KnowledgeFileNotFound):
        fs.read_file(written.path)
