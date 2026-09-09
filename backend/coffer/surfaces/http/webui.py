"""Serve the built web UI from the daemon itself (spec 001 FR-024).

Coffer used to ship the UI inside a Tauri desktop shell. The shell is gone: the
daemon now serves ``frontend/dist`` at its own loopback origin, so the UI and
the management API share a scheme, host and port. That makes the browser treat
API calls as same-origin, and it removes the shell's standing operating cost —
there is no bundle to rebuild and reinstall, and no built artifact that can
drift away from the source it was built from.

Two layouts have to resolve:

* **Frozen build** — PyInstaller unpacks ``datas`` under ``sys._MEIPASS``; the
  build ships the UI there as ``webui/``.
* **Source install / dev** — the repo's ``frontend/dist``, produced by
  ``npm run build``. Absent until someone builds it, which is fine: the mount
  is skipped and the API still serves. Vite's dev server is the better UI in
  that situation anyway.

The mount is installed LAST so every API route is matched first; only paths no
router claimed fall through to static files.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope


def resolve_webui_dir() -> Path | None:
    """Locate the built UI, or None when this install has none.

    Honours ``COFFER_WEBUI_DIR`` first so a packager (or a test) can point the
    daemon at a build somewhere else entirely.
    """
    from os import environ

    override = environ.get("COFFER_WEBUI_DIR")
    if override:
        candidate = Path(override).expanduser()
        return candidate if (candidate / "index.html").is_file() else None

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass is not None:
        candidate = Path(meipass) / "webui"
        return candidate if (candidate / "index.html").is_file() else None

    # Source layout: backend/coffer/surfaces/http/webui.py → repo root is 5 up.
    candidate = Path(__file__).resolve().parents[4] / "frontend" / "dist"
    return candidate if (candidate / "index.html").is_file() else None


# Path roots that belong to the daemon's own surfaces. A request under one of
# these that reached the SPA mount is a genuine 404 — an API path no router
# claimed — and must be reported as one. Answering it with index.html would
# turn every client-side typo or stale endpoint into a 200 full of HTML, which
# is far harder to debug than a plain 404.
#
# Matched by whole path segment, never by bare prefix: the UI has its own
# `/mcp-servers` route, which a `startswith("mcp")` test would wrongly claim.
_RESERVED_ROOTS: frozenset[str] = frozenset(
    {"api", "mcp", "health", "docs", "redoc", "openapi.json"}
)


def _is_daemon_surface(path: str) -> bool:
    return path.split("/", 1)[0] in _RESERVED_ROOTS


class _SpaStaticFiles(StaticFiles):
    """StaticFiles that falls back to ``index.html`` for client-side routes.

    The UI is a client-side-routed SPA: a browser asked to open
    ``/mcp-servers`` requests that path from the daemon, which has no such
    file on disk. Serving ``index.html`` lets the router take over once the
    bundle boots.
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            # StaticFiles signals a miss by raising, not by returning a 404.
            if exc.status_code != 404:
                raise
            if _is_daemon_surface(path):
                raise
            return await super().get_response("index.html", scope)


def install(app: FastAPI) -> None:
    """Mount the built UI at ``/`` when this install ships one."""
    directory = resolve_webui_dir()
    if directory is None:
        return
    app.mount("/", _SpaStaticFiles(directory=str(directory), html=True), name="webui")
