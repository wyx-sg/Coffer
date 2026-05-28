"""Contract test: runtime OpenAPI dump conforms to the published wire shape.

Compares the runtime FastAPI schema against the hand-written
`specs/001-mcp-gateway/contracts/api.openapi.yaml` for the surfaces we
have already implemented. Additional endpoints are verified as their tasks land.
"""

from coffer.main import app


def test_openapi_dump_declares_openapi_3() -> None:
    schema = app.openapi()
    assert schema["openapi"].startswith("3.")


def test_openapi_dump_has_project_metadata() -> None:
    schema = app.openapi()
    assert schema["info"]["title"] == "Coffer"
    assert schema["info"]["version"] == "0.1.0"


def test_openapi_dump_exposes_daemon_status_endpoint() -> None:
    schema = app.openapi()
    assert "/api/v1/daemon/status" in schema["paths"]
    get_op = schema["paths"]["/api/v1/daemon/status"]["get"]
    assert get_op["responses"]["200"]["description"]


def test_openapi_dump_references_daemon_status_schema() -> None:
    schema = app.openapi()
    assert "DaemonStatusOut" in schema["components"]["schemas"]
    daemon_status = schema["components"]["schemas"]["DaemonStatusOut"]
    assert set(daemon_status["required"]) == {"status", "version", "started_at", "port"}
    status_prop = daemon_status["properties"]["status"]
    assert status_prop["type"] == "string"
    assert status_prop.get("enum") == [
        "starting",
        "ready",
        "draining",
    ], f"DaemonStatusOut.status enum mismatch in runtime schema: {status_prop}"
    assert daemon_status["properties"]["version"]["type"] == "string"
    assert daemon_status["properties"]["port"]["type"] == "integer"
