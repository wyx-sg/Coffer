"""Wire contract for the one ``knowledge`` kind.

The oracle is an explicit table: the routes, the wire models and the built-in
tool set are written down here, and the app must match them. That catches the
drift class this module exists for — a route quietly renamed or dropped, a
built-in tool appearing without anyone deciding on it, a field slipping back
onto a payload the layer no longer has anything to put in.

Two entries in that table are the redesign itself, and they are the reason an
equality is used rather than a subset check. ``search`` and ``grep`` are gone
from the route set, and five of the six built-in tools are gone from the tool
set (spec knowledge FR-033): the layer keeps no index and offers no retrieval
on any surface, so a route or a tool reappearing here is not a new feature but
a reversal, and it should have to be written down before it ships.
"""

from __future__ import annotations

import pytest

from coffer.surfaces.http.knowledge import schemas

#: Every route the knowledge kind serves, as (method, path). Deleting a
#: collection goes through the kind-agnostic Resource route, so it is
#: deliberately absent (spec knowledge FR-033). So are ``search`` and ``grep``:
#: this surface serves the person and the UI, and neither retrieves.
_EXPECTED_ROUTES = {
    ("GET", "/api/v1/knowledge/collections"),
    ("POST", "/api/v1/knowledge/collections"),
    ("GET", "/api/v1/knowledge/tree"),
    ("GET", "/api/v1/knowledge/file"),
    ("DELETE", "/api/v1/knowledge/file"),
    # New knowledge arrives as material, never as a file write: there is no
    # ``PUT /file``, because a person edits a document in their own editor and
    # the next sweep carries the edit through (FR-013, FR-022).
    ("POST", "/api/v1/knowledge/material"),
    # The collection by its uid — a pass runs for minutes and must keep meaning
    # the same collection across a rename. The file routes above stay
    # name-addressed on purpose: their arguments are filesystem paths.
    ("POST", "/api/v1/knowledge/collections/{uid}/curate"),
    ("POST", "/api/v1/knowledge/upload"),
}

#: Exactly one (FR-050). Upload is deliberately not among them — a document
#: enters through a human surface (the Knowledge page, a channel, or the CLI),
#: not an agent's tool call — and neither is any way to read: an agent reads
#: the files with its own tools at the paths its delivered skill carries.
_EXPECTED_BUILTIN_TOOLS = {"write"}

#: The names that were retired with the retrieval surface. Listed by name so a
#: revival reds this test with the name in the message rather than as an
#: anonymous set difference.
_RETIRED_BUILTIN_TOOLS = {"list", "grep", "read", "search", "delete"}


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


def test_the_builtin_tool_set_is_write_alone(builtin_registry) -> None:  # type: ignore[no-untyped-def]
    names = {t.name for t in builtin_registry.list()}
    assert names == _EXPECTED_BUILTIN_TOOLS
    assert not names & _RETIRED_BUILTIN_TOOLS, sorted(names & _RETIRED_BUILTIN_TOOLS)


def test_every_builtin_tool_describes_itself(builtin_registry) -> None:  # type: ignore[no-untyped-def]
    for tool in builtin_registry.list():
        assert tool.description.strip(), f"{tool.name} has no description"
        assert tool.input_schema.get("type") == "object"


def test_the_write_tool_tells_the_agent_where_reading_happens(builtin_registry) -> None:  # type: ignore[no-untyped-def]
    """The tool's description is one of only two places this layer is ever in a
    model's context, and the one question a model will have on finding a write
    tool and no read tool is where the reading went (FR-050)."""
    [tool] = builtin_registry.list()
    assert "coffer-guide" in tool.description
    assert "no read tool" in tool.description


def test_no_builtin_tool_takes_a_scope_or_a_mode(builtin_registry) -> None:  # type: ignore[no-untyped-def]
    """Both axes are gone: there are no retrieval modes, and a caller never
    names a scope — it sees every collection it is authorized for (FR-012)."""
    for tool in builtin_registry.list():
        properties = set(tool.input_schema.get("properties", {}))
        assert not properties & {"scope", "mode", "top_k", "cwd"}, tool.name


def test_the_write_tool_never_lets_a_caller_choose_where_it_lands(builtin_registry) -> None:  # type: ignore[no-untyped-def]
    """FR-013: what an agent writes is material, and where it belongs in the
    collection is curation's call. A tool that accepted a ``path`` or a
    ``folder`` would be a way to write a document around the pass."""
    [tool] = builtin_registry.list()
    properties = set(tool.input_schema.get("properties", {}))
    assert properties == {"collection", "title", "description", "body"}
    assert tool.input_schema["required"] == ["collection", "title", "description"]


def test_a_material_payload_requires_a_description() -> None:
    """The skill's catalogue is how a document is ever found, so material that
    fails to describe itself is unfindable (FR-003)."""
    with pytest.raises(ValueError):
        schemas.MaterialIn(title="t", description="", body="b", collection="shopee")


def test_a_material_payload_names_a_collection_and_nothing_finer() -> None:
    """Material goes to a collection's inbox; no field aims it at a path."""
    assert set(schemas.MaterialIn.model_fields) == {"collection", "title", "description", "body"}
    assert not hasattr(schemas, "FileWrite")


def test_a_submission_says_whether_it_became_a_document() -> None:
    """``pending`` while it waits for a pass, ``written`` with the document's
    path when no model could merge it (FR-029)."""
    assert set(schemas.SubmissionOut.model_fields) == {"status", "collection", "title", "path"}


def test_no_wire_model_carries_a_retrieval_payload() -> None:
    """A search request, a hit or a grep match here would be a second
    retrieval surface no one decided to add (FR-050)."""
    for gone in ("SearchRequest", "SearchHit", "SearchResultOut", "GrepMatchOut", "GrepOut"):
        assert not hasattr(schemas, gone), gone


def test_an_ingested_document_names_no_original() -> None:
    """FR-016: neither the uploaded bytes nor a separate extracted file is
    kept, so there is no original to report — only the document the upload
    became, or that it is still pending."""
    fields = set(schemas.IngestedDocumentOut.model_fields)
    assert {"path", "pending", "title", "description", "converter"} == fields
    assert not fields & {"original_path", "raw_path"}


def test_a_collection_reports_documents_and_pending_material_apart() -> None:
    """Material waiting in the inbox is what an agent cannot read yet, and a
    single total would hide exactly that (FR-005)."""
    fields = set(schemas.CollectionOut.model_fields)
    assert {"document_count", "pending_count"} <= fields
    assert not fields & {"file_count", "source_count", "topic_count"}


def test_a_curation_report_names_its_item_and_what_it_promoted() -> None:
    fields = set(schemas.CurationOut.model_fields)
    assert {"item", "documents_before", "documents_after", "promoted"} <= fields
    assert schemas.CurationRequest.model_fields.keys() == {"document"}


def test_collection_config_carries_nothing() -> None:
    """A collection has no settings at all, and unknown keys are refused rather
    than quietly stored (FR-081)."""
    from coffer.domain.knowledge.config import KnowledgeConfig

    assert KnowledgeConfig().model_dump() == {}
    with pytest.raises(ValueError):
        KnowledgeConfig(retrieval_modes=["keyword"])  # type: ignore[call-arg]


@pytest.fixture
def app_with_knowledge(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))
    from coffer.surfaces.http.app import create_app

    return create_app()


@pytest.fixture
def builtin_registry():  # type: ignore[no-untyped-def]
    from coffer.application.builtin_tools import BuiltinToolRegistry
    from coffer.application.knowledge.builtin_tools import register_knowledge_builtin_tools

    registry = BuiltinToolRegistry()
    # This module tests the DECLARED surface (names, schemas), never an
    # invocation, so the service it would call is never reached.
    register_knowledge_builtin_tools(
        registry,
        knowledge_service=None,  # type: ignore[arg-type]
    )
    return registry
