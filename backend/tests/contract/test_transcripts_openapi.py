"""Drift check: specs/007-memory/contracts/transcripts.openapi.yaml vs the live app.

Two layers, mirroring test_kb_memory_openapi.py:

1. Every path+method declared in the contract exists on the FastAPI app
   (catches removed/renamed endpoints).
2. Every contract schema component maps to a Pydantic model whose property
   set covers the contract's properties and whose required set covers the
   contract's required list (catches silently dropped/renamed fields).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from coffer.surfaces.http.distill import schemas as distill_schemas

_SPECS = Path(__file__).resolve().parents[3] / "specs"
_TRANSCRIPTS_CONTRACT = _SPECS / "007-memory/contracts/transcripts.openapi.yaml"

#: contract component -> Pydantic model. ``None`` = intentionally unmapped
#: (enums / envelope shapes asserted by the dedicated test below).
_TRANSCRIPT_MODELS: dict[str, type | None] = {
    "TranscriptSessionSummary": distill_schemas.TranscriptSessionSummary,
    "TranscriptSessionListResponse": distill_schemas.TranscriptSessionListResponse,
    "DistillRequest": distill_schemas.DistillRequest,
    "InsightOut": distill_schemas.InsightOut,
    "DistillResponse": distill_schemas.DistillResponse,
    # Envelope / enum — no 1:1 Pydantic model at the surface layer.
    "ErrorEnvelope": None,
}


def _load(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())  # type: ignore[no-any-return]


def test_contract_file_exists() -> None:
    assert _TRANSCRIPTS_CONTRACT.exists(), f"contract file missing: {_TRANSCRIPTS_CONTRACT}"


def test_every_contract_endpoint_exists_in_app() -> None:
    from coffer.surfaces.http.app import create_app

    app = create_app()
    app_routes: set[tuple[str, str]] = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        if path:
            for m in methods:
                app_routes.add((m.upper(), path))

    doc = _load(_TRANSCRIPTS_CONTRACT)
    missing: list[str] = []
    for path, ops in doc["paths"].items():
        for method in ops:
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            if (method.upper(), path) not in app_routes:
                missing.append(f"{method.upper()} {path}")
    assert not missing, f"contract endpoints missing from the app: {missing}"


def test_schema_fields_cover_contract() -> None:
    """Every contract schema component's properties + required fields are
    present on the mapped Pydantic model."""
    doc = _load(_TRANSCRIPTS_CONTRACT)
    components = doc["components"]["schemas"]

    for component, model in _TRANSCRIPT_MODELS.items():
        assert component in components, f"{component} vanished from the transcripts contract"
        if model is None:
            continue
        spec = components[component]
        spec_props = set(spec.get("properties", {}))
        spec_required = set(spec.get("required", []))

        json_schema = model.model_json_schema()
        model_props = set(json_schema.get("properties", {}))
        model_required = set(json_schema.get("required", []))

        assert spec_props.issubset(model_props), (
            f"transcripts:{component}: contract properties missing from "
            f"{model.__name__}: {spec_props - model_props}"
        )
        assert spec_required.issubset(model_required), (
            f"transcripts:{component}: contract-required fields not required on "
            f"{model.__name__}: {spec_required - model_required}"
        )


def test_every_mapped_component_is_in_contract() -> None:
    """The mapping table above must not rot: every contract component is
    either mapped to a model or explicitly marked None."""
    components = set(_load(_TRANSCRIPTS_CONTRACT)["components"]["schemas"])
    unmapped = components - set(_TRANSCRIPT_MODELS)
    assert not unmapped, f"contract components not in the mapping: {unmapped}"


def test_error_envelope_shape_is_declared() -> None:
    """ErrorEnvelope must declare {code, message, details} nested under error."""
    components = _load(_TRANSCRIPTS_CONTRACT)["components"]["schemas"]
    envelope = components["ErrorEnvelope"]
    error_props = envelope["properties"]["error"]["properties"]
    assert {"code", "message", "details"} <= set(error_props)


def test_insight_type_enum_values_match_domain() -> None:
    """InsightOut.type enum in the contract must match the domain InsightType values."""
    from coffer.domain.distill.session import InsightType

    doc = _load(_TRANSCRIPTS_CONTRACT)
    insight_out = doc["components"]["schemas"]["InsightOut"]
    contract_enum = set(insight_out["properties"]["type"]["enum"])
    domain_values = {t.value for t in InsightType}
    assert contract_enum == domain_values, (
        f"contract InsightOut.type enum {contract_enum} != domain InsightType {domain_values}"
    )
