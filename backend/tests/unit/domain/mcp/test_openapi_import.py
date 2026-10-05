"""Reading OpenAPI documents into custom tools (design add-http-custom-tools §8)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.domain.mcp.http_api import HttpApiTransport
from coffer.domain.mcp.openapi_import import (
    OpenApiError,
    apply_reimport,
    plan_reimport,
    read_openapi,
)

_DOC = {
    "openapi": "3.0.3",
    "info": {"title": "Billing", "version": "2"},
    "servers": [{"url": "/{ver}", "variables": {"ver": {"default": "v2"}}}],
    "components": {
        "securitySchemes": {"key": {"type": "apiKey", "in": "header", "name": "X-Api-Key"}},
        "schemas": {
            "Node": {
                "type": "object",
                "properties": {"child": {"$ref": "#/components/schemas/Node"}},
            },
        },
        "parameters": {
            "Id": {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}
        },
    },
    "paths": {
        "/nodes/{id}": {
            "parameters": [{"$ref": "#/components/parameters/Id"}],
            "get": {"operationId": "getNode", "parameters": [{"name": "depth", "in": "query"}]},
            "put": {
                "operationId": "getNode",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {"schema": {"$ref": "#/components/schemas/Node"}}
                    },
                },
            },
        },
        "/upload": {"post": {"requestBody": {"content": {"multipart/form-data": {}}}}},
    },
}


def test_operations_become_draft_tools_with_holes_and_a_body_argument():
    r = read_openapi(_DOC, source_url="https://billing.example/specs/openapi.json")
    assert r.base_url == "https://billing.example/v2"
    assert r.auth_header == "X-Api-Key"
    tools = {op.key: op.tool for op in r.operations}
    get = tools["GET /nodes/{id}"]
    assert get.name == "get_node" and get.path == "/nodes/{id}?depth={depth}"
    assert get.input_schema["required"] == ["id"]
    put = tools["PUT /nodes/{id}"]
    assert put.name == "get_node_2"  # the duplicate operationId is de-duplicated
    assert put.body_template == "{body}"
    assert put.input_schema["properties"]["body"]["properties"]["child"] is not None
    assert tools["POST /upload"].name == "post_upload"
    assert any("not JSON" in w for w in r.warnings)


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="an OpenAPI document's description is read for the new group"
)
def test_the_specs_info_description_is_read_for_the_group():
    r = read_openapi({**_DOC, "info": {**_DOC["info"], "description": "  Bills and nodes \n"}})
    assert r.description == "Bills and nodes"
    assert read_openapi(_DOC).description is None


def test_a_document_that_is_not_openapi_3_is_refused():
    with pytest.raises(OpenApiError):
        read_openapi({"swagger": "2.0"})


def test_reimport_keeps_hand_made_tools_and_switches():
    first = read_openapi(_DOC)
    tools = [op.tool for op in first.operations if op.key != "POST /upload"]
    tools[0] = tools[0].model_copy(update={"enabled": False})
    hand = {"name": "by_hand", "path": "/ping"}
    transport = HttpApiTransport(
        base_url="https://billing.example/v2",
        tools=[*tools, hand],
        source={
            "kind": "url",
            "location": "https://billing.example/openapi.json",
            "fetched_at": datetime(2026, 9, 1, tzinfo=UTC),
            "skipped": ["POST /upload"],
        },
    )
    doc = {**_DOC, "paths": {k: v for k, v in _DOC["paths"].items() if k != "/upload"}}
    doc["paths"]["/nodes/{id}"] = {**doc["paths"]["/nodes/{id}"]}
    doc["paths"]["/nodes/{id}"].pop("put")
    doc["paths"]["/fresh"] = {"get": {"operationId": "fresh"}}
    reading = read_openapi(doc)
    plan = plan_reimport(transport, reading)
    assert [op.key for op in plan.added] == ["GET /fresh"]
    assert plan.removed == ["get_node_2"]
    after = apply_reimport(
        transport, reading, add_keys={"GET /fresh"}, fetched_at=datetime(2026, 9, 30, tzinfo=UTC)
    )
    names = {t.name: t for t in after.tools}
    assert set(names) == {"get_node", "by_hand", "fresh"}
    assert names["get_node"].enabled is False
    assert after.source is not None and after.source.skipped == []
