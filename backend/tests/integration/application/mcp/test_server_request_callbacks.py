"""Behavioural coverage for the sampling/roots SDK callback error branches.

Companion to test_server_initiated_requests.py. That file exercises the happy
paths; this file drives the failure/edge branches that the SDK relies on:

  - send_request raising UpstreamUnavailable when no downstream sink is wired.
  - handle_response ignoring an envelope that carries no id.
  - the sampling callback mapping UpstreamUnavailable / arbitrary downstream
    failures / malformed downstream payloads onto the correct ErrorData.
  - the roots/list callback mapping the same failure modes onto ErrorData and
    falling back to an empty ListRootsResult on a malformed payload.

Every test asserts a concrete output (a specific ErrorData.code/message, a
specific exception type, or a validated model), so each one fails if the
corresponding branch regresses.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import mcp.types as mcp_types
import pytest

from coffer.application.mcp.gateway_server_requests import (
    ServerRequestRegistry,
    build_list_roots_callback,
    build_sampling_callback,
)
from coffer.domain.errors import UpstreamUnavailable


def _make_registry() -> ServerRequestRegistry:
    return ServerRequestRegistry()


# ---------------------------------------------------------------------------
# send_request: no downstream sink connected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_request_raises_when_no_downstream_sink() -> None:
    """send_request must refuse to forward when no downstream client is connected."""
    registry = _make_registry()

    with pytest.raises(UpstreamUnavailable, match="no downstream client connected"):
        await registry.send_request("roots/list", {}, None, timeout=5.0)

    # Nothing should have been enqueued as a pending future.
    assert registry._pending == {}


# ---------------------------------------------------------------------------
# handle_response: envelope with no id is not consumed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_response_returns_false_for_missing_id() -> None:
    """A response envelope without an id can't match a pending request."""
    registry = _make_registry()

    matched = registry.handle_response({"jsonrpc": "2.0", "result": {"roots": []}})
    assert matched is False


# ---------------------------------------------------------------------------
# sampling callback: UpstreamUnavailable -> METHOD_NOT_FOUND ErrorData
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sampling_callback_upstream_unavailable_returns_error_data() -> None:
    """Capability present but no sink => UpstreamUnavailable mapped to METHOD_NOT_FOUND."""
    registry = _make_registry()

    sampling_cb = build_sampling_callback(
        registry,
        lambda: None,  # get_sink returns no sink -> send_request raises UpstreamUnavailable
        lambda: {"sampling": {}},
        session_id="test-session",
    )

    fake_params = MagicMock(spec=mcp_types.CreateMessageRequestParams)
    fake_params.model_dump = MagicMock(return_value={"messages": [], "maxTokens": 100})

    result = await sampling_cb(context=None, params=fake_params)  # type: ignore[arg-type]

    assert isinstance(result, mcp_types.ErrorData)
    assert result.code == mcp_types.METHOD_NOT_FOUND
    assert "no downstream client connected" in result.message


# ---------------------------------------------------------------------------
# sampling callback: arbitrary send_request failure -> internal error ErrorData
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sampling_callback_generic_failure_returns_internal_error() -> None:
    """A non-UpstreamUnavailable failure surfaces as a -32603 ErrorData."""
    registry = _make_registry()

    async def boom_sink(payload: dict[str, Any]) -> None:
        raise ValueError("sink exploded")

    sampling_cb = build_sampling_callback(
        registry,
        lambda: boom_sink,
        lambda: {"sampling": {}},
        session_id="test-session",
    )

    fake_params = MagicMock(spec=mcp_types.CreateMessageRequestParams)
    fake_params.model_dump = MagicMock(return_value={"messages": [], "maxTokens": 100})

    result = await sampling_cb(context=None, params=fake_params)  # type: ignore[arg-type]

    assert isinstance(result, mcp_types.ErrorData)
    assert result.code == -32603
    assert "sampling failed" in result.message
    assert "sink exploded" in result.message


# ---------------------------------------------------------------------------
# sampling callback: malformed downstream result -> invalid response ErrorData
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sampling_callback_malformed_result_returns_error_data() -> None:
    """A downstream result that fails CreateMessageResult validation => ErrorData."""
    registry = _make_registry()
    emitted: list[dict[str, Any]] = []

    async def capturing_sink(payload: dict[str, Any]) -> None:
        emitted.append(payload)

    sampling_cb = build_sampling_callback(
        registry,
        lambda: capturing_sink,
        lambda: {"sampling": {}},
        session_id="test-session",
    )

    fake_params = MagicMock(spec=mcp_types.CreateMessageRequestParams)
    fake_params.model_dump = MagicMock(return_value={"messages": [], "maxTokens": 100})

    task = asyncio.create_task(
        sampling_cb(context=None, params=fake_params)  # type: ignore[arg-type]
    )
    await asyncio.sleep(0)

    assert len(emitted) == 1
    req_id = emitted[0]["id"]

    # Missing required CreateMessageResult fields (role/content/model) -> validation fails.
    registry.handle_response({"jsonrpc": "2.0", "id": req_id, "result": {"not": "a-valid-result"}})

    result = await asyncio.wait_for(task, timeout=2.0)
    assert isinstance(result, mcp_types.ErrorData)
    assert result.code == -32603
    assert "invalid sampling response" in result.message


# ---------------------------------------------------------------------------
# list_roots callback: UpstreamUnavailable -> METHOD_NOT_FOUND ErrorData
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_roots_callback_upstream_unavailable_returns_error_data() -> None:
    """No sink => roots/list maps UpstreamUnavailable to a METHOD_NOT_FOUND ErrorData."""
    registry = _make_registry()

    roots_cb = build_list_roots_callback(
        registry,
        lambda: None,  # no sink
        session_id="test-session",
    )

    result = await roots_cb(context=None)  # type: ignore[arg-type]

    assert isinstance(result, mcp_types.ErrorData)
    assert result.code == mcp_types.METHOD_NOT_FOUND
    assert "no downstream client connected" in result.message


# ---------------------------------------------------------------------------
# list_roots callback: arbitrary failure -> internal error ErrorData
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_roots_callback_generic_failure_returns_internal_error() -> None:
    """A non-UpstreamUnavailable failure surfaces as a -32603 ErrorData."""
    registry = _make_registry()

    async def boom_sink(payload: dict[str, Any]) -> None:
        raise ValueError("sink exploded")

    roots_cb = build_list_roots_callback(
        registry,
        lambda: boom_sink,
        session_id="test-session",
    )

    result = await roots_cb(context=None)  # type: ignore[arg-type]

    assert isinstance(result, mcp_types.ErrorData)
    assert result.code == -32603
    assert "roots/list failed" in result.message
    assert "sink exploded" in result.message


# ---------------------------------------------------------------------------
# list_roots callback: malformed downstream result -> empty ListRootsResult
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_roots_callback_malformed_result_falls_back_to_empty() -> None:
    """A downstream result that fails ListRootsResult validation => empty roots."""
    registry = _make_registry()
    emitted: list[dict[str, Any]] = []

    async def capturing_sink(payload: dict[str, Any]) -> None:
        emitted.append(payload)

    roots_cb = build_list_roots_callback(
        registry,
        lambda: capturing_sink,
        session_id="test-session",
    )

    task = asyncio.create_task(roots_cb(context=None))  # type: ignore[arg-type]
    await asyncio.sleep(0)

    assert len(emitted) == 1
    req_id = emitted[0]["id"]

    # "roots" must be a list; a string fails validation -> fallback to empty result.
    registry.handle_response({"jsonrpc": "2.0", "id": req_id, "result": {"roots": "not-a-list"}})

    result = await asyncio.wait_for(task, timeout=2.0)
    assert isinstance(result, mcp_types.ListRootsResult)
    assert result.roots == []
