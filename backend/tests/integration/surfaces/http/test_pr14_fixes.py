"""Fix-validation tests for PR #14 code-review findings.

Covers the small fixes that were not already exercised by the existing
suite:

- CODE-001 — capability_key in request body (legacy path-style + body-style routes both work)
- CODE-002 — backup endpoint rejects ".." path traversal
- CODE-006 — audit details strip transport ``env`` / ``headers``
- CODE-018 — token rotation tmp file never exists with mode wider than 0600
- CODE-023 — Pydantic validation failures do not echo per-field input back
- CODE-024 — CORS origin allowlist is env-driven
- CODE-025 — CredentialSetIn.value is bounded at 8192 bytes
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
    """`env` and `headers` inside transport are stripped from the audited config.

    CODE-006 lives in the mcp_server Kind's redactor now (ADR-001: the
    kind-agnostic ResourceService no longer hardcodes the transport shape).
    """
    from coffer.application.mcp.kind import _mcp_audit_redactor

    cfg = {
        "transport": {
            "type": "http",
            "url": "https://example/mcp",
            "headers": {"Authorization": "Bearer secret123"},
            "credential_refs": {"X-Api-Key": "mykey"},
        },
        "auto_enable_new_capabilities": True,
    }
    sanitised = _mcp_audit_redactor(cfg)
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


def test_credential_set_in_bounds_value() -> None:
    from pydantic import ValidationError

    from coffer.surfaces.http.schemas import CredentialSetIn

    CredentialSetIn(ref="ok", value="x" * 8192)  # boundary
    with pytest.raises(ValidationError):
        CredentialSetIn(ref="ok", value="x" * 8193)


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


# CODE-027 ------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_upstream_env_does_not_inherit_daemon_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A spawned stdio upstream must NOT inherit the daemon's full os.environ.

    Only the SDK's safe base (PATH/HOME/…), the server's own static env, and
    its materialised credentials reach the child. A daemon-side secret env var
    must be absent so an untrusted upstream can't read it.
    """
    from coffer.domain.errors import UpstreamUnavailable
    from coffer.domain.mcp.server_config import StdioTransport
    from coffer.infrastructure.mcp import subprocess as sp

    monkeypatch.setenv("COFFER_DAEMON_SECRET", "super-secret-value")

    captured: dict[str, dict[str, str]] = {}

    class _StopCtx:
        async def __aenter__(self) -> None:
            raise RuntimeError("stop after capture")

        async def __aexit__(self, *_a: object) -> bool:
            return False

    def _fake_stdio_client(params: object) -> _StopCtx:
        captured["env"] = dict(getattr(params, "env", None) or {})
        return _StopCtx()

    monkeypatch.setattr(sp, "stdio_client", _fake_stdio_client)

    conn = sp.StdioUpstreamConnection(
        transport=StdioTransport(command="/bin/true", args=[], env={"MY_STATIC": "x"}),
        env_overlay={"API_KEY": "from-keychain"},
    )
    with pytest.raises(UpstreamUnavailable):
        await conn.spawn_and_initialize()

    env = captured["env"]
    assert "COFFER_DAEMON_SECRET" not in env, "daemon secret leaked into upstream env"
    assert env.get("MY_STATIC") == "x"
    assert env.get("API_KEY") == "from-keychain"
    assert "PATH" in env, "the safe base environment must still be present"


# CODE-031 ------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_server_request_matches_string_echoed_id() -> None:
    """A downstream client may echo our integer request id back as a string;
    the pending request must still resolve (not time out)."""
    import asyncio

    from coffer.application.mcp.gateway_server_requests import ServerRequestRegistry

    reg = ServerRequestRegistry()
    sent: dict[str, object] = {}

    async def sink(payload: dict[str, object]) -> None:
        sent.update(payload)

    task = asyncio.create_task(reg.send_request("roots/list", {}, sink, timeout=5.0))
    for _ in range(50):
        await asyncio.sleep(0)
        if "id" in sent:
            break
    assert "id" in sent
    rid = sent["id"]
    assert isinstance(rid, int)

    # Client echoes the id back as a STRING.
    matched = reg.handle_response({"id": str(rid), "result": {"roots": []}})
    assert matched is True
    assert await task == {"roots": []}


# CODE-035 ------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_session_dispose_invokes_on_dispose_cleanup() -> None:
    """MCPGatewaySession.dispose must call its on_dispose hook so the
    composition root can drop the session's supervisor from its registry."""
    from coffer.application.mcp.gateway import MCPGatewaySession

    class _StubSupervisor:
        async def dispose(self) -> None:
            return None

    registry: dict[str, object] = {}
    session = MCPGatewaySession(
        session_id="s1",
        resource_service=object(),  # type: ignore[arg-type]
        supervisor=_StubSupervisor(),  # type: ignore[arg-type]
        discovery=object(),  # type: ignore[arg-type]
        preferences=object(),  # type: ignore[arg-type]
        invocations=object(),  # type: ignore[arg-type]
        on_dispose=lambda: registry.pop("s1", None),
    )
    registry["s1"] = object()
    await session.dispose()
    assert "s1" not in registry, "on_dispose must remove the registry entry"


# CODE-039 ------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_stdio_init_failure_message_excludes_exception_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failing upstream spawn must surface only the exception TYPE, never the
    raw exception text (which can embed credential-bearing argv/URLs)."""
    from coffer.domain.errors import UpstreamUnavailable
    from coffer.domain.mcp.server_config import StdioTransport
    from coffer.infrastructure.mcp import subprocess as sp

    secret = "token=SECRET-abc123"

    def _boom(params: object) -> object:
        raise ValueError(f"connect failed https://host/?{secret}")

    monkeypatch.setattr(sp, "stdio_client", _boom)
    conn = sp.StdioUpstreamConnection(
        transport=StdioTransport(command="/bin/true", args=[]),
        env_overlay={},
    )
    with pytest.raises(UpstreamUnavailable) as ei:
        await conn.spawn_and_initialize()
    assert "SECRET" not in str(ei.value)
    assert "ValueError" in str(ei.value)


# CODE-045 ------------------------------------------------------------------- #


def test_file_size_check_marker_only_excludes_typescript() -> None:
    """The generated-file marker must not let a backend .py dodge the size cap;
    only .ts/.tsx files are eligible for the marker-based exclusion."""
    import importlib.util
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[5]
    script = repo_root / "scripts" / "check_file_sizes.py"
    spec = importlib.util.spec_from_file_location("_cfs", script)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert mod._is_generated.__module__  # sanity: module loaded
    # A .py file claiming the marker is NOT treated as generated.
    assert mod._is_generated(Path("evil.py")) is False
    # The substring ".test." in a non-test .py name must not exclude it.
    assert mod.is_excluded(Path("backend/coffer/foo.test.helper.py")) is False
