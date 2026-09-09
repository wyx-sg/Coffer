"""Convert MCP JSON-Schema tool inputs into pydantic arg models.

LangChain binds a tool to a model through a pydantic ``args_schema``, but MCP
describes a tool's input as a raw JSON-Schema dict. These helpers bridge the
two: :func:`schema_to_pydantic` builds a minimal Pydantic v2 model from an MCP
``input_schema``, with :func:`json_type_to_python` mapping JSON types to Python
ones and :func:`sanitise_name` turning a tool name into a valid identifier
fragment.

Lives under ``infrastructure.chat`` alongside the LangChain/LangGraph loops
that consume it (import-linter Contract 9).
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "json_type_to_python",
    "sanitise_name",
    "schema_to_pydantic",
]


def schema_to_pydantic(tool_name: str, schema: dict[str, Any]) -> Any:
    """Build a minimal Pydantic v2 model from a JSON Schema dict."""
    from pydantic import BaseModel, create_model
    from pydantic.fields import FieldInfo

    properties: dict[str, Any] = schema.get("properties") or {}
    required: list[str] = schema.get("required") or []

    field_definitions: dict[str, Any] = {}
    for field_name, field_schema in properties.items():
        json_type = field_schema.get("type", "string")
        py_type: type = json_type_to_python(json_type)
        description = field_schema.get("description", "")

        if field_name in required:
            field_definitions[field_name] = (py_type, FieldInfo(description=description))
        else:
            field_definitions[field_name] = (
                py_type | None,
                FieldInfo(default=None, description=description),
            )

    if not field_definitions:
        return create_model(f"Args_{sanitise_name(tool_name)}", __base__=BaseModel)

    return create_model(
        f"Args_{sanitise_name(tool_name)}",
        __base__=BaseModel,
        **field_definitions,
    )


def json_type_to_python(json_type: str) -> type:
    """Map a JSON-Schema scalar/container type name to a Python type."""
    mapping: dict[str, type] = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "object": dict,
        "array": list,
    }
    return mapping.get(json_type, str)


def sanitise_name(name: str) -> str:
    """Convert a tool name to a valid Python identifier fragment."""
    return name.replace("-", "_").replace(".", "_")
