"""The schemas in ``specs/mcp-gateway`` that no route exposes, pinned by name.

This module used to hand-enumerate ~30 schemas and check field *presence* in
both directions. :mod:`test_schema_types_match_openapi` now discovers every
contract in the spec tree and compares its payload shapes against
``app.openapi()`` at **type** level, anchored on the route — which subsumes 27
of those 28 HTTP entries outright, and does more with them than the hand list
ever did. Two gates asserting the same thing is worse than one, so the list is
gone and what is left here is only what a route-anchored sweep provably cannot
reach:

  - **``ErrorResponse``** — the contract's error envelope. It is referenced
    only from ``components.responses``, and FastAPI emits no counterpart at
    all: a generated document carries 200 and 422 and nothing else. So no walk
    from a 2xx response can arrive at it.
  - **``MCPServerConfig``, ``StdioTransport``, ``HttpTransport``** — the shape
    of an ``mcp_server`` resource's ``config``. On the wire that field is
    ``dict[str, Any]``, so it generates as an untyped object and the sweep
    correctly declines to claim anything about its contents. These models are
    real and validated, just not visible through the HTTP schema, so the only
    way to hold the contract to them is to name them. This is where
    ``MCPServerConfig.idle_timeout_seconds`` — declared, validated,
    UI-controlled and implemented by nothing — was free to sit.

:func:`test_the_split_with_the_generic_sweep_is_still_real` keeps that boundary
honest: if any entry below ever becomes reachable from a route, the generic
sweep covers it and the entry here is duplication to delete.

The comparison itself is imported from the generic module rather than
reimplemented, so both gates ignore the same annotations and understand the
same nullable spellings. The truth side here is the model's own
``model_json_schema()`` instead of ``app.openapi()``, for the same reason as
above: these models never appear in the app's document.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import BaseModel

from coffer.domain.mcp import server_config as mcp_server_config
from coffer.surfaces.http import schemas

from .test_schema_types_match_openapi import _compare, route_reachable_schemas

_CONTRACT = "specs/mcp-gateway/contracts/api.openapi.yaml"
_OPENAPI_PATH = Path(__file__).resolve().parents[3] / _CONTRACT


@pytest.fixture(scope="session")
def openapi_doc() -> dict[str, Any]:
    return yaml.safe_load(_OPENAPI_PATH.read_text())  # type: ignore[no-any-return]


#: ``(schema name in the contract, the model that answers for it, is_request)``.
#: Every entry must be unreachable from any route — see the module docstring
#: and :func:`test_the_split_with_the_generic_sweep_is_still_real`. The flag
#: picks the direction the payload travels, which is what decides whether a
#: ``required`` mismatch can break a client.
_UNEXPOSED_SCHEMAS: list[tuple[str, type[BaseModel], bool]] = [
    ("ErrorResponse", schemas.ErrorResponse, False),
    ("MCPServerConfig", mcp_server_config.MCPServerConfig, True),
    ("StdioTransport", mcp_server_config.StdioTransport, True),
    ("HttpTransport", mcp_server_config.HttpTransport, True),
]


def test_the_split_with_the_generic_sweep_is_still_real() -> None:
    """An entry here that the generic sweep can reach is duplication.

    The whole justification for this module is that these four schemas are
    invisible to a route-anchored walk. The day one of them becomes reachable
    — a route starts returning a typed ``config``, or the error envelope lands
    on a 2xx — that justification is gone and the entry should be deleted
    rather than left asserting the same thing twice.
    """
    reachable = route_reachable_schemas(_CONTRACT)
    duplicated = sorted({name for name, _, _ in _UNEXPOSED_SCHEMAS} & reachable)
    assert not duplicated, (
        f"{duplicated} are now reachable from a route in {_CONTRACT}, so "
        f"test_schema_types_match_openapi already compares them — at type level, in both "
        f"directions. Delete them from _UNEXPOSED_SCHEMAS here."
    )


@pytest.mark.parametrize(
    "openapi_name,model,is_request",
    _UNEXPOSED_SCHEMAS,
    ids=[name for name, _, _ in _UNEXPOSED_SCHEMAS],
)
def test_unexposed_schema_matches_its_model(
    openapi_name: str,
    model: type[BaseModel],
    is_request: bool,
    openapi_doc: dict[str, Any],
) -> None:
    """The contract's shape for a schema no route exposes, against the model.

    Same comparison the generic sweep applies to everything else: a property
    the contract declares that the model lacks, a property the model has that
    the contract does not declare, a differing type kind, an array's item kind,
    and — for a shape a client sends — a field the model requires that the
    contract lets the client omit.
    """
    declared = (openapi_doc.get("components") or {}).get("schemas") or {}
    assert openapi_name in declared, (
        f"{_CONTRACT} no longer declares {openapi_name}; either the contract dropped it and "
        f"this entry is stale, or it was renamed and this entry must follow"
    )

    model_doc = model.model_json_schema()
    findings: list[str] = []
    _compare(
        declared[openapi_name],
        model_doc,
        openapi_doc,
        model_doc,
        openapi_name,
        findings,
        is_request=is_request,
    )
    assert not findings, (
        f"{_CONTRACT} and {model.__module__}.{model.__name__} disagree. The model is the truth "
        f"about what is accepted; the contract is the promise:\n    " + "\n    ".join(findings)
    )
