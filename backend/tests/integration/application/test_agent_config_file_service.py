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
    assert [f.key for f in files] == ["settings", "settings_local", "global", "memory"]
    assert by_key["settings"].exists is True
    assert by_key["settings"].size == len('{"theme": "dark"}')
    assert by_key["settings"].modified_at is not None
    assert by_key["memory"].exists is False
    assert by_key["memory"].size is None


@pytest.mark.acceptance(spec="004-agent-registry", scenario="read an existing config file")
async def test_read_existing(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_claude(agent_bundle, tmp_path)
    (tmp_path / ".claude" / "settings.json").write_text('{"a": 1}', encoding="utf-8")

    out = await agent_bundle.config_files.read_file("cc", "settings")
    assert out.exists is True
    assert out.content == '{"a": 1}'
    assert out.format.value == "json"


@pytest.mark.acceptance(spec="004-agent-registry", scenario="read a not-yet-created config file")
async def test_read_missing_is_empty_and_no_create(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_claude(agent_bundle, tmp_path)

    out = await agent_bundle.config_files.read_file("cc", "memory")
    assert out.exists is False
    assert out.content == ""
    assert not (tmp_path / ".claude" / "CLAUDE.md").exists()


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
