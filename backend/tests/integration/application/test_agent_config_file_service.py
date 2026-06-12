"""Integration tests for AgentConfigFileService over a real ConfigFileStore.

Covers spec 004 acceptance scenarios: list/read/write config files, missing file
reads empty, malformed content rejected (file unchanged), and unknown key
rejected.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import (
    ConfigFileFormatInvalid,
    ConfigFileNotAllowed,
    ResourceNotFound,
)

pytestmark = pytest.mark.asyncio


async def _register_claude(bundle, home: pathlib.Path):
    """Register a claude_code agent (default skill_dir under HOME/.claude)."""
    (home / ".claude" / "skills").mkdir(parents=True, exist_ok=True)
    return await bundle.svc.register(agent_type=AgentType.CLAUDE_CODE, name="cc", actor="cli")


@pytest.mark.acceptance(spec="004-agent-registry", scenario="list an agent's config files")
async def test_list_files_reports_existence(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_claude(agent_bundle, tmp_path)
    # Create one of the files so we can assert exists/size.
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text('{"theme": "dark"}', encoding="utf-8")

    files = await agent_bundle.config_files.list_files("cc")
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
    assert by_key["instructions"].exists is False
    assert by_key["instructions"].size is None
    # subagents is a directory entry
    assert by_key["subagents"].kind == "directory"
    # agents/ dir doesn't exist yet → exists=False, files=None
    assert by_key["subagents"].exists is False
    assert by_key["subagents"].files is None


@pytest.mark.acceptance(spec="004-agent-registry", scenario="list a directory config entry's files")
async def test_list_files_subagents_directory_with_children(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_claude(agent_bundle, tmp_path)
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "helper.md").write_text("# Helper", encoding="utf-8")

    files = await agent_bundle.config_files.list_files("cc")
    by_key = {f.key: f for f in files}
    entry = by_key["subagents"]
    assert entry.exists is True
    assert entry.files is not None
    assert len(entry.files) == 1
    assert entry.files[0].relpath == "helper.md"


@pytest.mark.acceptance(spec="004-agent-registry", scenario="read an existing config file")
async def test_read_existing(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_claude(agent_bundle, tmp_path)
    (tmp_path / ".claude" / "settings.json").write_text('{"a": 1}', encoding="utf-8")

    out = await agent_bundle.config_files.read_file("cc", "settings")
    assert out.exists is True
    assert out.content == '{"a": 1}'
    assert out.format.value == "json"
    assert out.fingerprint != ""
    assert out.memory_block is False


@pytest.mark.acceptance(spec="004-agent-registry", scenario="read a not-yet-created config file")
async def test_read_missing_is_empty_and_no_create(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_claude(agent_bundle, tmp_path)

    out = await agent_bundle.config_files.read_file("cc", "instructions")
    assert out.exists is False
    assert out.content == ""
    assert out.fingerprint == ""
    assert not (tmp_path / ".claude" / "CLAUDE.md").exists()


async def test_read_file_directory_key_rejected(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_claude(agent_bundle, tmp_path)
    with pytest.raises(ConfigFileNotAllowed):
        await agent_bundle.config_files.read_file("cc", "subagents")


@pytest.mark.acceptance(spec="004-agent-registry", scenario="save a config file with valid content")
async def test_write_valid_atomic_with_backup_and_audit(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_claude(agent_bundle, tmp_path)
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text('{"theme": "light"}', encoding="utf-8")

    info = await agent_bundle.config_files.write_file(
        "cc", "settings", '{"theme": "dark"}', actor="cli"
    )

    # File holds the new content; a .bak preserves the prior version.
    assert settings.read_text(encoding="utf-8") == '{"theme": "dark"}'
    assert (tmp_path / ".claude" / "settings.json.bak").read_text(
        encoding="utf-8"
    ) == '{"theme": "light"}'
    # Returned metadata reflects the refreshed file.
    assert info.key == "settings"
    assert info.exists is True
    assert info.size == len('{"theme": "dark"}')
    assert info.kind == "file"
    # Read-back through the service agrees.
    out = await agent_bundle.config_files.read_file("cc", "settings")
    assert out.content == '{"theme": "dark"}'
    # An audit entry was recorded.
    entries = await agent_bundle.audit.query(
        event_type=AuditEventType.AGENT_CONFIG_FILE_WRITTEN.value
    )
    assert len(entries) == 1
    assert entries[0].resource_kind == "agent"
    assert entries[0].resource_name == "cc"
    assert entries[0].actor == "cli"
    assert entries[0].details == {"key": "settings"}


@pytest.mark.acceptance(spec="004-agent-registry", scenario="reject malformed config-file content")
async def test_write_malformed_rejected_file_unchanged(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_claude(agent_bundle, tmp_path)
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text('{"theme": "light"}', encoding="utf-8")

    with pytest.raises(ConfigFileFormatInvalid):
        await agent_bundle.config_files.write_file("cc", "settings", "{not json")

    # The on-disk file is untouched and no .bak was created.
    assert settings.read_text(encoding="utf-8") == '{"theme": "light"}'
    assert not (tmp_path / ".claude" / "settings.json.bak").exists()
    # No audit entry for the rejected write.
    entries = await agent_bundle.audit.query(
        event_type=AuditEventType.AGENT_CONFIG_FILE_WRITTEN.value
    )
    assert entries == []


async def test_write_unknown_key_rejected_no_fs_access(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_claude(agent_bundle, tmp_path)
    with pytest.raises(ConfigFileNotAllowed):
        await agent_bundle.config_files.write_file("cc", "nope", "x")


@pytest.mark.acceptance(
    spec="004-agent-registry", scenario="reject config-file key outside the allowlist"
)
async def test_unknown_key_rejected_no_fs_access(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_claude(agent_bundle, tmp_path)
    with pytest.raises(ConfigFileNotAllowed):
        await agent_bundle.config_files.read_file("cc", "../../etc/passwd")
    with pytest.raises(ConfigFileNotAllowed):
        await agent_bundle.config_files.read_file("cc", "config")  # codex key, not claude_code


async def test_unknown_agent_raises_not_found(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(ResourceNotFound):
        await agent_bundle.config_files.list_files("nope")


@pytest.mark.acceptance(
    spec="004-agent-registry", scenario="create a file inside a directory entry"
)
async def test_write_child_and_read_child(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_claude(agent_bundle, tmp_path)

    info = await agent_bundle.config_files.write_child(
        "cc", "subagents", "helper.md", "# Helper agent", actor="cli"
    )
    # Returns refreshed directory info.
    assert info.kind == "directory"
    assert info.exists is True
    assert info.files is not None
    assert any(e.relpath == "helper.md" for e in info.files)

    # Read back the child.
    out = await agent_bundle.config_files.read_child("cc", "subagents", "helper.md")
    assert out.exists is True
    assert out.content == "# Helper agent"
    assert out.fingerprint != ""

    # Audit entry recorded.
    entries = await agent_bundle.audit.query(
        event_type=AuditEventType.AGENT_CONFIG_FILE_WRITTEN.value
    )
    assert len(entries) == 1
    assert entries[0].details == {"key": "subagents", "child": "helper.md"}


@pytest.mark.acceptance(
    spec="004-agent-registry", scenario="delete a file inside a directory entry"
)
async def test_delete_child(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_claude(agent_bundle, tmp_path)
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "old.md").write_text("# Old", encoding="utf-8")

    await agent_bundle.config_files.delete_child("cc", "subagents", "old.md", actor="cli")

    assert not (agents_dir / "old.md").exists()
    entries = await agent_bundle.audit.query(
        event_type=AuditEventType.AGENT_CONFIG_FILE_DELETED.value
    )
    assert len(entries) == 1
    assert entries[0].details == {"key": "subagents", "child": "old.md"}


async def test_child_symlink_escape_rejected_on_real_fs(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_claude(agent_bundle, tmp_path)
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside.md"
    outside.write_text("# secret")
    (agents_dir / "evil.md").symlink_to(outside)
    with pytest.raises(ConfigFileNotAllowed):
        await agent_bundle.config_files.read_child("cc", "subagents", "evil.md")
    with pytest.raises(ConfigFileNotAllowed):
        await agent_bundle.config_files.delete_child("cc", "subagents", "evil.md", actor="cli")
    assert outside.read_text() == "# secret"
