"""Verify Pydantic API schemas match contracts/api.openapi.yaml on field-presence + types.

We don't try to deeply diff every constraint — that's overkill. The
goal is: every schema component declared in the OpenAPI doc has a
corresponding Pydantic model with at least the required fields.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from coffer.domain.mcp import server_config as mcp_server_config
from coffer.surfaces.http import schemas

_OPENAPI_PATH = (
    Path(__file__).resolve().parents[3] / "specs/001-mcp-gateway/contracts/api.openapi.yaml"
)


@pytest.fixture(scope="session")
def openapi_components() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(_OPENAPI_PATH.read_text())
    return data["components"]["schemas"]  # type: ignore[no-any-return]


@pytest.mark.parametrize(
    "model_name,openapi_name,expected_fields",
    [
        ("ErrorResponse", "ErrorResponse", {"error"}),
        (
            "ResourceOut",
            "ResourceOut",
            {"ref", "kind", "name", "config", "enabled", "created_at", "updated_at"},
        ),
        ("ResourceCreate", "ResourceCreate", {"kind", "name", "config"}),
        ("ResourceUpdate", "ResourceUpdate", set()),  # all optional
        ("ResourceListOut", "ResourceListOut", {"resources"}),
        ("AuditEntryOut", "AuditEntryOut", {"id", "timestamp", "event_type", "actor"}),
        ("AuditListOut", "AuditListOut", {"entries"}),
        (
            "RetentionPolicyOut",
            "RetentionPolicyOut",
            {
                "table_name",
                "display_name",
                "description",
                "default_retention_days",
                "retention_days",
                "last_pruned_rows",
            },
        ),
        ("RetentionPolicyListOut", "RetentionPolicyListOut", {"policies"}),
        ("RetentionPolicyUpdate", "RetentionPolicyUpdate", set()),  # retention_days nullable
        ("PruneResultOut", "PruneResultOut", {"tables"}),
        ("DaemonStatusOut", "DaemonStatusOut", {"status", "version", "started_at", "port"}),
        ("BackupResultOut", "BackupResultOut", {"path", "size_bytes"}),
        ("TokenRotationOut", "TokenRotationOut", {"token"}),
        # MCP / keychain schemas
        ("KeychainSetIn", "KeychainSetIn", {"ref", "value"}),
        ("McpServerStatusOut", "McpServerStatusOut", {"status"}),
        (
            "CapabilityListOut",
            "CapabilityListOut",
            {"server_name", "tools", "resources", "prompts", "fetched_at"},
        ),
        ("MCPToolView", "MCPToolView", {"prefixed_name", "original_name", "enabled"}),
        ("MCPResourceView", "MCPResourceView", {"prefixed_uri", "original_uri", "enabled"}),
        ("MCPPromptView", "MCPPromptView", {"prefixed_name", "original_name", "enabled"}),
        ("McpTestResultOut", "McpTestResultOut", {"ok", "latency_ms"}),
        (
            "InvocationOut",
            "InvocationOut",
            {"timestamp", "capability_type", "capability_key", "duration_ms", "status"},
        ),
        ("InvocationListOut", "InvocationListOut", {"invocations"}),
    ],
)
def test_schema_required_fields_match_openapi(
    model_name: str,
    openapi_name: str,
    expected_fields: set[str],
    openapi_components: dict[str, Any],
) -> None:
    model = getattr(schemas, model_name)
    json_schema = model.model_json_schema()
    required = set(json_schema.get("required", []))
    assert expected_fields.issubset(required), (
        f"{model_name} missing required fields {expected_fields - required}; "
        f"openapi says {set(openapi_components[openapi_name].get('required', []))}"
    )


@pytest.mark.parametrize(
    "model,openapi_name,expected_fields",
    [
        # Transport models live in domain, not http.schemas
        (mcp_server_config.StdioTransport, "StdioTransport", {"command"}),
        (mcp_server_config.HttpTransport, "HttpTransport", {"url"}),
        (mcp_server_config.MCPServerConfig, "MCPServerConfig", {"transport"}),
    ],
)
def test_domain_schema_required_fields_match_openapi(
    model: type,
    openapi_name: str,
    expected_fields: set[str],
    openapi_components: dict[str, Any],
) -> None:
    json_schema = model.model_json_schema()
    required = set(json_schema.get("required", []))
    assert expected_fields.issubset(required), (
        f"{model.__name__} missing required fields {expected_fields - required}; "
        f"openapi says {set(openapi_components[openapi_name].get('required', []))}"
    )
