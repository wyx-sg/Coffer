"""Contract test: the running app's generated OpenAPI for the /api/v1/sync
paths structurally matches openspec/specs/vault-sync/contracts/api.openapi.yaml.

Same shape as test_memory_openapi.py: routes are checked in both directions
(nothing declared is unserved, nothing served is undeclared) and every
component the yaml declares must exist with at least the yaml's required
fields, driven from the yaml rather than a hand-copied table. Sync is a
cross-cutting service rather than a resource kind, so it owns the whole
``/api/v1/sync`` prefix and that prefix is the route family.

**The status vocabulary is checked in three places at once**, because it is
what discriminates the one round shape across every round-shaped operation.
The wire model types ``RoundOut.status`` as ``ConvergeStatus`` itself, so the
generated schema narrows the field by ``$ref`` to an eight-value enum: the
domain enum, the yaml and the generated schema are each asserted to hold
exactly the same eight values, and none of the three can quietly gain or lose
one. ``DocChangeOut.status`` — the round's other status — is narrowed the
same way, to the three ways a document can move.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from coffer.domain.sync.convergence import ConvergeStatus
from coffer.domain.sync.diff import ChangeStatus
from coffer.main import app

_SYNC_OPENAPI_PATH = (
    Path(__file__).resolve().parents[3] / "openspec/specs/vault-sync/contracts/api.openapi.yaml"
)

_SYNC_PREFIX = "/api/v1/sync"
_OPERATION_METHODS = frozenset({"get", "post", "put", "patch", "delete"})

#: Every value ``ConvergeStatus`` has, written down so the enum losing one is a
#: failure rather than a quietly narrower contract. ``no_change`` and
#: ``disabled`` are successes rather than skips.
_CONVERGE_STATUS_VALUES = frozenset(
    {
        "ok",
        "no_change",
        "conflict",
        "awaiting_confirmation",
        "push_failed",
        "failed",
        "disabled",
        "awaiting_join",
    }
)

#: Raised as a ``CofferError`` and mapped centrally, so it is never a route's
#: ``response_model`` and never reaches the generated components. Same
#: situation as the memory contract's copy of this shape.
_CENTRALLY_MAPPED_ERROR_SHAPE = "ErrorEnvelope"


@pytest.fixture(scope="module")
def generated_schema() -> dict[str, Any]:
    """Return the FastAPI-generated OpenAPI schema once per test module."""
    return app.openapi()  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def spec_doc() -> dict[str, Any]:
    """Parse openspec/specs/vault-sync/contracts/api.openapi.yaml once per module."""
    return yaml.safe_load(_SYNC_OPENAPI_PATH.read_text())  # type: ignore[no-any-return]


def _operations(doc: dict[str, Any]) -> set[tuple[str, str]]:
    """Every (METHOD, path) under the sync prefix in either document."""
    return {
        (method.upper(), path)
        for path, operations in (doc.get("paths") or {}).items()
        if path.startswith(_SYNC_PREFIX)
        for method in operations
        if method.lower() in _OPERATION_METHODS
    }


def _required_fields(schema: dict[str, Any]) -> set[str]:
    """Required field names, flattening one level of ``allOf``.

    ``RunRecordOut`` is ``allOf: [RoundOut, {required: [id, started_at,
    finished_at]}]`` in the yaml and a flat subclass in Pydantic.
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
    """Every sync path+method written in api.openapi.yaml must be served."""
    declared = _operations(spec_doc)
    assert declared, "the yaml declares no /api/v1/sync paths — wrong file?"
    missing = declared - _operations(generated_schema)
    assert not missing, (
        f"declared in api.openapi.yaml but not served by the app: "
        f"{sorted(f'{m} {p}' for m, p in missing)}"
    )


def test_no_sync_route_is_undocumented(
    generated_schema: dict[str, Any],
    spec_doc: dict[str, Any],
) -> None:
    """And the reverse: a sync route that exists without appearing in the
    contract fails too."""
    undeclared = _operations(generated_schema) - _operations(spec_doc)
    assert not undeclared, (
        f"served by the app but absent from openspec/specs/vault-sync/contracts/api.openapi.yaml: "
        f"{sorted(f'{m} {p}' for m, p in undeclared)}"
    )


def test_the_run_history_route_is_served(generated_schema: dict[str, Any]) -> None:
    """``GET /sync/runs`` is the run history — read-only, unfiltered, one query
    with one knob, because the surface searches and pages in the browser."""
    runs = generated_schema["paths"].get(f"{_SYNC_PREFIX}/runs")
    assert runs is not None, "GET /api/v1/sync/runs is not served"
    assert "get" in runs
    assert set(runs) & _OPERATION_METHODS == {"get"}, (
        f"/sync/runs is read-only; it gained {sorted(set(runs) & _OPERATION_METHODS - {'get'})}"
    )


def test_the_run_history_limit_matches_the_contract(
    generated_schema: dict[str, Any],
    spec_doc: dict[str, Any],
) -> None:
    """The one knob, with the contract's own bounds: an optional ``limit``,
    defaulting to 500 and capped there, so the window a surface is handed can
    never quietly become unbounded."""
    declared = next(
        p
        for p in spec_doc["paths"][f"{_SYNC_PREFIX}/runs"]["get"]["parameters"]
        if p["name"] == "limit"
    )
    served = next(
        p
        for p in generated_schema["paths"][f"{_SYNC_PREFIX}/runs"]["get"]["parameters"]
        if p["name"] == "limit"
    )
    assert served["in"] == declared["in"] == "query"
    assert not served.get("required") and not declared.get("required")
    for key in ("default", "minimum", "maximum"):
        assert served["schema"][key] == declared["schema"][key], (
            f"limit.{key}: app says {served['schema'][key]}, yaml says {declared['schema'][key]}"
        )


# ---------------------------------------------------------------------------
# Schema components
# ---------------------------------------------------------------------------


def test_every_yaml_component_exists_with_its_required_fields(
    generated_schema: dict[str, Any],
    spec_doc: dict[str, Any],
) -> None:
    """Every component the yaml declares must exist in the generated schemas
    with at least the required fields the yaml lists."""
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
    assert not problems, "openspec/specs/vault-sync/contracts/api.openapi.yaml drift:\n  " + "\n  ".join(
        problems
    )


def test_the_history_row_is_a_superset_of_a_round(generated_schema: dict[str, Any]) -> None:
    """``RunRecordOut`` is ``RoundOut`` plus when, not a shape of its own, so
    the status page and the history table cannot drift into describing a round
    differently."""
    generated = generated_schema["components"]["schemas"]
    round_props = set(generated["RoundOut"]["properties"])
    record_props = set(generated["RunRecordOut"]["properties"])
    assert round_props < record_props
    assert record_props - round_props == {"id", "started_at", "finished_at"}


def test_the_run_list_is_a_list_of_history_rows(generated_schema: dict[str, Any]) -> None:
    """``SyncRunListOut.runs`` carries the history row, not a trimmed-down
    summary — including the rounds that changed nothing, which are what make a
    gap in the record visible."""
    runs = generated_schema["components"]["schemas"]["SyncRunListOut"]["properties"]["runs"]
    assert runs["type"] == "array"
    assert runs["items"]["$ref"].endswith("/RunRecordOut")


# ---------------------------------------------------------------------------
# ConvergeStatus — the eight values
# ---------------------------------------------------------------------------


def test_converge_status_is_exactly_eight_values() -> None:
    """The domain enum is the oracle for the status vocabulary, because the wire
    model does not narrow it. Exactly these eight — a subset is not enough."""
    assert {status.value for status in ConvergeStatus} == set(_CONVERGE_STATUS_VALUES)
    assert len(ConvergeStatus) == 8


def test_the_yaml_declares_exactly_the_domains_eight_statuses(spec_doc: dict[str, Any]) -> None:
    """``status`` is what discriminates the one round shape across every
    round-shaped operation, so the contract must list the whole of
    ``ConvergeStatus`` — no more, no fewer."""
    declared = spec_doc["components"]["schemas"]["RoundOut"]["properties"]["status"]["enum"]
    assert len(declared) == len(set(declared)), f"duplicate status in the yaml: {declared}"
    assert set(declared) == {status.value for status in ConvergeStatus}


def test_the_generated_schema_narrows_status_to_the_same_eight(
    generated_schema: dict[str, Any], spec_doc: dict[str, Any]
) -> None:
    """The third place the vocabulary is pinned: what the app actually serves.

    ``status`` is typed as ``ConvergeStatus``, so every round-shaped response
    narrows it by ``$ref`` rather than promising any string — and a client
    generated from this schema gets the eight values instead of ``str``. Both
    round shapes must ref the same enum, or the status page and the history
    table could describe a round differently.
    """
    generated = generated_schema["components"]["schemas"]
    refs = {
        generated[shape]["properties"]["status"]["$ref"] for shape in ("RoundOut", "RunRecordOut")
    }
    assert refs == {"#/components/schemas/ConvergeStatus"}, refs

    served = generated["ConvergeStatus"]
    assert served["type"] == "string"
    assert set(served["enum"]) == set(_CONVERGE_STATUS_VALUES)
    assert set(served["enum"]) == set(
        spec_doc["components"]["schemas"]["RoundOut"]["properties"]["status"]["enum"]
    )


def test_a_document_change_narrows_its_status_on_both_sides(
    generated_schema: dict[str, Any], spec_doc: dict[str, Any]
) -> None:
    """The round's other status. The yaml narrows it to the three ways a
    document can move, so the wire model types it as ``ChangeStatus`` and the
    served schema refs the same three — a client cannot be handed a fourth."""
    generated = generated_schema["components"]["schemas"]
    ref = generated["DocChangeOut"]["properties"]["status"]["$ref"]
    assert ref == "#/components/schemas/ChangeStatus", ref

    served = generated["ChangeStatus"]
    declared = spec_doc["components"]["schemas"]["DocChangeOut"]["properties"]["status"]
    assert served["type"] == "string"
    assert set(served["enum"]) == set(declared["enum"])
    assert set(served["enum"]) == {status.value for status in ChangeStatus}


def test_a_round_that_changed_nothing_is_a_success() -> None:
    """``no_change`` and ``disabled`` are outcomes, not skips: an unchanged
    vault makes no commit by design, and an unconfigured remote is the ordinary
    state of a fresh install."""
    assert ConvergeStatus.NO_CHANGE.value == "no_change"
    assert ConvergeStatus.DISABLED.value == "disabled"
