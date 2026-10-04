"""The served OpenAPI document states Coffer's error envelope and what a response always carries.

Every checked-in contract is cut from this document, so what it says wrongly
the contracts and the generated frontend types say wrongly too.
"""

from __future__ import annotations

from typing import Any

from coffer.surfaces.http.openapi_document import describe_errors

_ENVELOPE = {"$ref": "#/components/schemas/ErrorResponse"}


def _document() -> dict[str, Any]:
    return {
        "paths": {
            "/things": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/ThingIn"}}
                        }
                    },
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ThingOut"}
                                }
                            }
                        },
                        "422": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/HTTPValidationError"}
                                }
                            }
                        },
                    },
                }
            }
        },
        "components": {
            "schemas": {
                "ThingIn": {"properties": {"name": {}, "tags": {}}, "required": ["name"]},
                "ThingOut": {
                    "properties": {"name": {}, "note": {}, "part": {}},
                    "required": ["name"],
                },
                "PartOut": {"properties": {"size": {}}},
                "HTTPValidationError": {},
                "ValidationError": {},
            }
        },
    }


def test_validation_failures_and_every_other_error_are_the_envelope() -> None:
    doc = describe_errors(_document())
    responses = doc["paths"]["/things"]["post"]["responses"]
    assert responses["422"]["content"]["application/json"]["schema"] == _ENVELOPE
    assert responses["default"]["content"]["application/json"]["schema"] == _ENVELOPE
    schemas = doc["components"]["schemas"]
    assert "HTTPValidationError" not in schemas and "ValidationError" not in schemas
    assert set(schemas["ErrorResponse"]["properties"]) == {"error"}
    assert {"code", "message", "details"} <= set(schemas["ErrorDetail"]["properties"])


def test_a_response_schema_requires_every_field_and_a_request_schema_keeps_its_defaults() -> None:
    doc = describe_errors(_document())
    schemas = doc["components"]["schemas"]
    assert schemas["ThingOut"]["required"] == ["name", "note", "part"]
    assert schemas["PartOut"]["required"] == ["size"]
    assert schemas["ThingIn"]["required"] == ["name"]
