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
from coffer.surfaces.http import openapi_document

_logger = logging.getLogger(__name__)

_STATUS: dict[str, int] = {
    "RESOURCE_NOT_FOUND": 404,
    # The vault's write path (ADR every-vault-write-is-a-validated-commit-naming-its-writer).
    "VAULT_FILE_STALE": 409,
    "VAULT_FILE_INVALID": 422,
    "VAULT_PATH_INVALID": 400,
    "VAULT_VERSION_NOT_FOUND": 404,
    "VAULT_GIT_FAILED": 500,
    "GIT_MISSING": 500,
    # custom tools (spec mcp-gateway "Manage custom tools on REST and the command line")
    "CUSTOM_TOOL_NOT_FOUND": 404,
    "NOT_A_CUSTOM_TOOL_GROUP": 404,
    "CUSTOM_TOOL_EXISTS": 409,
    "OPENAPI_UNREADABLE": 422,
    "NOT_IMPORTED_FROM_OPENAPI": 409,
    "OPENAPI_FILE_NEEDED": 422,
    "RESOURCE_ALREADY_EXISTS": 409,
    "AGENT_CONFIG_DIR_REGISTERED": 409,
    "AGENT_TYPE_REGISTERED": 409,
    # The agent's config dir is absent on this machine — a state of the
    # machine, not a malformed request.
    "AGENT_CONFIG_DIR_MISSING": 409,
    # The database was migrated by a newer build than this one.
    "DB_SCHEMA_TOO_NEW": 409,
    "GENERIC_CREATE_NOT_ALLOWED": 409,
    # A changed name on a kind whose name is fixed (ADR
    # names-visible-to-agents-are-fixed): a conflict with what quotes the name.
    "NAME_IMMUTABLE": 409,
    # The daemon's settable port (spec daemon "Bind a fixed, settable port").
    "PORT_OUT_OF_RANGE": 422,
    "PORT_IN_USE": 409,
    "UNKNOWN_KIND": 400,
    "CONFIG_INVALID": 422,
    "SCOPE_INVALID": 422,  # per-agent activation scope (ADR per-agent-resource-scope)
    "CREDENTIAL_MISSING": 400,
    "CREDENTIAL_IN_USE": 409,
    "CREDENTIAL_LOCKED": 503,
    # Ciphertext exists but no key opens it (spec credentials "Refuse to start
    # when the master key is missing"). Same class as CREDENTIAL_LOCKED: the
    # store is unusable until the key comes back, not a bad request.
    "MASTER_KEY_MISSING": 503,
    "CREDENTIAL_UNREADABLE": 500,
    # The secret boundary (ADR only-a-present-human-sees-a-secret-or-sends-it-
    # somewhere-new): a destination nobody approved yet is a state that waits
    # for a person, not a bad request; a grant that does not verify is refused.
    "SECRET_BINDING_PENDING": 409,
    "MASTER_KEY_CONFLICT": 503,
    "APPROVAL_PENDING": 202,
    "PRESENCE_GRANT_INVALID": 403,
    "APPROVAL_NOT_FOUND": 404,
    "APPROVAL_NOT_PENDING": 409,
    "SECRET_NAME_INVALID": 422,
    "SECRET_NOT_FOUND": 404,
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
    # whose Host does not name this daemon's loopback address and port, or
    # whose Origin is not one of Coffer's own.
    "HOST_NOT_ALLOWED": 403,
    "ORIGIN_NOT_ALLOWED": 403,
    "BAD_REQUEST": 400,
    # A paging cursor that does not decode, or names another list or other
    # filters (spec resource-framework "Page growing lists by an opaque cursor").
    "CURSOR_INVALID": 400,
    "NOT_FOUND": 404,
    "FORBIDDEN": 403,
    # spec skill-manager
    "SKILL_INVALID": 422,
    "TARGET_CONFLICT": 409,
    "RESOURCE_PROTECTED": 409,
    # A kind with no enabled switch (knowledge, memory) asked to flip it.
    "RESOURCE_NOT_TOGGLEABLE": 409,
    # agent workspace (specs agent-registry/skill-manager amendment)
    "MCP_ENTRY_NOT_FOUND": 404,
    "PLUGIN_NOT_FOUND": 404,
    "UNMANAGED_SKILL_NOT_FOUND": 404,
    "CONFIG_FILE_STALE": 409,
    "SKILL_FILE_STALE": 409,
    # The commands skills require (spec skill-manager "Install a required
    # command only through Homebrew and only when asked"): every refusal runs
    # nothing.
    "CLI_NOT_REQUIRED": 404,
    "CLI_INSTALL_NOT_FOUND": 404,
    "CLI_FORMULA_MISMATCH": 422,
    "CLI_NOT_INSTALLABLE": 409,
    "HOMEBREW_NOT_FOUND": 409,
    "CLI_INSTALL_RUNNING": 409,
    # skill sources (spec skill-manager "Add skills from an archive", "Add
    # skills from a Git repository", "Update a Git-imported skill from its
    # source"): an expired stage is a missing thing; git failing to fetch is
    # the upstream refusing us (502, like the vault remote); an update over a
    # local edit is a state conflict; updating a folder-added skill is too.
    "SKILL_STAGING_NOT_FOUND": 404,
    "SKILL_SOURCE_UNREACHABLE": 502,
    "SKILL_UPDATE_CONFLICT": 409,
    "SKILL_NOT_FROM_GIT": 409,
    "MCP_ENTRY_PROTECTED": 422,
    "MCP_ENTRY_SOURCE_AMBIGUOUS": 422,
    "ADOPT_SECRET_UNRESOLVED": 422,
    "AGENT_CONFIG_PARSE_ERROR": 422,
    "PLUGIN_UNINSTALL_UNSUPPORTED": 422,
    "PLUGIN_UNINSTALL_FAILED": 422,
    "PLUGIN_TOGGLE_UNSUPPORTED": 422,
    "MCP_INSTALL_UNSUPPORTED": 422,
    "UNMANAGED_SKILL_INVALID": 422,
    # knowledge ingestion (spec knowledge). One code for "this upload is
    # refused", with ``details.reason`` naming which refusal; the size ceiling
    # gets its own code because 413 is the honest status for it.
    "INGEST_REJECTED": 400,
    # ripgrep's two failures. No surface calls it any more — the layer offers
    # no retrieval ("Expose exactly one knowledge tool") — but curation still
    # matches literally to pick its candidates ("Assemble a pass from a bounded
    # context"), so a missing binary or a bad pattern can still
    # surface through a pass.
    "ENGINE_UNAVAILABLE": 503,
    "GREP_PATTERN_INVALID": 400,
    # spec memory
    "MEMORY_NOTE_NOT_FOUND": 404,
    "MEMORY_RAW_ENTRY_NOT_FOUND": 404,
    "MEMORY_FILE_NOT_FOUND": 404,
    "MEMORY_UNSAFE_PATH": 400,
    "MEMORY_UNREADABLE": 422,
    "MEMORY_DELIVERY_UNSUPPORTED": 422,
    "MEMORY_DELIVERY_CONFIG_INVALID": 422,
    "MEMORY_TRIGGER_INVALID": 422,
    "MEMORY_TRIGGER_NOT_FOUND": 404,
    # agent turns (spec chat)
    "CONVERSATION_NOT_FOUND": 404,
    "TURN_IN_PROGRESS": 409,
    "UNKNOWN_AGENT": 400,
    "AGENT_CONFIG_REJECTED": 400,
    # web composer uploads (spec chat "Upload a file for a web message",
    # "Send uploaded files with a web message"). The ceiling is 413 and the
    # refused type 415, the honest statuses; an id in a send body that names no
    # upload is a bad body, not a missing path.
    "ATTACHMENT_TOO_LARGE": 413,
    "ATTACHMENT_TYPE_UNSUPPORTED": 415,
    "ATTACHMENT_NOT_FOUND": 422,
    # resending a message (spec chat "Show a failed turn as one inline banner
    # with Retry"): its row is a missing subresource; a file the media sweep
    # deleted since is gone for good, which is what 410 says.
    "MESSAGE_NOT_FOUND": 404,
    "ATTACHMENT_EXPIRED": 410,
    # channels (spec channels)
    "CHANNEL_NOT_PAIRED": 409,
    "CHANNEL_NOT_RUNNING": 409,
    "CHANNEL_SEND_FAILED": 502,
    # vault export/import (spec vault-sync, ADR: vault-sync)
    "SYNC_BUNDLE_TOO_NEW": 409,
    "SYNC_BUNDLE_INVALID": 422,
    "SYNC_SERIALIZATION_INVALID": 422,
    "MASTER_KEY_FILE_INVALID": 422,
    # vault backup (spec vault-sync "Allow at most one user-owned sync remote").
    # A bad remote is the caller's configuration (422); a git invocation that
    # failed is the remote or the network refusing us, which is an upstream
    # failure (502).
    "BACKUP_REMOTE_INVALID": 422,
    "GIT_MIRROR_FAILED": 502,
    # A round the user has to answer before anything else can happen. Each is
    # an ordinary state of the feature, not a fault: without an entry here they
    # fall through to 500, which tells a browser (and the CLI's exit-code
    # mapping) that Coffer broke when in fact it is waiting for an answer.
    "SYNC_NOTHING_PENDING": 409,
    "SYNC_NOTHING_TO_ROLL_BACK": 409,
    "SYNC_JOIN_AMBIGUOUS": 409,
    "SYNC_CANNOT_RETIRE_SELF": 422,
    # The thin sync round (spec vault-sync): no round waiting for this answer,
    # a hand merge that still has markers, a remote git would refuse, and a
    # remote that refused us (upstream, like GIT_MIRROR_FAILED).
    "SYNC_NOTHING_STOPPED": 409,
    "SYNC_CONFLICT_MARKERS_LEFT": 422,
    "SYNC_REMOTE_INVALID": 422,
    "SYNC_REMOTE_FAILED": 502,
    # provider switching (spec provider-switching)
    "PROVIDER_CREDENTIAL_SOURCE_INVALID": 422,
    # Not 422: the patch is well-formed, and the same patch succeeds once the
    # connection is no longer projected — a state conflict, not a bad body.
    "PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE": 409,
    # An ollama connection is internal-only and never switched on for an agent.
    "PROVIDER_INTERNAL_ONLY": 409,
    # A second internal-engine default outside the route that moves the flag.
    "PROVIDER_INTERNAL_DEFAULT_TAKEN": 409,
    "NO_ACTIVE_PROVIDER": 404,
    # knowledge (spec knowledge). A collection an agent is not authorized for
    # is NOT FOUND rather than FORBIDDEN: telling an unauthorized caller that
    # the name exists is itself a disclosure, and the layer treats "not visible
    # to you" and "not there" as the same answer.
    "KNOWLEDGE_COLLECTION_NOT_FOUND": 404,
    "KNOWLEDGE_COLLECTION_EXISTS": 409,
    "KNOWLEDGE_FILE_NOT_FOUND": 404,
    # A save from the web UI naming a fingerprint the file no longer has (spec
    # knowledge "Save a document edited in the web UI"): the file moved on
    # disk since the editor read it, and is left as it is.
    "KNOWLEDGE_FILE_CONFLICT": 409,
    # History (spec knowledge "Keep every document's history and undo a pass as
    # a whole"): no git on this machine is a state of the machine, an unknown
    # version a missing thing, an undo over a later change a conflict.
    "KNOWLEDGE_HISTORY_UNAVAILABLE": 503,
    "KNOWLEDGE_VERSION_NOT_FOUND": 404,
    "KNOWLEDGE_NOT_A_PASS": 400,
    "KNOWLEDGE_UNDO_CONFLICT": 409,
    # Also the answer for a path that cannot name a document — the
    # collection itself, its README, or anything hidden (spec knowledge "Guard
    # every path through one module").
    "KNOWLEDGE_PATH_UNSAFE": 400,
    # Ingestion (spec knowledge "Bound uploads and leave nothing behind on
    # failure"): named the limit, refused
    # before any conversion or write.
    "KNOWLEDGE_UPLOAD_TOO_LARGE": 413,
    # Curation's two refusals (spec knowledge "Refuse file-name references in
    # documents", "Bound a pass to eight writes"). Both are the
    # request being wrong rather than Coffer failing, so both are 400-class
    # like KNOWLEDGE_PATH_UNSAFE above: a topic naming another knowledge file
    # is a link that rots, and a pass past its write bound is one source trying
    # to rewrite the corpus. Neither is retryable unchanged.
    "KNOWLEDGE_TOPIC_REFERENCES_FILE": 400,
    "KNOWLEDGE_CURATION_BOUND": 400,
    "KNOWLEDGE_ERROR": 400,
    # Upkeep passes (memory organise, knowledge curation). A second pass over a
    # target one is already rewriting is refused, not queued — the surface
    # that asked should already have been showing the running one
    # (``application.upkeep_runs``).
    "UPKEEP_ALREADY_RUNNING": 409,
    # experimental features (spec experimental-features). A switched-off
    # feature's route is NOT FOUND, like a route this build never had.
    "FEATURE_UNKNOWN": 404,
    "FEATURE_PINNED": 409,
    "FEATURE_DISABLED": 404,
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

    It carried one exception once: ``IngestRejected``'s status depended on WHY
    an upload was refused. Uploads are still live (``POST
    /api/v1/knowledge/upload``), but a refusal now says why in
    ``details.reason`` while the status stays 400, so the per-reason branch is
    gone and this is the same lookup ``error_response`` does.
    """
    return _STATUS.get(exc.code, 500)


def _details_for(exc: errors.CofferError) -> dict[str, Any]:
    """Surface the machine-readable `reason`/`feature` of an error, if any."""
    out: dict[str, Any] = {}
    reason = getattr(exc, "reason", None)
    if reason:
        out["reason"] = reason
    # The feature errors name their key, so a client (the CLI's one-line
    # "switch it on" message, the web notice) need not parse the message.
    feature = getattr(exc, "feature", None)
    if feature:
        out["feature"] = feature
    # The secret boundary names the approvals a refusal waits on, so the CLI
    # can wait for them and the UI can point at them.
    approval_ids = getattr(exc, "approval_ids", None)
    if approval_ids:
        out["approval_ids"] = list(approval_ids)
    # An error that carries its own machine-readable context (a stale save's
    # disk version, the document an undo would overwrite) hands it over whole.
    extra = getattr(exc, "error_details", None)
    if isinstance(extra, dict):
        out.update(extra)
    return out


def register(app: FastAPI) -> None:
    """Answer every failure with the envelope, and say so in the OpenAPI document."""
    openapi_document.install(app)

    @app.exception_handler(errors.CofferError)
    async def _handle_coffer(request: Request, exc: errors.CofferError) -> JSONResponse:
        body = _envelope(exc.code, str(exc), _details_for(exc))
        resp = JSONResponse(status_code=_status_for(exc), content=body)
        resp.headers["X-Coffer-Trace"] = get_trace_id()
        return resp

    @app.exception_handler(ValidationError)
    async def _handle_pydantic(request: Request, exc: ValidationError) -> JSONResponse:
        # Don't echo exc.errors() to the client — per-field `input`
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
        # Log the full exception server-side; the trace id ties the
        # 500 response back to this stack on the operator's side.
        _logger.exception(
            "http.unhandled_exception",
            extra={"path": str(request.url.path), "trace_id": get_trace_id()},
        )
        body = _envelope("INTERNAL_ERROR", "internal error")
        resp = JSONResponse(status_code=500, content=body)
        resp.headers["X-Coffer-Trace"] = get_trace_id()
        return resp
