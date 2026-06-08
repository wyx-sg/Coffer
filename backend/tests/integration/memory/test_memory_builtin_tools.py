"""Integration: the memory built-in MCP tools."""

from __future__ import annotations

import pytest

from coffer.application.builtin_tools import COFFER_TOOL_PREFIX, BuiltinToolRegistry
from coffer.application.memory.builtin_tools import register_memory_builtin_tools

pytestmark = pytest.mark.asyncio


def _registry(mem) -> BuiltinToolRegistry:
    reg = BuiltinToolRegistry()
    register_memory_builtin_tools(reg, memory_service=mem.service)
    return reg


@pytest.mark.acceptance(
    spec="007-memory", scenario="built-in memory tools appear in client tool list"
)
async def test_memory_tools_registered(mem) -> None:
    reg = _registry(mem)
    names = {t.name for t in reg.list()}
    assert names == {"recall", "remember", "update_memory", "forget", "list_memory"}
    assert reg.is_builtin(f"{COFFER_TOOL_PREFIX}recall")


async def test_remember_defaults_to_project_scope(mem) -> None:
    reg = _registry(mem)
    remember = reg.get(f"{COFFER_TOOL_PREFIX}remember")
    assert remember is not None
    out = await remember.handler(
        {"text": "uses pnpm not npm", "cwd": mem.project_cwd, "name": "pkg-manager"}
    )
    assert out["scope"] == "project"
    assert out["status"] == "created"


async def test_recall_tool_spans_scopes(mem) -> None:
    reg = _registry(mem)
    remember = reg.get(f"{COFFER_TOOL_PREFIX}remember")
    recall = reg.get(f"{COFFER_TOOL_PREFIX}recall")
    assert remember is not None and recall is not None
    await remember.handler(
        {"text": "global fact about quokkas", "scope": "global", "cwd": mem.project_cwd}
    )
    await remember.handler(
        {"text": "project fact about quokkas", "scope": "project", "cwd": mem.project_cwd}
    )
    out = await recall.handler({"query": "quokkas", "cwd": mem.project_cwd, "top_k": 10})
    assert len(out["hits"]) >= 2
    sources = {h["source"].split(":")[0] for h in out["hits"]}
    assert {"global", "project"} <= sources


async def test_update_and_forget_by_id(mem) -> None:
    reg = _registry(mem)
    remember = reg.get(f"{COFFER_TOOL_PREFIX}remember")
    update = reg.get(f"{COFFER_TOOL_PREFIX}update_memory")
    forget = reg.get(f"{COFFER_TOOL_PREFIX}forget")
    recall = reg.get(f"{COFFER_TOOL_PREFIX}recall")
    assert all(t is not None for t in (remember, update, forget, recall))
    created = await remember.handler({"text": "original kangaroo note", "cwd": mem.project_cwd})
    fact_id = created["id"]
    await update.handler({"id": fact_id, "text": "updated dingo note", "cwd": mem.project_cwd})
    out = await recall.handler({"query": "dingo", "cwd": mem.project_cwd})
    assert any("dingo" in h["text"] for h in out["hits"])
    await forget.handler({"id": fact_id, "cwd": mem.project_cwd})
    gone = await recall.handler({"query": "dingo", "cwd": mem.project_cwd})
    assert gone["hits"] == []


async def test_recall_grep_mode_maps_to_keyword_and_never_raises(mem) -> None:
    # ``grep`` is not a passage mode; memory recall maps it to ``keyword`` at the
    # boundary, so recalling with ``mode="grep"`` returns hits instead of raising
    # ``ValueError("grep is not a passage mode")`` (finding #1).
    reg = _registry(mem)
    remember = reg.get(f"{COFFER_TOOL_PREFIX}remember")
    recall = reg.get(f"{COFFER_TOOL_PREFIX}recall")
    assert remember is not None and recall is not None
    await remember.handler({"text": "ships via make release", "cwd": mem.project_cwd})

    # The tool no longer advertises grep, but a grep value must still be safe.
    out = await recall.handler({"query": "make release", "cwd": mem.project_cwd, "mode": "grep"})
    assert any("make release" in h["text"] for h in out["hits"])

    # The deeper bug: a store whose default_mode is grep must recall, not crash.
    from coffer.domain.memory.config import MemoryStoreConfig
    from coffer.domain.resource import ResourceRef

    ref = ResourceRef("memory", "global")
    await mem.service.add_fact_to_store(
        store_name="global", name="g", description="", body="global make release note", actor="user"
    )
    cfg = MemoryStoreConfig(retrieval_modes=["grep", "keyword"], default_mode="grep")
    await mem.resources.update_config(ref, new_config=cfg.model_dump(mode="json"), actor="user")
    hits, eff_mode, _ = await mem.service.recall_in_store(
        store_name="global", query="make release", mode=None
    )
    assert any("make release" in h.text for h in hits)
    assert eff_mode == "keyword"  # grep degrades to keyword, never surfaces grep


async def test_recall_tool_excludes_grep_from_mode_enum(mem) -> None:
    # Memory recall serves only passage modes, so the advertised enum must not
    # include the dead ``grep`` mode (finding #23).
    reg = _registry(mem)
    recall = reg.get(f"{COFFER_TOOL_PREFIX}recall")
    assert recall is not None
    assert recall.input_schema["properties"]["mode"]["enum"] == ["keyword", "vector"]


async def test_remember_rejects_empty_text(mem) -> None:
    reg = _registry(mem)
    remember = reg.get(f"{COFFER_TOOL_PREFIX}remember")
    assert remember is not None
    with pytest.raises(ValueError, match="text"):
        await remember.handler({"text": "   ", "cwd": mem.project_cwd})


async def test_list_memory_tool(mem) -> None:
    reg = _registry(mem)
    remember = reg.get(f"{COFFER_TOOL_PREFIX}remember")
    list_tool = reg.get(f"{COFFER_TOOL_PREFIX}list_memory")
    assert remember is not None and list_tool is not None
    await remember.handler({"text": "fact A about emus", "cwd": mem.project_cwd})
    out = await list_tool.handler({"scope": "project", "cwd": mem.project_cwd})
    assert out["scope"] == "project"
    assert out["total"] == 1
    assert out["facts"][0]["actor"] == "agent"
