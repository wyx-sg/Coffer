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
    """Full scenario: set writes the per-branch scene, resume returns it with a
    freshness note, AND the handoff is never returned by ``coffer__recall``."""
    reg = BuiltinToolRegistry()
    register_memory_builtin_tools(
        reg, memory_service=handoff.memory_service, handoff_service=handoff.svc
    )
    set_tool = reg.get(f"{COFFER_TOOL_PREFIX}set_handoff")
    resume_tool = reg.get(f"{COFFER_TOOL_PREFIX}resume")
    recall_tool = reg.get(f"{COFFER_TOOL_PREFIX}recall")
    assert set_tool is not None
    assert resume_tool is not None
    assert recall_tool is not None

    secret = "ZZ_HANDOFF_SECRET_ZZ"
    out = await set_tool.handler({"body": f"{secret} at step 3; next step 4", "cwd": handoff.cwd})
    assert out["status"] == "saved"
    assert out["branch"] == "work"

    got = await resume_tool.handler({"cwd": handoff.cwd})
    assert got["found"] is True
    assert "step 3" in got["body"]
    assert got["branch"] == "work"
    assert "可能已过期" in got["note"]  # staleness annotation present

    # ...and the handoff is NEVER returned by recall (any mode; grep is the only
    # lane that recurses into handoff/).
    for mode in ("grep", "keyword", "vector"):
        res = await recall_tool.handler(
            {"query": secret, "mode": mode, "top_k": 20, "cwd": handoff.cwd}
        )
        leaked = [h for h in res["hits"] if secret in h["text"]]
        assert leaked == [], f"handoff leaked into coffer__recall(mode={mode!r}): {leaked}"


async def test_handoff_never_returned_by_recall(handoff) -> None:
    """The recall-isolation guarantee: a saved handoff body MUST NOT surface in
    ``coffer__recall`` — not even in ``grep`` mode, which (unlike keyword/vector)
    descends into the store's ``handoff/`` subdir. Regression for the leak where
    a handoff file parsed gracefully into a fake fact and was emitted as a hit."""
    reg = BuiltinToolRegistry()
    register_memory_builtin_tools(
        reg, memory_service=handoff.memory_service, handoff_service=handoff.svc
    )
    set_tool = reg.get(f"{COFFER_TOOL_PREFIX}set_handoff")
    recall_tool = reg.get(f"{COFFER_TOOL_PREFIX}recall")
    assert set_tool is not None
    assert recall_tool is not None

    secret = "ZZ_HANDOFF_SECRET_ZZ"
    out = await set_tool.handler({"body": f"{secret} continue at step 4", "cwd": handoff.cwd})
    assert out["status"] == "saved"

    # grep mode is the ONLY lane that recurses into handoff/ — assert it stays clean.
    for mode in ("grep", "keyword", "vector"):
        res = await recall_tool.handler(
            {"query": secret, "mode": mode, "top_k": 20, "cwd": handoff.cwd}
        )
        leaked = [h for h in res["hits"] if secret in h["text"]]
        assert leaked == [], f"handoff leaked into coffer__recall(mode={mode!r}): {leaked}"


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
