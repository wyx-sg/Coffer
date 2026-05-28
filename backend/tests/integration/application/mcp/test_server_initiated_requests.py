"""Exercise sampling/createMessage and roots/list server-initiated pass-through.

T-061 (sampling) + T-062 (roots/list).

These tests exercise the session's bookkeeping layer directly — without a
real upstream subprocess — to confirm:
  1. handle_response_from_downstream + _send_request_to_downstream round-trip.
  2. Sampling is capability-gated (capability missing → ErrorData, not a hang).
  3. handle_response_from_downstream returns False for unmatched ids.

Full end-to-end (real upstream invoking the SDK's create_message helper) would
require extending fake_mcp_server.py to actually call sampling; that is deferred
to a dedicated e2e suite.
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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_registry() -> ServerRequestRegistry:
    return ServerRequestRegistry()


async def _null_sink(payload: dict[str, Any]) -> None:
    """No-op downstream sink."""


# ---------------------------------------------------------------------------
# Test: pending request round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pending_request_round_trip() -> None:
    """send_request suspends until handle_response resolves the future."""
    registry = _make_registry()

    emitted: list[dict[str, Any]] = []

    async def capturing_sink(payload: dict[str, Any]) -> None:
        emitted.append(payload)

    # Start the send_request coroutine in a background task
    send_task = asyncio.create_task(
        registry.send_request("roots/list", {}, capturing_sink, timeout=5.0)
    )

    # Yield control so send_request can emit the envelope and suspend on the future
    await asyncio.sleep(0)

    # The registry should have emitted one envelope with an id
    assert len(emitted) == 1
    req_id = emitted[0]["id"]
    assert emitted[0]["method"] == "roots/list"

    # Synthesise the downstream client's response
    response_envelope = {"jsonrpc": "2.0", "id": req_id, "result": {"roots": []}}
    matched = registry.handle_response(response_envelope)
    assert matched is True

    # The send_request task should now complete with the result
    result = await asyncio.wait_for(send_task, timeout=2.0)
    assert result == {"roots": []}


# ---------------------------------------------------------------------------
# Test: handle_response returns False for unmatched id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_response_returns_false_for_unmatched_id() -> None:
    """An envelope whose id doesn't match any pending request is left alone."""
    registry = _make_registry()

    response_envelope = {"jsonrpc": "2.0", "id": 9999, "result": {"roots": []}}
    matched = registry.handle_response(response_envelope)
    assert matched is False


# ---------------------------------------------------------------------------
# Test: sampling callback — capability gate blocks when sampling absent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sampling_capability_gate_rejected() -> None:
    """If the client didn't declare sampling, the callback returns ErrorData immediately."""
    registry = _make_registry()
    # No downstream sink needed — we should never reach the SSE send
    client_capabilities: dict[str, Any] = {}  # sampling key absent

    sampling_cb = build_sampling_callback(
        registry,
        lambda: None,  # get_sink — should not be called
        lambda: client_capabilities,
        session_id="test-session",
    )

    fake_params = MagicMock(spec=mcp_types.CreateMessageRequestParams)
    fake_params.model_dump = MagicMock(return_value={"messages": [], "maxTokens": 100})

    result = await sampling_cb(context=None, params=fake_params)  # type: ignore[arg-type]

    assert isinstance(result, mcp_types.ErrorData)
    assert result.code == mcp_types.METHOD_NOT_FOUND
    assert "sampling" in result.message.lower()


# ---------------------------------------------------------------------------
# Test: sampling callback — forwards when capability is present
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sampling_callback_forwards_when_capable() -> None:
    """When sampling capability is declared, the request is forwarded downstream."""
    registry = _make_registry()
    emitted: list[dict[str, Any]] = []

    async def capturing_sink(payload: dict[str, Any]) -> None:
        emitted.append(payload)

    client_capabilities: dict[str, Any] = {"sampling": {}}

    sampling_cb = build_sampling_callback(
        registry,
        lambda: capturing_sink,
        lambda: client_capabilities,
        session_id="test-session",
    )

    fake_params = MagicMock(spec=mcp_types.CreateMessageRequestParams)
    fake_params.model_dump = MagicMock(
        return_value={
            "messages": [{"role": "user", "content": {"type": "text", "text": "hi"}}],
            "maxTokens": 100,
        }
    )

    # Run the callback in a task; it will block waiting for the downstream reply
    task = asyncio.create_task(
        sampling_cb(context=None, params=fake_params)  # type: ignore[arg-type]
    )
    await asyncio.sleep(0)

    # The request should have been forwarded
    assert len(emitted) == 1
    assert emitted[0]["method"] == "sampling/createMessage"
    req_id = emitted[0]["id"]

    # Synthesise a valid-enough CreateMessageResult
    response_envelope = {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "role": "assistant",
            "content": {"type": "text", "text": "Hello!"},
            "model": "claude-3-5-sonnet",
            "stopReason": "end_turn",
        },
    }
    registry.handle_response(response_envelope)

    result = await asyncio.wait_for(task, timeout=2.0)
    assert isinstance(result, mcp_types.CreateMessageResult)
    assert result.model == "claude-3-5-sonnet"


# ---------------------------------------------------------------------------
# Test: list_roots callback — forwards and returns ListRootsResult
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_roots_callback_round_trip() -> None:
    """roots/list callback forwards downstream and returns a ListRootsResult."""
    registry = _make_registry()
    emitted: list[dict[str, Any]] = []

    async def capturing_sink(payload: dict[str, Any]) -> None:
        emitted.append(payload)

    roots_cb = build_list_roots_callback(
        registry,
        lambda: capturing_sink,
        session_id="test-session",
    )

    task = asyncio.create_task(
        roots_cb(context=None)  # type: ignore[arg-type]
    )
    await asyncio.sleep(0)

    assert len(emitted) == 1
    assert emitted[0]["method"] == "roots/list"
    req_id = emitted[0]["id"]

    response_envelope = {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {"roots": [{"uri": "file:///home/user/project", "name": "project"}]},
    }
    registry.handle_response(response_envelope)

    result = await asyncio.wait_for(task, timeout=2.0)
    assert isinstance(result, mcp_types.ListRootsResult)
    assert len(result.roots) == 1
    assert result.roots[0].name == "project"


# ---------------------------------------------------------------------------
# Test: cancel_all cancels all pending futures
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_all_cancels_pending_futures() -> None:
    """cancel_all() cancels every in-flight request future."""
    registry = _make_registry()
    emitted: list[dict[str, Any]] = []

    async def capturing_sink(payload: dict[str, Any]) -> None:
        emitted.append(payload)

    # Start two requests
    task1 = asyncio.create_task(
        registry.send_request("roots/list", {}, capturing_sink, timeout=10.0)
    )
    task2 = asyncio.create_task(
        registry.send_request("sampling/createMessage", {}, capturing_sink, timeout=10.0)
    )
    await asyncio.sleep(0)  # let them suspend

    registry.cancel_all()

    with pytest.raises((asyncio.CancelledError, asyncio.TimeoutError)):
        await asyncio.wait_for(task1, timeout=1.0)
    # task2 also done (cancelled or timed out)
    assert task2.done() or task2.cancelled()


# ---------------------------------------------------------------------------
# Test: handle_response with error sets exception on future
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_response_with_error_propagates_exception() -> None:
    """An error response causes the awaiting coroutine to raise RuntimeError."""
    registry = _make_registry()
    emitted: list[dict[str, Any]] = []

    async def capturing_sink(payload: dict[str, Any]) -> None:
        emitted.append(payload)

    task = asyncio.create_task(registry.send_request("roots/list", {}, capturing_sink, timeout=5.0))
    await asyncio.sleep(0)

    req_id = emitted[0]["id"]
    error_envelope = {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": "Method not found"},
    }
    matched = registry.handle_response(error_envelope)
    assert matched is True

    with pytest.raises(RuntimeError, match="Method not found"):
        await asyncio.wait_for(task, timeout=2.0)
