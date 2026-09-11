"""Serve the built web UI from the daemon itself (spec mcp-gateway FR-024).

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

**The served ``index.html`` carries the daemon's live API token.** Serving the
page is itself a channel to the browser, and it is the only one that survives a
daemon restart: the token is minted fresh on every start, so anything the page
persisted from a previous daemon is dead. Injecting it into the document the
daemon is already sending means a bookmark, a typed URL, or a plain reload is
authenticated with no user action and nothing stored. What makes that safe is
:mod:`coffer.surfaces.http.host_guard` — without the ``Host`` check a
DNS-rebound page could simply fetch ``/`` and read the token out of it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.responses import HTMLResponse, Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from coffer.surfaces.http.auth import get_active_token


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


# The paths StaticFiles resolves to the SPA document itself. "." is what
# ``get_path`` produces for a bare "/" request.
_INDEX_PATHS: frozenset[str] = frozenset({"", ".", "index.html"})

_TOKEN_SCRIPT = "<script>window.__COFFER_TOKEN__={value};</script>"


def _token_script() -> str:
    """The injected global, or "" before the daemon has published a token.

    The value comes from :func:`coffer.surfaces.http.auth.get_active_token` —
    the same module-level token :func:`~coffer.surfaces.http.auth.require_token`
    compares against, read per request rather than captured at mount time. A
    rotation through ``/daemon/rotate-token`` republishes that one variable, so
    the injected value and the accepted value cannot drift apart.
    """
    token = get_active_token()
    if token is None:
        return ""
    # json.dumps gives a correctly quoted+escaped JS string literal. It does not
    # escape "/", so a "</script>" inside the value would still close the
    # element early; neutralise it, even though a urlsafe token can never hold
    # one, because the cost of being wrong here is the whole vault.
    value = json.dumps(token).replace("</", "<\\/")
    return _TOKEN_SCRIPT.format(value=value)


def _with_token(html: str) -> str:
    """Put the token script first inside ``<head>`` so it runs before the bundle."""
    script = _token_script()
    if not script:
        return html
    lowered = html.lower()
    head = lowered.find("<head")
    if head >= 0:
        close = html.find(">", head)
        if close >= 0:
            return html[: close + 1] + script + html[close + 1 :]
    return script + html


class _SpaStaticFiles(StaticFiles):
    """StaticFiles that falls back to ``index.html`` for client-side routes.

    The UI is a client-side-routed SPA: a browser asked to open
    ``/mcp-servers`` requests that path from the daemon, which has no such
    file on disk. Serving ``index.html`` lets the router take over once the
    bundle boots.

    Every route that ends at ``index.html`` — the bare ``/`` and every deep
    link alike — goes through :meth:`_index_response`, because the token the
    document carries is what authenticates the page. A fix that covered only
    ``/`` would leave a browser reopened on ``/agents`` exactly as stranded as
    before.
    """

    def __init__(self, *, directory: str, html: bool = False) -> None:
        super().__init__(directory=directory, html=html)
        #: Kept as our own attribute: StaticFiles types ``directory`` as optional.
        self._index_path = Path(directory) / "index.html"

    def _index_response(self) -> Response:
        html_text = self._index_path.read_text(encoding="utf-8")
        # `no-store`, and no ETag or Last-Modified to revalidate against. The
        # document now holds a per-daemon secret, so a cached copy would hand a
        # restarted daemon's browser the previous daemon's dead token — which is
        # the precise failure this injection exists to end. Hashed files under
        # /assets are untouched by this and keep StaticFiles' normal caching.
        return HTMLResponse(_with_token(html_text), headers={"Cache-Control": "no-store"})

    async def get_response(self, path: str, scope: Scope) -> Response:
        if path in _INDEX_PATHS:
            return self._index_response()
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            # StaticFiles signals a miss by raising, not by returning a 404.
            if exc.status_code != 404:
                raise
            if _is_daemon_surface(path):
                raise
            return self._index_response()


def install(app: FastAPI) -> None:
    """Mount the built UI at ``/`` when this install ships one."""
    directory = resolve_webui_dir()
    if directory is None:
        return
    app.mount("/", _SpaStaticFiles(directory=str(directory), html=True), name="webui")
