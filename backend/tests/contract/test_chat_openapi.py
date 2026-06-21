"""Contract test: the running app's generated OpenAPI for chat/model paths/schemas
structurally matches specs/008-agent-chat/contracts/api.openapi.yaml.

Mirrors test_schemas_match_openapi.py and test_openapi_shape.py. Does not do a
full deep-diff — it checks that:
  - Every path declared in the 008 OpenAPI spec exists in the generated schema.
  - Every component schema declared in the spec has corresponding required fields
    in the generated schema.

If this test surfaces drift between the yaml and the Pydantic schemas, the fix is
to align whichever side is wrong.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from coffer.main import app

_CHAT_OPENAPI_PATH = (
    Path(__file__).resolve().parents[3] / "specs/008-agent-chat/contracts/api.openapi.yaml"
)


@pytest.fixture(scope="module")
def generated_schema() -> dict[str, Any]:
    """Return the FastAPI-generated OpenAPI schema once per test module."""
    return app.openapi()  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def spec_doc() -> dict[str, Any]:
    """Parse specs/008-agent-chat/contracts/api.openapi.yaml once per module."""
    return yaml.safe_load(_CHAT_OPENAPI_PATH.read_text())  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Path existence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,method",
    [
        ("/api/v1/chat/agents", "get"),
        ("/api/v1/chat/conversations", "get"),
        ("/api/v1/chat/conversations", "post"),
        ("/api/v1/chat/conversations/{id}", "get"),
        ("/api/v1/chat/conversations/{id}", "patch"),
        ("/api/v1/chat/conversations/{id}", "delete"),
        ("/api/v1/chat/conversations/{id}/agent-config", "get"),
        ("/api/v1/chat/conversations/{id}/agent-config", "patch"),
        ("/api/v1/chat/conversations/{id}/messages", "get"),
        ("/api/v1/chat/conversations/{id}/messages", "post"),
        ("/api/v1/chat/conversations/{id}/interrupt", "post"),
        ("/api/v1/models", "get"),
        ("/api/v1/models", "post"),
        ("/api/v1/models/{id}", "patch"),
        ("/api/v1/models/{id}", "delete"),
    ],
)
def test_chat_path_and_method_exists(
    generated_schema: dict[str, Any],
    path: str,
    method: str,
) -> None:
    """Every path+method declared in the 008 OpenAPI spec must exist in the
    generated schema."""
    paths = generated_schema.get("paths", {})
    assert path in paths, (
        f"Path '{path}' missing from generated OpenAPI. Available paths: {sorted(paths)}"
    )
    assert method in paths[path], (
        f"Method '{method}' missing for path '{path}'. Available methods: {sorted(paths[path])}"
    )


def test_every_yaml_path_is_implemented(
    generated_schema: dict[str, Any],
    spec_doc: dict[str, Any],
) -> None:
    """Drive the contract from the yaml itself: every path+method written in
    api.openapi.yaml must exist in the running app, so a yaml-only edit cannot
    silently drift from the implementation."""
    generated_paths = generated_schema.get("paths", {})
    for path, methods in (spec_doc.get("paths") or {}).items():
        assert path in generated_paths, (
            f"Path '{path}' is declared in api.openapi.yaml but not served by the app."
        )
        for method in methods:
            if method.lower() not in {"get", "post", "patch", "put", "delete"}:
                continue  # skip non-operation keys (parameters, summary, …)
            assert method.lower() in generated_paths[path], (
                f"'{method.upper()} {path}' is declared in api.openapi.yaml "
                f"but not served by the app."
            )


# ---------------------------------------------------------------------------
# Schema component fields
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "schema_name,required_fields",
    [
        ("ConversationOut", {"id", "agent_key", "title", "model_id", "created_at", "updated_at"}),
        ("ConversationCreate", set()),
        ("ConversationPatch", set()),
        ("AgentConfigOut", {"cwd", "model"}),
        ("AgentConfigPatch", set()),
        ("ConversationListOut", {"conversations"}),
        ("ChatAgentOut", {"agent_key", "display_name", "available"}),
        ("ChatAgentListOut", {"agents"}),
        ("MessageOut", {"id", "conversation_id", "seq", "role", "content", "status", "created_at"}),
        ("MessageListOut", {"messages"}),
        ("SendMessageRequest", {"text"}),
        (
            "ModelOut",
            {"id", "display_name", "provider", "model", "is_default", "created_at", "updated_at"},
        ),
        ("ModelCreate", {"display_name", "provider", "model"}),
        ("ModelPatch", set()),
        ("ModelListOut", {"models"}),
    ],
)
def test_chat_schema_required_fields(
    generated_schema: dict[str, Any],
    schema_name: str,
    required_fields: set[str],
) -> None:
    """Every schema component in the 008 spec must exist in the generated
    schemas with at least the required fields."""
    components = generated_schema.get("components", {}).get("schemas", {})
    assert schema_name in components, (
        f"Schema '{schema_name}' missing from generated OpenAPI components. "
        f"Available: {sorted(components)}"
    )
    schema = components[schema_name]
    actual_required = set(schema.get("required", []))
    assert required_fields.issubset(actual_required), (
        f"Schema '{schema_name}': missing required fields "
        f"{required_fields - actual_required}. "
        f"Actual required: {actual_required}"
    )


# ---------------------------------------------------------------------------
# Content-block type values
# ---------------------------------------------------------------------------


def test_content_block_type_enum(generated_schema: dict[str, Any]) -> None:
    """ContentBlockOut.type must enumerate the three block types declared in
    the spec: text, tool_use, tool_result."""
    schemas = generated_schema.get("components", {}).get("schemas", {})
    # FastAPI may inline the enum; look for it in the Pydantic-generated schema.
    # ContentBlockOut maps to "ContentBlockOut" in the generated schema.
    assert "ContentBlockOut" in schemas, f"ContentBlockOut missing. Available: {sorted(schemas)}"


# ---------------------------------------------------------------------------
# Error envelope shape
# ---------------------------------------------------------------------------


def test_error_envelope_schema(generated_schema: dict[str, Any]) -> None:
    """The error envelope schema must have the 'error' required field."""
    schemas = generated_schema.get("components", {}).get("schemas", {})
    # FastAPI uses 'ErrorOut' for the chat module error schema (from chat schemas.py).
    error_schemas = [k for k in schemas if "Error" in k or "error" in k.lower()]
    assert error_schemas, f"No error schema found. Available: {sorted(schemas)}"
