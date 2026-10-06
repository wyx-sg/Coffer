"""Integration: an upstream tool's ``outputSchema`` survives the gateway.

A real stdio upstream declares an ``outputSchema`` on one tool and none on
another; the gateway's ``tools/list`` and ``coffer__search_tools`` carry the
declared schema verbatim, the other tool gains no key, and a call's
``structuredContent`` comes back as the upstream sent it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from tests.fixtures.keyring import install_in_memory_keyring
from tests.fixtures.output_schema_mcp_server import OUTPUT_SCHEMA, STRUCTURED
from tests.integration.application.mcp.test_gateway_tool_search_integration import (
    _safe_dispose,
    _setup,
)

_SERVER = Path(__file__).resolve().parents[3] / "fixtures" / "output_schema_mcp_server.py"
_CONFIG = {"transport": {"type": "stdio", "command": sys.executable, "args": [str(_SERVER)]}}


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="pass an upstream tool's output schema through"
)
@pytest.mark.asyncio
async def test_output_schema_reaches_list_and_search(tmp_path, monkeypatch):
    install_in_memory_keyring(monkeypatch)
    session, _inv, engine = await _setup(tmp_path, {"up": _CONFIG})
    try:
        listed = {t["name"]: t for t in (await session.handle_request("tools/list"))["tools"]}
        assert listed["up__typed"]["outputSchema"] == OUTPUT_SCHEMA
        assert "outputSchema" not in listed["up__plain"]

        found = await session.handle_request(
            "tools/call",
            {"name": "coffer__search_tools", "arguments": {"query": "count things say hello"}},
        )
        searched = {t["name"]: t for t in json.loads(found["content"][0]["text"])["tools"]}
        assert searched["up__typed"]["outputSchema"] == OUTPUT_SCHEMA
        assert "outputSchema" not in searched["up__plain"]
    finally:
        await session.dispose()
        await _safe_dispose(engine)


@pytest.mark.asyncio
async def test_structured_content_is_passed_through_untouched(tmp_path, monkeypatch):
    install_in_memory_keyring(monkeypatch)
    session, _inv, engine = await _setup(tmp_path, {"up": _CONFIG})
    try:
        await session.handle_request("tools/list")
        result = await session.handle_request("tools/call", {"name": "up__typed", "arguments": {}})
        assert result["structuredContent"] == STRUCTURED
        assert result["isError"] is False
    finally:
        await session.dispose()
        await _safe_dispose(engine)
