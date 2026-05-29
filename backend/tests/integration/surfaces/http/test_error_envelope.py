"""Verify the error envelope shape is uniform across the API surface.

The frontend's translateApiError() matches on {error: {code}}; a route that
leaks raw FastAPI {"detail": ...} would fall through to the generic
"unexpected error" toast and break i18n. These tests pin the contract so
adding a new route via HTTPException can't silently regress that shape.
"""

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token


def _app(tmp_path, monkeypatch, port_start: int):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port_start))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port_start + 9))
    return create_app()


def _assert_envelope(body: dict, code: str) -> None:
    assert "error" in body, body
    assert body["error"]["code"] == code, body
    assert isinstance(body["error"]["message"], str)
    assert isinstance(body["error"]["details"], dict)


def test_missing_token_returns_unauthenticated_envelope(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59300)
    with TestClient(app) as c:
        set_active_token("real-token")
        r = c.get("/api/v1/resources")
        assert r.status_code == 401
        _assert_envelope(r.json(), "UNAUTHENTICATED")


def test_wrong_token_returns_unauthenticated_envelope(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59310)
    with TestClient(app) as c:
        set_active_token("real-token")
        r = c.get("/api/v1/resources", headers={"X-Coffer-Token": "wrong"})
        assert r.status_code == 401
        _assert_envelope(r.json(), "UNAUTHENTICATED")


def test_token_unset_returns_daemon_not_ready_envelope(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59320)
    with TestClient(app) as c:
        set_active_token(None)
        r = c.get("/api/v1/resources", headers={"X-Coffer-Token": "anything"})
        assert r.status_code == 503
        _assert_envelope(r.json(), "DAEMON_NOT_READY")


def test_unknown_route_returns_not_found_envelope(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59330)
    with TestClient(app) as c:
        set_active_token("real-token")
        r = c.get("/api/v1/this-route-does-not-exist")
        assert r.status_code == 404
        _assert_envelope(r.json(), "NOT_FOUND")


def test_duplicate_resource_returns_409_envelope(tmp_path, monkeypatch):
    """Registering a duplicate resource must return 409 with RESOURCE_ALREADY_EXISTS envelope."""
    app = _app(tmp_path, monkeypatch, 59340)
    with TestClient(app) as c:
        set_active_token("real-token")
        hdrs = {"X-Coffer-Token": "real-token"}
        body = {
            "kind": "mcp_server",
            "name": "dup",
            "config": {"transport": {"type": "stdio", "command": "cat", "args": []}},
        }
        r1 = c.post("/api/v1/resources", json=body, headers=hdrs)
        assert r1.status_code == 201, r1.text
        r2 = c.post("/api/v1/resources", json=body, headers=hdrs)
        assert r2.status_code == 409
        _assert_envelope(r2.json(), "RESOURCE_ALREADY_EXISTS")


def test_invalid_config_returns_422_envelope(tmp_path, monkeypatch):
    """Registering with a bad config schema must return 422 with CONFIG_INVALID envelope."""
    app = _app(tmp_path, monkeypatch, 59350)
    with TestClient(app) as c:
        set_active_token("real-token")
        hdrs = {"X-Coffer-Token": "real-token"}
        # transport.type is required; omit it to trigger validation failure
        r = c.post(
            "/api/v1/resources",
            json={"kind": "mcp_server", "name": "bad", "config": {"transport": {}}},
            headers=hdrs,
        )
        assert r.status_code == 422
        _assert_envelope(r.json(), "CONFIG_INVALID")


@pytest.mark.asyncio
async def test_tool_disabled_returns_403_envelope(tmp_path, monkeypatch):
    """Calling a disabled tool via /mcp must return 200 (JSON-RPC) with TOOL_DISABLED error code.

    The gateway surfaces ToolDisabled as a JSON-RPC error with code -32000;
    the HTTP status code stays 200 (per JSON-RPC over HTTP semantics).
    This test verifies the envelope is never a bare 403 HTTP error — the
    TOOL_DISABLED error is encapsulated in the JSON-RPC error envelope.
    """
    import sys
    from pathlib import Path

    _fake = Path(__file__).resolve().parents[3] / "fixtures" / "fake_mcp_server.py"

    import keyring
    import keyring.core
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from coffer.application.audit_service import AuditService
    from coffer.application.mcp.credential_resolver import CredentialResolver
    from coffer.application.mcp.discovery import CapabilityDiscovery
    from coffer.application.mcp.gateway import MCPGatewaySession
    from coffer.application.mcp.supervisor import SubprocessSupervisor
    from coffer.application.resource_service import ResourceService
    from coffer.domain.mcp.server_config import MCPServerConfig
    from coffer.domain.resource import Kind, ResourceRef
    from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter
    from coffer.infrastructure.mcp.persistence import (
        MCPCapabilityPreferenceRepo,
        MCPInvocationRepo,
    )
    from coffer.infrastructure.persistence.base import Base
    from coffer.infrastructure.persistence.engine import (
        create_async_engine_with_pragmas,
        session_maker,
    )
    from coffer.infrastructure.persistence.repos import (
        SqlAlchemyAuditRepo,
        SqlAlchemyResourceRepo,
    )
    from coffer.surfaces.http import errors as err_handlers
    from coffer.surfaces.http.auth import set_active_token as _set_token
    from coffer.surfaces.http.dependencies import set_mcp_session_factory
    from coffer.surfaces.http.mcp.protocol_routes import (
        _ACTIVE_SESSIONS,
        _LAST_ACTIVITY,
        _NOTIFICATION_QUEUES,
        shutdown_all_sessions,
    )
    from coffer.surfaces.http.mcp.protocol_routes import router as mcp_router

    class _Keyring(keyring.backend.KeyringBackend):
        priority = 1.0  # type: ignore[assignment]

        def get_password(self, s: str, u: str) -> str | None:
            return None

        def set_password(self, s: str, u: str, p: str) -> None:
            pass

        def delete_password(self, s: str, u: str) -> None:
            pass

    monkeypatch.setattr(keyring.core, "_keyring_backend", _Keyring())

    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'tool_dis.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    rsvc = ResourceService(
        kinds={
            "mcp_server": Kind(
                name="mcp_server",
                display_name="MCP Server",
                config_schema=MCPServerConfig,
            )
        },
        repo=SqlAlchemyResourceRepo(sm),
        audit=audit,
    )
    await rsvc.register(
        kind="mcp_server",
        name="fs",
        config={
            "transport": {
                "type": "stdio",
                "command": sys.executable,
                "args": [str(_fake), "--tools", "read_file"],
            }
        },
        actor="test",
    )
    prefs = MCPCapabilityPreferenceRepo(sm)
    inv = MCPInvocationRepo(sm)

    def factory(session_id: str) -> MCPGatewaySession:
        sup = SubprocessSupervisor(
            resource_service=rsvc,
            credential_resolver=CredentialResolver(KeyringAdapter()),
        )
        disc = CapabilityDiscovery(
            resource_service=rsvc,
            supervisor=sup,
            preferences=prefs,
            audit=audit,
        )
        return MCPGatewaySession(
            session_id=session_id,
            resource_service=rsvc,
            supervisor=sup,
            discovery=disc,
            preferences=prefs,
            invocations=inv,
        )

    _set_token("t")
    set_mcp_session_factory(factory)

    app2 = FastAPI()
    err_handlers.register(app2)
    app2.include_router(mcp_router)

    transport = ASGITransport(app=app2)
    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"X-Coffer-Token": "t"},
        ) as client:
            # Initialize
            init = await client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
            )
            session_id = init.headers["mcp-session-id"]

            # List tools (populates prefs)
            await client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                headers={"Mcp-Session-Id": session_id},
            )

            # Disable read_file via prefs
            resource = await rsvc.get(ResourceRef("mcp_server", "fs"))
            await prefs.set_enabled(resource.id, "tool", "read_file", False)

            # Try calling the disabled tool
            r = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "fs__read_file", "arguments": {}},
                },
                headers={"Mcp-Session-Id": session_id},
            )

        # JSON-RPC over HTTP: status is 200, error is in the JSON body
        assert r.status_code == 200
        body = r.json()
        assert "error" in body, f"Expected JSON-RPC error envelope, got: {body}"
        # TOOL_DISABLED maps to JSON-RPC code -32000
        assert body["error"]["code"] == -32000, f"Expected -32000 for TOOL_DISABLED, got: {body}"
    finally:
        await shutdown_all_sessions()
        await engine.dispose()
        _set_token(None)
        _ACTIVE_SESSIONS.clear()
        _NOTIFICATION_QUEUES.clear()
        _LAST_ACTIVITY.clear()


def test_upstream_timeout_returns_504_envelope(tmp_path, monkeypatch):
    """A route that raises UpstreamTimeout must return 504 with UPSTREAM_TIMEOUT envelope."""
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from starlette.testclient import TestClient

    from coffer.domain.errors import UpstreamTimeout
    from coffer.surfaces.http import errors as err_handlers

    # Build a minimal app that raises UpstreamTimeout
    err_app = FastAPI()
    err_handlers.register(err_app)

    @err_app.get("/test-timeout")
    async def _raise_timeout() -> JSONResponse:
        raise UpstreamTimeout("upstream timed out")

    with TestClient(err_app, raise_server_exceptions=False) as c:
        r = c.get("/test-timeout")
        assert r.status_code == 504
        _assert_envelope(r.json(), "UPSTREAM_TIMEOUT")


def _err_app():
    """Minimal app with only the error handlers registered."""
    from fastapi import FastAPI

    from coffer.surfaces.http import errors as err_handlers

    app = FastAPI()
    err_handlers.register(app)
    return app


@pytest.mark.parametrize(
    ("exc_factory", "expected_status", "expected_code"),
    [
        (lambda e: e.ResourceNotFound("mcp_server", "missing"), 404, "RESOURCE_NOT_FOUND"),
        (lambda e: e.ResourceAlreadyExists("mcp_server", "dup"), 409, "RESOURCE_ALREADY_EXISTS"),
        (lambda e: e.UnknownKind("widget"), 400, "UNKNOWN_KIND"),
        (lambda e: e.ConfigValidationError("bad config"), 422, "CONFIG_INVALID"),
        (lambda e: e.CredentialMissing("kc://ref"), 400, "CREDENTIAL_MISSING"),
        (lambda e: e.CredentialLocked("locked"), 503, "CREDENTIAL_LOCKED"),
        (lambda e: e.UpstreamUnavailable("down"), 503, "UPSTREAM_UNAVAILABLE"),
        (lambda e: e.UpstreamTimeout("slow"), 504, "UPSTREAM_TIMEOUT"),
        (lambda e: e.ToolDisabled("off"), 403, "TOOL_DISABLED"),
        (lambda e: e.InvalidPrefix("bad__prefix"), 400, "INVALID_PREFIX"),
    ],
    ids=[
        "ResourceNotFound",
        "ResourceAlreadyExists",
        "UnknownKind",
        "ConfigValidationError",
        "CredentialMissing",
        "CredentialLocked",
        "UpstreamUnavailable",
        "UpstreamTimeout",
        "ToolDisabled",
        "InvalidPrefix",
    ],
)
def test_each_coffer_error_maps_to_status_and_code(exc_factory, expected_status, expected_code):
    """Every CofferError subclass maps to its declared HTTP status + envelope code."""
    from starlette.testclient import TestClient

    from coffer.domain import errors as domain_errors

    app = _err_app()
    exc = exc_factory(domain_errors)

    @app.get("/boom")
    async def _boom():
        raise exc

    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/boom")
    assert r.status_code == expected_status, r.text
    _assert_envelope(r.json(), expected_code)
    # The trace header is always present so a client error ties to a server log.
    assert "X-Coffer-Trace" in r.headers
    # The message echoes the domain exception's str(), not a generic placeholder.
    assert r.json()["error"]["message"] == str(exc)


def test_base_coffer_error_falls_back_to_500():
    """A CofferError with an unmapped .code defaults to 500 (the _STATUS.get default)."""
    from starlette.testclient import TestClient

    from coffer.domain import errors as domain_errors

    app = _err_app()

    @app.get("/raw")
    async def _raw():
        # Base CofferError carries code=INTERNAL_ERROR which maps to 500.
        raise domain_errors.CofferError("something internal broke")

    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/raw")
    assert r.status_code == 500
    _assert_envelope(r.json(), "INTERNAL_ERROR")


def test_pydantic_validation_error_is_sanitised(caplog):
    """A raised pydantic ValidationError returns a generic 422 and never echoes
    the submitted per-field input (which may carry PII/credentials)."""
    import logging

    from pydantic import BaseModel, ValidationError
    from starlette.testclient import TestClient

    app = _err_app()

    class _Model(BaseModel):
        secret: int

    @app.get("/validate")
    async def _validate():
        try:
            _Model(secret="not-a-number-this-is-a-secret-token")  # type: ignore[arg-type]
        except ValidationError as ve:
            raise ve

    # Other tests call configure_logging() which can disable this stdlib logger
    # via structlog; re-enable so the "logs server-side" behavior is observable
    # regardless of test ordering.
    logging.getLogger("coffer.surfaces.http.errors").disabled = False
    with (
        caplog.at_level(logging.WARNING, logger="coffer.surfaces.http.errors"),
        TestClient(app, raise_server_exceptions=False) as c,
    ):
        r = c.get("/validate")

    assert r.status_code == 422
    body = r.json()
    _assert_envelope(body, "CONFIG_INVALID")
    assert body["error"]["message"] == "request validation failed"
    # The submitted secret value must not leak in the response body.
    assert "secret-token" not in r.text
    assert "X-Coffer-Trace" in r.headers
    # The structured error IS logged server-side for the operator.
    assert any("http.validation_error" in rec.getMessage() for rec in caplog.records)


def test_unhandled_exception_returns_500_without_leaking_detail(caplog):
    """A non-Coffer Exception maps to a generic 500 with a trace id and must
    not leak the exception's message to the client."""
    import logging

    from starlette.testclient import TestClient

    app = _err_app()

    @app.get("/explode")
    async def _explode():
        raise ValueError("DB_PASSWORD=hunter2 leaked in stack")

    # Other tests call configure_logging() which can disable this stdlib logger
    # via structlog; re-enable so the "logs server-side" behavior is observable
    # regardless of test ordering.
    logging.getLogger("coffer.surfaces.http.errors").disabled = False
    with (
        caplog.at_level(logging.ERROR, logger="coffer.surfaces.http.errors"),
        TestClient(app, raise_server_exceptions=False) as c,
    ):
        r = c.get("/explode")

    assert r.status_code == 500
    body = r.json()
    _assert_envelope(body, "INTERNAL_ERROR")
    assert body["error"]["message"] == "internal error"
    # The raised detail must never reach the client.
    assert "hunter2" not in r.text
    assert "DB_PASSWORD" not in r.text
    # The trace id is returned so the operator can correlate with the server log.
    assert "X-Coffer-Trace" in r.headers
    # The full exception IS logged server-side.
    assert any("http.unhandled_exception" in rec.getMessage() for rec in caplog.records)
