"""Mechanical drift check: specs 006/007 OpenAPI contracts vs the live app.

Two layers, mirroring the spec-001 contract suite:

1. Every path+method declared in the contract exists on the FastAPI app
   (catches removed/renamed endpoints).
2. Every contract schema component maps to a Pydantic model whose property
   set covers the contract's properties and whose required set covers the
   contract's required list (catches silently dropped/renamed fields).

This is the suite the review flagged as missing — without it the 006/007
yamls could drift from the wire shapes with no failing test.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from coffer.surfaces.http.knowledge_base import schemas as kb_schemas
from coffer.surfaces.http.memory import schemas as mem_schemas

_SPECS = Path(__file__).resolve().parents[3] / "specs"
_KB_CONTRACT = _SPECS / "006-knowledge-base/contracts/api.openapi.yaml"
_MEM_CONTRACT = _SPECS / "007-memory/contracts/api.openapi.yaml"

#: contract component -> Pydantic model. ``None`` = intentionally unmapped
#: (enums / envelope shapes asserted elsewhere, or domain-level models).
_KB_MODELS: dict[str, type | None] = {
    "KnowledgeBaseCreate": kb_schemas.KnowledgeBaseCreateRequest,
    "KnowledgeBaseOut": kb_schemas.KnowledgeBaseOut,
    "KnowledgeBaseListOut": kb_schemas.KnowledgeBaseListOut,
    "DocumentOut": kb_schemas.DocumentOut,
    "DocumentDetailOut": kb_schemas.DocumentDetailOut,
    "DocumentListOut": kb_schemas.DocumentListOut,
    "DocumentEditRequest": kb_schemas.DocumentEditRequest,
    "ReindexResult": kb_schemas.ReindexResult,
    "SourceStatus": kb_schemas.SourceStatusOut,
    "SourceCheckResponse": kb_schemas.SourceCheckResponse,
    "SearchRequest": kb_schemas.SearchRequest,
    "SearchResponse": kb_schemas.SearchResponse,
    "Passage": kb_schemas.Passage,
    "GrepRequest": kb_schemas.GrepRequest,
    "GrepHit": kb_schemas.GrepHitOut,
    "GrepResponse": kb_schemas.GrepResponse,
    "KnowledgeBaseMetrics": kb_schemas.KnowledgeBaseMetrics,
    # Enum / envelope / domain-config components without a 1:1 wire model:
    "RetrievalMode": None,
    "ErrorEnvelope": None,
    "KnowledgeBaseConfig": None,  # domain model (coffer.domain.knowledge_base.config)
    "EmbeddingConfig": None,  # domain model (coffer.domain.knowledge.embedder)
}

_MEM_MODELS: dict[str, type | None] = {
    "MemoryStoreConfig": mem_schemas.MemoryStoreConfigOut,
    "MemoryStoreConfigPatch": mem_schemas.MemoryStoreConfigPatch,
    "MemoryStoreLabelPatch": mem_schemas.MemoryStoreLabelPatch,
    "MemoryStoreOut": mem_schemas.MemoryStoreOut,
    "MemoryStoreListOut": mem_schemas.MemoryStoreListOut,
    "MemoryStoreMetrics": mem_schemas.MemoryStoreMetrics,
    "FactCreate": mem_schemas.FactCreate,
    "FactUpdate": mem_schemas.FactUpdate,
    "FactOut": mem_schemas.FactOut,
    "FactListOut": mem_schemas.FactListOut,
    "RecallRequest": mem_schemas.RecallRequest,
    "RecallHit": mem_schemas.RecallHit,
    "RecallResponse": mem_schemas.RecallResponse,
    "OrganizeResponse": mem_schemas.OrganizeResponse,
    "ReorgResponse": mem_schemas.ReorgResponse,
    "RetrievalMode": None,
    "Scope": None,
    "ErrorEnvelope": None,
}


def _load(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())  # type: ignore[no-any-return]


@pytest.fixture(scope="session")
def app_routes() -> set[tuple[str, str]]:
    from coffer.surfaces.http.app import create_app

    app = create_app()
    out: set[tuple[str, str]] = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        if path:
            for m in methods:
                out.add((m.upper(), path))
    return out


@pytest.mark.parametrize("contract_path", [_KB_CONTRACT, _MEM_CONTRACT], ids=["006", "007"])
def test_every_contract_endpoint_exists(contract_path: Path, app_routes) -> None:
    doc = _load(contract_path)
    missing: list[str] = []
    for path, ops in doc["paths"].items():
        for method in ops:
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            if (method.upper(), path) not in app_routes:
                missing.append(f"{method.upper()} {path}")
    assert not missing, f"contract endpoints missing from the app: {missing}"


def _component_cases() -> list[tuple[str, str, type | None, Path]]:
    cases: list[tuple[str, str, type | None, Path]] = []
    for label, mapping, path in [
        ("006", _KB_MODELS, _KB_CONTRACT),
        ("007", _MEM_MODELS, _MEM_CONTRACT),
    ]:
        for component, model in mapping.items():
            cases.append((label, component, model, path))
    return cases


@pytest.mark.parametrize(
    "label,component,model,contract_path",
    _component_cases(),
    ids=[f"{c[0]}:{c[1]}" for c in _component_cases()],
)
def test_schema_fields_cover_contract(
    label: str, component: str, model: type | None, contract_path: Path
) -> None:
    doc = _load(contract_path)
    components = doc["components"]["schemas"]
    assert component in components, f"{component} vanished from the {label} contract"
    if model is None:
        return
    spec = components[component]
    spec_props = set(spec.get("properties", {}))
    spec_required = set(spec.get("required", []))

    json_schema = model.model_json_schema()
    model_props = set(json_schema.get("properties", {}))
    model_required = set(json_schema.get("required", []))

    assert spec_props.issubset(model_props), (
        f"{label} {component}: contract properties missing from "
        f"{model.__name__}: {spec_props - model_props}"
    )
    assert spec_required.issubset(model_required), (
        f"{label} {component}: contract-required fields not required on "
        f"{model.__name__}: {spec_required - model_required}"
    )


def test_every_mapped_component_is_in_contract() -> None:
    """The mapping tables above must not rot: every contract component is
    either mapped to a model or explicitly marked None."""
    for mapping, path in [(_KB_MODELS, _KB_CONTRACT), (_MEM_MODELS, _MEM_CONTRACT)]:
        components = set(_load(path)["components"]["schemas"])
        unmapped = components - set(mapping)
        assert not unmapped, f"{path.name}: contract components not in the mapping: {unmapped}"


def test_retrieval_mode_enum_values_match_code() -> None:
    """Enum VALUES are the one drift class the field-coverage check waves
    through — pin them against the domain literal (review gap)."""
    from coffer.domain.knowledge.retrieval import RETRIEVAL_MODES

    for path in (_KB_CONTRACT, _MEM_CONTRACT):
        components = _load(path)["components"]["schemas"]
        assert set(components["RetrievalMode"]["enum"]) == set(RETRIEVAL_MODES), path.name


def test_memory_scope_enum_values_match_wire() -> None:
    components = _load(_MEM_CONTRACT)["components"]["schemas"]
    # Store-level scope (MemoryStoreOut.scope).
    assert set(components["Scope"]["enum"]) == {"global", "project"}
    # Recall-request scope is an inline enum: project-only / global-only / both.
    recall_scope = components["RecallRequest"]["properties"]["scope"]
    assert set(recall_scope["enum"]) == {"global", "project", "both"}


def test_error_envelope_shape_is_declared() -> None:
    for path in (_KB_CONTRACT, _MEM_CONTRACT):
        envelope = _load(path)["components"]["schemas"]["ErrorEnvelope"]
        error_props = envelope["properties"]["error"]["properties"]
        assert {"code", "message", "details"} <= set(error_props), path.name
