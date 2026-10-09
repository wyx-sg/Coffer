"""The server page's row previews: read a resource, fill a prompt (spec mcp-gateway)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from coffer.application.mcp import capability_preview
from coffer.surfaces.http.mcp.capability_preview_routes import router as preview_router
from tests.integration.surfaces.http.mcp.test_capability_routes import (
    _build_app,
    _with_in_memory,
)

_BASE = "/api/v1/resources/mcp_server"


@pytest.fixture
async def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Any]:
    _with_in_memory(monkeypatch)
    app, engine, _rsvc, _prefs, supervisor, uid = await _build_app(
        tmp_path, resources=["file:///tmp/a.txt"], prompts=["summarise"]
    )
    app.include_router(preview_router)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Coffer-Token": "test-token"},
    ) as client:
        yield client, uid
    await supervisor.dispose()
    await engine.dispose()


@pytest.mark.acceptance(spec="mcp-gateway", scenario="read a resource from its row")
async def test_read_resource_returns_its_text(ctx: Any) -> None:
    client, uid = ctx
    r = await client.post(f"{_BASE}/{uid}/resources/read", json={"uri": "file:///tmp/a.txt"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["error"] is None
    [content] = body["contents"]
    assert content["kind"] == "text"
    assert content["text"] == "content of file:///tmp/a.txt"
    assert content["mime_type"] == "text/plain"
    assert content["truncated"] is False


@pytest.mark.acceptance(spec="mcp-gateway", scenario="fill a prompt from its row")
async def test_get_prompt_returns_its_messages(ctx: Any) -> None:
    client, uid = ctx
    r = await client.post(
        f"{_BASE}/{uid}/prompts/get", json={"name": "summarise", "arguments": {"topic": "x"}}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["description"] == "fake prompt summarise"
    assert body["contents"] == [
        {
            "kind": "text",
            "text": "prompt-text:summarise",
            "truncated": False,
            "size_bytes": None,
            "uri": None,
            "mime_type": None,
            "role": "user",
        }
    ]


async def test_preview_of_unknown_uid_is_404(ctx: Any) -> None:
    client, _uid = ctx
    r = await client.post(f"{_BASE}/nope/resources/read", json={"uri": "file:///tmp/a.txt"})
    assert r.status_code == 404


def test_long_text_is_cut_and_a_blob_is_sized() -> None:
    long = capability_preview._body({"text": "x" * (capability_preview.PREVIEW_TEXT_LIMIT + 5)})
    assert long.truncated is True
    assert len(long.text or "") == capability_preview.PREVIEW_TEXT_LIMIT
    blob = capability_preview._body({"blob": "aGVsbG8=", "mimeType": "image/png"})
    assert (blob.kind, blob.size_bytes, blob.text) == ("blob", 5, None)
    image = capability_preview._message(
        {"role": "user", "content": {"type": "image", "data": "aGVsbG8=", "mimeType": "image/png"}}
    )
    assert (image.kind, image.size_bytes, image.role) == ("image", 5, "user")


def test_an_upstream_error_is_named_by_its_code_not_its_text() -> None:
    from mcp import MCPError

    error = MCPError(code=-32602, message="bad token sk-secret-value")
    assert capability_preview._answered(error) == "JSON-RPC error -32602 (invalid params)"
    assert capability_preview._answered(MCPError(code=-1, message="x")) == "JSON-RPC error -1"
