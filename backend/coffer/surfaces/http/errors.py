"""FastAPI exception handlers — map domain errors to the HTTP error envelope.

Response shape: {error: {code, message, details}}.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from coffer.domain import errors
from coffer.infrastructure.logging.setup import get_trace_id

_logger = logging.getLogger(__name__)

_STATUS: dict[str, int] = {
    "RESOURCE_NOT_FOUND": 404,
    "RESOURCE_ALREADY_EXISTS": 409,
    "UNKNOWN_KIND": 400,
    "CONFIG_INVALID": 422,
    "CREDENTIAL_MISSING": 400,
    "CREDENTIAL_LOCKED": 503,
    "UPSTREAM_UNAVAILABLE": 503,
    "UPSTREAM_TIMEOUT": 504,
    "TOOL_DISABLED": 403,
    "INVALID_PREFIX": 400,
    "SKILL_DIR_NOT_WRITABLE": 422,
    "PRIVILEGED_PATH": 422,
    "INTERNAL_ERROR": 500,
    "UNKNOWN_PRUNABLE_TABLE": 404,
    "UNAUTHENTICATED": 401,
    "DAEMON_NOT_READY": 503,
    "BAD_REQUEST": 400,
    "NOT_FOUND": 404,
    "FORBIDDEN": 403,
    # spec 005-skill-manager
    "SKILL_INVALID": 422,
    "SOURCE_FETCH_FAILED": 502,
    "SSRF_BLOCKED": 422,
    "TARGET_CONFLICT": 409,
    "SKILL_NAME_MISMATCH": 409,
    "UPDATE_NOT_SUPPORTED": 400,
    # knowledge_base kind (spec 006)
    "KB_NOT_FOUND": 404,
    "DOCUMENT_NOT_FOUND": 404,
    "INGEST_REJECTED": 400,  # `_status_for` refines this by reason
    "ENGINE_UNAVAILABLE": 503,
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


def _status_for(exc: errors.CofferError) -> int:
    """HTTP status for a domain error.

    Most codes map 1:1 via `_STATUS`. `IngestRejected` is the exception: its
    status depends on the rejection `reason` (a too-large upload is 413, a
    duplicate is 409, everything else is a plain 400).
    """
    if isinstance(exc, errors.IngestRejected):
        return {"too_large": 413, "duplicate": 409}.get(exc.reason, 400)
    return _STATUS.get(exc.code, 500)


def _details_for(exc: errors.CofferError) -> dict[str, Any]:
    """Surface the machine-readable `reason` of a rejection error, if any."""
    reason = getattr(exc, "reason", None)
    return {"reason": reason} if reason else {}


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
