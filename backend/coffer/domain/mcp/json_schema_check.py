"""Is a custom tool's argument schema a well-formed JSON Schema?

Spec mcp-gateway "Validate a custom tool's arguments before any request";
design align-cli-with-ui-and-add-tool-environments D7. Run when a tool is
saved, so :mod:`coffer.domain.mcp.json_schema` validates only schemas that
passed it. Pure: the standard library only.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_TYPES = ("null", "boolean", "object", "array", "number", "integer", "string")


class InvalidSchema(ValueError):  # noqa: N818
    """The schema itself is malformed; raised by :func:`check_schema`."""


def _pointer(parts: tuple[str | int, ...]) -> str:
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def _compiled(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern)


_NUMBER_KEYWORDS = ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf")
_COUNT_KEYWORDS = (
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
    "minProperties",
    "maxProperties",
    "minContains",
    "maxContains",
)
_SUBSCHEMA_KEYWORDS = ("not", "if", "then", "else", "contains", "propertyNames")
_SCHEMA_LIST_KEYWORDS = ("allOf", "anyOf", "oneOf", "prefixItems")
_SCHEMA_MAP_KEYWORDS = ("properties", "patternProperties", "$defs", "definitions")


def resolve_ref(root: Mapping[str, Any], ref: str) -> Any:
    if not ref.startswith("#"):
        raise InvalidSchema(f"$ref {ref!r} is not a local reference (it must start with '#')")
    node: Any = root
    for raw in ref[1:].lstrip("/").split("/") if ref not in ("#", "#/") else []:
        part = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        else:
            raise InvalidSchema(f"$ref {ref!r} points at nothing")
    if not isinstance(node, (dict, bool)):
        raise InvalidSchema(f"$ref {ref!r} does not point at a schema")
    return node


def check_schema(schema: Any) -> None:
    """Raise :class:`InvalidSchema` naming the first malformed spot of ``schema``."""
    _check(schema, schema, ())


def _check(node: Any, root: Any, at: tuple[str | int, ...]) -> None:
    where = _pointer(at) or "/"
    if isinstance(node, bool):
        return
    if not isinstance(node, dict):
        raise InvalidSchema(f"the schema at {where} must be an object or a boolean")

    def fail(message: str) -> None:
        raise InvalidSchema(f"the schema at {where}: {message}")

    if "type" in node:
        t = node["type"]
        names = t if isinstance(t, list) else [t]
        if not names or any(n not in _TYPES for n in names):
            fail(f"'type' must be one of {', '.join(_TYPES)} or a list of them")
    for key in _NUMBER_KEYWORDS:
        if key in node:
            value = node[key]
            # draft-04 / OpenAPI 3.0 spell exclusive bounds as booleans.
            if key.startswith("exclusive") and isinstance(value, bool):
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                fail(f"'{key}' must be a number")
            if key == "multipleOf" and value <= 0:
                fail("'multipleOf' must be greater than 0")
    for key in _COUNT_KEYWORDS:
        if key in node:
            value = node[key]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                fail(f"'{key}' must be a non-negative integer")
    if "pattern" in node:
        if not isinstance(node["pattern"], str):
            fail("'pattern' must be a string")
        try:
            _compiled(node["pattern"])
        except re.error as e:
            fail(f"'pattern' is not a valid regular expression: {e}")
    if "enum" in node and (not isinstance(node["enum"], list) or not node["enum"]):
        fail("'enum' must be a non-empty list")
    for key in ("required",):
        if key in node:
            value = node[key]
            if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
                fail(f"'{key}' must be a list of property names")
    if "dependentRequired" in node:
        dep = node["dependentRequired"]
        if not isinstance(dep, dict) or any(
            not isinstance(v, list) or any(not isinstance(x, str) for x in v) for v in dep.values()
        ):
            fail("'dependentRequired' must map property names to lists of names")
    for key in ("uniqueItems", "nullable"):
        if key in node and not isinstance(node[key], bool):
            fail(f"'{key}' must be true or false")
    if "$ref" in node:
        if not isinstance(node["$ref"], str):
            fail("'$ref' must be a string")
        try:
            resolve_ref(root, node["$ref"])
        except InvalidSchema as e:
            fail(str(e))
    for key in _SUBSCHEMA_KEYWORDS:
        if key in node:
            _check(node[key], root, (*at, key))
    for key in ("items", "additionalProperties", "additionalItems"):
        if key in node:
            value = node[key]
            if isinstance(value, list):  # draft-07 tuple form
                for i, sub in enumerate(value):
                    _check(sub, root, (*at, key, i))
            else:
                _check(value, root, (*at, key))
    for key in _SCHEMA_LIST_KEYWORDS:
        if key in node:
            value = node[key]
            if not isinstance(value, list) or not value:
                fail(f"'{key}' must be a non-empty list of schemas")
            for i, sub in enumerate(value):
                _check(sub, root, (*at, key, i))
    for key in _SCHEMA_MAP_KEYWORDS:
        if key in node:
            value = node[key]
            if not isinstance(value, dict):
                fail(f"'{key}' must be an object")
            for name, sub in value.items():
                if key == "patternProperties":
                    try:
                        _compiled(name)
                    except re.error as e:
                        fail(
                            f"'{name}' in patternProperties is not a valid regular expression: {e}"
                        )
                _check(sub, root, (*at, key, name))


__all__ = ["InvalidSchema", "check_schema", "resolve_ref"]
