"""FastAPI exception handlers — map domain errors to the HTTP error envelope.

Response shape: {error: {code, message, details}}.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from coffer.domain import errors
from coffer.infrastructure.logging.setup import get_trace_id

_logger = logging.getLogger(__name__)

_STATUS: dict[str, int] = {
    "RESOURCE_NOT_FOUND": 404,
    "RESOURCE_ALREADY_EXISTS": 409,
    "AGENT_CONFIG_DIR_REGISTERED": 409,
    "GENERIC_CREATE_NOT_ALLOWED": 409,
    "UNKNOWN_KIND": 400,
    "CONFIG_INVALID": 422,
    "SCOPE_INVALID": 422,  # machine x agent activation scope (ADR per-agent-resource-scope)
    "CREDENTIAL_MISSING": 400,
    "CREDENTIAL_IN_USE": 409,
    "CREDENTIAL_LOCKED": 503,
    "CREDENTIAL_UNREADABLE": 500,
    "UPSTREAM_UNAVAILABLE": 503,
    "UPSTREAM_TIMEOUT": 504,
    "TOOL_DISABLED": 403,
    "INVALID_PREFIX": 400,
    "SKILL_DIR_NOT_WRITABLE": 422,
    "PRIVILEGED_PATH": 422,
    "CONFIG_FILE_NOT_ALLOWED": 404,
    "CONFIG_FILE_FORMAT_INVALID": 422,
    "SHIM_NOT_FOUND": 422,
    "FS_PATH_NOT_BROWSABLE": 400,
    "FS_PATH_NOT_OPENABLE": 400,
    "INTERNAL_ERROR": 500,
    "UNKNOWN_PRUNABLE_TABLE": 404,
    "UNAUTHENTICATED": 401,
    "DAEMON_NOT_READY": 503,
    # Emitted by the host_guard middleware, not by a CofferError: a request
    # whose Host header does not name this daemon's loopback authority.
    "HOST_NOT_LOOPBACK": 421,
    "BAD_REQUEST": 400,
    "NOT_FOUND": 404,
    "FORBIDDEN": 403,
    # spec skill-manager
    "SKILL_INVALID": 422,
    "TARGET_CONFLICT": 409,
    # agent workspace (specs agent-registry/skill-manager amendment)
    "MCP_ENTRY_NOT_FOUND": 404,
    "PLUGIN_NOT_FOUND": 404,
    "UNMANAGED_SKILL_NOT_FOUND": 404,
    "CONFIG_FILE_STALE": 409,
    "SKILL_FILE_STALE": 409,
    "MCP_ENTRY_PROTECTED": 422,
    "MCP_ENTRY_SOURCE_AMBIGUOUS": 422,
    "ADOPT_SECRET_UNRESOLVED": 422,
    "AGENT_CONFIG_PARSE_ERROR": 422,
    "MCP_INSTALL_UNSUPPORTED": 422,
    "UNMANAGED_SKILL_INVALID": 422,
    "SKILL_OUT_OF_SCOPE": 422,  # activation scope (ADR per-agent-resource-scope)
    # knowledge_base kind (spec knowledge)
    "KB_NOT_FOUND": 404,
    "DOCUMENT_NOT_FOUND": 404,
    "INGEST_REJECTED": 400,  # `_status_for` refines this by reason
    "ENGINE_UNAVAILABLE": 503,
    "RECONVERSION_BLOCKED": 409,
    "GREP_PATTERN_INVALID": 400,
    # memory kind (spec knowledge)
    "MEMORY_STORE_NOT_FOUND": 404,
    "MEMORY_STORE_MERGE_INVALID": 400,
    "MEMORY_NOT_FOUND": 404,
    "MEMORY_REJECTED": 422,  # empty / too-long fact rejected at the boundary
    "SCOPE_UNRESOLVED": 400,
    "EMBEDDING_UNAVAILABLE": 503,
    # agent turns (spec channels)
    "CONVERSATION_NOT_FOUND": 404,
    "TURN_IN_PROGRESS": 409,
    "UNKNOWN_AGENT": 400,
    "AGENT_CONFIG_REJECTED": 400,
    # channels (spec channels)
    "CHANNEL_NOT_PAIRED": 409,
    "CHANNEL_NOT_RUNNING": 409,
    "CHANNEL_SEND_FAILED": 502,
    # vault export/import (spec vault-export-import, ADR: vault-export-import)
    "SYNC_BUNDLE_TOO_NEW": 409,
    "SYNC_BUNDLE_INVALID": 422,
    "SYNC_SERIALIZATION_INVALID": 422,
    "MASTER_KEY_FILE_INVALID": 422,
    # vault backup (spec vault-export-import ## Backup). A bad remote is the
    # caller's configuration (422); a git invocation that failed is the remote
    # or the network refusing us, which is an upstream failure (502).
    "BACKUP_REMOTE_INVALID": 422,
    "GIT_MIRROR_FAILED": 502,
    # provider switching (spec provider-switching)
    "PROVIDER_CREDENTIAL_SOURCE_INVALID": 422,
    "NO_ACTIVE_PROVIDER": 404,
    # knowledge (spec knowledge). A collection an agent is not authorized for
    # is NOT FOUND rather than FORBIDDEN: telling an unauthorized caller that
    # the name exists is itself a disclosure, and the layer treats "not visible
    # to you" and "not there" as the same answer.
    "KNOWLEDGE_COLLECTION_NOT_FOUND": 404,
    "KNOWLEDGE_COLLECTION_EXISTS": 409,
    "KNOWLEDGE_FILE_NOT_FOUND": 404,
    "KNOWLEDGE_PATH_UNSAFE": 400,
    "KNOWLEDGE_ERROR": 400,
}

# Map raw HTTP status codes back to envelope codes when a surface raises a
# bare HTTPException. This keeps the response shape consistent so frontend
# translateApiError can match on a stable `code` rather than free-text detail.
_HTTP_CODE: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    503: "DAEMON_NOT_READY",
}


def _envelope(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def error_response(code: str, message: str, details: dict[str, Any] | None = None) -> JSONResponse:
    """Build the standard error-envelope response for a domain error code.

    Route handlers that need to attach ``details`` (the global ``CofferError``
    handler carries none) return this directly so the envelope shape, status
    mapping, and ``X-Coffer-Trace`` header stay identical to the handler's.
    """
    resp = JSONResponse(
        status_code=_STATUS.get(code, 500), content=_envelope(code, message, details)
    )
    resp.headers["X-Coffer-Trace"] = get_trace_id()
    return resp


def _status_for(exc: errors.CofferError) -> int:
    """HTTP status for a domain error — every code maps 1:1 via `_STATUS`.

    The one exception this function used to carry was ``IngestRejected``, whose
    status depended on why an upload was refused. Nothing uploads any more, so
    the special case went with it.
    """
    return _STATUS.get(exc.code, 500)


def _details_for(exc: errors.CofferError) -> dict[str, Any]:
    """Surface the machine-readable `reason`/`hint` of an error, if any."""
    out: dict[str, Any] = {}
    reason = getattr(exc, "reason", None)
    if reason:
        out["reason"] = reason
    # SyncRemoteUnreachable carries a hint code (auth/not_found/network) the
    # UI translates into configuration guidance.
    hint = getattr(exc, "hint", None)
    if hint:
        out["hint"] = hint
    return out


def register(app: FastAPI) -> None:
    @app.exception_handler(errors.CofferError)
    async def _handle_coffer(request: Request, exc: errors.CofferError) -> JSONResponse:
        body = _envelope(exc.code, str(exc), _details_for(exc))
        resp = JSONResponse(status_code=_status_for(exc), content=body)
        resp.headers["X-Coffer-Trace"] = get_trace_id()
        return resp

    @app.exception_handler(ValidationError)
    async def _handle_pydantic(request: Request, exc: ValidationError) -> JSONResponse:
        # CODE-023: don't echo exc.errors() to the client — per-field `input`
        # values can include PII or credentials the client just submitted.
        # Log the structured error server-side and return a generic envelope.
        _logger.warning(
            "http.validation_error",
            extra={"path": str(request.url.path), "errors": exc.errors()},
        )
        body = _envelope("CONFIG_INVALID", "request validation failed")
        resp = JSONResponse(status_code=422, content=body)
        resp.headers["X-Coffer-Trace"] = get_trace_id()
        return resp

    @app.exception_handler(RequestValidationError)
    async def _handle_request_validation(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # FastAPI body/query validation raises RequestValidationError (NOT
        # pydantic.ValidationError), which would otherwise bypass the envelope
        # with a raw ``{"detail": [...]}``. Same redaction rationale as above.
        _logger.warning(
            "http.request_validation_error",
            extra={"path": str(request.url.path), "errors": exc.errors()},
        )
        body = _envelope("CONFIG_INVALID", "request validation failed")
        resp = JSONResponse(status_code=422, content=body)
        resp.headers["X-Coffer-Trace"] = get_trace_id()
        return resp

    async def _handle_http(request: Request, exc: Exception) -> JSONResponse:
        # Typed wide to satisfy Starlette's exception-handler signature
        # (Exception, not HTTPException). Narrowed back here.
        assert isinstance(exc, StarletteHTTPException)
        code = _HTTP_CODE.get(exc.status_code, f"HTTP_{exc.status_code}")
        message = exc.detail if isinstance(exc.detail, str) else "request failed"
        details: dict[str, Any] = exc.detail if isinstance(exc.detail, dict) else {}
        body = _envelope(code, message, details)
        resp = JSONResponse(status_code=exc.status_code, content=body)
        resp.headers["X-Coffer-Trace"] = get_trace_id()
        return resp

    app.add_exception_handler(StarletteHTTPException, _handle_http)
    app.add_exception_handler(FastAPIHTTPException, _handle_http)

    @app.exception_handler(Exception)
    async def _handle_unknown(request: Request, exc: Exception) -> JSONResponse:
        # CODE-026: log the full exception server-side; the trace id ties the
        # 500 response back to this stack on the operator's side.
        _logger.exception(
            "http.unhandled_exception",
            extra={"path": str(request.url.path), "trace_id": get_trace_id()},
        )
        body = _envelope("INTERNAL_ERROR", "internal error")
        resp = JSONResponse(status_code=500, content=body)
        resp.headers["X-Coffer-Trace"] = get_trace_id()
        return resp
