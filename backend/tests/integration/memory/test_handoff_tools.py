"""Integration: the coffer__set_handoff / coffer__resume built-in MCP tools."""

from __future__ import annotations

import pytest

from coffer.application.builtin_tools import COFFER_TOOL_PREFIX, BuiltinToolRegistry
from coffer.application.memory.builtin_tools import register_memory_builtin_tools

pytestmark = pytest.mark.asyncio


@pytest.mark.acceptance(
    spec="007-memory", scenario="agent saves and resumes a working-state handoff"
)
async def test_set_handoff_then_resume(handoff) -> None:
    reg = BuiltinToolRegistry()
    register_memory_builtin_tools(
        reg, memory_service=handoff.memory_service, handoff_service=handoff.svc
    )
    set_tool = reg.get(f"{COFFER_TOOL_PREFIX}set_handoff")
    assert set_tool is not None
    out = await set_tool.handler({"body": "at step 3; next step 4", "cwd": handoff.cwd})
    assert out["status"] == "saved"
    assert out["branch"] == "work"
    resume_tool = reg.get(f"{COFFER_TOOL_PREFIX}resume")
    assert resume_tool is not None
    got = await resume_tool.handler({"cwd": handoff.cwd})
    assert got["found"] is True
    assert "step 3" in got["body"]
    assert got["branch"] == "work"
    assert "可能已过期" in got["note"]  # staleness annotation present


@pytest.mark.acceptance(spec="007-memory", scenario="resume reports no handoff for a fresh branch")
async def test_resume_not_found(handoff) -> None:
    reg = BuiltinToolRegistry()
    register_memory_builtin_tools(
        reg, memory_service=handoff.memory_service, handoff_service=handoff.svc
    )
    resume_tool = reg.get(f"{COFFER_TOOL_PREFIX}resume")
    assert resume_tool is not None
    got = await resume_tool.handler({"cwd": handoff.cwd})
    assert got["found"] is False
