"""CORS allowlist for browser-origin requests.

The daemon serves the web UI at its own origin now (spec mcp-gateway FR-024), so the
production path is **same-origin** and needs no CORS at all — the browser does
not preflight a request to the page's own origin. That makes the empty
allowlist the correct default, and a narrower one than the desktop shell's
``tauri://localhost``.

What remains is development, where Vite serves the UI on :5173 while the API
stays on the daemon's port:

- ``COFFER_DEV_CORS=1`` allows ``http://localhost:5173`` and
  ``http://127.0.0.1:5173``.
- ``COFFER_CORS_ORIGINS`` (comma-separated) overrides the list entirely.

``allow_credentials`` stays False — cookies are never used; auth is the
``X-Coffer-Token`` header alone.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

_DEV_ORIGINS: tuple[str, ...] = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def _resolve_origins() -> list[str]:
    explicit = os.environ.get("COFFER_CORS_ORIGINS")
    if explicit:
        return [o.strip() for o in explicit.split(",") if o.strip()]
    if os.environ.get("COFFER_DEV_CORS") == "1":
        return list(_DEV_ORIGINS)
    return []


# Back-compat export for any code/test importing the constant directly.
ALLOWED_ORIGINS: tuple[str, ...] = _DEV_ORIGINS


def install(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_resolve_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["X-Coffer-Token", "X-Coffer-Actor", "Content-Type", "Accept"],
        expose_headers=["X-Coffer-Trace"],
        max_age=600,
    )
