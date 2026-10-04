"""``GET /api/v1/openapi.json`` — the management API's schema, behind the token.

FastAPI's own schema route, and the ``/docs`` and ``/redoc`` pages built on it,
answer without the token; ``create_app`` switches all three off and mounts this
one instead, so the only unauthenticated API route stays
``GET /api/v1/daemon/status`` (spec daemon "Require a token on every
management call"). Nothing reads the schema over HTTP to work — the contracts and the
frontend's types are generated from ``create_app().openapi()`` in process — so
a caller that wants it is a developer holding the token.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse

from coffer.surfaces.http.auth import require_token

OPENAPI_PATH = "/api/v1/openapi.json"


def include_openapi_route(app: FastAPI) -> None:
    """Serve ``app``'s OpenAPI schema at :data:`OPENAPI_PATH` to a token holder."""

    @app.get(
        OPENAPI_PATH,
        include_in_schema=False,
        response_class=JSONResponse,
        dependencies=[Depends(require_token)],
    )
    async def openapi_schema() -> JSONResponse:
        return JSONResponse(app.openapi())


__all__ = ["OPENAPI_PATH", "include_openapi_route"]
