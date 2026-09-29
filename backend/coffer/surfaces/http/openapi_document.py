"""Make the daemon's OpenAPI document say what the daemon really answers.

The document FastAPI derives from the routes is the source of every checked-in
contract (``make contracts``) and of the docs-site REST reference, so what it
gets wrong, both of them get wrong. FastAPI gets one thing wrong about Coffer:
errors. It declares a ``422`` answering ``HTTPValidationError`` (``{"detail":
[...]}``) on every route that takes input, while :func:`errors.register`
answers every failure — a validation failure included — with Coffer's own
envelope ``{"error": {"code", "message", "details"}}``, and it declares no
other error at all although any route can answer one.

:func:`install` wraps ``app.openapi`` so the document it serves and caches has
the envelope instead: each FastAPI ``422`` is replaced by the envelope under
``CONFIG_INVALID``, every operation gains a ``default`` response carrying the
envelope, and FastAPI's two validation schemas, which no longer describe
anything the daemon sends, are dropped. The status codes of specific errors
live in the error-code catalogue, not per route.

It also marks every field of a response-only schema required: Pydantic leaves
a defaulted field out of ``required`` because a *sender* may omit it, but the
daemon, sending, never does.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI

from coffer.surfaces.http.schemas import ErrorResponse

_REF_PREFIX = "#/components/schemas/"
_FASTAPI_VALIDATION_SCHEMAS = ("HTTPValidationError", "ValidationError")
_OPERATION_METHODS = frozenset({"get", "put", "post", "delete", "options", "head", "patch"})


def _envelope_response(description: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": {
            "application/json": {"schema": {"$ref": f"{_REF_PREFIX}{ErrorResponse.__name__}"}}
        },
    }


def _add_envelope_schemas(schemas: dict[str, Any]) -> None:
    doc = ErrorResponse.model_json_schema(ref_template=_REF_PREFIX + "{model}")
    for name, definition in doc.pop("$defs", {}).items():
        schemas.setdefault(name, definition)
    schemas.setdefault(ErrorResponse.__name__, doc)


def describe_errors(document: dict[str, Any]) -> dict[str, Any]:
    """Rewrite ``document`` in place so its errors are Coffer's envelope."""
    schemas = document.setdefault("components", {}).setdefault("schemas", {})
    _add_envelope_schemas(schemas)
    for operations in (document.get("paths") or {}).values():
        for method, operation in operations.items():
            if method not in _OPERATION_METHODS:
                continue
            responses = operation.setdefault("responses", {})
            if "422" in responses:
                responses["422"] = _envelope_response(
                    "The request failed validation (`CONFIG_INVALID`); the submitted "
                    "values are not echoed back."
                )
            responses.setdefault(
                "default",
                _envelope_response("Any other error, as Coffer's error envelope."),
            )
    for name in _FASTAPI_VALIDATION_SCHEMAS:
        schemas.pop(name, None)
    _require_every_response_field(document, schemas)
    return document


def _refs(node: Any) -> set[str]:
    found: set[str] = set()
    stack = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            ref = current.get("$ref")
            if isinstance(ref, str) and ref.startswith(_REF_PREFIX):
                found.add(ref[len(_REF_PREFIX) :])
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return found


def _closure(roots: set[str], schemas: dict[str, Any]) -> set[str]:
    seen: set[str] = set()
    pending = list(roots)
    while pending:
        name = pending.pop()
        if name in seen or name not in schemas:
            continue
        seen.add(name)
        pending.extend(_refs(schemas[name]))
    return seen


def _require_every_response_field(document: dict[str, Any], schemas: dict[str, Any]) -> None:
    """Mark every property of a response-only schema required.

    A field with a default is optional to *send*, so Pydantic leaves it out of
    ``required`` — but a response always carries it, because no route excludes
    unset or ``None`` fields. Left alone, the generated client would type every
    defaulted response field as possibly absent. A schema that is also a
    request body or parameter keeps Pydantic's reading, which is the true one
    for the request side.
    """
    inputs: set[str] = set()
    for operations in (document.get("paths") or {}).values():
        for method, operation in operations.items():
            if method not in _OPERATION_METHODS:
                continue
            inputs |= _refs(operation.get("requestBody"))
            inputs |= _refs(operation.get("parameters"))
    for name in set(schemas) - _closure(inputs, schemas):
        properties = schemas[name].get("properties")
        if properties:
            schemas[name]["required"] = list(properties)


def install(app: FastAPI) -> None:
    """Serve (and cache) the corrected document from ``app.openapi``."""
    generate: Callable[[], dict[str, Any]] = app.openapi
    corrected: dict[str, Any] | None = None

    def openapi() -> dict[str, Any]:
        nonlocal corrected
        if corrected is None:
            corrected = describe_errors(generate())
        return corrected

    app.openapi = openapi  # type: ignore[method-assign]


__all__ = ["describe_errors", "install"]
