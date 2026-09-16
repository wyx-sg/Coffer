"""Contract test: the running app's generated OpenAPI for the /api/v1/memory
paths structurally matches specs/memory/contracts/api.openapi.yaml.

Mirrors test_chat_openapi.py and test_channel_contract.py (drive the assertions
from the yaml itself) and test_knowledge_openapi.py (compare the route set
set-for-set, so a route that appears without anyone deciding on it fails too).

The memory contract had no test module at all until this one: every module in
this directory names its yaml by hand, so a contract file that nobody wired up
was gated by nothing. test_contract_coverage.py now refuses that state; this
module is the memory half of closing it.

Two deliberate notes on what is *not* asserted here:

  - ``ErrorEnvelope`` (specs/memory/contracts/api.openapi.yaml:383) has no
    counterpart in the generated components, and neither does the app-wide
    ``ErrorResponse``. Every failure on this family is raised as a
    ``CofferError`` and mapped centrally rather than declared as a route's
    ``response_model``, so FastAPI never emits the shape. The yaml is right
    about the wire and the generated schema simply cannot see it — that is a
    known, app-wide property, not memory drift, and
    ``test_the_error_envelope_is_never_a_generated_component`` pins it so a
    future central declaration is noticed rather than silently accepted.
  - The yaml narrows three string fields with ``enum``
    (``FactSummaryOut.type``, ``FactSummaryOut.status``,
    ``ComposedContextOut.layers``) while
    backend/coffer/surfaces/http/memory/schemas.py types them as plain ``str``,
    so the generated schema carries no enum to compare. Asserted against the
    domain's own enums instead, which is where the values actually live.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from coffer.main import app

_MEMORY_OPENAPI_PATH = (
    Path(__file__).resolve().parents[3] / "specs/memory/contracts/api.openapi.yaml"
)

_MEMORY_PREFIX = "/api/v1/memory"
_OPERATION_METHODS = frozenset({"get", "post", "put", "patch", "delete"})

#: The one component the generated schema cannot carry — see the module
#: docstring. Pinned separately rather than skipped silently.
_CENTRALLY_MAPPED_ERROR_SHAPE = "ErrorEnvelope"


@pytest.fixture(scope="module")
def generated_schema() -> dict[str, Any]:
    """Return the FastAPI-generated OpenAPI schema once per test module."""
    return app.openapi()  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def spec_doc() -> dict[str, Any]:
    """Parse specs/memory/contracts/api.openapi.yaml once per module."""
    return yaml.safe_load(_MEMORY_OPENAPI_PATH.read_text())  # type: ignore[no-any-return]


def _declared_operations(doc: dict[str, Any]) -> set[tuple[str, str]]:
    """Every (METHOD, path) the yaml declares under the memory prefix."""
    return {
        (method.upper(), path)
        for path, operations in (doc.get("paths") or {}).items()
        if path.startswith(_MEMORY_PREFIX)
        for method in operations
        if method.lower() in _OPERATION_METHODS
    }


def _served_operations(schema: dict[str, Any]) -> set[tuple[str, str]]:
    """Every (METHOD, path) the app declares under the memory prefix."""
    return {
        (method.upper(), path)
        for path, operations in (schema.get("paths") or {}).items()
        if path.startswith(_MEMORY_PREFIX)
        for method in operations
        if method.lower() in _OPERATION_METHODS
    }


def _required_fields(schema: dict[str, Any]) -> set[str]:
    """Required field names, flattening one level of ``allOf``.

    ``FactOut`` is ``allOf: [FactSummaryOut, {required: [body, origins]}]`` in
    the yaml and a flat subclass in Pydantic, so the two sides only line up
    once the composition is collapsed.
    """
    required = set(schema.get("required") or [])
    for part in schema.get("allOf") or []:
        required |= set(part.get("required") or [])
    return required


# ---------------------------------------------------------------------------
# Routes, both directions
# ---------------------------------------------------------------------------


def test_every_yaml_path_is_implemented(
    generated_schema: dict[str, Any],
    spec_doc: dict[str, Any],
) -> None:
    """Every memory path+method written in api.openapi.yaml must be served, so a
    yaml-only edit cannot silently drift from the implementation."""
    declared = _declared_operations(spec_doc)
    assert declared, "the yaml declares no /api/v1/memory paths — wrong file?"
    served = _served_operations(generated_schema)
    missing = declared - served
    assert not missing, (
        f"declared in api.openapi.yaml but not served by the app: "
        f"{sorted(f'{m} {p}' for m, p in missing)}"
    )


def test_no_memory_route_is_undocumented(
    generated_schema: dict[str, Any],
    spec_doc: dict[str, Any],
) -> None:
    """And the reverse: a memory route that exists without appearing in the
    contract fails too. This is the direction that let an undocumented route
    ship — the contract is the whole management plane or it is decoration."""
    served = _served_operations(generated_schema)
    declared = _declared_operations(spec_doc)
    undeclared = served - declared
    assert not undeclared, (
        f"served by the app but absent from specs/memory/contracts/api.openapi.yaml: "
        f"{sorted(f'{m} {p}' for m, p in undeclared)}"
    )


def test_the_management_plane_is_eleven_routes(spec_doc: dict[str, Any]) -> None:
    """The contract's own ``info.description`` says eleven routes and that this
    is the whole management plane (FR-061). A twelfth arriving is a decision,
    not an accident, so the count is pinned."""
    assert len(_declared_operations(spec_doc)) == 11


def test_deleting_a_partition_is_not_on_this_surface(spec_doc: dict[str, Any]) -> None:
    """A partition's lifecycle is a Resource's lifecycle, so deletion goes
    through DELETE /api/v1/resources/memory/{name} and there is deliberately no
    DELETE on the partition route here."""
    assert ("DELETE", f"{_MEMORY_PREFIX}/partitions/{{name}}") not in _declared_operations(spec_doc)


def test_the_file_family_is_read_only(spec_doc: dict[str, Any]) -> None:
    """The tree is derived, so an edit would survive exactly until the next
    aggregation pass — there is no write counterpart, by design."""
    file_writes = {
        (method, path)
        for method, path in _declared_operations(spec_doc)
        if "/files" in path and method in {"PUT", "POST", "PATCH", "DELETE"}
    }
    assert not file_writes, f"the memory file family gained a write: {sorted(file_writes)}"


# ---------------------------------------------------------------------------
# Schema components
# ---------------------------------------------------------------------------


def test_every_yaml_component_exists_with_its_required_fields(
    generated_schema: dict[str, Any],
    spec_doc: dict[str, Any],
) -> None:
    """Every component the yaml declares must exist in the generated schemas
    with at least the required fields the yaml lists.

    Driven from the yaml rather than a hand-copied table so a component added
    to the contract is checked the moment it lands.
    """
    generated = generated_schema.get("components", {}).get("schemas", {})
    declared = (spec_doc.get("components") or {}).get("schemas") or {}
    assert declared, "the yaml declares no components — wrong file?"

    problems: list[str] = []
    for name, schema in declared.items():
        if name == _CENTRALLY_MAPPED_ERROR_SHAPE:
            continue  # see the module docstring
        if name not in generated:
            problems.append(f"{name}: missing from the generated components entirely")
            continue
        missing = _required_fields(schema) - _required_fields(generated[name])
        if missing:
            problems.append(f"{name}: required in the yaml but not generated: {sorted(missing)}")
    assert not problems, "specs/memory/contracts/api.openapi.yaml drift:\n  " + "\n  ".join(
        problems
    )


def test_the_error_envelope_is_never_a_generated_component(
    generated_schema: dict[str, Any],
) -> None:
    """Pins the one discrepancy the module docstring records.

    No route on this family declares the error envelope as a ``response_model``
    — a ``CofferError`` is mapped centrally — so neither the yaml's
    ``ErrorEnvelope`` nor the app-wide ``ErrorResponse`` reaches the generated
    schema. If that ever changes, the exclusion above stops being honest and
    this test says so.
    """
    generated = generated_schema.get("components", {}).get("schemas", {})
    assert _CENTRALLY_MAPPED_ERROR_SHAPE not in generated
    assert "ErrorResponse" not in generated


def test_the_read_only_file_shape_carries_no_fingerprint(
    generated_schema: dict[str, Any],
) -> None:
    """A fingerprint exists to make a later write conditional, and this family
    has no write — unlike the skill kind's equivalent shape."""
    file_content = generated_schema["components"]["schemas"]["FileContentOut"]
    assert "fingerprint" not in file_content.get("properties", {})


def test_delivery_status_answers_only_installed_or_not(
    generated_schema: dict[str, Any],
) -> None:
    """A fire is an event, not a property of an agent (FR-055, FR-064): there is
    deliberately no last-fired field, so a hook installed a minute ago is not
    flagged for its own normal state."""
    delivery = generated_schema["components"]["schemas"]["DeliveryStatusOut"]
    properties = set(delivery.get("properties", {}))
    assert properties == {"agent", "installed", "command", "event"}


# ---------------------------------------------------------------------------
# The values the yaml narrows with ``enum``
# ---------------------------------------------------------------------------


def test_the_fact_type_and_status_values_are_the_domains(spec_doc: dict[str, Any]) -> None:
    """The yaml's ``enum`` lists have no generated counterpart (the wire models
    type these as plain ``str``), so the domain's own vocabulary is the oracle."""
    from coffer.domain.memory.fact import FACT_TYPES, STATUS_ACTIVE, STATUS_SUPERSEDED

    fact_summary = spec_doc["components"]["schemas"]["FactSummaryOut"]["properties"]
    assert set(fact_summary["type"]["enum"]) == set(FACT_TYPES)
    assert set(fact_summary["status"]["enum"]) == {STATUS_ACTIVE, STATUS_SUPERSEDED}


def test_the_context_layers_are_l0_and_l1(spec_doc: dict[str, Any]) -> None:
    """A tiny budget can ship L0 alone; it can never ship half of L0 (FR-050).
    Two layers, and the contract says which two."""
    layers = spec_doc["components"]["schemas"]["ComposedContextOut"]["properties"]["layers"]
    assert set(layers["items"]["enum"]) == {"L0", "L1"}
