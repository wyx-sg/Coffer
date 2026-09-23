"""Acceptance coverage for agent-registry config-file scenarios over the real store.

Uses the ``agent_bundle`` fixture (real ``AgentService`` + ``AgentConfigFileService``
on a fresh SQLite and the real ``ConfigFileStore``); ``HOME`` is pointed at
``tmp_path`` so the agent's standard config directory is a temp tree.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.application.agent.config_file_service import MEMORY_BLOCK_MARKER
from coffer.domain.agent.types import AgentType

pytestmark = pytest.mark.asyncio


async def _register_claude(bundle, home: pathlib.Path):
    (home / ".claude" / "skills").mkdir(parents=True, exist_ok=True)
    return await bundle.svc.register(agent_type=AgentType.CLAUDE_CODE, name="cc", actor="cli")


@pytest.mark.acceptance(
    spec="agent-registry", scenario="report each config file's path, folder and existence"
)
async def test_config_file_listing_carries_location_and_existence(
    agent_bundle, tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    agent = await _register_claude(agent_bundle, tmp_path)
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text('{"a": 1}', encoding="utf-8")

    files = {f.key: f for f in await agent_bundle.config_files.list_files(agent.uid)}

    present, missing = files["settings"], files["instructions"]
    for f in (present, missing):
        assert f.display_name
        assert pathlib.Path(f.path).is_absolute()
        assert f.folder_path == str(pathlib.Path(f.path).parent)
    assert (present.path, present.format.value, present.exists) == (str(settings), "json", True)
    assert present.size == len('{"a": 1}')
    assert present.modified_at is not None
    assert missing.path == str(tmp_path / ".claude" / "CLAUDE.md")
    assert missing.exists is False
    assert missing.size is None
    assert missing.modified_at is None


@pytest.mark.acceptance(
    spec="agent-registry/claude-code",
    scenario="list nested subagent files in the agents directory",
)
async def test_subagents_entry_lists_top_level_and_nested_files(
    agent_bundle, tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    agent = await _register_claude(agent_bundle, tmp_path)
    agents_dir = tmp_path / ".claude" / "agents"
    (agents_dir / "team").mkdir(parents=True)
    (agents_dir / "reviewer.md").write_text("# Reviewer", encoding="utf-8")
    (agents_dir / "team" / "planner.md").write_text("# Planner", encoding="utf-8")

    files = {f.key: f for f in await agent_bundle.config_files.list_files(agent.uid)}

    entry = files["subagents"]
    assert entry.kind == "directory"
    assert entry.path == str(agents_dir)
    assert sorted(child.relpath for child in entry.files) == ["reviewer.md", "team/planner.md"]


@pytest.mark.acceptance(
    spec="agent-registry", scenario="annotate a leftover memory block in the instructions file"
)
async def test_legacy_memory_block_is_reported_on_read(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    agent = await _register_claude(agent_bundle, tmp_path)
    instructions = tmp_path / ".claude" / "CLAUDE.md"

    instructions.write_text("# Rules\n\nbe terse\n", encoding="utf-8")
    clean = await agent_bundle.config_files.read_file(agent.uid, "instructions")
    assert clean.memory_block is False

    instructions.write_text(
        f"# Rules\n\n{MEMORY_BLOCK_MARKER}:start -->\nold facts\n<!-- coffer:memory:end -->\n",
        encoding="utf-8",
    )
    before = instructions.read_bytes()
    leftover = await agent_bundle.config_files.read_file(agent.uid, "instructions")
    assert leftover.memory_block is True
    # Detection only: the read neither rewrites nor strips the block.
    assert instructions.read_bytes() == before
