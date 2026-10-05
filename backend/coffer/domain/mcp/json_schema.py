"""A JSON Schema validator for custom tools' arguments.

Spec mcp-gateway "Validate a custom tool's arguments before any request";
design align-cli-with-ui-and-add-tool-environments D7. Two entry points:

* :func:`check_schema` — the schema itself is well formed (keyword types,
  valid regular expressions, resolvable local ``$ref``), run when a tool is
  saved;
* :func:`validate` — every way ``instance`` breaks ``schema``, each as a
  :class:`SchemaError` naming the instance path, the keyword and a message,
  run before any request is made.

The vocabulary is what OpenAPI imports and hand-written tools use: draft
2020-12's validation keywords, draft-07's ``definitions`` and array ``items``,
and OpenAPI 3.0's ``nullable``. Unknown keywords (``description``, ``format``,
``example``...) are annotations and never fail a value.

Pure: the standard library only (the domain fence forbids a third-party
validator here).
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from coffer.domain.mcp.json_schema_check import InvalidSchema, check_schema, resolve_ref

#: The most errors one validation reports: enough to fix a call, bounded so a
#: hostile array cannot make an answer huge.
MAX_ERRORS = 50
#: How deep ``$ref`` may recurse on one value before it counts as a cycle.
_MAX_DEPTH = 64


@dataclass(frozen=True)
class SchemaError:
    #: JSON Pointer to the offending value (``""`` is the whole argument object).
    path: str
    keyword: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"path": self.path or "/", "keyword": self.keyword, "message": self.message}


def _pointer(parts: tuple[str | int, ...]) -> str:
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def _short(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= 60 else text[:57] + "..."


def _is_type(value: Any, name: str) -> bool:
    if name == "null":
        return value is None
    if name == "boolean":
        return isinstance(value, bool)
    if name == "object":
        return isinstance(value, dict)
    if name == "array":
        return isinstance(value, list)
    if name == "string":
        return isinstance(value, str)
    if isinstance(value, bool):
        return False
    if name == "integer":
        return isinstance(value, int) or (isinstance(value, float) and value.is_integer())
    if name == "number":
        return isinstance(value, (int, float)) and not (
            isinstance(value, float) and (math.isnan(value) or math.isinf(value))
        )
    return False


def _equal(a: Any, b: Any) -> bool:
    """JSON equality: ``1 == 1.0``, but ``True`` is not ``1``."""
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_equal(x, y) for x, y in zip(a, b, strict=True))
    return bool(a == b)


def _compiled(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern)


# --- validation ----------------------------------------------------------------


class _Validator:
    def __init__(self, root: Any) -> None:
        self.root = root
        self.errors: list[SchemaError] = []

    def run(self, schema: Any, value: Any, at: tuple[str | int, ...], depth: int = 0) -> bool:
        """Validate, collecting errors; answer whether ``value`` passed."""
        before = len(self.errors)
        for error in self._errors(schema, value, at, depth):
            if len(self.errors) < MAX_ERRORS:
                self.errors.append(error)
        return len(self.errors) == before

    def passes(self, schema: Any, value: Any, at: tuple[str | int, ...], depth: int) -> bool:
        """Whether ``value`` passes, recording nothing (for the combinators)."""
        trial = _Validator(self.root)
        return trial.run(schema, value, at, depth)

    def _errors(
        self, schema: Any, value: Any, at: tuple[str | int, ...], depth: int
    ) -> Iterator[SchemaError]:
        path = _pointer(at)
        if schema is True or schema == {}:
            return
        if schema is False:
            yield SchemaError(path, "false", "no value is allowed here")
            return
        if not isinstance(schema, dict):
            return
        if depth > _MAX_DEPTH:
            yield SchemaError(path, "$ref", "the schema refers to itself too deeply")
            return
        if "$ref" in schema:
            target = resolve_ref(self.root, schema["$ref"])
            sub = _Validator(self.root)
            sub.run(target, value, at, depth + 1)
            yield from sub.errors
            # 2020-12: siblings of $ref apply too.
        if value is None and schema.get("nullable") is True:
            return
        if "type" in schema:
            names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
            if not any(_is_type(value, n) for n in names):
                yield SchemaError(
                    path, "type", f"expected {' or '.join(names)}, got {_type_name(value)}"
                )
                return
        if "const" in schema and not _equal(value, schema["const"]):
            yield SchemaError(path, "const", f"must be {_short(schema['const'])}")
        if "enum" in schema and not any(_equal(value, e) for e in schema["enum"]):
            options = ", ".join(_short(e) for e in schema["enum"][:10])
            yield SchemaError(path, "enum", f"must be one of {options}")
        if _is_type(value, "number"):
            yield from self._number(schema, value, path)
        if isinstance(value, str):
            yield from self._string(schema, value, path)
        if isinstance(value, list):
            yield from self._array(schema, value, at, depth)
        if isinstance(value, dict):
            yield from self._object(schema, value, at, depth)
        yield from self._combinators(schema, value, at, depth)

    def _number(self, schema: dict[str, Any], value: float, path: str) -> Iterator[SchemaError]:
        lo, hi = schema.get("minimum"), schema.get("maximum")
        ex_lo, ex_hi = schema.get("exclusiveMinimum"), schema.get("exclusiveMaximum")
        if ex_lo is True and lo is not None:
            if value <= lo:
                yield SchemaError(path, "exclusiveMinimum", f"must be greater than {lo}")
        elif lo is not None and value < lo:
            yield SchemaError(path, "minimum", f"must be at least {lo}")
        if ex_hi is True and hi is not None:
            if value >= hi:
                yield SchemaError(path, "exclusiveMaximum", f"must be less than {hi}")
        elif hi is not None and value > hi:
            yield SchemaError(path, "maximum", f"must be at most {hi}")
        if isinstance(ex_lo, int | float) and not isinstance(ex_lo, bool) and value <= ex_lo:
            yield SchemaError(path, "exclusiveMinimum", f"must be greater than {ex_lo}")
        if isinstance(ex_hi, int | float) and not isinstance(ex_hi, bool) and value >= ex_hi:
            yield SchemaError(path, "exclusiveMaximum", f"must be less than {ex_hi}")
        step = schema.get("multipleOf")
        if step:
            quotient = value / step
            if not math.isclose(quotient, round(quotient), rel_tol=0, abs_tol=1e-9):
                yield SchemaError(path, "multipleOf", f"must be a multiple of {step}")

    def _string(self, schema: dict[str, Any], value: str, path: str) -> Iterator[SchemaError]:
        length = len(value)
        if "minLength" in schema and length < schema["minLength"]:
            yield SchemaError(
                path, "minLength", f"must be at least {schema['minLength']} characters"
            )
        if "maxLength" in schema and length > schema["maxLength"]:
            yield SchemaError(
                path, "maxLength", f"must be at most {schema['maxLength']} characters"
            )
        if "pattern" in schema and _compiled(schema["pattern"]).search(value) is None:
            yield SchemaError(path, "pattern", f"must match {schema['pattern']!r}")

    def _array(
        self, schema: dict[str, Any], value: list[Any], at: tuple[str | int, ...], depth: int
    ) -> Iterator[SchemaError]:
        path = _pointer(at)
        if "minItems" in schema and len(value) < schema["minItems"]:
            yield SchemaError(path, "minItems", f"must hold at least {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            yield SchemaError(path, "maxItems", f"must hold at most {schema['maxItems']} items")
        if schema.get("uniqueItems"):
            for i, item in enumerate(value):
                if any(_equal(item, other) for other in value[:i]):
                    yield SchemaError(path, "uniqueItems", f"item {i} repeats an earlier item")
                    break
        prefix = schema.get("prefixItems")
        items = schema.get("items")
        if isinstance(items, list):  # draft-07 tuple form
            prefix, items = items, schema.get("additionalItems")
        start = 0
        if isinstance(prefix, list):
            for i, sub in enumerate(prefix[: len(value)]):
                sub_v = _Validator(self.root)
                sub_v.run(sub, value[i], (*at, i), depth)
                yield from sub_v.errors
            start = len(prefix)
        if items is not None and not isinstance(items, list):
            for i in range(start, len(value)):
                sub_v = _Validator(self.root)
                sub_v.run(items, value[i], (*at, i), depth)
                yield from sub_v.errors
        if "contains" in schema:
            matches = sum(
                1
                for i, v in enumerate(value)
                if self.passes(schema["contains"], v, (*at, i), depth)
            )
            least = schema.get("minContains", 1)
            if matches < least:
                yield SchemaError(path, "contains", f"must hold at least {least} matching item(s)")
            if "maxContains" in schema and matches > schema["maxContains"]:
                yield SchemaError(
                    path, "maxContains", f"must hold at most {schema['maxContains']} matching items"
                )

    def _object(
        self, schema: dict[str, Any], value: dict[str, Any], at: tuple[str | int, ...], depth: int
    ) -> Iterator[SchemaError]:
        path = _pointer(at)
        for name in schema.get("required", []):
            if name not in value:
                yield SchemaError(_pointer((*at, name)), "required", "is required")
        for name, needs in (schema.get("dependentRequired") or {}).items():
            if name in value:
                for other in needs:
                    if other not in value:
                        yield SchemaError(
                            _pointer((*at, other)),
                            "dependentRequired",
                            f"is required when {name!r} is given",
                        )
        if "minProperties" in schema and len(value) < schema["minProperties"]:
            yield SchemaError(
                path, "minProperties", f"must hold at least {schema['minProperties']} properties"
            )
        if "maxProperties" in schema and len(value) > schema["maxProperties"]:
            yield SchemaError(
                path, "maxProperties", f"must hold at most {schema['maxProperties']} properties"
            )
        props: dict[str, Any] = schema.get("properties") or {}
        patterns: dict[str, Any] = schema.get("patternProperties") or {}
        extra = schema.get("additionalProperties", True)
        names_schema = schema.get("propertyNames")
        for name, item in value.items():
            if names_schema is not None and not self.passes(names_schema, name, (*at, name), depth):
                yield SchemaError(
                    _pointer((*at, name)), "propertyNames", f"{name!r} is not an allowed name"
                )
            matched = False
            if name in props:
                matched = True
                sub_v = _Validator(self.root)
                sub_v.run(props[name], item, (*at, name), depth)
                yield from sub_v.errors
            for pattern, sub in patterns.items():
                if _compiled(pattern).search(name):
                    matched = True
                    sub_v = _Validator(self.root)
                    sub_v.run(sub, item, (*at, name), depth)
                    yield from sub_v.errors
            if not matched:
                if extra is False:
                    yield SchemaError(
                        _pointer((*at, name)),
                        "additionalProperties",
                        f"{name!r} is not an allowed argument",
                    )
                elif isinstance(extra, dict):
                    sub_v = _Validator(self.root)
                    sub_v.run(extra, item, (*at, name), depth)
                    yield from sub_v.errors

    def _combinators(
        self, schema: dict[str, Any], value: Any, at: tuple[str | int, ...], depth: int
    ) -> Iterator[SchemaError]:
        path = _pointer(at)
        for sub in schema.get("allOf") or []:
            sub_v = _Validator(self.root)
            sub_v.run(sub, value, at, depth)
            yield from sub_v.errors
        if "anyOf" in schema and not any(
            self.passes(sub, value, at, depth) for sub in schema["anyOf"]
        ):
            yield SchemaError(path, "anyOf", "must match at least one of the allowed shapes")
        if "oneOf" in schema:
            matched = sum(1 for sub in schema["oneOf"] if self.passes(sub, value, at, depth))
            if matched != 1:
                yield SchemaError(
                    path,
                    "oneOf",
                    "must match exactly one of the allowed shapes"
                    + (f" (it matches {matched})" if matched else " (it matches none)"),
                )
        if "not" in schema and self.passes(schema["not"], value, at, depth):
            yield SchemaError(path, "not", "matches a shape that is not allowed")
        if "if" in schema:
            branch = "then" if self.passes(schema["if"], value, at, depth) else "else"
            if branch in schema:
                sub_v = _Validator(self.root)
                sub_v.run(schema[branch], value, at, depth)
                yield from sub_v.errors


def _type_name(value: Any) -> str:
    for name in ("null", "boolean", "integer", "number", "string", "array", "object"):
        if _is_type(value, name):
            return name
    return type(value).__name__


def validate(schema: Any, instance: Any) -> list[SchemaError]:
    """Every way ``instance`` breaks ``schema`` (empty when it is valid).

    ``schema`` is assumed to have passed :func:`check_schema`; a reference that
    cannot be resolved still raises :class:`InvalidSchema` rather than passing.
    """
    validator = _Validator(schema)
    validator.run(schema, instance, ())
    return validator.errors


__all__ = ["MAX_ERRORS", "InvalidSchema", "SchemaError", "check_schema", "validate"]
