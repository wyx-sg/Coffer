"""Contract test: the app's generated OpenAPI for ``/api/v1/workflow`` matches
specs/workflow/contracts/api.openapi.yaml.

``test_contract_coverage.py`` already sweeps every contract in both directions.
This module is what that sweep cannot know: what is **deliberately absent**, how
many routes the management plane is, and the vocabularies the yaml narrows with
``enum``.

The same two app-wide notes ``test_memory_openapi.py`` records apply here:

  - ``ErrorEnvelope`` has no generated counterpart. Every refusal on this family
    is a ``CofferError`` mapped centrally in ``surfaces/http/errors.py``, so
    FastAPI never emits the shape. Pinned, not skipped.
  - The yaml narrows the statuses with ``enum`` while
    ``surfaces/http/workflow/schemas.py`` types them as plain ``str`` — the
    vocabulary lives in ``domain.workflow``'s ``StrEnum``s. Those are the oracle
    below, so the yaml cannot drift from the values the engine actually writes.

One more is this contract's own: ``WorkflowTemplate`` and the ``Template*``
family under it describe a template's ``config`` for the editor (FR-054) and are
served by NO route here, because a template is written through the
kind-agnostic resource endpoint (FR-056). They cannot have a generated
counterpart, so the component sweep walks out from ``WorkflowTemplate`` and
excludes what it reaches — computed rather than listed, so a new sub-schema of a
template is covered the day it lands and a schema that stops being one is not.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from coffer.main import app

_WORKFLOW_OPENAPI_PATH = (
    Path(__file__).resolve().parents[3] / "specs/workflow/contracts/api.openapi.yaml"
)

_WORKFLOW_PREFIX = "/api/v1/workflow"
_OPERATION_METHODS = frozenset({"get", "post", "put", "patch", "delete"})

#: See the module docstring.
_CENTRALLY_MAPPED_ERROR_SHAPE = "ErrorEnvelope"

#: The root of the documentation-only family, likewise.
_EDITOR_ONLY_ROOT = "WorkflowTemplate"


@pytest.fixture(scope="module")
def generated_schema() -> dict[str, Any]:
    return app.openapi()  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def spec_doc() -> dict[str, Any]:
    return yaml.safe_load(_WORKFLOW_OPENAPI_PATH.read_text())  # type: ignore[no-any-return]


def _declared_operations(doc: dict[str, Any]) -> set[tuple[str, str]]:
    return {
        (method.upper(), path)
        for path, operations in (doc.get("paths") or {}).items()
        if path.startswith(_WORKFLOW_PREFIX)
        for method in operations
        if method.lower() in _OPERATION_METHODS
    }


def _served_operations(schema: dict[str, Any]) -> set[tuple[str, str]]:
    return {
        (method.upper(), path)
        for path, operations in (schema.get("paths") or {}).items()
        if path.startswith(_WORKFLOW_PREFIX)
        for method in operations
        if method.lower() in _OPERATION_METHODS
    }


def _properties(doc: dict[str, Any], component: str) -> dict[str, Any]:
    props: dict[str, Any] = doc["components"]["schemas"][component]["properties"]
    return props


def _reachable_from(doc: dict[str, Any], root: str) -> set[str]:
    """``root`` and every component it references, transitively.

    Used to exclude the editor-only template family from the "is it served?"
    sweep. Computed from the document rather than written down, because a list
    of names is a list that goes stale in exactly the direction that matters:
    quietly, by growing a member nobody excluded.
    """
    schemas = (doc.get("components") or {}).get("schemas") or {}
    seen: set[str] = set()
    frontier = [root] if root in schemas else []
    while frontier:
        name = frontier.pop()
        if name in seen:
            continue
        seen.add(name)
        frontier.extend(
            ref.rsplit("/", 1)[-1]
            for ref in _refs_in(schemas[name])
            if ref.rsplit("/", 1)[-1] in schemas
        )
    return seen


def _refs_in(node: Any) -> list[str]:
    """Every ``$ref`` string anywhere under ``node``."""
    if isinstance(node, dict):
        found = [str(node["$ref"])] if isinstance(node.get("$ref"), str) else []
        for value in node.values():
            found.extend(_refs_in(value))
        return found
    if isinstance(node, list):
        return [ref for item in node for ref in _refs_in(item)]
    return []


def _enum_of(doc: dict[str, Any], component: str, field: str) -> set[str]:
    """The values the yaml narrows one field to, ``null`` dropped.

    ``NodeAttemptOut.failure_reason`` lists ``null`` beside its four reasons
    because the field is nullable; that is a nullability statement, not a
    member of the vocabulary.
    """
    schema = _properties(doc, component)[field]
    items = schema.get("items", schema)
    return {value for value in items["enum"] if value is not None}


# ---------------------------------------------------------------------------
# Routes, both directions
# ---------------------------------------------------------------------------


def test_every_yaml_path_is_implemented(
    generated_schema: dict[str, Any],
    spec_doc: dict[str, Any],
) -> None:
    declared = _declared_operations(spec_doc)
    assert declared, "the yaml declares no /api/v1/workflow paths — wrong file?"
    missing = declared - _served_operations(generated_schema)
    assert not missing, (
        f"declared in api.openapi.yaml but not served by the app: "
        f"{sorted(f'{m} {p}' for m, p in missing)}"
    )


def test_no_workflow_route_is_undocumented(
    generated_schema: dict[str, Any],
    spec_doc: dict[str, Any],
) -> None:
    """A route that exists without appearing in the contract fails too — the
    contract is the whole management plane or it is decoration."""
    undeclared = _served_operations(generated_schema) - _declared_operations(spec_doc)
    assert not undeclared, (
        f"served by the app but absent from specs/workflow/contracts/api.openapi.yaml: "
        f"{sorted(f'{m} {p}' for m, p in undeclared)}"
    )


def test_the_management_plane_is_twenty_four_routes(spec_doc: dict[str, Any]) -> None:
    """A run's whole management plane, counted. A twenty-fifth arriving is a
    decision, not an accident.

    It was thirteen while a run had a main thread of its own. Four inputs
    routes joined (FR-050, FR-051) and the one message route left, because a
    run has no conversation to say anything in. The seventeenth reads ONE file
    out of the run's directory (FR-064), so the context table can show what it
    lists rather than only naming it — read-only, one path, and guarded
    against everything that is not this run's to read. The eighteenth takes a
    feedback edge (FR-025): the edges were in every template and no surface
    could cross one, which made "send work back" a promise the product did not
    keep. The nineteenth is one sentence to one task (FR-068) — a run is driven
    by talking, and until it existed a task could only be talked to during the
    hours its turn was in flight. The last three are the developer's own notes
    (FR-069) — writing one, rewriting it, and serving the bytes of an image
    pasted into it, which the text preview cannot answer for by design. The
    twenty-third rewrites the run's LABEL (FR-070): its title is typed before
    the first task has opened, when the developer knows least about the work,
    and until this existed it could never be corrected. The twenty-fourth
    chooses who runs a task and on what (FR-071), which the pickers on a
    conversation cannot answer for a task that has no conversation yet.
    """
    assert len(_declared_operations(spec_doc)) == 24


def test_a_template_is_not_written_through_this_surface(spec_doc: dict[str, Any]) -> None:
    """A workflow template is a Resource (FR-001), so it is created, edited,
    scoped and deleted through the kind-agnostic resource routes. A second way
    to write one would be a second contract for the same data."""
    template_routes = {
        (method, path) for method, path in _declared_operations(spec_doc) if "template" in path
    }
    assert not template_routes, f"the workflow surface grew template routes: {template_routes}"


def test_a_run_is_never_edited_in_place(spec_doc: dict[str, Any]) -> None:
    """A run's POSITION is rebuilt from its event log (FR-014), so no surface
    may write it in place — one that did would be a second writer of the
    projection, and the log would stop being the record of truth.

    What the invariant protects is the PROJECTION: `status`,
    `current_stage_key`, `current_node_key`, `version`, `tokens_spent`. Two
    kinds of edit are outside it and are named here rather than left to be
    rediscovered:

    * a note's contents — a note is a FILE under the run's directory (FR-069),
      and replacing a file's bytes is what PUT is for;
    * the run's LABEL — its title and description (FR-070). A label is what the
      developer called the work, typed before the first task opened, when they
      knew least about it. It is not folded from anything and it moves the run
      nowhere, which is why it carries no `version` either.

    Anything else gaining a PUT or a PATCH is the failure this guards.
    """
    allowed = {("PATCH", "/api/v1/workflow/runs/{run_id}")}
    edits = {
        (method, path)
        for method, path in _declared_operations(spec_doc)
        if method in {"PUT", "PATCH"} and "/inputs/" not in path
    } - allowed
    assert not edits, f"the workflow surface gained an in-place edit: {sorted(edits)}"


def test_the_one_editable_thing_on_a_run_is_its_label(spec_doc: dict[str, Any]) -> None:
    """The exemption above is narrow by construction: the body that PATCH takes
    carries a title and a description and nothing else, so it cannot grow into
    a way to write the projection without this going red."""
    body = spec_doc["components"]["schemas"]["RunLabelIn"]
    assert set(body["properties"]) == {"title", "description"}
    assert "version" not in body["properties"], "a label edit must not join the lock cycle"


def test_every_mutating_run_command_carries_a_version(spec_doc: dict[str, Any]) -> None:
    """The optimistic lock is the contract's own rule (FR-015): the three bodies
    that move a run all require ``version``."""
    for component in ("RunSignalIn", "NodeActionIn", "AdhocTaskIn"):
        required = set(spec_doc["components"]["schemas"][component]["required"])
        assert "version" in required, f"{component} may be sent without a version"


def test_a_run_has_no_conversation_of_its_own(spec_doc: dict[str, Any]) -> None:
    """Every conversation in a run belongs to one task (FR-030), so there is no
    route for writing to the run and no field naming a thread it owns.

    This is asserted from the absent side on purpose: the message route and
    ``RunOut.main_conversation_id`` both existed, and a surface that quietly
    grew either back would be describing a main thread this layer does not
    have.
    """
    writes = {
        (method, path)
        for method, path in _declared_operations(spec_doc)
        if path.endswith("/messages")
    }
    assert not writes, f"the workflow surface grew a run-level message route: {sorted(writes)}"
    assert "main_conversation_id" not in _properties(spec_doc, "RunOut")
    assert "RunMessageIn" not in spec_doc["components"]["schemas"]
    assert "RunMessageOut" not in spec_doc["components"]["schemas"]


def test_a_node_names_the_conversation_that_is_opened(spec_doc: dict[str, Any]) -> None:
    """The counterpart of the rule above: a task IS its conversation, so the
    thing the web UI navigates to has to be on the node the developer clicked,
    not only inside the attempt row that happens to carry it (FR-030)."""
    assert "conversation_id" in _properties(spec_doc, "NodeOut")


def test_the_buttons_moved_rather_than_disappeared(spec_doc: dict[str, Any]) -> None:
    """The run's own page offers nothing that advances or alters the run
    (FR-052) — every such action is taken in the task's conversation. What a
    node allows still has to be SAID by this surface, or the conversation page
    has nothing to draw."""
    node = spec_doc["components"]["schemas"]["NodeOut"]
    assert "allowed_actions" in node["properties"]


def test_an_input_is_managed_at_any_point_in_a_runs_life(spec_doc: dict[str, Any]) -> None:
    """FR-050. Mounting is not something that happens only at creation, so the
    inputs are a route family of their own — and every one of the three that
    changes something answers with the list afterwards, so a client never has
    to ask twice what the run now reads.

    The upload is separate from the add (FR-051) because it carries bytes
    rather than a reference; that is what makes it ``multipart/form-data``
    rather than a base64 field in a JSON body.
    """
    prefix = f"{_WORKFLOW_PREFIX}/runs/{{run_id}}/inputs"
    assert _declared_operations(spec_doc) >= {
        ("GET", prefix),
        ("POST", prefix),
        ("POST", f"{prefix}/uploads"),
        ("DELETE", f"{prefix}/{{input_ref}}"),
    }

    upload = spec_doc["paths"][f"{prefix}/uploads"]["post"]["requestBody"]["content"]
    assert set(upload) == {"multipart/form-data"}

    for path, method in ((prefix, "post"), (f"{prefix}/uploads", "post"), (prefix, "get")):
        codes = set(spec_doc["paths"][path][method]["responses"])
        (ok,) = [code for code in codes if code.startswith("2")]
        body = spec_doc["paths"][path][method]["responses"][ok]["content"]["application/json"]
        assert body["schema"]["$ref"].endswith("/InputListOut")


def test_an_input_carries_no_version(spec_doc: dict[str, Any]) -> None:
    """An input is not a transition: the run did not move, it was given
    something to read. Requiring the optimistic lock here would make two
    developers mounting two collections a conflict, which it is not."""
    body = spec_doc["paths"][f"{_WORKFLOW_PREFIX}/runs/{{run_id}}/inputs"]["post"]["requestBody"]
    schema = body["content"]["application/json"]["schema"]
    # The REQUEST shape, which is narrower than the stored one on purpose:
    # ``size``, ``path`` and ``mount`` are what the server made of the request,
    # not things a caller gets to assert about its own upload.
    assert schema["$ref"].endswith("/RunInputIn")
    declared = spec_doc["components"]["schemas"]["RunInputIn"]["properties"]
    assert "version" not in declared
    assert not {"size", "path", "mount"} & set(declared)


# ---------------------------------------------------------------------------
# Schema components
# ---------------------------------------------------------------------------


def test_every_yaml_component_exists_with_its_required_fields(
    generated_schema: dict[str, Any],
    spec_doc: dict[str, Any],
) -> None:
    """Driven from the yaml rather than a hand-copied table, so a component
    added to the contract is checked the moment it lands."""
    generated = generated_schema.get("components", {}).get("schemas", {})
    declared = (spec_doc.get("components") or {}).get("schemas") or {}
    assert declared, "the yaml declares no components — wrong file?"

    unserved = {_CENTRALLY_MAPPED_ERROR_SHAPE} | _reachable_from(spec_doc, _EDITOR_ONLY_ROOT)
    problems: list[str] = []
    for name, schema in declared.items():
        if name in unserved:
            continue  # see the module docstring
        if name not in generated:
            problems.append(f"{name}: missing from the generated components entirely")
            continue
        missing = set(schema.get("required") or []) - set(generated[name].get("required") or [])
        if missing:
            problems.append(f"{name}: required in the yaml but not generated: {sorted(missing)}")
    assert not problems, "specs/workflow/contracts/api.openapi.yaml drift:\n  " + "\n  ".join(
        problems
    )


def test_the_template_shape_is_documented_without_a_route_to_write_it(
    spec_doc: dict[str, Any],
) -> None:
    """``WorkflowTemplate`` exists for the editor (FR-054) and nothing else.

    It is the one family this contract declares and does not serve, so the
    exclusion above has to be earned: the schema must be here, and there must
    still be no route through which a template is written (FR-056, which
    ``test_a_template_is_not_written_through_this_surface`` asserts from the
    route side).
    """
    excluded = _reachable_from(spec_doc, _EDITOR_ONLY_ROOT)
    assert _EDITOR_ONLY_ROOT in excluded, "the editor's template shape is not in the contract"
    assert excluded > {_EDITOR_ONLY_ROOT}, "a template shape with no parts is not a shape"


def test_the_error_envelope_is_never_a_generated_component(
    generated_schema: dict[str, Any],
) -> None:
    """Pins the one discrepancy the module docstring records."""
    generated = generated_schema.get("components", {}).get("schemas", {})
    assert _CENTRALLY_MAPPED_ERROR_SHAPE not in generated


def test_owned_here_is_on_every_run_the_api_reports(spec_doc: dict[str, Any]) -> None:
    """A run belongs to one machine and is read-only everywhere else (FR-012).
    The field is required, so no client can be shown a run without being told
    whether it may act on it."""
    assert "owned_here" in set(spec_doc["components"]["schemas"]["RunOut"]["required"])


def test_an_approval_payload_is_the_arguments_themselves(spec_doc: dict[str, Any]) -> None:
    """A decision on a summary is not a decision (FR-033): ``payload`` is a
    free-form object — the exact arguments — and it is required."""
    approval = spec_doc["components"]["schemas"]["ApprovalOut"]
    assert "payload" in set(approval["required"])
    assert approval["properties"]["payload"]["additionalProperties"] is True


# ---------------------------------------------------------------------------
# The values the yaml narrows with ``enum``
# ---------------------------------------------------------------------------


def test_the_run_statuses_are_the_domains(spec_doc: dict[str, Any]) -> None:
    from coffer.domain.workflow.run import RunStatus

    expected = {status.value for status in RunStatus}
    assert _enum_of(spec_doc, "RunOut", "status") == expected
    listing = spec_doc["paths"][f"{_WORKFLOW_PREFIX}/runs"]["get"]["parameters"][0]
    assert set(listing["schema"]["enum"]) == expected


def test_the_node_statuses_are_the_domains(spec_doc: dict[str, Any]) -> None:
    from coffer.domain.workflow.run import NodeStatus

    expected = {status.value for status in NodeStatus}
    assert _enum_of(spec_doc, "NodeOut", "status") == expected
    assert _enum_of(spec_doc, "NodeAttemptOut", "status") == expected


def test_the_signals_and_actions_are_the_domains(spec_doc: dict[str, Any]) -> None:
    """Four signals about the run, six actions about a node — and they are two
    vocabularies, not one, which is why they are two routes."""
    from coffer.domain.workflow.run import NodeAction, RunSignal

    assert _enum_of(spec_doc, "RunSignalIn", "signal") == {s.value for s in RunSignal}
    actions = {a.value for a in NodeAction}
    assert _enum_of(spec_doc, "NodeActionIn", "action") == actions
    assert _enum_of(spec_doc, "NodeOut", "allowed_actions") == actions


def test_the_node_types_and_approval_policies_are_the_domains(spec_doc: dict[str, Any]) -> None:
    from coffer.domain.workflow.template import ApprovalPolicy, NodeType

    assert _enum_of(spec_doc, "NodeOut", "type") == {t.value for t in NodeType}
    assert _enum_of(spec_doc, "NodeOut", "approval") == {p.value for p in ApprovalPolicy}


def test_the_failure_reasons_are_the_domains(spec_doc: dict[str, Any]) -> None:
    from coffer.domain.workflow.run import FailureReason

    assert _enum_of(spec_doc, "NodeAttemptOut", "failure_reason") == {
        reason.value for reason in FailureReason
    }


def test_the_approval_vocabularies_are_the_domains(spec_doc: dict[str, Any]) -> None:
    from coffer.domain.workflow.run import ApprovalKind, ApprovalStatus

    assert _enum_of(spec_doc, "ApprovalOut", "kind") == {k.value for k in ApprovalKind}
    assert _enum_of(spec_doc, "ApprovalOut", "status") == {s.value for s in ApprovalStatus}


def test_only_a_person_s_two_decisions_are_accepted(spec_doc: dict[str, Any]) -> None:
    """``expired`` and ``superseded`` are outcomes the system reaches on its
    own; a surface that accepted them could forge one."""
    assert _enum_of(spec_doc, "ApprovalDecisionIn", "decision") == {"approved", "rejected"}


def test_the_mounted_input_kinds_are_the_domains(spec_doc: dict[str, Any]) -> None:
    from coffer.domain.workflow.run import RunInputKind

    assert _enum_of(spec_doc, "RunInput", "kind") == {k.value for k in RunInputKind}


def test_the_event_actor_kinds_are_the_domains(spec_doc: dict[str, Any]) -> None:
    from coffer.domain.workflow.events import ActorKind

    actor = _properties(spec_doc, "EventOut")["actor"]
    assert set(actor["properties"]["actor_kind"]["enum"]) == {k.value for k in ActorKind}


def test_the_conflict_codes_are_the_errors_the_domain_raises(spec_doc: dict[str, Any]) -> None:
    """The contract's ``Conflict`` response names four codes by hand. They are
    the codes four domain errors carry, and ``surfaces/http/errors.py`` maps
    each to 409 — one string in three places, not three that agree today."""
    from coffer.domain.workflow.errors import (
        IllegalTransition,
        NotThisMachine,
        RunTerminal,
        WorkflowVersionConflict,
    )
    from coffer.surfaces.http.errors import _STATUS

    described = spec_doc["components"]["responses"]["Conflict"]["description"]
    for error in (WorkflowVersionConflict, RunTerminal, NotThisMachine, IllegalTransition):
        assert error.code in described, f"{error.code} is not named by the Conflict response"
        assert _STATUS[error.code] == 409, f"{error.code} does not map to 409"
