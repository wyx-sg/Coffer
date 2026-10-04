"""The shim's stdout: the MCP wire back to the client.

Stdout IS the wire, so every line written here must be one complete JSON-RPC
message — a stray non-JSON line crashes the client on its next read. Each
write is a whole line plus a flush with no ``await`` in between, which is what
lets concurrent request tasks share stdout without interleaving.
"""

from __future__ import annotations

import json as _json
import logging
import sys
from typing import Any

import httpx

_logger = logging.getLogger("coffer.shim")


def forward_response(
    envelope: dict[str, Any],
    response: httpx.Response,
) -> None:
    req_id = envelope.get("id")
    raw_body = (response.text or "").strip()
    if response.status_code >= 400:
        _logger.warning(
            "shim.gateway_error_status",
            extra={"status": response.status_code, "body_head": raw_body[:200]},
        )
        emit_error(
            req_id,
            code=-32603,
            message=f"coffer gateway HTTP {response.status_code}: {_error_text(raw_body)}",
        )
        return
    if not raw_body:
        # 2xx with empty body is allowed by /mcp for matched-response acks;
        # nothing to forward.
        return
    try:
        _json.loads(raw_body)
    except _json.JSONDecodeError as e:
        _logger.warning(
            "shim.non_json_2xx",
            extra={"error": str(e), "body_head": raw_body[:200]},
        )
        emit_error(
            req_id,
            code=-32603,
            message=f"coffer gateway returned non-JSON 2xx: {raw_body[:200]}",
        )
        return
    sys.stdout.write(raw_body + "\n")
    sys.stdout.flush()


def _error_text(raw_body: str) -> str:
    """What the agent is told about a refused call: the daemon's own message
    and, when the refusal carries one, its hand-off prompt in full — a daemon
    waiting for git says why and how to fix it (spec daemon "Wait in a setup
    state when git is missing or too old"). Anything else, the body's head."""
    try:
        error = _json.loads(raw_body).get("error") or {}
        message = str(error["message"])
    except (ValueError, AttributeError, KeyError, TypeError):
        return raw_body[:200] or "(empty body)"
    handoff = (error.get("details") or {}).get("handoff") or {}
    prompt = handoff.get("prompt") if isinstance(handoff, dict) else None
    return f"{message}\n\n{prompt}" if prompt else message


def emit_error(req_id: Any, code: int, message: str) -> None:
    err = {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": code, "message": message},
    }
    sys.stdout.write(_json.dumps(err) + "\n")
    sys.stdout.flush()
