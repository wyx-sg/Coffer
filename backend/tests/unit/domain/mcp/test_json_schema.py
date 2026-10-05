"""The custom tools' JSON Schema validator, keyword by keyword (spec
mcp-gateway "Validate a custom tool's arguments before any request")."""

from __future__ import annotations

from typing import Any

import pytest

from coffer.domain.mcp.json_schema import InvalidSchema, check_schema, validate


def _fails(schema: dict[str, Any], value: Any) -> set[tuple[str, str]]:
    check_schema(schema)
    return {(e.path, e.keyword) for e in validate(schema, value)}


@pytest.mark.parametrize(
    ("schema", "good", "bad", "keyword"),
    [
        ({"type": "integer"}, 3, 3.5, "type"),
        ({"type": "integer"}, 3.0, True, "type"),
        ({"type": ["string", "null"]}, None, 1, "type"),
        ({"type": "string", "nullable": True}, None, 1, "type"),
        ({"enum": ["a", 1]}, 1, "b", "enum"),
        ({"const": {"a": 1}}, {"a": 1.0}, {"a": 2}, "const"),
        ({"minimum": 1}, 1, 0, "minimum"),
        ({"maximum": 10}, 10, 11, "maximum"),
        ({"exclusiveMinimum": 1}, 2, 1, "exclusiveMinimum"),
        ({"minimum": 1, "exclusiveMinimum": True}, 2, 1, "exclusiveMinimum"),
        ({"exclusiveMaximum": 5}, 4, 5, "exclusiveMaximum"),
        ({"multipleOf": 0.5}, 1.5, 1.2, "multipleOf"),
        ({"minLength": 2}, "ab", "a", "minLength"),
        ({"maxLength": 2}, "ab", "abc", "maxLength"),
        ({"pattern": "^[a-z]+$"}, "abc", "Ab", "pattern"),
        ({"minItems": 1}, [1], [], "minItems"),
        ({"maxItems": 1}, [1], [1, 2], "maxItems"),
        ({"uniqueItems": True}, [1, 2], [1, 1.0], "uniqueItems"),
        ({"contains": {"const": 2}}, [1, 2], [1], "contains"),
        ({"minProperties": 1}, {"a": 1}, {}, "minProperties"),
        ({"maxProperties": 1}, {"a": 1}, {"a": 1, "b": 2}, "maxProperties"),
        ({"propertyNames": {"pattern": "^x"}}, {"xa": 1}, {"ya": 1}, "propertyNames"),
        ({"anyOf": [{"type": "string"}, {"minimum": 3}]}, 4, 1, "anyOf"),
        ({"not": {"type": "string"}}, 1, "s", "not"),
    ],
)
def test_each_keyword_refuses_what_it_should(
    schema: dict[str, Any], good: Any, bad: Any, keyword: str
) -> None:
    assert _fails(schema, good) == set()
    assert keyword in {k for _, k in _fails(schema, bad)}


def test_object_keywords_name_the_argument_that_broke_them() -> None:
    schema = {
        "type": "object",
        "required": ["a"],
        "additionalProperties": False,
        "patternProperties": {"^x_": {"type": "integer"}},
        "dependentRequired": {"b": ["c"]},
        "properties": {"a": {"type": "string"}, "b": {"type": "string"}, "c": {}},
    }
    assert _fails(schema, {"a": "1", "x_n": 2}) == set()
    assert _fails(schema, {"b": "1", "x_n": "s", "z": 1}) == {
        ("/a", "required"),
        ("/c", "dependentRequired"),
        ("/x_n", "type"),
        ("/z", "additionalProperties"),
    }


def test_arrays_check_every_item_and_tuple_positions() -> None:
    schema = {"type": "array", "prefixItems": [{"type": "string"}], "items": {"type": "integer"}}
    assert _fails(schema, ["a", 1, 2]) == set()
    assert _fails(schema, [1, "x"]) == {("/0", "type"), ("/1", "type")}
    draft7 = {"items": [{"type": "string"}], "additionalItems": False}
    assert ("/1", "false") in _fails(draft7, ["a", "b"])


def test_one_of_counts_its_matches_and_if_then_else_branches() -> None:
    one = {"oneOf": [{"required": ["card"]}, {"required": ["iban"]}]}
    assert _fails(one, {"card": 1}) == set()
    assert ("", "oneOf") in _fails(one, {"card": 1, "iban": 2})
    assert ("", "oneOf") in _fails(one, {})
    cond = {
        "if": {"properties": {"kind": {"const": "card"}}},
        "then": {"required": ["number"]},
        "else": {"required": ["iban"]},
    }
    assert ("/number", "required") in _fails(cond, {"kind": "card"})
    assert ("/iban", "required") in _fails(cond, {"kind": "bank"})


def test_local_refs_resolve_and_a_cycle_stops() -> None:
    schema = {
        "$defs": {"node": {"type": "object", "properties": {"next": {"$ref": "#/$defs/node"}}}},
        "$ref": "#/$defs/node",
    }
    assert _fails(schema, {"next": {"next": {}}}) == set()
    assert ("/next", "type") in _fails(schema, {"next": 1})
    loop = {"$defs": {"a": {"$ref": "#/$defs/a"}}, "$ref": "#/$defs/a"}
    assert ("", "$ref") in _fails(loop, 1)


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "text"},
        {"minimum": "1"},
        {"minLength": -1},
        {"multipleOf": 0},
        {"pattern": "("},
        {"enum": []},
        {"required": "a"},
        {"$ref": "#/$defs/missing"},
        {"$ref": "https://example.com/schema"},
        {"properties": {"a": 1}},
        {"allOf": []},
        {"patternProperties": {"(": {}}},
    ],
)
def test_a_malformed_schema_is_refused(schema: dict[str, Any]) -> None:
    with pytest.raises(InvalidSchema):
        check_schema(schema)


def test_annotations_never_fail_a_value_and_errors_are_bounded() -> None:
    schema = {"type": "string", "format": "email", "description": "x", "example": "y"}
    assert _fails(schema, "not an email") == set()
    many = {"type": "array", "items": {"type": "string"}}
    assert len(validate(many, list(range(500)))) == 50
