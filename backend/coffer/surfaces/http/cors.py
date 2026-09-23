"""CORS allowlist for browser-origin requests.

The same built UI has two hosts, and only one of them needs CORS at all.

**Daemon-served, in a browser** (spec daemon "Serve the built web UI from the
daemon's own origin"): the page comes from
the daemon's own origin, so every call is same-origin and a browser does not
preflight it. Nothing has to be allowed for this path.

**The desktop shell**: it loads the UI as a bundled asset, so the page's origin
is the WebView's own — ``tauri://localhost`` on macOS — while its API calls go
to ``http://127.0.0.1:<port>``. That is cross-origin, its CSP allows exactly it
(``connect-src … http://127.0.0.1:*``), and every call carries
``X-Coffer-Token``, which is not a CORS-safelisted header and so needs a
preflight. The shell's origin is therefore allowed here by default.

Two structural reasons it is allowed in the daemon rather than handed to it:
the shell **detect-or-spawns**, so it routinely attaches to a daemon it did not
start (one left by the CLI, or by a previous app run) and could not have passed
an environment variable to; and the shell carries no HTTP-proxy plugin, so the
WebView really does make these requests itself.

Allowing that origin widens nothing, because CORS is not this daemon's security
boundary — the token is. The daemon binds loopback only, ``allow_credentials``
is False so no cookie is ever attached, and a request without a valid
``X-Coffer-Token`` is refused whatever origin it claims. ``tauri://localhost``
is the origin of *every* Tauri app, so another one on this machine could send a
cross-origin request; it would still need the token (``test_auth.py``), and any
process running as this user can already read that token out of
``~/.coffer/daemon.json``. The allowlist neither grants nor withholds anything
a local process does not already have.

One thing this cannot settle from here: whether the macOS WebView enforces CORS
for a custom-scheme page at all. If it does not, the entry is harmless and
unused; if it does, it is what makes the app work. It was added on that
reasoning rather than on a measurement, because only running the built ``.app``
can measure it.

Development adds the Vite origin, where the UI is on :5173 while the API stays
on the daemon's port:

- ``COFFER_DEV_CORS=1`` adds ``http://localhost:5173`` and
  ``http://127.0.0.1:5173``.
- ``COFFER_CORS_ORIGINS`` (comma-separated) replaces the list entirely, shell
  origin included — the escape hatch for a host this file does not know.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

#: The desktop shell's own page origin. macOS serves the bundled asset from
#: ``tauri://localhost``; Tauri uses ``http://tauri.localhost`` on Windows and
#: Linux, kept here so a future non-macOS build needs no change.
SHELL_ORIGINS: tuple[str, ...] = (
    "tauri://localhost",
    "http://tauri.localhost",
)

_DEV_ORIGINS: tuple[str, ...] = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def _resolve_origins() -> list[str]:
    explicit = os.environ.get("COFFER_CORS_ORIGINS")
    if explicit:
        return [o.strip() for o in explicit.split(",") if o.strip()]
    origins = list(SHELL_ORIGINS)
    if os.environ.get("COFFER_DEV_CORS") == "1":
        origins.extend(_DEV_ORIGINS)
    return origins


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
