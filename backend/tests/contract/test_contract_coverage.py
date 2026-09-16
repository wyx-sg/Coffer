"""The gate on the gate: no contract file lands ungated, in either direction.

``make verify-contract`` is ``pytest backend/tests/contract``, and every other
module in this directory names its OpenAPI yaml **by hand** — test_chat_openapi
points at the channels contract, test_schemas_match_openapi at the mcp-gateway
one, and so on. That enumeration is invisible to anything: a new
``specs/**/contracts/api.openapi.yaml`` used to land with no test naming it, and
nothing failed and nothing noticed. Two contracts (memory and vault-sync) sat in
exactly that state.

So this module discovers the contracts instead of trusting the enumeration:

  - :func:`test_every_contract_file_is_enumerated` globs the spec tree
    recursively and compares it against :data:`_CONTRACTS`. A new contract file
    fails here until it is added, and the message says what to add. This test
    starts no app, so the gap is reported in milliseconds.
  - The sweep below then checks **both** directions over every discovered
    contract, so an entry in the table is real coverage rather than a
    registration: nothing the yaml declares may be unserved, and nothing served
    under a contract's own route prefix may be undeclared. The reverse
    direction is the one that let ``POST /api/v1/channels/{name}/callback-test``
    sit undocumented.

A per-contract module (test_memory_openapi.py, test_sync_openapi.py, …) still
earns its place: it pins what is *deliberately* absent, the counts and the
vocabularies, which a generic sweep cannot know. The sweep is the floor, not the
ceiling — :data:`_CONTRACTS` names the module that goes deeper where one exists.

Two limits, recorded rather than hidden:

  - The prefixes a contract owns are derived from the paths it declares (the
    first three segments, e.g. ``/api/v1/memory``), not hand-listed, so they
    cannot fall out of date. Two contracts legitimately share ``/api/v1/agents``
    — agent-registry owns the agent itself, skill-manager owns
    ``/agents/{name}/unmanaged-skills`` — so the reverse direction asks whether
    a served route is documented by *some* contract rather than by one
    particular file. A route under a prefix no contract claims at all is out of
    scope here by construction.
  - A route excluded from the schema (``include_in_schema=False``) is invisible
    to both directions, because the generated OpenAPI is the only thing
    FastAPI 0.141 still lets us read the route table out of. There are none in
    the tree today.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SPECS_DIR = _REPO_ROOT / "specs"
_CONTRACT_GLOB = "**/contracts/api.openapi.yaml"

_OPERATION_METHODS = frozenset({"get", "post", "put", "patch", "delete"})

#: Every contract file in the spec tree, and the module that covers it beyond
#: this sweep — or ``None`` where the sweep below is the whole of its coverage.
#: Keys are repo-relative POSIX paths. Adding a contract file means adding a key
#: here; the value is a promise about where a reader looks next, so it is a
#: module name in this directory or nothing.
_CONTRACTS: dict[str, str | None] = {
    "specs/agent-registry/contracts/api.openapi.yaml": None,
    "specs/channels/contracts/api.openapi.yaml": "test_channel_contract.py",
    "specs/chat/contracts/api.openapi.yaml": "test_chat_openapi.py",
    "specs/credentials/contracts/api.openapi.yaml": None,
    "specs/daemon/contracts/api.openapi.yaml": None,
    "specs/internal-engine/contracts/api.openapi.yaml": None,
    "specs/knowledge/contracts/api.openapi.yaml": "test_knowledge_openapi.py",
    "specs/mcp-gateway/contracts/api.openapi.yaml": "test_schemas_match_openapi.py",
    "specs/memory/contracts/api.openapi.yaml": "test_memory_openapi.py",
    "specs/provider-switching/contracts/api.openapi.yaml": None,
    "specs/resource-framework/contracts/api.openapi.yaml": None,
    "specs/skill-manager/contracts/api.openapi.yaml": None,
    "specs/vault-sync/contracts/api.openapi.yaml": "test_sync_openapi.py",
}


def _discover() -> list[str]:
    """Every contract file in the tree, repo-relative, recursively.

    Recursive by design: the spec tree is nesting, so
    ``specs/<parent>/<child>/contracts/api.openapi.yaml`` must be found too.
    """
    return sorted(
        path.relative_to(_REPO_ROOT).as_posix() for path in _SPECS_DIR.glob(_CONTRACT_GLOB)
    )


def _load(relpath: str) -> dict[str, Any]:
    return yaml.safe_load((_REPO_ROOT / relpath).read_text())  # type: ignore[no-any-return]


def _base_path(doc: dict[str, Any]) -> str:
    """The path component of the contract's first server URL.

    Contracts in this repo use both conventions: some declare whole paths
    (``/api/v1/memory/partitions``) against a bare host, others declare
    ``/agents`` against ``http://127.0.0.1:{port}/api/v1``. Comparing either
    against the app means reading the base off the server entry.
    """
    servers = doc.get("servers") or [{}]
    return urlsplit(str(servers[0].get("url", ""))).path.rstrip("/")


def _declared_operations(doc: dict[str, Any]) -> set[tuple[str, str]]:
    """Every (METHOD, absolute path) the contract declares."""
    base = _base_path(doc)
    return {
        (method.upper(), base + path)
        for path, operations in (doc.get("paths") or {}).items()
        for method in operations
        if method.lower() in _OPERATION_METHODS
    }


def _prefix_of(path: str) -> str:
    """The route family a path belongs to: its first three segments."""
    return "/".join(path.split("/")[:4])


@pytest.fixture(scope="module")
def served_operations() -> set[tuple[str, str]]:
    """Every (METHOD, path) the app declares, read from its generated OpenAPI.

    Read from the schema rather than by walking ``app.routes``: FastAPI 0.141
    stopped flattening an included router's routes into that list, so
    introspecting it silently finds nothing.
    """
    from coffer.main import app

    schema = app.openapi()
    return {
        (method.upper(), path)
        for path, operations in (schema.get("paths") or {}).items()
        for method in operations
        if method.lower() in _OPERATION_METHODS
    }


# ---------------------------------------------------------------------------
# Discovery — no app, no imports, milliseconds
# ---------------------------------------------------------------------------


def test_every_contract_file_is_enumerated() -> None:
    """Discovered contract files and the enumerated ones must be the same set."""
    discovered = set(_discover())
    assert discovered, (
        f"no contract file found under {_SPECS_DIR}/{_CONTRACT_GLOB} — the glob is wrong, "
        f"and the coverage gate below is passing vacuously"
    )

    ungated = sorted(discovered - set(_CONTRACTS))
    stale = sorted(set(_CONTRACTS) - discovered)
    problems: list[str] = []
    if ungated:
        problems.append(
            "these contract files are gated by nothing:\n    "
            + "\n    ".join(ungated)
            + "\n  Add each to _CONTRACTS in backend/tests/contract/test_contract_coverage.py. "
            "That alone gets it the route sweep in this module, in both directions. If it "
            "needs more than that — deliberate absences, a route count, an enum's values — "
            "add a module beside test_memory_openapi.py and name it as the entry's value."
        )
    if stale:
        problems.append(
            "these _CONTRACTS entries name a file that no longer exists, so they assert "
            "nothing:\n    " + "\n    ".join(stale) + "\n  Delete the entry, and the module "
            "that named the deleted contract with it."
        )
    assert not problems, "\n\n".join(problems)


@pytest.mark.parametrize("relpath", sorted(_CONTRACTS))
def test_the_named_module_exists(relpath: str) -> None:
    """An entry may promise a module that goes deeper. If it names one, that
    module must be here — a stale name is worse than no name."""
    module = _CONTRACTS[relpath]
    if module is None:
        return
    assert (Path(__file__).parent / module).is_file(), (
        f"_CONTRACTS says {relpath} is covered by {module}, which does not exist in "
        f"{Path(__file__).parent}"
    )


def test_no_module_names_a_contract_that_is_gone() -> None:
    """Every contract path written into a module in this directory must resolve.

    The other half of the stale-enumeration problem: a module that points at a
    deleted contract does not fail loudly, it fails *quietly* — depending on its
    shape it can iterate an empty document and pass vacuously. Read the sources
    rather than import them, so one bad path is reported rather than crashing
    collection.
    """
    pattern = re.compile(r"specs/[\w./-]*contracts/api\.openapi\.yaml")
    dangling: list[str] = []
    for module in sorted(Path(__file__).parent.glob("test_*.py")):
        if module.name == Path(__file__).name:
            continue  # this module's own paths come from the glob, not from text
        for named in sorted(set(pattern.findall(module.read_text()))):
            if not (_REPO_ROOT / named).is_file():
                dangling.append(f"{module.name} names {named}, which does not exist")
    assert not dangling, (
        "a contract test points at a contract file that is gone:\n    " + "\n    ".join(dangling)
    )


@pytest.mark.parametrize("relpath", sorted(_CONTRACTS))
def test_every_contract_file_parses_and_declares_routes(relpath: str) -> None:
    """A contract that declares nothing would satisfy the sweep vacuously."""
    doc = _load(relpath)
    assert doc.get("openapi"), f"{relpath} has no openapi version — is it an OpenAPI document?"
    assert _declared_operations(doc), (
        f"{relpath} declares no operations, so every route assertion over it would pass "
        f"vacuously. Either it is not finished, or its paths are not where this sweep looks."
    )


# ---------------------------------------------------------------------------
# The sweep — both directions, over every discovered contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("relpath", sorted(_CONTRACTS))
def test_every_declared_route_is_served(
    relpath: str,
    served_operations: set[tuple[str, str]],
) -> None:
    """Forward direction: nothing a contract declares may be unserved, so a
    yaml-only edit cannot drift away from the implementation."""
    missing = _declared_operations(_load(relpath)) - served_operations
    assert not missing, (
        f"{relpath} declares routes the app does not serve: "
        f"{sorted(f'{m} {p}' for m, p in missing)}"
    )


def test_no_served_route_under_a_contract_prefix_is_undocumented(
    served_operations: set[tuple[str, str]],
) -> None:
    """Reverse direction: a route the app serves under a route family some
    contract claims must appear in some contract.

    This is the direction nothing asserted before, and the reason an
    undocumented route could ship. Asked across the contracts rather than
    per-file because two of them legitimately share ``/api/v1/agents`` — see
    the module docstring.
    """
    declared: set[tuple[str, str]] = set()
    owners: dict[str, set[str]] = {}
    for relpath in _CONTRACTS:
        operations = _declared_operations(_load(relpath))
        declared |= operations
        for _, path in operations:
            owners.setdefault(_prefix_of(path), set()).add(relpath)

    undocumented = sorted(
        (method, path)
        for method, path in served_operations - declared
        if _prefix_of(path) in owners
    )
    assert not undocumented, (
        "these routes are served but appear in no contract:\n    "
        + "\n    ".join(
            f"{method} {path}  (add it to: {', '.join(sorted(owners[_prefix_of(path)]))})"
            for method, path in undocumented
        )
    )
