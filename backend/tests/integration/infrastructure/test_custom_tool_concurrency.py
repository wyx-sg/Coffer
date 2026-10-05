"""Fifty concurrent calls of one custom tool in two environments do not mix.

Spec mcp-gateway "Choose a custom tool's environment on every call": the
connection keeps no current environment, so calls in flight at the same time
each use only their own environment's URL, headers, variables and secret —
here with every secret lookup and every upstream answer interleaved.
"""

from __future__ import annotations

import asyncio
import json
import random
from collections.abc import Iterator

import pytest

from coffer.domain.mcp.http_api import HttpApiTransport
from coffer.domain.mcp.http_api_environment import HttpApiEnvironment
from coffer.infrastructure.mcp.http_api_client import HttpApiUpstreamConnection
from tests.support.fake_http_api import FakeHttpApi, fake_http_api

SECRETS = {"test": "tok-test-aaaa", "live": "tok-live-bbbb"}


@pytest.fixture
def api() -> Iterator[FakeHttpApi]:
    with fake_http_api() as a:
        yield a


def _transport(api: FakeHttpApi) -> HttpApiTransport:
    env = lambda name, region: {  # noqa: E731
        "name": name,
        "base_url": f"{api.base_url}/{name}",
        "headers": {"X-Env": name},
        "secret_refs": {"Authorization": f"secret/{name}"},
        "auth_schemes": {"Authorization": "Bearer"},
        "variables": {"region": region},
    }
    return HttpApiTransport.model_validate(
        {
            "environments": [env("test", "eu-1"), env("live", "us-1")],
            "tools": [
                {
                    "name": "search",
                    "method": "POST",
                    "path": "/{env:region}/search",
                    "changes_data": False,
                    "input_schema": {
                        "type": "object",
                        "properties": {"q": {"type": "string"}, "region": {"type": "string"}},
                        "required": ["q"],
                    },
                }
            ],
        }
    )


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="concurrent calls in two environments do not mix"
)
async def test_fifty_concurrent_calls_keep_their_environment(api: FakeHttpApi) -> None:
    async def secrets(env: HttpApiEnvironment) -> dict[str, str]:
        await asyncio.sleep(random.random() / 100)  # interleave the lookups
        return {"Authorization": SECRETS[env.name]}

    conn = HttpApiUpstreamConnection(
        transport=_transport(api), header_overlay={}, server_name="billing", env_secrets=secrets
    )
    calls = [
        conn.request(
            "tools/call",
            {
                "name": "search",
                "arguments": {
                    "q": f"q{i}",
                    "region": f"cid-{i}",
                    "coffer_environment": "test" if i % 2 == 0 else "live",
                },
            },
        )
        for i in range(50)
    ]
    results = await asyncio.gather(*calls)
    assert not any(r.is_error for r in results)
    assert len(api.seen) == 50
    for seen in api.seen:
        name = seen.path.split("/")[1]
        region = {"test": "eu-1", "live": "us-1"}[name]
        assert seen.path == f"/{name}/{region}/search"
        assert seen.headers["x-env"] == name
        assert seen.headers["authorization"] == f"Bearer {SECRETS[name]}"
        body = json.loads(seen.body)
        assert set(body) == {"q", "region"} and body["region"].startswith("cid-")
        i = int(body["q"][1:])
        assert name == ("test" if i % 2 == 0 else "live")
