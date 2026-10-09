"""A call's content, recorded end to end: capture in the gateway, the plaintext
rules in the writer, the row in SQLite (spec mcp-gateway "Record invocations
with redacted, bounded content")."""

from __future__ import annotations

import contextlib
import json
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from coffer.application.mcp import call_content
from coffer.application.mcp.call_content import CallContentRecording
from coffer.application.mcp.gateway_handlers import handle_tools_call
from coffer.domain.activity_content import MASK
from coffer.domain.mcp.http_api import HttpApiTransport
from coffer.domain.mcp.http_api_environment import HttpApiEnvironment
from coffer.domain.resource import Resource
from coffer.infrastructure.mcp.http_api_client import HttpApiUpstreamConnection
from coffer.infrastructure.mcp.persistence import MCPInvocationRepo
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from tests.support.fake_http_api import FakeHttpApi, fake_http_api

LIVE_TOKEN = "tok-live-0123456789abcdef"
INJECTED = "stdio-secret-value-98765"


class _Store:
    def __init__(self) -> None:
        self.value: bool | None = None

    def read(self) -> bool | None:
        return self.value

    def write(self, enabled: bool) -> None:
        self.value = enabled


@pytest.fixture(autouse=True)
def _recording() -> Iterator[None]:
    call_content.configure(CallContentRecording(_Store()))
    yield
    call_content.configure(None)


@pytest.fixture
def api() -> Iterator[FakeHttpApi]:
    with fake_http_api() as a:
        yield a


@pytest.fixture
async def repo(tmp_path: Path) -> AsyncIterator[MCPInvocationRepo]:
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'runs.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield MCPInvocationRepo(session_maker(engine))
    await engine.dispose()


class _Resources:
    async def get_by_name(self, kind: str, name: str) -> Resource:
        now = datetime.now(tz=UTC)
        return Resource(
            uid="0f1e2d3c4b5a69788796a5b4c3d2e1f0",
            kind="mcp_server",
            name=name,
            description=None,
            config={},
            enabled=True,
            created_at=now,
            updated_at=now,
        )


class _Prefs:
    async def find(self, *_a: Any) -> None:
        return None


class _Supervisor:
    def __init__(self, conn: Any, injected: tuple[str, ...] = ()) -> None:
        self._conn, self._injected = conn, injected

    def mask_values(self, name: str) -> tuple[str, ...]:
        return self._injected

    async def get_or_spawn(self, name: str) -> Any:
        return self._conn

    async def evict(self, name: str) -> None:
        return None


async def _call(repo: MCPInvocationRepo, sup: _Supervisor, name: str, args: dict[str, Any]) -> Any:
    async def _noop(_n: str) -> None:
        return None

    with contextlib.suppress(Exception):
        await handle_tools_call(
            {"name": name, "arguments": args},
            resources=_Resources(),
            supervisor=sup,
            prefs=_Prefs(),
            invocations=repo,
            session_id="s1",
            clock=lambda: datetime.now(tz=UTC),
            ensure_subscribed=_noop,
        )
    [row] = await repo.query(limit=1)
    stored = await repo.get(row.id or 0)
    assert stored is not None and stored.content is not None
    return {k: json.loads(v["text"]) for k, v in stored.content.items()}


def _group(api: FakeHttpApi, path: str) -> HttpApiUpstreamConnection:
    transport = HttpApiTransport.model_validate(
        {
            "environments": [
                {
                    "name": "live",
                    "base_url": api.base_url,
                    "headers": {"X-Env": "live"},
                    "secret_refs": {"Authorization": "secret/live"},
                    "auth_schemes": {"Authorization": "Bearer"},
                }
            ],
            "tools": [
                {
                    "name": "check",
                    "method": "POST",
                    "path": path,
                    "changes_data": False,
                    "body_template": '{"q": "{q}"}',
                    "input_schema": {
                        "type": "object",
                        "properties": {"q": {"type": "string"}},
                        "required": ["q"],
                    },
                }
            ],
        }
    )

    async def secrets(env: HttpApiEnvironment) -> dict[str, str]:
        return {"Authorization": LIVE_TOKEN}

    return HttpApiUpstreamConnection(
        transport=transport, header_overlay={}, server_name="billing", env_secrets=secrets
    )


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a custom tool's call records its request and response"
)
async def test_a_custom_tool_records_its_request_and_response(
    api: FakeHttpApi, repo: MCPInvocationRepo
) -> None:
    parts = await _call(repo, _Supervisor(_group(api, "/sp-error")), "billing__check", {"q": "x"})
    request, response = parts["request"], parts["response"]
    assert request["method"] == "POST"
    assert request["url"] == f"{api.base_url}/sp-error"
    assert request["headers"]["Authorization"] == MASK
    assert request["headers"]["X-Env"] == "live"
    assert request["body"] == {"q": "x"}
    assert response["status"] == 200
    assert response["headers"]["x-sp-error"] == "101"
    assert response["body"] == {"error": "denied"}
    assert LIVE_TOKEN not in json.dumps(parts)


@pytest.mark.acceptance(spec="mcp-gateway", scenario="a plaintext key the rules know is masked")
async def test_a_plaintext_key_in_a_result_is_masked(
    api: FakeHttpApi, repo: MCPInvocationRepo
) -> None:
    parts = await _call(repo, _Supervisor(_group(api, "/token")), "billing__check", {"q": "x"})
    text = json.dumps(parts)
    assert "ghp_a1B2c3D4" not in text
    assert f"minted {MASK} for you" in parts["response"]["body"]


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="an injected secret echoed by the upstream is masked in the record"
)
async def test_no_file_under_the_data_dir_holds_an_injected_value(
    tmp_path: Path, repo: MCPInvocationRepo
) -> None:
    class _Echo:
        def __init__(self, fail: bool) -> None:
            self._fail = fail

        async def request(self, method: str, params: dict[str, Any]) -> Any:
            if self._fail:
                raise RuntimeError(f"refused key {INJECTED}")
            return {"content": [{"type": "text", "text": f"env has {INJECTED}"}]}

    ok = await _call(repo, _Supervisor(_Echo(False), (INJECTED,)), "fs__env", {})
    failed = await _call(repo, _Supervisor(_Echo(True), (INJECTED,)), "fs__env", {})
    assert MASK in ok["result"]["content"][0]["text"]
    assert failed["error"] == f"RuntimeError: refused key {MASK}"
    for f in tmp_path.rglob("*"):
        if f.is_file():
            assert INJECTED.encode() not in f.read_bytes(), f
