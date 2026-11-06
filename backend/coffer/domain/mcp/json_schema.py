"""JSON Schema checks for custom tools' arguments, over the ``jsonschema`` library.

Spec mcp-gateway "Validate a custom tool's arguments before any request";
ADR json-schema-validation-library. Two entry points:

* :func:`check_schema` — the schema itself is well formed (against the draft
  2020-12 meta-schema, valid regular expressions, resolvable local ``$ref``),
  run when a tool is saved;
* :func:`validate` — every way ``instance`` breaks ``schema``, each as a
  :class:`SchemaError` naming the instance path, the keyword and a message,
  run before any request is made.

Schemas are draft 2020-12. Before either step a schema is normalised so the
older spellings agents copy from API documents keep working: OpenAPI 3.0's
``nullable``, draft-04's boolean ``exclusiveMinimum`` / ``exclusiveMaximum``
and draft-07's array ``items`` with ``additionalItems``. Unknown keywords
(``description``, ``format``, ``example``...) are annotations and never fail a
value. No reference is ever fetched: the registry is empty, so only local
``$ref`` resolve. ``jsonschema`` is pure computation, so it may live in the
domain (the domain fence forbids I/O libraries, not this one).
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from itertools import islice
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError as _MetaSchemaError
from jsonschema.exceptions import ValidationError
from referencing import Registry
from referencing.exceptions import Unresolvable

#: The most errors one validation reports: enough to fix a call, bounded so a
#: hostile array cannot make an answer huge.
MAX_ERRORS = 50

_EMPTY_REGISTRY: Registry[Any] = Registry()


class InvalidSchema(ValueError):  # noqa: N818
    """The schema itself is malformed; raised by :func:`check_schema`."""


@dataclass(frozen=True)
class SchemaError:
    #: JSON Pointer to the offending value (``""`` is the whole argument object).
    path: str
    keyword: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"path": self.path or "/", "keyword": self.keyword, "message": self.message}


def _pointer(parts: Any) -> str:
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def _normalise(node: Any) -> Any:
    """Rewrite the older spellings into draft 2020-12 (see the module docstring)."""
    if isinstance(node, list):
        return [_normalise(v) for v in node]
    if not isinstance(node, dict):
        return node
    out = {k: _normalise(v) for k, v in node.items()}
    if out.get("nullable") is True and "type" in out:
        types = out["type"] if isinstance(out["type"], list) else [out["type"]]
        if "null" not in types:
            out["type"] = [*types, "null"]
    if out.get("nullable") in (True, False):
        out.pop("nullable")
    for exclusive, bound in (("exclusiveMinimum", "minimum"), ("exclusiveMaximum", "maximum")):
        if isinstance(out.get(exclusive), bool) and out.pop(exclusive) and bound in out:
            out[exclusive] = out.pop(bound)
    if isinstance(out.get("items"), list):
        out["prefixItems"] = out.pop("items")
        if "additionalItems" in out:
            out["items"] = out.pop("additionalItems")
    return out


def _resolve_local(root: Mapping[str, Any], ref: str) -> None:
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


def _refs(node: Any) -> Iterator[Any]:
    if isinstance(node, dict):
        if "$ref" in node:
            yield node["$ref"]
        for key, value in node.items():
            if key not in ("enum", "const", "default", "examples", "example"):
                yield from _refs(value)
    elif isinstance(node, list):
        for value in node:
            yield from _refs(value)


def _empty_enums(node: Any) -> bool:
    if isinstance(node, dict):
        if node.get("enum") == []:
            return True
        return any(
            _empty_enums(v)
            for k, v in node.items()
            if k not in ("const", "default", "examples", "example")
        )
    if isinstance(node, list):
        return any(_empty_enums(v) for v in node)
    return False


def check_schema(schema: Any) -> None:
    """Raise :class:`InvalidSchema` naming the first malformed spot of ``schema``."""
    normal = _normalise(schema)
    try:
        Draft202012Validator.check_schema(normal)
    except _MetaSchemaError as e:
        where = _pointer(e.path) or "/"
        raise InvalidSchema(f"the schema at {where}: {e.message}") from None
    if _empty_enums(normal):
        raise InvalidSchema("'enum' must be a non-empty list")
    if isinstance(normal, dict):
        for ref in _refs(normal):
            if not isinstance(ref, str):
                raise InvalidSchema("'$ref' must be a string")
            _resolve_local(normal, ref)


def _entries(error: ValidationError) -> Iterator[SchemaError]:
    """One entry per argument: ``required``, ``dependentRequired`` and
    ``additionalProperties`` name each property, not the object holding it."""
    at = list(error.absolute_path)
    keyword = str(error.validator)
    instance = error.instance
    value: Any = error.validator_value
    if keyword == "required" and isinstance(instance, dict):
        for name in value:
            if name not in instance:
                yield SchemaError(_pointer([*at, name]), keyword, f"'{name}' is required")
        return
    if keyword == "dependentRequired" and isinstance(instance, dict):
        for owner, needed in value.items():
            if owner in instance:
                for name in needed:
                    if name not in instance:
                        yield SchemaError(
                            _pointer([*at, name]), keyword, f"'{name}' is required with '{owner}'"
                        )
        return
    if keyword == "additionalProperties" and isinstance(instance, dict):
        schema = error.schema if isinstance(error.schema, dict) else {}
        known = set(schema.get("properties") or {})
        patterns = list(schema.get("patternProperties") or {})
        for name in instance:
            if name not in known and not any(re.search(p, name) for p in patterns):
                yield SchemaError(_pointer([*at, name]), keyword, f"'{name}' is not allowed")
        return
    yield SchemaError(_pointer(at), keyword, error.message)


def validate(schema: Any, instance: Any) -> list[SchemaError]:
    """Every way ``instance`` breaks ``schema`` (empty when it is valid).

    ``schema`` is assumed to have passed :func:`check_schema`; a reference that
    cannot be resolved, or never ends, is reported as a ``$ref`` failure rather
    than passing.
    """
    validator = Draft202012Validator(_normalise(schema), registry=_EMPTY_REGISTRY)
    out: list[SchemaError] = []
    seen: set[SchemaError] = set()
    try:
        for error in validator.iter_errors(instance):
            for entry in _entries(error):
                if entry not in seen:
                    seen.add(entry)
                    out.append(entry)
            if len(out) >= MAX_ERRORS:
                break
    except RecursionError:
        out.append(SchemaError("", "$ref", "the schema's $ref never reaches a value check"))
    except Unresolvable as e:
        out.append(SchemaError("", "$ref", f"$ref {e.ref!r} cannot be resolved"))
    return list(islice(out, MAX_ERRORS))


__all__ = ["MAX_ERRORS", "InvalidSchema", "SchemaError", "check_schema", "validate"]
