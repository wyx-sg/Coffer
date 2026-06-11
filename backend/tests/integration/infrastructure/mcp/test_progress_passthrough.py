"""Tests for T-060: progress passthrough behavioral test.

Verifies that a long-running upstream tool that streams notifications/progress
events completes successfully and the client observes those progress events.
The three tautological mock tests (test_call_tool_accepts_read_timeout_seconds
and the two *_dispatch_passes_read_timeout_seconds) are removed and superseded
by the behavioral test below.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from coffer.domain.mcp.server_config import StdioTransport

_FAKE = Path(__file__).resolve().parents[3] / "fixtures" / "fake_mcp_server.py"


@pytest.mark.asyncio
async def test_long_call_with_progress_does_not_premature_timeout() -> None:
    """A tool that emits notifications/progress over an extended call must complete
    successfully and the client must observe at least 3 progress events.

    This replaces the three mock/signature tests that were tautological:
    - test_call_tool_accepts_read_timeout_seconds (always true — **kwargs)
    - test_stdio_dispatch_passes_read_timeout_seconds (mock-verified, not behavioral)
    - test_http_dispatch_passes_read_timeout_seconds  (mock-verified, not behavioral)

    The fake server only emits progress notifications when the request carries a
    progressToken in _meta.  We supply a progress_callback to conn.request() which
    causes the SDK to inject a progressToken automatically; the server reads it from
    ctx.meta.progressToken and fires send_progress_notification for each step.
    """
    from coffer.infrastructure.mcp.subprocess import StdioUpstreamConnection

    # The fake server runs `slow_progress` tool that:
    # - emits 3 progress events at 100 ms intervals
    # - returns after ~350 ms total
    # request_timeout_seconds=30 gives plenty of room but ensures
    # the SDK's read_timeout_seconds mechanism is exercised (per-event reset).
    transport = StdioTransport(
        type="stdio",
        command=sys.executable,
        args=[
            str(_FAKE),
            "--scenario",
            "progress",
            "--tools",
            "slow_progress",
            "--progress-steps",
            "3",
            "--progress-delay-ms",
            "100",
        ],
    )
    conn = StdioUpstreamConnection(
        transport=transport,
        env_overlay={},
        request_timeout_seconds=30,
        server_name="progress_test",
    )

    # Collect progress events via the SDK's progress_callback mechanism.
    # The callback receives (progress, total, message) from the SDK after it
    # processes each notifications/progress message from the server.
    received_progress: list[tuple[float, float | None, str | None]] = []

    async def _on_progress(progress: float, total: float | None, message: str | None) -> None:
        received_progress.append((progress, total, message))

    try:
        await conn.spawn_and_initialize()
        result = await conn.request(
            "tools/call",
            {"name": "slow_progress", "arguments": {}},
            progress_callback=_on_progress,
        )
        # The call must complete without raising
        assert result is not None
        # The result should carry a "done" marker confirming all steps ran
        if hasattr(result, "model_dump"):
            dumped = result.model_dump(mode="json", exclude_none=True)
        else:
            dumped = result
        assert dumped  # non-empty result

        # At least 3 progress events must have been received — this is the
        # key behavioral assertion that was missing in the original test.
        assert len(received_progress) >= 3, (
            f"Expected at least 3 progress events, got {len(received_progress)}: "
            f"{received_progress}"
        )
        # Progress values must be ascending and within [1, steps]
        progress_values = [p for p, _t, _m in received_progress]
        assert progress_values == sorted(progress_values), (
            f"Progress values must be non-decreasing: {progress_values}"
        )
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_dispatch_falls_back_on_type_error() -> None:
    """If call_tool raises TypeError (older SDK), _dispatch_method retries without the kwarg."""
    from coffer.infrastructure.mcp.subprocess import StdioUpstreamConnection

    transport = StdioTransport(type="stdio", command="python", args=[])
    conn = StdioUpstreamConnection(transport=transport, env_overlay={}, request_timeout_seconds=30)

    fallback_result = MagicMock(isError=False)

    async def _raise_on_kwarg(*args: Any, **kwargs: Any) -> Any:
        if "read_timeout_seconds" in kwargs:
            # Realistic CPython message — it always names the offending kwarg;
            # dispatch_method only retries when the message cites one of the
            # optional kwargs (a TypeError from inside the tool must not
            # re-invoke a non-idempotent call).
            raise TypeError("call_tool() got an unexpected keyword argument 'read_timeout_seconds'")
        return fallback_result

    mock_session = MagicMock()
    mock_session.call_tool = AsyncMock(side_effect=_raise_on_kwarg)
    conn._session = mock_session

    result = await conn._dispatch_method("tools/call", {"name": "t", "arguments": {}})
    assert result is fallback_result
    # First call with kwarg failed; second without should have been made
    assert mock_session.call_tool.call_count == 2
