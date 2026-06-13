"""``dispatch_tool_search`` feeds the eval-capture sink (ADR-019, slice 2).

A real ``coffer__search_tools`` call is the cleanest capture surface: the query
(the agent's intent) and the ranked tool names are both right there. When
opted in, the dispatch must emit one ``tool_search`` capture record; when not,
it must stay silent.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import pytest

from coffer.application.eval_capture import CAPTURE_LOGGER_NAME
from coffer.application.mcp.gateway_builtin import dispatch_tool_search

_AGGREGATED = [
    {"name": "fs__read_file", "description": "read a file from disk"},
    {"name": "fs__write_file", "description": "write a file to disk"},
    {"name": "coffer__search_tools", "description": "the meta tool itself"},
]


class _FakeInvocations:
    async def insert(self, _inv: object) -> None:  # matches MCPInvocationRepoPort.insert
        return None


async def _dispatch(query: str) -> dict:
    return await dispatch_tool_search(
        params={"arguments": {"query": query, "top_k": 2}},
        aggregated_tools=_AGGREGATED,
        invocations=_FakeInvocations(),  # type: ignore[arg-type]
        session_id="t",
        clock=lambda: datetime.now(tz=UTC),
    )


@pytest.mark.asyncio
async def test_captures_query_and_ranked_tools_when_enabled(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("COFFER_EVAL_CAPTURE", "1")
    with caplog.at_level(logging.INFO, logger=CAPTURE_LOGGER_NAME):
        await _dispatch("read a file from disk")

    records = [r for r in caplog.records if r.name == CAPTURE_LOGGER_NAME]
    assert len(records) == 1
    payload = json.loads(records[0].getMessage())
    assert payload["kind"] == "tool_search"
    assert payload["query"] == "read a file from disk"
    # Only upstream tools are ranked — Coffer's own meta tool is excluded.
    assert "fs__read_file" in payload["results"]
    assert all(not name.startswith("coffer__") for name in payload["results"])


@pytest.mark.asyncio
async def test_silent_when_disabled(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("COFFER_EVAL_CAPTURE", raising=False)
    with caplog.at_level(logging.INFO, logger=CAPTURE_LOGGER_NAME):
        await _dispatch("read a file")
    assert [r for r in caplog.records if r.name == CAPTURE_LOGGER_NAME] == []
