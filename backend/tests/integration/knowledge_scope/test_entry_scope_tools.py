"""Integration: the eight built-in MCP tools over the two auto-scopes.

The sibling ``knowledge_documents/test_document_scope_tools.py`` drives the same
eight against a named collection. Here the material is entries an agent writes
and the scope is resolved from its cwd — what the pre-merge ``memory`` tools
existed for.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.application.builtin_tools import COFFER_TOOL_PREFIX, BuiltinToolRegistry
from coffer.application.knowledge.builtin_tools import register_knowledge_builtin_tools
from coffer.application.knowledge.document_tools import register_document_builtin_tools
from coffer.application.knowledge.handoff import HandoffService
from coffer.domain.knowledge.document import KIND_KNOWLEDGE
from coffer.domain.knowledge.scope import project_scope_name
from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.knowledge_scope.scope_fs import git_branch, project_ulid

pytestmark = pytest.mark.asyncio


def _registry(mem) -> BuiltinToolRegistry:
    reg = BuiltinToolRegistry()
    handoff_service = HandoffService(
        scope=mem.scope,
        git_branch=git_branch,
        scope_dir=paths.scope_dir,
        now=lambda: datetime.now(tz=UTC),
    )
    register_knowledge_builtin_tools(
        reg, knowledge_service=mem.service, handoff_service=handoff_service
    )
    register_document_builtin_tools(reg, resources=mem.resources, knowledge_service=mem.service)
    return reg


def _tool(reg: BuiltinToolRegistry, name: str):
    tool = reg.get(f"{COFFER_TOOL_PREFIX}{name}")
    assert tool is not None, f"{name} not registered"
    return tool


@pytest.mark.acceptance(
    spec="007-memory", scenario="built-in memory tools appear in client tool list"
)
async def test_the_eight_tools_are_registered(mem) -> None:
    reg = _registry(mem)
    assert {t.name for t in reg.list()} == {
        "search",
        "grep",
        "read",
        "list",
        "write",
        "delete",
        "set_handoff",
        "resume",
    }
    assert reg.is_builtin(f"{COFFER_TOOL_PREFIX}search")


async def test_write_defaults_to_the_cwd_project_scope(mem) -> None:
    """No scope argument: the cwd decides, so the common case needs none."""
    reg = _registry(mem)
    out = await _tool(reg, "write").handler(
        {"text": "uses pnpm not npm", "cwd": mem.project_cwd, "title": "pkg-manager"}
    )
    assert out["scope"].startswith("project-")
    assert out["type"] == "entry"
    assert out["status"] == "created"
    assert out["title"] == "pkg-manager"


async def test_write_falls_back_to_global_outside_a_project(mem) -> None:
    """No cwd and no scope: ``global`` still works rather than erroring."""
    reg = _registry(mem)
    out = await _tool(reg, "write").handler({"text": "prefers tabs", "title": "tabs"})
    assert out["scope"] == "global"


async def test_write_accepts_legacy_name_alias(mem) -> None:
    # ``name`` is the deprecated alias of ``title`` — live agent calls that still
    # send ``name`` must keep working, canonicalised to ``title`` on the way out.
    reg = _registry(mem)
    out = await _tool(reg, "write").handler(
        {"text": "uses pnpm not npm", "cwd": mem.project_cwd, "name": "legacy-title"}
    )
    assert out["status"] == "created"
    assert out["title"] == "legacy-title"


async def test_search_spans_project_and_global_by_default(mem) -> None:
    """An implicit scope folds in ``global``: knowledge filed globally is meant
    to follow the user everywhere."""
    reg = _registry(mem)
    write = _tool(reg, "write")
    project_scope = (await write.handler({"text": "seed", "cwd": mem.project_cwd}))["scope"]
    await write.handler({"text": "global fact about quokkas", "scope": "global"})
    await write.handler({"text": "project fact about quokkas", "scope": project_scope})
    out = await _tool(reg, "search").handler(
        {"query": "quokkas", "cwd": mem.project_cwd, "top_k": 10}
    )
    assert len(out["hits"]) >= 2
    sources = {h["source"].split(":")[0] for h in out["hits"]}
    assert {"global", "project"} <= sources


async def test_the_pre_merge_tool_names_are_gone(mem) -> None:
    """Twelve names over two kinds became eight over one. None of the old names
    survives as an alias — an agent reads the descriptions, not a synonym list."""
    reg = _registry(mem)
    for gone in (
        "recall",
        "remember",
        "list_memory",
        "search_knowledge",
        "grep_knowledge",
        "read_document",
        "list_knowledge_bases",
        "add_document",
        "edit_document",
        "delete_document",
        "update_memory",
        "forget",
    ):
        assert reg.get(f"{COFFER_TOOL_PREFIX}{gone}") is None, gone


@pytest.mark.acceptance(
    spec="007-memory", scenario="remembered items are stored in the knowledge lane"
)
async def test_write_lands_in_the_knowledge_inbox(mem) -> None:
    """A written entry lands under the project scope's ``knowledge/inbox/`` (never
    the scope root), no ``MEMORY.md`` is generated, and ``search`` returns it."""
    from pathlib import Path

    reg = _registry(mem)
    await _tool(reg, "write").handler(
        {"text": "the wombat fact about burrows", "cwd": mem.project_cwd, "name": "wombat"}
    )
    store_dir = paths.scope_dir(project_scope_name(project_ulid(str(Path(mem.project_cwd).parent))))
    assert len(list(paths.inbox_dir(store_dir).glob("*.md"))) == 1  # under knowledge/inbox/
    assert list(store_dir.glob("*.md")) == []  # never at the store root
    assert not (store_dir / "MEMORY.md").exists()  # no derived index
    out = await _tool(reg, "search").handler({"query": "wombat burrows", "cwd": mem.project_cwd})
    assert any("wombat" in h["text"] for h in out["hits"])


async def test_search_resolves_the_mode_internally(mem) -> None:
    # The MCP surface never selects a mode; the service resolves it from the
    # scope's ``default_mode`` (grep here) and serves it for real (FR-008).
    reg = _registry(mem)
    await _tool(reg, "write").handler({"text": "ships via make release", "cwd": mem.project_cwd})

    out = await _tool(reg, "search").handler({"query": "make release", "cwd": mem.project_cwd})
    assert any("make release" in h["text"] for h in out["hits"])

    from coffer.domain.knowledge.scope_config import KnowledgeConfig
    from coffer.domain.resource import ResourceRef

    ref = ResourceRef(KIND_KNOWLEDGE, "global")
    await mem.service.add_fact_to_scope(
        scope_name="global",
        title="g",
        description="",
        body="global make release note",
        actor="user",
    )
    cfg = KnowledgeConfig(retrieval_modes=["grep", "keyword"], default_mode="grep")
    await mem.resources.update_config(ref, new_config=cfg.model_dump(mode="json"), actor="user")
    # Internal callers still pass mode (here None ⇒ store default_mode=grep).
    hits, eff_mode, _ = await mem.service.recall_in_scope(
        scope_name="global", query="make release", mode=None
    )
    assert any("make release" in h.text for h in hits)
    assert eff_mode == "grep"  # grep is served for real and reported internally


async def test_search_tool_has_no_mode_property(mem) -> None:
    # One query → one answer: the caller asks a question, not for an algorithm.
    reg = _registry(mem)
    assert "mode" not in _tool(reg, "search").input_schema["properties"]


async def test_write_rejects_empty_text(mem) -> None:
    reg = _registry(mem)
    with pytest.raises(ValueError, match="text"):
        await _tool(reg, "write").handler({"text": "   ", "cwd": mem.project_cwd})


async def test_list_shows_the_cwd_scope_then_the_catalogue(mem) -> None:
    reg = _registry(mem)
    await _tool(reg, "write").handler({"text": "fact A about emus", "cwd": mem.project_cwd})
    out = await _tool(reg, "list").handler({"cwd": mem.project_cwd})
    assert out["scope"].startswith("project-")
    assert out["entry_total"] == 1
    assert out["entries"][0]["actor"] == "agent"

    catalogue = await _tool(reg, "list").handler({"all": True})
    assert any(s["scope"] == out["scope"] for s in catalogue["scopes"])


async def test_read_and_delete_resolve_an_entry_id(mem) -> None:
    """``read``/``delete`` take an id from ``search``/``list`` without the caller
    having to say which lane it came from."""
    reg = _registry(mem)
    written = await _tool(reg, "write").handler(
        {"text": "the pangolin fact", "cwd": mem.project_cwd, "title": "pangolin"}
    )
    read = await _tool(reg, "read").handler(
        {"id": written["id"], "scope": written["scope"], "cwd": mem.project_cwd}
    )
    assert read["type"] == "entry"
    assert "pangolin" in read["text"]

    deleted = await _tool(reg, "delete").handler(
        {"id": written["id"], "scope": written["scope"], "cwd": mem.project_cwd}
    )
    assert deleted["deleted"] is True and deleted["type"] == "entry"


async def test_search_serves_grep_via_the_scope_default(mem) -> None:
    """FR-008: search supports grep for real — ripgrep over the files (essential
    for CJK content FTS5 cannot tokenize). The MCP surface never picks a mode; a
    scope whose ``default_mode`` is grep finds CJK content via grep."""
    from coffer.domain.knowledge.scope_config import KnowledgeConfig
    from coffer.domain.resource import ResourceRef

    reg = _registry(mem)
    await _tool(reg, "write").handler(
        {"text": "we deploy with 蓝绿发布 strategy", "scope": "global"}
    )
    ref = ResourceRef(KIND_KNOWLEDGE, "global")
    cfg = KnowledgeConfig(retrieval_modes=["grep", "keyword"], default_mode="grep")
    await mem.resources.update_config(ref, new_config=cfg.model_dump(mode="json"), actor="user")
    out = await _tool(reg, "search").handler({"query": "蓝绿发布", "scope": "global"})
    assert any("蓝绿发布" in h["text"] for h in out["hits"])
    assert out["mode"] == "grep"
