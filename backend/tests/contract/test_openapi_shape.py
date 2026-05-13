"""Contract test: runtime OpenAPI dump conforms to the published wire shape.

When feature specs land with their own `specs/<NNN>-*/contracts/*.openapi.yaml`,
this file (or sibling files) will compare the hand-written yaml against the
runtime dump. For the scaffolding phase, we just assert the runtime dump is
structurally valid and exposes the surfaces we expect.
"""

from coffer.main import app


def test_openapi_dump_declares_openapi_3() -> None:
    schema = app.openapi()
    assert schema["openapi"].startswith("3.")


def test_openapi_dump_has_project_metadata() -> None:
    schema = app.openapi()
    assert schema["info"]["title"] == "Coffer"
    assert schema["info"]["version"] == "0.1.0"


def test_openapi_dump_exposes_health_endpoint() -> None:
    schema = app.openapi()
    assert "/health" in schema["paths"]
    get_op = schema["paths"]["/health"]["get"]
    assert get_op["responses"]["200"]["description"]


def test_openapi_dump_references_health_response_schema() -> None:
    schema = app.openapi()
    assert "HealthResponse" in schema["components"]["schemas"]
    health_response = schema["components"]["schemas"]["HealthResponse"]
    assert set(health_response["required"]) == {"status", "version"}
    assert health_response["properties"]["status"]["type"] == "string"
    assert health_response["properties"]["version"]["type"] == "string"
