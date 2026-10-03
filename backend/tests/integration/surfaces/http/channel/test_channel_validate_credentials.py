"""POST /channels/validate-credentials (spec channels "Check credentials before
they are saved"): the route over a stub check — shape, auth, and that a refusal
is a 200 answer rather than an error."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.application.channel.credential_check import (
    CredentialCheck,
    CredentialProbeError,
    ProbedBot,
    StoredCredentials,
)
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.channel_routes import router, set_credential_check

_TOKEN = "test-token"


class _Probe:
    async def telegram(self, bot_token: str) -> ProbedBot:
        if bot_token == "bad":
            raise CredentialProbeError("rejected", "Unauthorized")
        return ProbedBot("7", "a_bot", "A")

    async def seatalk(self, app_id: str, app_secret: str) -> ProbedBot:
        return ProbedBot(app_id)


class _Stored:
    async def read(self, channel_uid: str) -> StoredCredentials | None:
        return StoredCredentials(platform="telegram", bot_token="old")


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(router)
    set_credential_check(CredentialCheck(_Probe(), _Stored()))
    set_active_token(_TOKEN)
    async with AsyncClient(
        transport=ASGITransport(app), base_url="http://t", headers={"X-Coffer-Token": _TOKEN}
    ) as c:
        yield c
    set_active_token(None)


@pytest.mark.acceptance(spec="channels", scenario="check a token as it is pasted")
async def test_valid_token_names_the_bot_and_compares_with_the_channel(
    client: AsyncClient,
) -> None:
    r = await client.post(
        "/api/v1/channels/validate-credentials",
        json={"platform": "telegram", "bot_token": "good", "channel_uid": "u"},
    )
    assert r.status_code == 200
    assert r.json() == {
        "ok": True,
        "bot_handle": "a_bot",
        "bot_name": "A",
        "same_bot": True,
        "reason": None,
        "detail": None,
    }


@pytest.mark.acceptance(
    spec="channels", scenario="a refused or unreachable platform is reported, not raised"
)
async def test_rejected_token_is_ok_false_with_a_reason(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/channels/validate-credentials", json={"platform": "telegram", "bot_token": "bad"}
    )
    assert r.status_code == 200
    assert r.json()["ok"] is False and r.json()["reason"] == "rejected"


async def test_requires_the_token() -> None:
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(router)
    set_active_token(_TOKEN)
    async with AsyncClient(transport=ASGITransport(app), base_url="http://t") as c:
        r = await c.post("/api/v1/channels/validate-credentials", json={"platform": "telegram"})
    set_active_token(None)
    assert r.status_code in (401, 403)
