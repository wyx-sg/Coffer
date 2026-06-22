"""Integration tests for AgentNativeMemoryService over a real scanner.

The agent lookup is faked (returns a hand-built agent Resource); the filesystem
scan uses the real ``FileNativeMemoryScanner`` against a temp config-dir tree.
"""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime

import pytest

from coffer.application.agent.native_memory_service import AgentNativeMemoryService
from coffer.domain.errors import ResourceNotFound
from coffer.domain.resource import Resource
from coffer.infrastructure.agent.native_memory_store import FileNativeMemoryScanner

pytestmark = pytest.mark.asyncio


class _FakeAgents:
    """Minimal _AgentLookup: returns one agent Resource, else ResourceNotFound."""

    def __init__(self, *, name: str, config: dict) -> None:
        self._name = name
        self._config = config

    async def get(self, name: str) -> Resource:
        if name != self._name:
            raise ResourceNotFound("agent", name)
        now = datetime(2026, 6, 21, tzinfo=UTC)
        return Resource(
            id=1,
            kind="agent",
            name=name,
            description=None,
            config=self._config,
            enabled=True,
            created_at=now,
            updated_at=now,
        )


def _write(p: pathlib.Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x", encoding="utf-8")


async def test_list_stores_for_claude_code(tmp_path: pathlib.Path) -> None:
    cfg_dir = tmp_path / ".claude"
    _write(cfg_dir / "projects" / "-Users-x-Proj" / "memory" / "a.md")
    _write(cfg_dir / "projects" / "-Users-x-Proj" / "memory" / "b.md")
    _write(cfg_dir / "projects" / "-Users-x-Proj" / "memory" / "MEMORY.md")

    svc = AgentNativeMemoryService(
        agent_service=_FakeAgents(
            name="cc",
            config={"type": "claude_code", "config_dir": str(cfg_dir)},
        ),
        scanner=FileNativeMemoryScanner(),
    )

    stores = await svc.list_stores("cc")
    assert len(stores) == 1
    store = stores[0]
    assert store.project_label == "Proj"
    assert store.project_path == "/Users/x/Proj"
    assert store.slug == "-Users-x-Proj"
    assert store.memory_dir == str(cfg_dir / "projects" / "-Users-x-Proj" / "memory")
    assert store.item_count == 2


async def test_list_stores_label_from_session_cwd_not_lossy_slug(tmp_path: pathlib.Path) -> None:
    """A hyphenated project name (``account-gateway``) under a ``.``-containing
    home (``yuxing.wu``) cannot be recovered by decoding the slug — the slug
    lossily collapses to label ``gateway``. The real cwd from the session log
    fixes both label and path."""
    import json

    cfg_dir = tmp_path / ".claude"
    slug = "-Users-yuxing-wu-WorkEnv-account-gateway"
    _write(cfg_dir / "projects" / slug / "memory" / "a.md")
    (cfg_dir / "projects" / slug / "s.jsonl").write_text(
        json.dumps({"cwd": "/Users/yuxing.wu/WorkEnv/account-gateway"}) + "\n",
        encoding="utf-8",
    )

    svc = AgentNativeMemoryService(
        agent_service=_FakeAgents(
            name="cc", config={"type": "claude_code", "config_dir": str(cfg_dir)}
        ),
        scanner=FileNativeMemoryScanner(),
    )

    store = (await svc.list_stores("cc"))[0]
    assert store.project_label == "account-gateway"
    assert store.project_path == "/Users/yuxing.wu/WorkEnv/account-gateway"


async def test_list_stores_sorted_by_count_then_label(tmp_path: pathlib.Path) -> None:
    cfg_dir = tmp_path / ".claude"
    # -A-zeta: 1 fact ; -A-beta: 1 fact ; -A-alpha: 3 facts
    _write(cfg_dir / "projects" / "-A-zeta" / "memory" / "x.md")
    _write(cfg_dir / "projects" / "-A-beta" / "memory" / "x.md")
    for n in ("a.md", "b.md", "c.md"):
        _write(cfg_dir / "projects" / "-A-alpha" / "memory" / n)

    svc = AgentNativeMemoryService(
        agent_service=_FakeAgents(
            name="cc", config={"type": "claude_code", "config_dir": str(cfg_dir)}
        ),
        scanner=FileNativeMemoryScanner(),
    )

    stores = await svc.list_stores("cc")
    # count desc, then label asc.
    assert [(s.project_label, s.item_count) for s in stores] == [
        ("alpha", 3),
        ("beta", 1),
        ("zeta", 1),
    ]


async def test_list_stores_codex_without_memories_file_is_empty(tmp_path: pathlib.Path) -> None:
    cfg_dir = tmp_path / ".codex"
    # Codex uses a global memories/MEMORY.md, not a projects/ tree — so a stray
    # projects/.../memory dir is ignored and, with no memories file, the list is empty.
    _write(cfg_dir / "projects" / "-X" / "memory" / "a.md")

    svc = AgentNativeMemoryService(
        agent_service=_FakeAgents(name="cx", config={"type": "codex", "config_dir": str(cfg_dir)}),
        scanner=FileNativeMemoryScanner(),
    )

    assert await svc.list_stores("cx") == []


async def test_list_stores_codex_global_groups_by_cwd(tmp_path: pathlib.Path) -> None:
    cfg_dir = tmp_path / ".codex"
    memories = cfg_dir / "memories"
    memories.mkdir(parents=True)
    (memories / "MEMORY.md").write_text(
        "# Task Group: gw one\n\napplies_to: cwd=/p/account-gateway; reuse_rule=x\n\n"
        "## Task 1: a, success\n\n"
        "# Task Group: gw two\n\napplies_to: cwd=/p/account-gateway; reuse_rule=x\n\n"
        "## Task 1: b, success\n\n"
        "# Task Group: bff\n\napplies_to: cwd=/p/account-bff; reuse_rule=x\n\n"
        "## Task 1: c, success\n",
        encoding="utf-8",
    )

    svc = AgentNativeMemoryService(
        agent_service=_FakeAgents(name="cx", config={"type": "codex", "config_dir": str(cfg_dir)}),
        scanner=FileNativeMemoryScanner(),
    )

    stores = await svc.list_stores("cx")
    # One row per distinct cwd, count desc then label; memory_dir is the shared store.
    assert [(s.project_label, s.item_count) for s in stores] == [
        ("account-gateway", 2),
        ("account-bff", 1),
    ]
    assert all(s.memory_dir == str(memories) for s in stores)
    assert stores[0].project_path == "/p/account-gateway"


async def test_list_stores_missing_projects_dir_returns_empty(tmp_path: pathlib.Path) -> None:
    cfg_dir = tmp_path / ".claude"
    cfg_dir.mkdir()  # no projects/ subdir

    svc = AgentNativeMemoryService(
        agent_service=_FakeAgents(
            name="cc", config={"type": "claude_code", "config_dir": str(cfg_dir)}
        ),
        scanner=FileNativeMemoryScanner(),
    )

    assert await svc.list_stores("cc") == []


async def test_list_stores_unknown_agent_raises(tmp_path: pathlib.Path) -> None:
    svc = AgentNativeMemoryService(
        agent_service=_FakeAgents(
            name="cc", config={"type": "claude_code", "config_dir": str(tmp_path)}
        ),
        scanner=FileNativeMemoryScanner(),
    )
    with pytest.raises(ResourceNotFound):
        await svc.list_stores("ghost")
