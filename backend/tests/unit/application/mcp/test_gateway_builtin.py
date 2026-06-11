"""Unit tests for built-in MCP tool dispatch + invocation logging.

The built-in (``coffer__*``) path shares the invocation log surface with
upstream tools, so it must honour the same SC-010 leak rule: an arbitrary
downstream exception is logged by class name only, never its message (which
could echo args / returned content). Coffer-authored errors keep their message.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.application.builtin_tools import BuiltinTool, BuiltinToolRegistry
from coffer.application.mcp.gateway_builtin import dispatch_builtin_tool
from coffer.domain.errors import MemoryStoreNotFound
from coffer.domain.mcp.capability import MCPInvocation

_SENTINEL = "COFFER_LEAK_SENTINEL_xyz789"


class _RecordingInvocations:
    """Captures inserted invocation rows (the ``MCPInvocationRepoPort`` shape)."""

    def __init__(self) -> None:
        self.rows: list[MCPInvocation] = []

    async def insert(self, inv: MCPInvocation) -> None:
        self.rows.append(inv)


def _clock() -> datetime:
    return datetime(2026, 6, 9, tzinfo=UTC)


def _registry(handler) -> BuiltinToolRegistry:
    reg = BuiltinToolRegistry()
    reg.register(BuiltinTool(name="recall", description="x", input_schema={}, handler=handler))
    return reg


async def test_downstream_exception_logs_class_name_only() -> None:
    async def _boom(_args: dict) -> dict:
        raise RuntimeError(f"downstream failure with secret {_SENTINEL}")

    invocations = _RecordingInvocations()
    with pytest.raises(RuntimeError):
        await dispatch_builtin_tool(
            prefixed_name="coffer__recall",
            params={"arguments": {}},
            builtin=_registry(_boom),
            invocations=invocations,
            session_id="s1",
            clock=_clock,
        )
    (row,) = invocations.rows
    assert row.status == "error"
    # Class name only — the sentinel-bearing message must NOT be persisted.
    assert row.error_message == "RuntimeError"
    assert _SENTINEL not in (row.error_message or "")


async def test_coffer_error_keeps_its_message() -> None:
    async def _coffer_boom(_args: dict) -> dict:
        raise MemoryStoreNotFound("project-X")

    invocations = _RecordingInvocations()
    with pytest.raises(MemoryStoreNotFound):
        await dispatch_builtin_tool(
            prefixed_name="coffer__recall",
            params={"arguments": {}},
            builtin=_registry(_coffer_boom),
            invocations=invocations,
            session_id="s1",
            clock=_clock,
        )
    (row,) = invocations.rows
    assert row.status == "error"
    assert "MemoryStoreNotFound" in (row.error_message or "")
    assert "project-X" in (row.error_message or "")


async def test_success_path_wraps_result_as_mcp_call_tool_result() -> None:
    """A built-in tool's raw dict must reach the wire as a valid MCP
    ``CallToolResult`` — ``content`` is REQUIRED; a bare payload dict fails SDK
    validation on every real client (found by the SDK-oracle e2e call)."""

    async def _handler(_args: dict) -> dict:
        return {"id": "f1", "status": "created"}

    invocations = _RecordingInvocations()
    result = await dispatch_builtin_tool(
        prefixed_name="coffer__recall",
        params={"name": "coffer__recall", "arguments": {}},
        builtin=_registry(_handler),
        invocations=invocations,
        session_id="s1",
        clock=_clock,
    )

    assert isinstance(result.get("content"), list) and result["content"], result
    assert result["content"][0]["type"] == "text"
    assert "created" in result["content"][0]["text"]
    assert result.get("isError") is False
    # The raw payload stays machine-readable alongside the text rendering.
    assert result.get("structuredContent") == {"id": "f1", "status": "created"}

    # status=ok invocation row with the bare tool name.
    assert len(invocations.rows) == 1
    row = invocations.rows[0]
    assert row.status == "ok"
    assert row.capability_key == "recall"
    assert row.resource_name == "coffer"
