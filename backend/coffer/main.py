"""ASGI entry point.

`uvicorn coffer.main:app` loads the composition root.
"""

from __future__ import annotations

from coffer.surfaces.http.app import create_app

app = create_app()
