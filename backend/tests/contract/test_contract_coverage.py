"""The gate on the gate: every served route has an owning capability.

The contracts under ``openspec/specs/**/contracts/api.openapi.yaml`` are
generated from the daemon's own OpenAPI document by ``scripts/gen_contracts.py``
(``make contracts``), and ``make lint`` fails when a checked-in file is not
what the models produce. What freshness cannot see is a route that belongs to
no contract at all: the generator splits the document by its ownership table,
and a route outside it would silently be in no file. So this module holds the
table to the route set, in both directions:

  - every route the app serves, except the MCP protocol endpoint, has exactly
    one owning capability, and that capability has a spec;
  - every ownership rule claims at least one served route, so a stale rule
    cannot linger after its routes are gone;
  - every contract file in the spec tree is one the generator writes, so a
    hand-made contract cannot sit beside the generated ones.

A route excluded from the schema (``include_in_schema=False``) is invisible
here, because the generated OpenAPI is the only route table FastAPI still lets
us read. There are none in the tree today.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
_GENERATOR = _REPO_ROOT / "scripts" / "gen_contracts.py"
_OPERATION_METHODS = frozenset({"get", "post", "put", "patch", "delete"})


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gen_contracts", _GENERATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["gen_contracts"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def generator() -> ModuleType:
    return _load_generator()


@pytest.fixture(scope="module")
def document(generator: ModuleType) -> dict[str, Any]:
    return generator.load_openapi()  # type: ignore[no-any-return]


def test_every_served_route_has_one_owner(generator: ModuleType, document: dict[str, Any]) -> None:
    """``split_paths`` raises on an unowned route, a rule that claims nothing,
    a capability with no route and a capability with no spec."""
    owned = generator.split_paths(document)
    served = {path for path in document["paths"] if path not in generator.UNCONTRACTED}
    assigned = [path for paths in owned.values() for path in paths]
    assert sorted(assigned) == sorted(served), "a served route is in no contract, or in two"


def test_an_unowned_route_fails_generation(generator: ModuleType) -> None:
    """The failure mode the table exists for, pinned so a refactor of the
    matcher cannot turn it into a silent drop."""
    doc = {"paths": {"/api/v1/nobody-owns-this": {"get": {}}}}
    with pytest.raises(generator.OwnershipError, match="no capability owns"):
        generator.split_paths(doc)


def test_a_narrower_rule_carves_out_a_subtree(generator: ModuleType) -> None:
    assert generator.owner_of("/api/v1/agents/{uid}") == "agent-registry"
    assert generator.owner_of("/api/v1/agents/{uid}/unmanaged-skills/{skill}") == "skill-manager"
    assert generator.owner_of("/api/v1/resources/{uid}/scope") == "resource-framework"
    assert generator.owner_of("/api/v1/resources/mcp_server/{uid}/test") == "mcp-gateway"
    # Segment prefixes, not string prefixes: /api/v1/mcpx is not /api/v1/mcp.
    assert generator.owner_of("/api/v1/mcpx") is None


def test_every_contract_file_is_generated(generator: ModuleType) -> None:
    checked_in = {
        path.relative_to(_REPO_ROOT).as_posix()
        for path in (_REPO_ROOT / "openspec" / "specs").glob("**/contracts/api.openapi.yaml")
    }
    expected = {
        f"openspec/specs/{capability}/contracts/api.openapi.yaml" for capability in generator.TITLES
    }
    assert checked_in == expected, (
        f"contract files the generator does not write: {sorted(checked_in - expected)}; "
        f"contract files it writes that are missing: {sorted(expected - checked_in)} "
        "— run `make contracts`"
    )


@pytest.mark.parametrize(
    "capability",
    sorted(_load_generator().TITLES),
)
def test_every_contract_declares_routes(capability: str) -> None:
    """A contract that declares nothing would make every consumer of it pass
    vacuously — the generated frontend module included."""
    path = _REPO_ROOT / "openspec" / "specs" / capability / "contracts" / "api.openapi.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert doc["openapi"].startswith("3.")
    operations = [
        method for item in doc["paths"].values() for method in item if method in _OPERATION_METHODS
    ]
    assert operations, f"{path} declares no operations"
