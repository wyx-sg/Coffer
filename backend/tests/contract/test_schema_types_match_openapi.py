"""Every contract's payload shapes, compared at *type* level against what the app serves.

The two gates next door check names. :mod:`test_contract_coverage` checks that
the set of paths and operations lines up in both directions;
:mod:`test_schemas_match_openapi` checks that a property the contract declares
exists on the model. Neither has ever compared a property's **type**, and that
is how four divergences shipped: ``SkillOut.scope`` was ``array of string`` in
``openspec/specs/skill-manager`` while the route served an object, ``ConversationOut``
kept ``model_id`` as *required* after the column was dropped,
``DaemonStatusOut.vec_available`` outlived its field, and
``MCPServerConfig.idle_timeout_seconds`` was declared, validated and
UI-controlled with nothing behind it.

FastAPI generates its OpenAPI document from the Pydantic models, so
``app.openapi()`` is the machine-readable truth about what the daemon accepts
and sends. This module compares the checked-in yaml against it.

Anchored on **routes, not schema names**
----------------------------------------
A name-keyed diff of ``components.schemas`` looks like the obvious move and is
a dead end: the contracts hand-name their schemas while the generator names
them after the Pydantic class. ``AdoptedResource`` is served as ``AdoptedOut``,
``ProviderCreateRequest`` as ``ProviderCreate``, ``ConfigFileContent`` as
``ConfigFileContentOut``, and the error envelopes (``ErrorOut``,
``ErrorEnvelope``, ``ErrorResponse``) have no generated counterpart at all
because FastAPI only ever emits 200 and 422. Keying on the name reports ~40
phantom absences across the eight contracts and proves nothing about any of
them. The route is the one stable join key, and :mod:`test_contract_coverage`
already proves the route sets agree — so this module joins on the route and
follows the ``$ref``s from there.

What it compares
----------------
For every operation both documents describe: the JSON request body and the
single 2xx JSON response body, walked recursively with ``$ref``s resolved on
both sides. It reports

  - a property the contract declares that the app does not have,
  - a property the app has that the contract does not declare,
  - a differing type *kind* (object / array / string / integer / number /
    boolean), and for an array a differing item kind,
  - on **request bodies**, a property the app requires that the contract lets
    the client omit — a generated client would send nothing and take a 422,
  - a 2xx status code that differs from the one the app returns,
  - a local ``$ref`` that resolves to nothing.

What it deliberately ignores, and why
-------------------------------------
A gate that cries wolf gets deleted, so each exclusion below is a case where
the hand-written contract and the generated document legitimately differ.

  - **Prose and hints** — ``description``, ``title``, ``example(s)``,
    ``default``, ``format``, ``deprecated``. Not shape.
  - **Constraints** — ``additionalProperties``, ``minLength``, ``maxLength``,
    ``pattern``, ``minimum``/``maximum``, ``minItems``. The contracts tighten
    these deliberately in places (``ScopeOut`` pins
    ``additionalProperties: false``) and the generator spells the same intent
    differently.
  - **The nullable spellings.** ``nullable: true``, ``type: [string, "null"]``
    and ``anyOf: [{type: string}, {type: "null"}]`` all mean the same thing and
    all appear in this tree. :func:`_normalise` collapses them to the non-null
    core before anything is compared.
  - **``$ref`` vs inlined.** Resolution happens first, so a contract that
    inlines what the generator ``$ref``s (or vice versa) compares equal.
  - **``required`` in the *response* direction.** This is the important one.
    FastAPI marks a response field optional exactly when it has a default, but
    Pydantic serialises it regardless, so the field is always on the wire.
    ``ScopeOut.agents`` is ``= None`` and the contract's ``required: [agents]``
    is factually right about what a client receives. Asserting this direction
    produced twelve findings and every one of them was wrong. (Nothing in
    ``surfaces/http`` responds with ``exclude_unset``/``exclude_none``, which
    is what would make it wrong the other way.)
  - **Real unions and untyped schemas.** More than one non-null branch, or no
    type information at all (``dict[str, Any]`` generates ``{}``): there is
    nothing to compare, so nothing is claimed. Likewise an object on either
    side with no ``properties`` — a free-form blob tells us nothing about the
    other side's fields.
  - **The generator's own machinery** — ``HTTPValidationError``,
    ``ValidationError``, ``Body_*`` multipart bodies, ``$defs``. Never reached,
    because it hangs off 422 and this walk only follows 2xx and request bodies.

Its own bite is tested
----------------------
:func:`test_the_comparator_reports_each_divergence_class` replays all four
historical divergences against synthetic documents, so the gate cannot quietly
stop detecting the things it was built for. :func:`_normalise` and
:func:`_kind` are pure and tested directly — they are where false positives
would come from.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SPECS_DIR = _REPO_ROOT / "openspec" / "specs"
_CONTRACT_GLOB = "**/contracts/api.openapi.yaml"

_OPERATION_METHODS = frozenset({"get", "post", "put", "patch", "delete"})
_JSON = "application/json"

#: Keys that describe a schema without constraining its shape. Dropped before
#: comparison — see "What it deliberately ignores" above.
_ANNOTATION_KEYS = frozenset(
    {
        "description",
        "title",
        "example",
        "examples",
        "default",
        "format",
        "deprecated",
        "readOnly",
        "writeOnly",
        "additionalProperties",
        "minLength",
        "maxLength",
        "pattern",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minItems",
        "maxItems",
        "uniqueItems",
        "nullable",
        "discriminator",
        "externalDocs",
        "summary",
        "const",
    }
)

#: A ``components.schemas`` entry no ``$ref`` in its own document points at is
#: dead documentation — with one standing exception. ``MCPServerConfig``
#: describes the opaque ``config`` blob of an ``mcp_server`` resource, which is
#: ``dict[str, Any]`` on the wire, so no route schema can reference it; it is
#: reached by name from ``test_schemas_match_openapi._DOMAIN_SCHEMAS`` instead.
_ORPHANS_BY_DESIGN = {
    "openspec/specs/mcp-gateway/contracts/api.openapi.yaml": {"MCPServerConfig"},
    # A workflow template's ``config``, declared for the editor's generated
    # type (spec workflow "Author templates in the web UI") and served by no
    # route on purpose: a template is written through the kind-agnostic
    # resource endpoint ("Write templates through the resource endpoint only"),
    # and a second write path would be a second contract for the same data.
    # Named by ``tests/contract/test_workflow_openapi.py``, which walks out
    # from it.
    "openspec/specs/workflow/contracts/api.openapi.yaml": {"WorkflowTemplate"},
}

_MAX_DEPTH = 12


# ---------------------------------------------------------------------------
# The pure core: resolution, normalisation, kind. Tested directly below.
# ---------------------------------------------------------------------------


def _deref(schema: Any, doc: dict[str, Any]) -> dict[str, Any]:
    """Follow a local ``$ref`` chain inside ``doc`` to the schema it names.

    Sibling keys alongside a ``$ref`` win over the target's, which is how
    OpenAPI 3.1 lets a reference carry its own description. An external or
    unresolvable reference yields a marker rather than raising, so one bad
    reference is reported instead of crashing the sweep.
    """
    for _ in range(_MAX_DEPTH):
        if not isinstance(schema, dict) or "$ref" not in schema:
            break
        ref = str(schema["$ref"])
        if not ref.startswith("#/"):
            return {}  # external reference: out of scope, claim nothing
        node: Any = doc
        for part in ref[2:].split("/"):
            if not isinstance(node, dict) or part not in node:
                return {"__unresolved__": ref}
            node = node[part]
        siblings = {k: v for k, v in schema.items() if k != "$ref"}
        schema = {**node, **siblings} if siblings else node
    return schema if isinstance(schema, dict) else {}


def _normalise(schema: Any, doc: dict[str, Any]) -> dict[str, Any]:
    """One schema node reduced to the shape it actually asserts.

    Resolves ``$ref``, merges ``allOf``, collapses every nullable spelling to
    its non-null core, and drops the annotation keys. Deliberately **one level
    deep**: ``properties`` and ``items`` come back untouched, and the recursion
    belongs to :func:`_compare`, which bounds its own depth. Normalising
    children here instead recurses forever on a self-referential schema —
    ``FileNodeOut.children`` is a list of ``FileNodeOut``.
    """
    if not isinstance(schema, dict):
        return {}
    node = _deref(schema, doc)
    if "__unresolved__" in node:
        return node

    if "allOf" in node:
        merged: dict[str, Any] = {k: v for k, v in node.items() if k != "allOf"}
        for member in node["allOf"]:
            resolved = _normalise(member, doc)
            for key, value in resolved.items():
                if key == "properties":
                    merged.setdefault("properties", {}).update(value)
                elif key == "required":
                    merged["required"] = sorted(set(merged.get("required", ())) | set(value))
                else:
                    merged.setdefault(key, value)
        node = merged

    for union_key in ("anyOf", "oneOf"):
        if union_key not in node:
            continue
        branches = [
            branch
            for branch in node[union_key]
            if not (isinstance(branch, dict) and branch.get("type") == "null")
        ]
        siblings = {k: v for k, v in node.items() if k not in (union_key, "type")}
        if len(branches) == 1:
            return _normalise({**branches[0], **siblings}, doc)
        node = {**siblings, union_key: branches}

    if isinstance(node.get("type"), list):
        concrete = [t for t in node["type"] if t != "null"]
        node = {**node, "type": concrete[0] if len(concrete) == 1 else concrete}

    return {k: v for k, v in node.items() if k not in _ANNOTATION_KEYS}


def _kind(normalised: dict[str, Any]) -> str:
    """The type kind a normalised schema asserts, or ``"any"`` if it asserts none.

    ``"any"`` and ``"union"`` are the two answers that make the comparison
    stand down: one side declaring nothing is not evidence that the other side
    is wrong.
    """
    if not normalised or "__unresolved__" in normalised:
        return "any"
    declared = normalised.get("type")
    if isinstance(declared, str):
        return declared
    if "properties" in normalised:
        return "object"
    if "items" in normalised:
        return "array"
    if "enum" in normalised:
        values = normalised["enum"]
        return "string" if values and all(isinstance(v, str) for v in values) else "any"
    if "anyOf" in normalised or "oneOf" in normalised:
        return "union"
    return "any"


# ---------------------------------------------------------------------------
# The comparison
# ---------------------------------------------------------------------------


def _compare(
    contract: Any,
    served: Any,
    contract_doc: dict[str, Any],
    served_doc: dict[str, Any],
    where: str,
    findings: list[str],
    *,
    is_request: bool,
    seen: frozenset[tuple[str | None, str | None]] = frozenset(),
    depth: int = 0,
) -> None:
    """Walk one payload shape on both sides, appending a line per divergence."""
    if depth > _MAX_DEPTH:
        return
    pair = (
        contract.get("$ref") if isinstance(contract, dict) else None,
        served.get("$ref") if isinstance(served, dict) else None,
    )
    if pair != (None, None):
        if pair in seen:
            return  # a cycle: FileNodeOut.children is a list of FileNodeOut
        seen = seen | {pair}

    want = _normalise(contract, contract_doc)
    have = _normalise(served, served_doc)
    want_kind, have_kind = _kind(want), _kind(have)
    if "any" in (want_kind, have_kind) or "union" in (want_kind, have_kind):
        return  # one side asserts nothing; claiming a divergence would be a guess

    if want_kind != have_kind:
        verb = "accepts" if is_request else "sends"
        findings.append(f"{where}: contract says {want_kind}, app {verb} {have_kind}")
        return

    if want_kind == "array":
        _compare(
            want.get("items", {}),
            have.get("items", {}),
            contract_doc,
            served_doc,
            f"{where}[]",
            findings,
            is_request=is_request,
            seen=seen,
            depth=depth + 1,
        )
        return

    if want_kind != "object":
        return

    declared = want.get("properties") or {}
    actual = have.get("properties") or {}
    if not declared or not actual:
        return  # a free-form object on either side says nothing about the other

    verb = "accept" if is_request else "send"
    for name in sorted(declared):
        if name not in actual:
            findings.append(f"{where}.{name}: contract declares it, the app does not {verb} it")
            continue
        _compare(
            declared[name],
            actual[name],
            contract_doc,
            served_doc,
            f"{where}.{name}",
            findings,
            is_request=is_request,
            seen=seen,
            depth=depth + 1,
        )

    undeclared = sorted(set(actual) - set(declared))
    if undeclared:
        findings.append(f"{where}: the app {verb}s {undeclared}, the contract is silent")

    # Only the request direction: see the module docstring on `required`.
    if is_request:
        unobliged = sorted(
            (set(have.get("required", ())) & set(declared)) - set(want.get("required", ()))
        )
        if unobliged:
            findings.append(
                f"{where}: the app REQUIRES {unobliged}, the contract lets the client omit them "
                f"— a generated client sends nothing and takes a 422"
            )


# ---------------------------------------------------------------------------
# Discovery and payload extraction
# ---------------------------------------------------------------------------


def _discover() -> list[str]:
    return sorted(
        path.relative_to(_REPO_ROOT).as_posix() for path in _SPECS_DIR.glob(_CONTRACT_GLOB)
    )


def _load(relpath: str) -> dict[str, Any]:
    return yaml.safe_load((_REPO_ROOT / relpath).read_text())  # type: ignore[no-any-return]


def _base_path(doc: dict[str, Any]) -> str:
    """The path prefix the contract declares its paths against.

    Contracts here use both conventions — whole paths against a bare host, or
    ``/skills`` against ``.../api/v1``. Same reasoning as
    ``test_contract_coverage._base_path``.
    """
    servers = doc.get("servers") or [{}]
    return urlsplit(str(servers[0].get("url", ""))).path.rstrip("/")


def _request_schema(operation: dict[str, Any]) -> Any:
    content = (operation.get("requestBody") or {}).get("content") or {}
    return content.get(_JSON, {}).get("schema")


def _success_response(operation: dict[str, Any]) -> tuple[str | None, Any]:
    """The operation's single 2xx JSON response, as ``(status, schema)``."""
    for status, response in (operation.get("responses") or {}).items():
        if not str(status).startswith("2"):
            continue
        schema = ((response or {}).get("content") or {}).get(_JSON, {}).get("schema")
        if schema is not None:
            return str(status), schema
    return None, None


def _schema_refs(node: Any) -> set[str]:
    """Every ``#/components/schemas/<name>`` this subtree references."""
    if isinstance(node, dict):
        found: set[str] = set()
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                if value.startswith("#/components/schemas/"):
                    found.add(value.rsplit("/", 1)[1])
            else:
                found |= _schema_refs(value)
        return found
    if isinstance(node, list):
        return {name for item in node for name in _schema_refs(item)}
    return set()


def route_reachable_schemas(relpath: str) -> set[str]:
    """The schema names this module's sweep actually reaches in one contract.

    Seeded from every operation's JSON request body and 2xx response — exactly
    what :func:`test_declared_payload_shapes_match_what_the_app_serves` walks —
    then closed transitively. Public because
    :mod:`test_schemas_match_openapi` uses it to prove that what it still pins
    by hand is precisely what this sweep *cannot* reach, so the division of
    labour between the two modules cannot rot into duplication.
    """
    doc = _load(relpath)
    schemas = (doc.get("components") or {}).get("schemas") or {}
    frontier: set[str] = set()
    for operations in (doc.get("paths") or {}).values():
        for method, operation in operations.items():
            if method.lower() not in _OPERATION_METHODS:
                continue
            body = _request_schema(operation)
            if body is not None:
                frontier |= _schema_refs(body)
            _, response = _success_response(operation)
            if response is not None:
                frontier |= _schema_refs(response)

    reached: set[str] = set()
    while frontier:
        name = frontier.pop()
        if name in reached or name not in schemas:
            continue
        reached.add(name)
        frontier |= _schema_refs(schemas[name])
    return reached


@pytest.fixture(scope="module")
def served_document() -> dict[str, Any]:
    """The app's own OpenAPI document — what the daemon actually accepts and sends.

    Read through ``app.openapi()`` for the same reason
    ``test_contract_coverage`` does: FastAPI 0.141 no longer flattens an
    included router's routes into ``app.routes``, so introspecting that
    silently finds nothing.
    """
    from coffer.main import app

    return app.openapi()  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# The gates
# ---------------------------------------------------------------------------


def test_contracts_are_discovered() -> None:
    """Without this, every parametrized sweep below could pass vacuously."""
    assert _discover(), f"no contract found under {_SPECS_DIR}/{_CONTRACT_GLOB}"


@pytest.mark.parametrize("relpath", _discover())
def test_every_ref_resolves(relpath: str) -> None:
    """A ``$ref`` naming a schema the document does not define promises a shape
    no client can generate, and yaml has no compiler to notice."""
    text = (_REPO_ROOT / relpath).read_text()
    doc = _load(relpath)
    dangling = sorted(
        {
            ref
            for ref in re.findall(r'"?#/[A-Za-z0-9_/.-]+"?', text)
            for ref in [ref.strip('"')]
            if "__unresolved__" in _deref({"$ref": ref}, doc)
        }
    )
    assert not dangling, f"{relpath} references schemas it does not define: {dangling}"


@pytest.mark.parametrize("relpath", _discover())
def test_no_schema_is_documented_for_nothing(relpath: str) -> None:
    """A ``components.schemas`` entry nothing in the document points at.

    The honest residue of "a schema name the yaml declares that the generated
    document has no counterpart for". Name-matching against the generated
    document cannot answer that question here — the generator names schemas
    after the model class, so most names differ by design (see the module
    docstring). What *is* answerable, and is the real risk, is a schema the
    contract carries that its own document has stopped using: it documents a
    shape no route promises, and nothing else would ever notice.
    """
    text = (_REPO_ROOT / relpath).read_text()
    declared = set((_load(relpath).get("components") or {}).get("schemas") or {})
    referenced = set(re.findall(r"#/components/schemas/([A-Za-z0-9_]+)", text))
    orphans = sorted(declared - referenced - _ORPHANS_BY_DESIGN.get(relpath, set()))
    assert not orphans, (
        f"{relpath} defines schemas nothing references: {orphans}. Either a route should "
        f"point at them, or they are dead documentation and should be deleted. If one is "
        f"reachable only by name from another test, add it to _ORPHANS_BY_DESIGN with the "
        f"reason."
    )


@pytest.mark.parametrize("relpath", _discover())
def test_declared_payload_shapes_match_what_the_app_serves(
    relpath: str,
    served_document: dict[str, Any],
) -> None:
    """The gate this module exists for: every declared payload, at type level."""
    contract_doc = _load(relpath)
    base = _base_path(contract_doc)
    served_paths = served_document.get("paths") or {}
    findings: list[str] = []
    compared = 0

    for path, operations in (contract_doc.get("paths") or {}).items():
        served_operations = served_paths.get(base + path)
        if not served_operations:
            continue  # an unserved route is test_contract_coverage's finding, not ours
        for method, operation in operations.items():
            if method.lower() not in _OPERATION_METHODS:
                continue
            served_operation = served_operations.get(method.lower())
            if not served_operation:
                continue
            label = f"{method.upper()} {base + path}"

            want_body, have_body = _request_schema(operation), _request_schema(served_operation)
            if want_body is not None and have_body is not None:
                compared += 1
                _compare(
                    want_body,
                    have_body,
                    contract_doc,
                    served_document,
                    f"{label} request",
                    findings,
                    is_request=True,
                )

            want_status, want_response = _success_response(operation)
            have_status, have_response = _success_response(served_operation)
            if want_response is not None and have_response is not None:
                compared += 1
                if want_status != have_status:
                    findings.append(
                        f"{label}: contract documents a {want_status}, the app returns "
                        f"{have_status}"
                    )
                _compare(
                    want_response,
                    have_response,
                    contract_doc,
                    served_document,
                    f"{label} {want_status} response",
                    findings,
                    is_request=False,
                )

    assert compared, (
        f"{relpath} produced no payload to compare, so this assertion passed vacuously — "
        f"either its paths do not line up with the app's, or its operations declare no JSON "
        f"bodies at all"
    )
    assert not findings, (
        f"{relpath} and the app disagree about {len(findings)} payload shape(s). The code is "
        f"the truth about what is sent; the contract is the promise. Read the route handler "
        f"and the model, decide which side is wrong, and fix that side (a yaml change means "
        f"re-running `npm run codegen`):\n    " + "\n    ".join(findings)
    )


# ---------------------------------------------------------------------------
# The pure functions, and the gate's own bite
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "schema,expected_kind",
    [
        ({"type": "string"}, "string"),
        ({"nullable": True, "type": "string"}, "string"),
        ({"type": ["string", "null"]}, "string"),
        ({"anyOf": [{"type": "string"}, {"type": "null"}]}, "string"),
        ({"oneOf": [{"type": "integer"}, {"type": "null"}]}, "integer"),
        ({"anyOf": [{"type": "array", "items": {"type": "string"}}, {"type": "null"}]}, "array"),
        ({"properties": {"a": {"type": "string"}}}, "object"),
        ({"items": {"type": "string"}}, "array"),
        ({"type": "string", "enum": ["a", "b"]}, "string"),
        ({"enum": ["a", "b"]}, "string"),
        ({}, "any"),
        ({"type": "object", "additionalProperties": True}, "object"),
        ({"anyOf": [{"type": "string"}, {"type": "integer"}]}, "union"),
    ],
)
def test_normalise_reduces_every_nullable_spelling_to_one_kind(
    schema: dict[str, Any], expected_kind: str
) -> None:
    """The four spellings of "string or null" in this tree must all read as
    ``string`` — this is where the false positives would come from."""
    assert _kind(_normalise(schema, {})) == expected_kind


def test_normalise_drops_annotations_but_keeps_shape() -> None:
    normalised = _normalise(
        {
            "type": "object",
            "description": "prose",
            "title": "T",
            "example": {"a": 1},
            "additionalProperties": False,
            "required": ["a"],
            "properties": {"a": {"type": "string", "maxLength": 9}},
        },
        {},
    )
    assert normalised == {
        "type": "object",
        "required": ["a"],
        "properties": {"a": {"type": "string", "maxLength": 9}},
    }, "annotations must go and shape must stay; children are left for _compare"


def test_normalise_resolves_refs_and_merges_allof() -> None:
    doc = {"components": {"schemas": {"Inner": {"type": "object", "required": ["x"]}}}}
    assert _normalise({"$ref": "#/components/schemas/Inner"}, doc) == {
        "type": "object",
        "required": ["x"],
    }
    assert _normalise(
        {"allOf": [{"$ref": "#/components/schemas/Inner"}], "description": "d"}, doc
    ) == {"type": "object", "required": ["x"]}


def test_normalise_reports_an_unresolvable_ref_rather_than_raising() -> None:
    assert _normalise({"$ref": "#/components/schemas/Gone"}, {}) == {
        "__unresolved__": "#/components/schemas/Gone"
    }


def _findings_for(contract: Any, served: Any, *, is_request: bool = False) -> list[str]:
    findings: list[str] = []
    _compare(contract, served, {}, {}, "X", findings, is_request=is_request)
    return findings


@pytest.mark.parametrize(
    "case,contract,served,is_request,must_mention",
    [
        # 1. DaemonStatusOut.vec_available: an optional property left in the
        #    yaml after the field was deleted from the model.
        (
            "property the model no longer has",
            {
                "type": "object",
                "properties": {"status": {"type": "string"}, "vec_available": {"type": "boolean"}},
            },
            {"type": "object", "properties": {"status": {"type": "string"}}},
            False,
            ["vec_available", "does not send it"],
        ),
        # 2. MCPServerConfig.idle_timeout_seconds: declared with nothing behind it.
        (
            "declared knob nothing implements",
            {
                "type": "object",
                "properties": {
                    "transport": {"type": "object", "properties": {"c": {"type": "string"}}},
                    "idle_timeout_seconds": {"type": "integer"},
                },
            },
            {
                "type": "object",
                "properties": {
                    "transport": {"type": "object", "properties": {"c": {"type": "string"}}}
                },
            },
            True,
            ["idle_timeout_seconds", "does not accept it"],
        ),
        # 3. SkillOut.scope: array of string in the yaml, an object on the wire.
        (
            "type kind differs",
            {
                "type": "object",
                "properties": {"scope": {"type": "array", "items": {"type": "string"}}},
            },
            {
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "object",
                        "properties": {"agents": {"type": "array", "items": {"type": "string"}}},
                    }
                },
            },
            False,
            ["X.scope", "contract says array", "app sends object"],
        ),
        # 4. ConversationOut.model_id: required in the yaml after the field went.
        (
            "required property the model no longer has",
            {
                "type": "object",
                "required": ["id", "model_id"],
                "properties": {"id": {"type": "string"}, "model_id": {"type": "string"}},
            },
            {"type": "object", "required": ["id"], "properties": {"id": {"type": "string"}}},
            False,
            ["model_id", "does not send it"],
        ),
        # The remaining classes this module claims to catch.
        (
            "array item kind differs",
            {"type": "array", "items": {"type": "string"}},
            {"type": "array", "items": {"type": "integer"}},
            False,
            ["X[]", "contract says string", "app sends integer"],
        ),
        (
            "app requires what the contract lets a client omit",
            {"type": "object", "properties": {"a": {"type": "string"}}},
            {"type": "object", "required": ["a"], "properties": {"a": {"type": "string"}}},
            True,
            ["REQUIRES", "'a'", "422"],
        ),
        (
            "app accepts a property the contract never mentions",
            {"type": "object", "properties": {"text": {"type": "string"}}},
            {
                "type": "object",
                "properties": {"text": {"type": "string"}, "chat_id": {"type": "string"}},
            },
            True,
            ["chat_id", "the contract is silent"],
        ),
    ],
)
def test_the_comparator_reports_each_divergence_class(
    case: str,
    contract: dict[str, Any],
    served: dict[str, Any],
    is_request: bool,
    must_mention: list[str],
) -> None:
    """A gate that cannot be made to fail is not a gate.

    Every case here is one of the four divergences that actually shipped, or
    one of the other classes the docstring promises. The message must name the
    property and both types, or a failure is unactionable.
    """
    findings = _findings_for(contract, served, is_request=is_request)
    assert findings, f"{case}: the comparator reported nothing"
    joined = "\n".join(findings)
    missing = [fragment for fragment in must_mention if fragment not in joined]
    assert not missing, f"{case}: message {joined!r} never mentions {missing}"


@pytest.mark.parametrize(
    "case,contract,served",
    [
        (
            "nullable spellings",
            {"type": ["string", "null"]},
            {"anyOf": [{"type": "string"}, {"type": "null"}]},
        ),
        (
            "nullable vs nullable:true",
            {"nullable": True, "type": "string"},
            {"anyOf": [{"type": "string"}, {"type": "null"}]},
        ),
        (
            "descriptions and examples",
            {"type": "string", "description": "d", "example": "e"},
            {"type": "string"},
        ),
        ("format", {"type": "string", "format": "date-time"}, {"type": "string"}),
        (
            "tightened additionalProperties",
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {"a": {"type": "string"}},
            },
            {"type": "object", "properties": {"a": {"type": "string"}}},
        ),
        (
            "contract requires what the model defaults (response)",
            {"type": "object", "required": ["a"], "properties": {"a": {"type": "string"}}},
            {"type": "object", "properties": {"a": {"type": "string"}}},
        ),
        (
            "free-form object on the served side",
            {"type": "object", "properties": {"a": {"type": "string"}}},
            {"type": "object"},
        ),
        ("untyped schema on either side", {"type": "string"}, {}),
        ("a real union", {"type": "string"}, {"anyOf": [{"type": "string"}, {"type": "integer"}]}),
    ],
)
def test_the_comparator_stays_quiet_on_legitimate_differences(
    case: str, contract: dict[str, Any], served: dict[str, Any]
) -> None:
    """Each case is a spelling difference the tree actually contains. Flagging
    any of them is how a gate earns its deletion."""
    assert not _findings_for(contract, served), f"{case}: false positive"
    assert not _findings_for(contract, served, is_request=True), f"{case}: false positive (request)"
