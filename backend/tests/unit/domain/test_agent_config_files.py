"""Unit tests for the config-file allowlist + format validation.

Covers spec 004 scenarios: list curated files, allowlist enforcement, and
malformed structured content rejection (domain half).
"""

from __future__ import annotations

import pytest

from coffer.domain.agent.config_files import (
    ConfigFileFormat,
    config_files_for,
    spec_for,
    validate_content,
)
from coffer.domain.agent.types import AgentType
from coffer.domain.errors import ConfigFileFormatInvalid, ConfigFileNotAllowed


def test_claude_code_allowlist(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    specs = config_files_for(AgentType.CLAUDE_CODE)
    keys = [s.key for s in specs]
    assert keys == ["settings", "settings_local", "global", "memory"]
    by_key = {s.key: s for s in specs}
    assert by_key["settings"].path == tmp_path / ".claude" / "settings.json"
    assert by_key["settings"].format is ConfigFileFormat.JSON
    # The global config lives at the home root, not under ~/.claude.
    assert by_key["global"].path == tmp_path / ".claude.json"
    assert by_key["memory"].path == tmp_path / ".claude" / "CLAUDE.md"
    assert by_key["memory"].format is ConfigFileFormat.MARKDOWN


def test_codex_allowlist(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    specs = config_files_for(AgentType.CODEX)
    by_key = {s.key: s for s in specs}
    assert set(by_key) == {"config", "memory"}
    assert by_key["config"].path == tmp_path / ".codex" / "config.toml"
    assert by_key["config"].format is ConfigFileFormat.TOML
    assert by_key["memory"].path == tmp_path / ".codex" / "AGENTS.md"


def test_all_paths_absolute():
    for t in AgentType:
        for spec in config_files_for(t):
            assert spec.path.is_absolute()


def test_spec_for_known_key(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    spec = spec_for(AgentType.CLAUDE_CODE, "settings")
    assert spec.key == "settings"


def test_spec_for_unknown_key_raises():
    with pytest.raises(ConfigFileNotAllowed) as ei:
        spec_for(AgentType.CLAUDE_CODE, "../../etc/passwd")
    assert ei.value.key == "../../etc/passwd"
    assert ei.value.agent_type == "claude_code"


def test_spec_for_key_from_other_type_raises():
    # `config` belongs to codex, not claude_code.
    with pytest.raises(ConfigFileNotAllowed):
        spec_for(AgentType.CLAUDE_CODE, "config")


@pytest.mark.parametrize("text", ['{"a": 1}', "{}", '{"nested": {"x": [1, 2]}}'])
def test_validate_json_accepts_well_formed(text):
    validate_content(ConfigFileFormat.JSON, text)  # no raise


@pytest.mark.parametrize("text", ["{not json}", '{"a": }', "", "trailing,"])
def test_validate_json_rejects_malformed(text):
    with pytest.raises(ConfigFileFormatInvalid) as ei:
        validate_content(ConfigFileFormat.JSON, text)
    assert ei.value.format == "json"


def test_validate_toml_accepts_well_formed():
    validate_content(ConfigFileFormat.TOML, 'a = 1\n[table]\nb = "two"\n')


def test_validate_toml_rejects_malformed():
    with pytest.raises(ConfigFileFormatInvalid) as ei:
        validate_content(ConfigFileFormat.TOML, "a = = 1")
    assert ei.value.format == "toml"


@pytest.mark.parametrize("fmt", [ConfigFileFormat.MARKDOWN, ConfigFileFormat.TEXT])
def test_validate_freeform_always_ok(fmt):
    validate_content(fmt, "anything # at all\n```\nnot json\n```")
