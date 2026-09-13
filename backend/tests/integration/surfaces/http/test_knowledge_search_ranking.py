"""Integration tests for the ranked-retrieval plumbing itself (spec knowledge
FR-025, FR-028, FR-029): a query that shares no wording with the file it
should surface, a file edited out-of-band picked up with no reindex step,
and the disposable sidecar losing no knowledge when deleted.

A previous pass on this spec skipped these three scenarios believing they
needed a real embedding model. They don't: the point of each one is the
plumbing *around* the vectors (freshness detection, the disposable sidecar,
the literal fallback), not the vectors' semantic quality. ``FakeEmbedder``
(``conftest.py``) gives deterministic, known vectors for known text, which
tests that plumbing exactly and repeatably.

Reuses the ``client`` fixture and ``_create_collection``/``_write_file``
helpers from ``conftest.py`` (shared with ``test_knowledge_search_ingest_routes.py``)
rather than duplicating them — that fixture is what pins
``COFFER_KNOWLEDGE_ROOT`` and ``COFFER_INDEX_ROOT`` into ``tmp_path`` and boots
the real app. Each test here builds its own ``SearchService`` with a
``FakeEmbedder`` (the app's own wired ``SearchService`` resolves a real
embedder from provider config, which this suite has none of) — the same
pattern ``test_builtin_search_tool_spans_only_the_agents_collections`` already
uses for the "no internal connection" case.
"""

from __future__ import annotations

import pytest

from coffer.application.knowledge.search import SearchService
from coffer.infrastructure.retrieval import index as index_module
from coffer.surfaces.http.dependencies import get_knowledge_service

from .conftest import FakeEmbedder, _create_collection, _write_file, embedder_factory


def _search_service(embedder: FakeEmbedder | None) -> SearchService:
    return SearchService(
        knowledge=get_knowledge_service(), embedder_factory=embedder_factory(embedder)
    )


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="search ranks a file whose wording never matches the query",
)
async def test_search_ranks_a_file_whose_wording_never_matches_the_query(client) -> None:
    _create_collection(client, "shopee")
    target_path = _write_file(
        client,
        directory="shopee",
        title="Zephyrcrest",
        description="d",
        body="This entry carries the codeword zephyrcrest for indexing purposes.",
    )
    _write_file(
        client,
        directory="shopee",
        title="Mooncalf",
        description="d",
        body="This entry carries the codeword mooncalf for indexing purposes.",
    )

    # Neither file's wording overlaps the query at all: a grep for it must
    # come back empty, so a ranked hit can only have come from the vectors.
    query = "reticulating splines"
    query_vector = (1.0, 0.0, 0.0)
    embedder = FakeEmbedder(
        {
            query: query_vector,
            "zephyrcrest": query_vector,  # the target: same vector as the query
            "mooncalf": (1.0, 1.0, 0.0),  # the decoy: related, but further away
        }
    )
    search_service = _search_service(embedder)

    outcome = await search_service.search(query)
    assert outcome.mode == "ranked"
    assert outcome.hits
    assert outcome.hits[0].path == target_path

    grep = client.get("/api/v1/knowledge/grep", params={"pattern": query})
    assert grep.status_code == 200, grep.text
    assert grep.json()["matches"] == []


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="the index picks up a file edited out-of-band",
)
async def test_index_picks_up_a_file_edited_out_of_band(client, tmp_path) -> None:
    _create_collection(client, "shopee")
    target_path = _write_file(
        client,
        directory="shopee",
        title="Rotating Marker",
        description="d",
        body="This document discusses the old-vector-marker in isolation.",
    )

    query = "aligned marker query"
    query_vector = (1.0, 0.0, 0.0)
    embedder = FakeEmbedder(
        {
            query: query_vector,
            "old-vector-marker": (0.0, 1.0, 0.0),  # orthogonal to the query
            "new-vector-marker": query_vector,  # what the edit will introduce
        }
    )
    search_service = _search_service(embedder)

    before = await search_service.search(query)
    assert before.mode == "literal"  # the old content scores below threshold
    assert target_path not in {hit.path for hit in before.hits}

    # Rewrite the file directly on disk — no Coffer API call, exactly like an
    # editor save or a `git checkout` would.
    raw_path = tmp_path / "knowledge" / target_path
    raw_path.write_text(
        raw_path.read_text(encoding="utf-8").replace("old-vector-marker", "new-vector-marker"),
        encoding="utf-8",
    )

    after = await search_service.search(query)  # no reindex call in between
    assert after.mode == "ranked"
    assert after.hits
    assert after.hits[0].path == target_path


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="deleting the index sidecar loses no knowledge",
)
async def test_deleting_the_index_sidecar_loses_no_knowledge(client) -> None:
    _create_collection(client, "shopee")
    target_path = _write_file(
        client,
        directory="shopee",
        title="Durable Note",
        description="d",
        body="This entry carries the codeword sidecar-marker for lookup.",
    )

    query = "sidecar-marker"
    embedder = FakeEmbedder({query: (1.0, 0.0, 0.0)})
    search_service = _search_service(embedder)

    first = await search_service.search(query)
    assert first.mode == "ranked"
    assert first.hits[0].path == target_path

    sidecar_path = index_module.index_path()
    assert sidecar_path.is_file()
    sidecar_path.unlink()

    # Everything that reads the files directly is unaffected by the sidecar
    # being gone.
    tree = client.get("/api/v1/knowledge/tree", params={"path": "shopee"})
    assert tree.status_code == 200, tree.text
    assert any(f["path"] == target_path for f in tree.json()["files"])

    grep = client.get("/api/v1/knowledge/grep", params={"pattern": "sidecar-marker"})
    assert grep.status_code == 200, grep.text
    assert any(m["path"] == target_path for m in grep.json()["matches"])

    read = client.get("/api/v1/knowledge/file", params={"path": target_path})
    assert read.status_code == 200, read.text
    assert "sidecar-marker" in read.json()["body"]

    # search still answers correctly with the sidecar missing — it rebuilds
    # as it goes, with no explicit rebuild call.
    rebuilt = await search_service.search(query)
    assert rebuilt.mode == "ranked"
    assert rebuilt.hits[0].path == target_path
    assert sidecar_path.is_file()

    # Delete it again, and this time take the embedder away too: search must
    # still answer, degrading to literal mode with a reason rather than
    # erroring or coming back empty (FR-027).
    sidecar_path.unlink()
    degraded = await _search_service(None).search(query)
    assert degraded.mode == "literal"
    assert degraded.reason
    assert degraded.hits
    assert degraded.hits[0].path == target_path
