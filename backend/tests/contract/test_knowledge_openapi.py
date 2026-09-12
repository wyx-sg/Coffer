"""Wire contract for the one ``knowledge`` kind.

The oracle is an explicit table: the routes, the wire models and the built-in
tool set are written down here, and the app must match them. That catches the
drift class this module exists for — a route quietly renamed or dropped, a
sixth built-in tool appearing without anyone deciding on it, a field slipping
back onto a payload the layer no longer has anything to put in.
"""

from __future__ import annotations

import pytest

from coffer.surfaces.http.knowledge import schemas

#: Every route the knowledge kind serves, as (method, path). Six gestures and a
#: manual tidy trigger; deleting a collection goes through the kind-agnostic
#: Resource route, so it is deliberately absent (spec knowledge FR-060).
_EXPECTED_ROUTES = {
    ("GET", "/api/v1/knowledge/collections"),
    ("POST", "/api/v1/knowledge/collections"),
    ("GET", "/api/v1/knowledge/tree"),
    ("GET", "/api/v1/knowledge/file"),
    ("PUT", "/api/v1/knowledge/file"),
    ("DELETE", "/api/v1/knowledge/file"),
    ("GET", "/api/v1/knowledge/grep"),
    ("POST", "/api/v1/knowledge/collections/{name}/tidy"),
}

#: Exactly five, and none of them is ``search``: with no ranked index behind it
#: that would be a second name for ``grep`` (FR-024, FR-040).
_EXPECTED_BUILTIN_TOOLS = {"list", "grep", "read", "write", "delete"}


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


def test_builtin_tool_set_is_the_five(builtin_registry) -> None:  # type: ignore[no-untyped-def]
    assert {t.name for t in builtin_registry.list()} == _EXPECTED_BUILTIN_TOOLS


def test_every_builtin_tool_describes_itself(builtin_registry) -> None:  # type: ignore[no-untyped-def]
    for tool in builtin_registry.list():
        assert tool.description.strip(), f"{tool.name} has no description"
        assert tool.input_schema.get("type") == "object"


def test_no_builtin_tool_takes_a_scope_or_a_mode(builtin_registry) -> None:  # type: ignore[no-untyped-def]
    """Both axes are gone: there are no retrieval modes, and a caller never
    names a scope — it sees every collection it is authorized for (FR-012)."""
    for tool in builtin_registry.list():
        properties = set(tool.input_schema.get("properties", {}))
        assert not properties & {"scope", "mode", "top_k", "cwd"}, tool.name


def test_a_write_payload_requires_a_description() -> None:
    """With no ranked index the catalogue is the retrieval surface, so a file
    that fails to describe itself is unfindable (FR-003)."""
    with pytest.raises(ValueError):
        schemas.FileWrite(title="t", description="", body="b", directory="shopee")


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
    register_knowledge_builtin_tools(registry, knowledge_service=None)  # type: ignore[arg-type]
    return registry
