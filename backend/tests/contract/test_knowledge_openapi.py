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
    # The one document write: a person's edited body, kept frontmatter, and a
    # fingerprint guard (see "Save a document edited in the web UI"). New
    # knowledge arrives as material: an upload, or a file an agent writes into
    # a collection's inbox (see "Submit every entrance's input as material").
    # There is no material route and no route that creates a document at a path
    # (see "Manage knowledge in the web UI").
    ("PUT", "/api/v1/knowledge/file"),
    # The collection by its uid — a pass runs for minutes and must keep meaning
    # the same collection across a rename. The file routes above stay
    # name-addressed on purpose: their arguments are filesystem paths.
    ("POST", "/api/v1/knowledge/collections/{uid}/curate"),
    ("POST", "/api/v1/knowledge/upload"),
    # History (see "Keep every document's history and undo a pass as a whole",
    # "Follow knowledge changes across collections"): a document's versions and
    # one version's diff, restoring one, the recent changes and one change in
    # full, and undoing a curation pass. None creates a document at a path.
    ("GET", "/api/v1/knowledge/history"),
    ("GET", "/api/v1/knowledge/history/diff"),
    ("POST", "/api/v1/knowledge/history/restore"),
    ("GET", "/api/v1/knowledge/changes"),
    ("GET", "/api/v1/knowledge/changes/{version}"),
    ("POST", "/api/v1/knowledge/changes/{version}/undo"),
    # One version's body, for Compare with current; putting back what a delete
    # removed (see "Restore a deleted collection or document from Recent
    # changes"); and a collection's description, its README's opening
    # paragraph (see "Name a collection by its folder and edit its description
    # in place").
    ("GET", "/api/v1/knowledge/history/version"),
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
    assert {m for m, p in routes if p == "/api/v1/knowledge/file"} == {"GET", "PUT", "DELETE"}


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
    there is no original to report — only the document the upload became, or
    that it is still pending (see "Convert uploads into material without
    keeping them")."""
    fields = set(schemas.IngestedDocumentOut.model_fields)
    assert {"path", "pending", "title", "description", "converter"} == fields
    assert not fields & {"original_path", "raw_path"}


def test_a_collection_reports_documents_and_pending_material_apart() -> None:
    """Material waiting in the inbox is what an agent cannot read yet, and a
    single total would hide exactly that (see "Hide dot-prefixed entries except
    the inbox")."""
    fields = set(schemas.CollectionOut.model_fields)
    assert {"document_count", "pending_count"} <= fields
    assert not fields & {"file_count", "source_count", "topic_count"}


def test_a_curation_report_names_its_item_and_what_it_promoted() -> None:
    fields = set(schemas.CurationOut.model_fields)
    assert {"item", "documents_before", "documents_after", "promoted"} <= fields
    assert schemas.CurationRequest.model_fields.keys() == {"document"}


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
