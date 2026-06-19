"""CORS allowlist for browser-origin requests (Tauri + Vite dev).

Origins:
- Production builds only allow ``tauri://localhost`` and ``http://tauri.localhost``.
- Set ``COFFER_DEV_CORS=1`` to additionally allow ``http://localhost:5173``
  and ``http://127.0.0.1:5173`` for the Vite dev server.
- Or override the entire list with ``COFFER_CORS_ORIGINS`` (comma-separated).

``allow_credentials`` stays False — cookies are never used; auth is the
``X-Coffer-Token`` header alone.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Production-safe defaults: the Tauri shim runs the UI under a dedicated
# scheme, and we never need to accept random localhost ports.
_PROD_ORIGINS: tuple[str, ...] = (
    "tauri://localhost",
    "http://tauri.localhost",
)

_DEV_EXTRA_ORIGINS: tuple[str, ...] = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def _resolve_origins() -> list[str]:
    explicit = os.environ.get("COFFER_CORS_ORIGINS")
    if explicit:
        return [o.strip() for o in explicit.split(",") if o.strip()]
    if os.environ.get("COFFER_DEV_CORS") == "1":
        return list(_PROD_ORIGINS + _DEV_EXTRA_ORIGINS)
    return list(_PROD_ORIGINS)


# Back-compat export for any code/test that imports the constant directly.
ALLOWED_ORIGINS: tuple[str, ...] = _PROD_ORIGINS + _DEV_EXTRA_ORIGINS


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
