"""X-Coffer-Token header authentication for the management API."""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status

_ACTIVE_TOKEN: str | None = None


def set_active_token(token: str | None) -> None:
    """Called at daemon startup (and on rotation) to publish the active token."""
    global _ACTIVE_TOKEN
    _ACTIVE_TOKEN = token


def require_token(x_coffer_token: str | None = Header(default=None)) -> None:
    """FastAPI dependency — raises 401 on bad/missing token, 503 if unset."""
    if _ACTIVE_TOKEN is None:
        raise HTTPException(status_code=503, detail="daemon not ready")
    if x_coffer_token is None or not hmac.compare_digest(x_coffer_token, _ACTIVE_TOKEN):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="bad token")
