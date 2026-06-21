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


async def test_list_stores_codex_returns_empty(tmp_path: pathlib.Path) -> None:
    cfg_dir = tmp_path / ".codex"
    # Even with a projects/.../memory tree present, codex has no native layout.
    _write(cfg_dir / "projects" / "-X" / "memory" / "a.md")

    svc = AgentNativeMemoryService(
        agent_service=_FakeAgents(name="cx", config={"type": "codex", "config_dir": str(cfg_dir)}),
        scanner=FileNativeMemoryScanner(),
    )

    assert await svc.list_stores("cx") == []


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
