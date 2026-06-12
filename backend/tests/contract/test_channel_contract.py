"""Contract test: the app's generated OpenAPI for the channel routes
structurally matches specs/009-channels/contracts/api.openapi.yaml.

Mirrors test_chat_openapi.py: every path declared in the 009 yaml must be
served, and every schema component must exist with at least the yaml's
required fields. Drift means one side must be realigned.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from coffer.main import app

_CHANNEL_OPENAPI_PATH = (
    Path(__file__).resolve().parents[3] / "specs/009-channels/contracts/api.openapi.yaml"
)


@pytest.fixture(scope="module")
def generated_schema() -> dict[str, Any]:
    """Return the FastAPI-generated OpenAPI schema once per test module."""
    return app.openapi()  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def spec_doc() -> dict[str, Any]:
    """Parse specs/009-channels/contracts/api.openapi.yaml once per module."""
    return yaml.safe_load(_CHANNEL_OPENAPI_PATH.read_text())  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Path existence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,method",
    [
        ("/api/v1/channels/{name}/pairing-code", "post"),
        ("/api/v1/channels/{name}/status", "get"),
        ("/api/v1/channels/{name}/notify", "post"),
        ("/api/v1/channels/{name}/events", "post"),
    ],
)
def test_channel_path_and_method_exists(
    generated_schema: dict[str, Any],
    path: str,
    method: str,
) -> None:
    """Every path+method declared in the 009 OpenAPI spec must exist in the
    generated schema."""
    paths = generated_schema.get("paths", {})
    assert path in paths, (
        f"Path '{path}' missing from generated OpenAPI. Available paths: {sorted(paths)}"
    )
    assert method in paths[path], (
        f"Method '{method}' missing for path '{path}'. Available methods: {sorted(paths[path])}"
    )


def test_every_yaml_path_is_implemented(
    generated_schema: dict[str, Any],
    spec_doc: dict[str, Any],
) -> None:
    """Drive the contract from the yaml itself: every path+method written in
    api.openapi.yaml must exist in the running app, so a yaml-only edit cannot
    silently drift from the implementation."""
    generated_paths = generated_schema.get("paths", {})
    yaml_paths = spec_doc.get("paths") or {}
    assert yaml_paths, "009 yaml declares no paths — wrong file?"
    for path, methods in yaml_paths.items():
        assert path in generated_paths, (
            f"Path '{path}' is declared in api.openapi.yaml but not served by the app."
        )
        for method in methods:
            if method.lower() not in {"get", "post", "patch", "put", "delete"}:
                continue  # skip non-operation keys (parameters, summary, …)
            assert method.lower() in generated_paths[path], (
                f"'{method.upper()} {path}' is declared in api.openapi.yaml "
                f"but not served by the app."
            )


# ---------------------------------------------------------------------------
# Schema component fields
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "schema_name,required_fields",
    [
        ("PairingCodeOut", {"code", "expires_at"}),
        ("ChannelStatusOut", {"name", "channel_type", "enabled", "running", "peer", "callback"}),
        ("ChannelPeerOut", {"chat_id", "display_name", "paired_at", "active_conversation_id"}),
        ("CallbackInfoOut", {"port", "path", "listener_running"}),
        ("NotifyIn", {"text"}),
        ("NotifyOut", {"sent"}),
        ("EventAcceptedOut", {"accepted"}),
    ],
)
def test_channel_schema_required_fields(
    generated_schema: dict[str, Any],
    schema_name: str,
    required_fields: set[str],
) -> None:
    """Every schema component in the 009 spec must exist in the generated
    schemas with at least the yaml's required fields."""
    components = generated_schema.get("components", {}).get("schemas", {})
    assert schema_name in components, (
        f"Schema '{schema_name}' missing from generated OpenAPI components. "
        f"Available: {sorted(components)}"
    )
    actual_required = set(components[schema_name].get("required", []))
    assert required_fields.issubset(actual_required), (
        f"Schema '{schema_name}': missing required fields "
        f"{required_fields - actual_required}. Actual required: {actual_required}"
    )


def test_notify_text_bounds_match_contract(
    generated_schema: dict[str, Any],
    spec_doc: dict[str, Any],
) -> None:
    """NotifyIn.text length bounds are part of the wire contract (the CLI and
    listener size their payloads against them)."""
    yaml_text = spec_doc["components"]["schemas"]["NotifyIn"]["properties"]["text"]
    generated_text = generated_schema["components"]["schemas"]["NotifyIn"]["properties"]["text"]
    assert generated_text.get("minLength") == yaml_text["minLength"] == 1
    assert generated_text.get("maxLength") == yaml_text["maxLength"] == 4096


def test_channel_status_type_enum_matches_contract(spec_doc: dict[str, Any]) -> None:
    """The yaml pins channel_type to the two shipped transports."""
    channel_type = spec_doc["components"]["schemas"]["ChannelStatusOut"]["properties"][
        "channel_type"
    ]
    assert channel_type["enum"] == ["telegram", "seatalk"]
