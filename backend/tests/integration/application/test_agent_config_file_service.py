"""Integration tests for AgentConfigFileService over a real ConfigFileStore.

Covers spec agent-registry acceptance scenarios for the config-file listing:
each file's location and existence, and a directory entry's files. The service
serves no content and writes nothing.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.domain.agent.types import AgentType
from coffer.domain.errors import ResourceNotFound

pytestmark = pytest.mark.asyncio


async def _register_claude(bundle, home: pathlib.Path):
    """Register a claude_code agent (default skill_dir under HOME/.claude)."""
    (home / ".claude" / "skills").mkdir(parents=True, exist_ok=True)
    return await bundle.svc.register(agent_type=AgentType.CLAUDE_CODE, actor="cli")


@pytest.mark.acceptance(
    spec="agent-registry", scenario="report each config file's path, folder and existence"
)
async def test_list_files_reports_existence(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    agent = await _register_claude(agent_bundle, tmp_path)
    # Create one of the files so we can assert exists/size.
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text('{"theme": "dark"}', encoding="utf-8")

    files = await agent_bundle.config_files.list_files(agent.uid)
    by_key = {f.key: f for f in files}
    # v2 allowlist: settings, settings_local, global, instructions, subagents
    assert [f.key for f in files] == [
        "settings",
        "settings_local",
        "global",
        "instructions",
        "subagents",
    ]
    assert by_key["settings"].exists is True
    assert by_key["settings"].size == len('{"theme": "dark"}')
    assert by_key["settings"].modified_at is not None
    assert by_key["settings"].kind == "file"
    # Absolute path + containing folder for the read-only open/reveal
    # affordances (see "Open config files in an external editor or reveal them").
    assert by_key["settings"].path == str(settings)
    assert by_key["settings"].folder_path == str(tmp_path / ".claude")
    assert by_key["instructions"].exists is False
    assert by_key["instructions"].size is None
    # subagents is a directory entry
    assert by_key["subagents"].kind == "directory"
    assert by_key["subagents"].path == str(tmp_path / ".claude" / "agents")
    assert by_key["subagents"].folder_path == str(tmp_path / ".claude")
    # agents/ dir doesn't exist yet → exists=False, files=None
    assert by_key["subagents"].exists is False
    assert by_key["subagents"].files is None


@pytest.mark.acceptance(spec="agent-registry", scenario="list a directory config entry's files")
@pytest.mark.acceptance(
    spec="agent-registry/claude-code",
    scenario="list nested subagent files in the agents directory",
)
async def test_list_files_subagents_directory_with_children(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    agent = await _register_claude(agent_bundle, tmp_path)
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "helper.md").write_text("# Helper", encoding="utf-8")
    (agents_dir / "team").mkdir()
    (agents_dir / "team" / "reviewer.md").write_text("# Reviewer", encoding="utf-8")

    files = await agent_bundle.config_files.list_files(agent.uid)
    by_key = {f.key: f for f in files}
    entry = by_key["subagents"]
    assert entry.exists is True
    assert entry.files is not None
    assert entry.kind == "directory"
    assert [f.relpath for f in entry.files] == ["helper.md", "team/reviewer.md"]
    assert entry.files[1].path == str(agents_dir / "team" / "reviewer.md")


async def test_unknown_agent_raises_not_found(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(ResourceNotFound):
        await agent_bundle.config_files.list_files("no-such-uid")
