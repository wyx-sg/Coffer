"""Integration: the memory built-in MCP tools."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.application.builtin_tools import COFFER_TOOL_PREFIX, BuiltinToolRegistry
from coffer.application.memory.builtin_tools import register_memory_builtin_tools
from coffer.application.memory.handoff import HandoffService
from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.memory.scope_fs import git_branch, project_ulid

pytestmark = pytest.mark.asyncio


def _registry(mem) -> BuiltinToolRegistry:
    reg = BuiltinToolRegistry()
    handoff_service = HandoffService(
        scope=mem.scope,
        git_branch=git_branch,
        store_dir=paths.memory_store_dir,
        audit=mem.audit,
        now=lambda: datetime.now(tz=UTC),
    )
    register_memory_builtin_tools(reg, memory_service=mem.service, handoff_service=handoff_service)
    return reg


@pytest.mark.acceptance(
    spec="007-memory", scenario="built-in memory tools appear in client tool list"
)
async def test_memory_tools_registered(mem) -> None:
    reg = _registry(mem)
    names = {t.name for t in reg.list()}
    assert names == {
        "recall",
        "remember",
        "list_memory",
        "set_handoff",
        "resume",
    }
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


async def test_update_and_forget_tools_are_removed(mem) -> None:
    """The agent write surface is ``remember`` only — the per-id ``update_memory``
    and ``forget`` MCP tools were removed in the knowledge-lane redesign."""
    reg = _registry(mem)
    assert reg.get(f"{COFFER_TOOL_PREFIX}update_memory") is None
    assert reg.get(f"{COFFER_TOOL_PREFIX}forget") is None


@pytest.mark.acceptance(
    spec="007-memory", scenario="remembered items are stored in the knowledge lane"
)
async def test_remember_writes_into_knowledge_inbox(mem) -> None:
    """A remembered item lands under the project store's ``knowledge/inbox/`` (never
    the store root), no ``MEMORY.md`` is generated, and ``recall`` returns it."""
    from pathlib import Path

    reg = _registry(mem)
    remember = reg.get(f"{COFFER_TOOL_PREFIX}remember")
    recall = reg.get(f"{COFFER_TOOL_PREFIX}recall")
    assert remember is not None and recall is not None
    await remember.handler(
        {"text": "the wombat fact about burrows", "cwd": mem.project_cwd, "name": "wombat"}
    )
    store_dir = paths.memory_store_dir(project_ulid(str(Path(mem.project_cwd).parent)))
    assert len(list(paths.inbox_dir(store_dir).glob("*.md"))) == 1  # under knowledge/inbox/
    assert list(store_dir.glob("*.md")) == []  # never at the store root
    assert not (store_dir / "MEMORY.md").exists()  # no derived index
    out = await recall.handler({"query": "wombat burrows", "cwd": mem.project_cwd})
    assert any("wombat" in h["text"] for h in out["hits"])


async def test_recall_grep_mode_never_raises(mem) -> None:
    # ``grep`` is a real recall mode (ripgrep over the fact files, FR-008); a
    # store whose ``default_mode`` is grep must recall via ripgrep, not crash.
    reg = _registry(mem)
    remember = reg.get(f"{COFFER_TOOL_PREFIX}remember")
    recall = reg.get(f"{COFFER_TOOL_PREFIX}recall")
    assert remember is not None and recall is not None
    await remember.handler({"text": "ships via make release", "cwd": mem.project_cwd})

    out = await recall.handler({"query": "make release", "cwd": mem.project_cwd, "mode": "grep"})
    assert any("make release" in h["text"] for h in out["hits"])

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
    assert eff_mode == "grep"  # grep is served for real and reported as such


async def test_recall_tool_advertises_all_three_modes(mem) -> None:
    # FR-008: recall serves grep, keyword and vector; the enum advertises all.
    reg = _registry(mem)
    recall = reg.get(f"{COFFER_TOOL_PREFIX}recall")
    assert recall is not None
    assert recall.input_schema["properties"]["mode"]["enum"] == ["grep", "keyword", "vector"]


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


@pytest.mark.acceptance(
    spec="007-memory",
    scenario="vector recall falls back when embedding is unconfigured",
)
async def test_recall_tool_reports_vector_fallback(mem) -> None:
    """The MCP ``coffer__recall`` must flag a degraded vector request, like the
    REST recall does (review misalignment #2)."""
    reg = _registry(mem)
    remember = reg.get(f"{COFFER_TOOL_PREFIX}remember")
    recall = reg.get(f"{COFFER_TOOL_PREFIX}recall")
    await remember.handler({"text": "wombat burrows are deep", "scope": "global"})
    out = await recall.handler({"query": "wombat", "mode": "vector"})
    assert out["fallback"] is True
    assert any("wombat" in h["text"] for h in out["hits"])

    keyword = await recall.handler({"query": "wombat", "mode": "keyword"})
    assert keyword["fallback"] is False


async def test_recall_tool_serves_grep_mode(mem) -> None:
    """FR-008: recall supports grep for real — ripgrep over the fact files
    (essential for CJK content FTS5 cannot tokenize)."""
    reg = _registry(mem)
    remember = reg.get(f"{COFFER_TOOL_PREFIX}remember")
    recall = reg.get(f"{COFFER_TOOL_PREFIX}recall")
    await remember.handler({"text": "we deploy with 蓝绿发布 strategy", "scope": "global"})
    out = await recall.handler({"query": "蓝绿发布", "mode": "grep"})
    assert any("蓝绿发布" in h["text"] for h in out["hits"])
    assert out["fallback"] is False
