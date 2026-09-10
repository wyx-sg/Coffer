"""Wire contract for the one ``knowledge`` kind.

The pre-merge version of this module diffed the live app against the OpenAPI
yamls of the two specs that have since merged — the knowledge base's and
memory's. Those contracts describe a world with two kinds and two route trees,
which no longer exists; until the merged spec lands they cannot be the oracle. So the oracle
here is an explicit table instead: the routes, the enums and the built-in tool
set are written down, and the app must match them.

That still catches the drift class the yaml check existed for — a route quietly
renamed or dropped, an enum that grew a value the wire never learned about, a
ninth built-in tool appearing without anyone deciding on it. **When the merged
``knowledge`` OpenAPI contract is written, restore the yaml-driven check** (the
component→model coverage assertions) on top of this one.
"""

from __future__ import annotations

import pytest

from coffer.surfaces.http.knowledge import schemas

# Every route the knowledge kind serves, as (method, path). The scope name is
# always the first path segment after the prefix: one tree, one addressing rule.
_EXPECTED_ROUTES = {
    # scopes
    ("GET", "/api/v1/knowledge"),
    ("POST", "/api/v1/knowledge"),
    ("GET", "/api/v1/knowledge/{name}"),
    ("PATCH", "/api/v1/knowledge/{name}"),
    ("PATCH", "/api/v1/knowledge/{name}/label"),
    ("GET", "/api/v1/knowledge/{name}/metrics"),
    # entries
    ("POST", "/api/v1/knowledge/{name}/entries"),
    ("GET", "/api/v1/knowledge/{name}/entries"),
    ("DELETE", "/api/v1/knowledge/{name}/entries"),
    ("GET", "/api/v1/knowledge/{name}/entries/{entry_id}"),
    ("PATCH", "/api/v1/knowledge/{name}/entries/{entry_id}"),
    ("DELETE", "/api/v1/knowledge/{name}/entries/{entry_id}"),
    # documents
    ("POST", "/api/v1/knowledge/{name}/documents"),
    ("GET", "/api/v1/knowledge/{name}/documents"),
    ("GET", "/api/v1/knowledge/{name}/documents/status"),
    ("POST", "/api/v1/knowledge/{name}/documents/reembed-batch"),
    ("GET", "/api/v1/knowledge/{name}/documents/{document_id}"),
    ("PUT", "/api/v1/knowledge/{name}/documents/{document_id}"),
    ("DELETE", "/api/v1/knowledge/{name}/documents/{document_id}"),
    ("POST", "/api/v1/knowledge/{name}/documents/{document_id}/reconvert"),
    ("POST", "/api/v1/knowledge/{name}/documents/{document_id}/update-source"),
    # retrieval + maintenance
    ("POST", "/api/v1/knowledge/{name}/recall"),
    ("POST", "/api/v1/knowledge/{name}/search"),
    ("POST", "/api/v1/knowledge/{name}/grep"),
    ("POST", "/api/v1/knowledge/{name}/reindex"),
    ("POST", "/api/v1/knowledge/{name}/check-sources"),
    # organizing passes
    ("POST", "/api/v1/knowledge/{name}/organize"),
    ("POST", "/api/v1/knowledge/{name}/reorg"),
    ("POST", "/api/v1/knowledge/merge_scan"),
    ("POST", "/api/v1/knowledge/merge"),
    # lanes
    ("GET", "/api/v1/knowledge/{name}/rules"),
    ("DELETE", "/api/v1/knowledge/{name}/rules"),
    ("GET", "/api/v1/knowledge/{name}/handoff"),
    ("DELETE", "/api/v1/knowledge/{name}/handoff/{branch}"),
    ("GET", "/api/v1/knowledge/{name}/consolidation-log"),
    ("DELETE", "/api/v1/knowledge/{name}/consolidation-log"),
}

#: The eight built-in MCP tools, unprefixed (the gateway adds ``coffer__``).
#: Two came from the handoff lane and stay as they were; the other six replace
#: the twelve the two pre-merge kinds registered between them.
_EXPECTED_TOOLS = {
    "search",
    "grep",
    "read",
    "list",
    "write",
    "delete",
    "set_handoff",
    "resume",
}


@pytest.fixture(scope="module")
def app_routes() -> set[tuple[str, str]]:
    """Every (method, path) the app publishes.

    Read from the generated OpenAPI document rather than by walking
    ``app.routes``: since FastAPI 0.141 ``include_router`` stores an opaque
    wrapper instead of copying the sub-router's routes up, so a direct walk
    sees nothing for any router that was included. The schema is what the app
    actually serves, and it is stable across that implementation detail.
    """
    from coffer.surfaces.http.app import create_app

    schema = create_app().openapi()
    return {
        (method.upper(), path)
        for path, operations in schema["paths"].items()
        for method in operations
    }


def test_every_knowledge_route_is_declared(app_routes) -> None:
    """The app serves exactly the routes above — no more, no fewer."""
    live = {(m, p) for m, p in app_routes if p.startswith("/api/v1/knowledge")}
    assert live == _EXPECTED_ROUTES, (
        f"undeclared routes: {sorted(live - _EXPECTED_ROUTES)}; "
        f"missing routes: {sorted(_EXPECTED_ROUTES - live)}"
    )


def test_no_pre_merge_route_trees_remain(app_routes) -> None:
    """``/memory_stores`` and ``/knowledge_bases`` are gone, not aliased."""
    stale = {(m, p) for m, p in app_routes if "memory_stores" in p or "knowledge_bases" in p}
    assert not stale, f"pre-merge route tree still mounted: {sorted(stale)}"


def test_builtin_tool_set_is_the_eight() -> None:
    from coffer.application.builtin_tools import BuiltinToolRegistry
    from coffer.application.knowledge.builtin_tools import register_knowledge_builtin_tools
    from coffer.application.knowledge.document_tools import register_document_builtin_tools

    registry = BuiltinToolRegistry()
    register_knowledge_builtin_tools(
        registry,
        knowledge_service=None,  # type: ignore[arg-type]
        handoff_service=None,  # type: ignore[arg-type]
    )
    register_document_builtin_tools(
        registry,
        resources=None,  # type: ignore[arg-type]
        knowledge_service=None,  # type: ignore[arg-type]
    )
    assert {t.name for t in registry.list()} == _EXPECTED_TOOLS


def test_every_builtin_tool_describes_itself() -> None:
    """The description is what an agent reads to choose a tool, so it has to say
    something. A one-liner that only restates the name is not a description."""
    from coffer.application.builtin_tools import BuiltinToolRegistry
    from coffer.application.knowledge.builtin_tools import register_knowledge_builtin_tools
    from coffer.application.knowledge.document_tools import register_document_builtin_tools

    registry = BuiltinToolRegistry()
    register_knowledge_builtin_tools(
        registry,
        knowledge_service=None,  # type: ignore[arg-type]
        handoff_service=None,  # type: ignore[arg-type]
    )
    register_document_builtin_tools(
        registry,
        resources=None,  # type: ignore[arg-type]
        knowledge_service=None,  # type: ignore[arg-type]
    )
    for tool in registry.list():
        assert len(tool.description) >= 80, f"{tool.name} needs a real description"
        assert tool.input_schema["type"] == "object"


def test_retrieval_mode_enum_values_match_the_domain() -> None:
    """Enum VALUES are the drift class a field-coverage check waves through.

    The config patch is what carries the enum on the wire — both as the list a
    scope indexes with and as the single default mode."""
    from coffer.domain.knowledge.retrieval import RETRIEVAL_MODES

    props = schemas.KnowledgeConfigPatch.model_json_schema()["properties"]
    modes_enum = props["retrieval_modes"]["anyOf"][0]["items"]["enum"]
    default_enum = props["default_mode"]["anyOf"][0]["enum"]
    assert set(modes_enum) == set(RETRIEVAL_MODES)
    assert set(default_enum) == set(RETRIEVAL_MODES)


def test_scope_kind_enum_covers_the_three_scopes() -> None:
    """A scope is one of exactly three things, and the wire says which."""
    schema = schemas.ScopeOut.model_json_schema()
    assert set(schema["properties"]["scope"]["enum"]) == {"global", "project", "named"}


def test_recall_scope_enum_is_project_global_both() -> None:
    schema = schemas.RecallRequest.model_json_schema()
    assert set(schema["properties"]["scope"]["enum"]) == {"global", "project", "both"}


def test_scope_config_carries_no_embedding_fields() -> None:
    """Embedding is installation-wide. Both pre-merge faces exposed dead
    per-scope embedding fields; a re-introduction would be a regression."""
    from coffer.domain.knowledge.scope_config import KnowledgeConfig

    fields = set(KnowledgeConfig.model_fields)
    assert not {f for f in fields if f.startswith("embedding")}
    assert "enabled_modes" not in fields  # renamed to retrieval_modes


def test_create_rejects_the_auto_provisioned_scope_names() -> None:
    """``global`` / ``project-*`` are provisioned on first use; creating one by
    hand would let a typo masquerade as an auto-scope."""
    for name in ("global", "project-01J0000000000000000000000A"):
        with pytest.raises(ValueError):
            schemas.ScopeCreate(name=name)
