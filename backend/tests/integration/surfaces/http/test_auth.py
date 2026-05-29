import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.surfaces.http.auth import require_token, set_active_token


@pytest.mark.asyncio
async def test_missing_token_returns_401():
    set_active_token("secret")
    app = FastAPI()

    @app.get("/foo")
    async def foo(_: None = Depends(require_token)) -> dict[str, str]:
        return {"ok": "yes"}

    async with AsyncClient(transport=ASGITransport(app), base_url="http://t") as c:
        r = await c.get("/foo")
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_wrong_token_returns_401():
    set_active_token("secret")
    app = FastAPI()

    @app.get("/foo")
    async def foo(_: None = Depends(require_token)) -> dict[str, str]:
        return {"ok": "yes"}

    async with AsyncClient(transport=ASGITransport(app), base_url="http://t") as c:
        r = await c.get("/foo", headers={"X-Coffer-Token": "wrong"})
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_correct_token_passes():
    set_active_token("secret")
    app = FastAPI()

    @app.get("/foo")
    async def foo(_: None = Depends(require_token)) -> dict[str, str]:
        return {"ok": "yes"}

    async with AsyncClient(transport=ASGITransport(app), base_url="http://t") as c:
        r = await c.get("/foo", headers={"X-Coffer-Token": "secret"})
        assert r.status_code == 200
        assert r.json() == {"ok": "yes"}


@pytest.mark.asyncio
async def test_token_unset_returns_503():
    set_active_token(None)
    app = FastAPI()

    @app.get("/foo")
    async def foo(_: None = Depends(require_token)) -> dict[str, str]:
        return {"ok": "yes"}

    async with AsyncClient(transport=ASGITransport(app), base_url="http://t") as c:
        r = await c.get("/foo", headers={"X-Coffer-Token": "anything"})
        assert r.status_code == 503
