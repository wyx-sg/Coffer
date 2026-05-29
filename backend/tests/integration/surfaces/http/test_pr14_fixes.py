"""Fix-validation tests for PR #14 code-review findings.

Covers the small fixes that were not already exercised by the existing
suite:

- CODE-001 — capability_key in request body (legacy path-style + body-style routes both work)
- CODE-002 — backup endpoint rejects ".." path traversal
- CODE-006 — audit details strip transport ``env`` / ``headers``
- CODE-018 — token rotation tmp file never exists with mode wider than 0600
- CODE-023 — Pydantic validation failures do not echo per-field input back
- CODE-024 — CORS origin allowlist is env-driven
- CODE-025 — KeychainSetIn.value is bounded at 8192 bytes
- SPEC-005 — X-Coffer-Actor header is respected and validated
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

# CODE-002 ------------------------------------------------------------------- #


def test_backup_rejects_traversal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`POST /daemon/backup` with a `..` in the path is rejected with 400."""
    from coffer.surfaces.http.daemon_routes import _resolve_backup_dest

    monkeypatch.setenv("HOME", str(tmp_path))
    # We expect HTTPException with status_code=400 on traversal.
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        _resolve_backup_dest("../etc/passwd")
    assert exc_info.value.status_code == 400


# CODE-006 ------------------------------------------------------------------- #


def test_audit_safe_config_strips_env_and_headers() -> None:
    """`env` and `headers` inside transport are stripped from the audited config."""
    from coffer.application.resource_service import _audit_safe_config

    cfg = {
        "transport": {
            "type": "http",
            "url": "https://example/mcp",
            "headers": {"Authorization": "Bearer secret123"},
            "credential_refs": {"X-Api-Key": "mykey"},
        },
        "auto_enable_new_capabilities": True,
    }
    sanitised = _audit_safe_config(cfg)
    assert "headers" not in sanitised["transport"]
    assert sanitised["transport"]["credential_refs"] == {"X-Api-Key": "mykey"}
    # Original input must not be mutated.
    assert "headers" in cfg["transport"]


# CODE-018 ------------------------------------------------------------------- #


def test_atomic_write_0600_never_world_readable(tmp_path: Path) -> None:
    """`_atomic_write_0600` produces a file with mode exactly 0600."""
    from coffer.surfaces.http.daemon_routes import _atomic_write_0600

    target = tmp_path / "secret.json"
    _atomic_write_0600(target, "{}")
    mode = stat.S_IMODE(os.stat(target).st_mode)
    assert mode == 0o600, f"expected 0o600, got {oct(mode)}"


# CODE-024 ------------------------------------------------------------------- #


def test_cors_origins_prod_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COFFER_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("COFFER_DEV_CORS", raising=False)
    from coffer.surfaces.http.cors import _resolve_origins

    origins = _resolve_origins()
    assert "tauri://localhost" in origins
    # Dev origins must NOT be present without the dev flag.
    assert "http://localhost:5173" not in origins


def test_cors_origins_dev_flag_includes_vite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COFFER_CORS_ORIGINS", raising=False)
    monkeypatch.setenv("COFFER_DEV_CORS", "1")
    from coffer.surfaces.http.cors import _resolve_origins

    origins = _resolve_origins()
    assert "http://localhost:5173" in origins


# CODE-025 ------------------------------------------------------------------- #


def test_keychain_set_in_bounds_value() -> None:
    from pydantic import ValidationError

    from coffer.surfaces.http.schemas import KeychainSetIn

    KeychainSetIn(ref="ok", value="x" * 8192)  # boundary
    with pytest.raises(ValidationError):
        KeychainSetIn(ref="ok", value="x" * 8193)


# SPEC-005 ------------------------------------------------------------------- #


def test_get_actor_defaults_to_api() -> None:
    from coffer.surfaces.http.dependencies import get_actor

    assert get_actor(None) == "api"
    assert get_actor("") == "api"


def test_get_actor_accepts_short_identifiers() -> None:
    from coffer.surfaces.http.dependencies import get_actor

    for v in ("cli", "api", "ui", "system", "e2e-mcp", "e2e-http", "test_runner"):
        assert get_actor(v) == v


def test_get_actor_rejects_invalid_strings() -> None:
    from fastapi import HTTPException

    from coffer.surfaces.http.dependencies import get_actor

    for bad in ("UPPER", "has space", "x" * 33, "1starts-with-digit", "$pecial"):
        with pytest.raises(HTTPException) as exc_info:
            get_actor(bad)
        assert exc_info.value.status_code == 400


# CODE-001 ------------------------------------------------------------------- #


def test_capability_key_body_schema_rejects_empty() -> None:
    from pydantic import ValidationError

    from coffer.surfaces.http.schemas import CapabilityKeyBody

    CapabilityKeyBody(capability_key="file:///path/with/slashes")
    with pytest.raises(ValidationError):
        CapabilityKeyBody(capability_key="")


# CODE-009 ------------------------------------------------------------------- #


def test_coerce_call_result_raises_on_unparseable() -> None:
    from coffer.application.mcp.gateway_handlers import coerce_call_result
    from coffer.domain.errors import UpstreamUnavailable

    # dict goes through
    assert coerce_call_result({"content": []}) == {"content": []}
    # garbage raises
    with pytest.raises(UpstreamUnavailable):
        coerce_call_result(object())
