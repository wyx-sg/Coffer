"""Wire contract for the one ``knowledge`` kind.

The oracle is an explicit table: the routes and the wire models are written
down here, and the app must match them. That catches the drift class this
module exists for — a route quietly renamed or dropped, a field slipping back
onto a payload the layer no longer has anything to put in.

Two facts in that table are the redesign itself, and they are the reason an
equality is used rather than a subset check. ``search``, ``grep`` and
``material`` are gone from the route set, and the layer has no built-in tool at
all (spec knowledge "Expose no knowledge tool", "Manage knowledge in the web
UI"): it keeps no index, offers no retrieval on any surface, and the routes are
the web UI's own, so a route or a tool reappearing here is not a new feature but
a reversal, and it should have to be written down before it ships.
"""

from __future__ import annotations

import pytest

from coffer.surfaces.http.knowledge import schemas

#: Every route the knowledge kind serves, as (method, path). Deleting a
#: collection goes through the kind-agnostic Resource route, so it is
#: deliberately absent (spec knowledge "Manage knowledge in the web UI"). So are
#: ``search`` and ``grep``: this surface serves the person and the UI, and
#: neither retrieves.
_EXPECTED_ROUTES = {
    ("GET", "/api/v1/knowledge/collections"),
    ("POST", "/api/v1/knowledge/collections"),
    ("GET", "/api/v1/knowledge/tree"),
    ("GET", "/api/v1/knowledge/file"),
    ("DELETE", "/api/v1/knowledge/file"),
    # New knowledge arrives as material: an upload (see "Promote submitted
    # material at once"). There is no route that saves a document, no material
    # route and no route that creates a document at a path (see "Manage
    # knowledge in the web UI").
    # The prompt that hands tidying every collection to the person's agent. The
    # file routes above stay name-addressed on purpose: their arguments are
    # filesystem paths.
    ("GET", "/api/v1/knowledge/tidy-handoff"),
    ("POST", "/api/v1/knowledge/upload"),
    # The changes feed (see "Follow edits across collections in one feed"),
    # which a delete's Undo reads; putting back what a delete removed (see "Undo
    # a knowledge delete from its toast"); and a collection's description, its
    # README's opening paragraph (see "Name a collection by its folder and edit
    # its description in place"). No route lists, diffs or restores a version.
    ("GET", "/api/v1/knowledge/changes"),
    ("POST", "/api/v1/knowledge/changes/{version}/restore"),
    ("PUT", "/api/v1/knowledge/collections/{uid}/description"),
}


def _knowledge_routes(app) -> set[tuple[str, str]]:  # type: ignore[no-untyped-def]
    """Every knowledge route the app DECLARES, read from its OpenAPI schema.

    Read from the schema rather than by walking ``app.routes``: FastAPI 0.141
    stopped flattening an included router's routes into that list (they sit
    behind an opaque wrapper object), so introspecting it silently found
    nothing. The schema is the wire contract anyway, which is what this module
    is about.
    """
    schema = app.openapi()
    return {
        (method.upper(), path)
        for path, operations in schema.get("paths", {}).items()
        if path.startswith("/api/v1/knowledge")
        for method in operations
        if method.upper() not in {"HEAD", "OPTIONS", "PARAMETERS"}
    }


def test_every_knowledge_route_is_declared(app_with_knowledge) -> None:  # type: ignore[no-untyped-def]
    assert _knowledge_routes(app_with_knowledge) == _EXPECTED_ROUTES


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="the routes are the web UI's, with no material or create-at-path route",
)
def test_the_routes_carry_no_material_or_create_at_path_route(app_with_knowledge) -> None:  # type: ignore[no-untyped-def]
    routes = _knowledge_routes(app_with_knowledge)
    assert routes, "the route table must not be empty"
    assert not {path for _, path in routes if path.endswith("/material")}
    assert {m for m, p in routes if p == "/api/v1/knowledge/file"} == {"GET", "DELETE"}
    assert not {path for _, path in routes if "/history" in path}


def test_no_material_wire_model_remains() -> None:
    """The web UI never submitted material through REST, so the payload and its
    answer are gone with the route."""
    assert not hasattr(schemas, "MaterialIn")
    assert not hasattr(schemas, "SubmissionOut")
    assert not hasattr(schemas, "FileWrite")


def test_the_knowledge_layer_registers_no_builtin_tool() -> None:
    """Knowledge is plain files an agent reads and writes with its own tools
    (see "Expose no knowledge tool")."""
    import importlib.util

    assert importlib.util.find_spec("coffer.application.knowledge.builtin_tools") is None


def test_no_wire_model_carries_a_retrieval_payload() -> None:
    """A search request, a hit or a grep match here would be a second retrieval
    surface no one decided to add (see "Manage knowledge in the web UI")."""
    for gone in ("SearchRequest", "SearchHit", "SearchResultOut", "GrepMatchOut", "GrepOut"):
        assert not hasattr(schemas, gone), gone


def test_an_ingested_document_names_no_original() -> None:
    """Neither the uploaded bytes nor a separate extracted file is kept, so
    there is no original to report — only the document the upload became (see
    "Convert uploads into documents without keeping the original")."""
    fields = set(schemas.IngestedDocumentOut.model_fields)
    assert {"path", "title", "description", "converter"} == fields
    assert not fields & {"original_path", "raw_path"}


def test_a_collection_reports_its_documents_and_a_tidy_handoff() -> None:
    fields = set(schemas.CollectionOut.model_fields)
    assert {"document_count", "tidy_handoff"} <= fields
    assert not fields & {"pending_count", "file_count", "source_count", "topic_count"}


def test_no_curation_wire_model_remains() -> None:
    for gone in ("CurationRequest", "CurationOut", "CurationRunOut"):
        assert not hasattr(schemas, gone), gone


def test_collection_config_carries_nothing() -> None:
    """A collection has no settings at all, and unknown keys are refused rather
    than quietly stored (spec resource-framework "Validate every registration
    and persist nothing on failure")."""
    from coffer.domain.knowledge.config import KnowledgeConfig

    assert KnowledgeConfig().model_dump() == {}
    with pytest.raises(ValueError):
        KnowledgeConfig(retrieval_modes=["keyword"])  # type: ignore[call-arg]


@pytest.fixture
def app_with_knowledge(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    from coffer.surfaces.http.app import create_app

    return create_app()
