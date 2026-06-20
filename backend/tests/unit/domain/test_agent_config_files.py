"""Unit tests for the config-file allowlist + format validation.

Covers spec 004 scenarios: list curated files, allowlist enforcement, and
malformed structured content rejection (domain half).
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.domain.agent.config_files import (
    ConfigFileFormat,
    ConfigFileKind,
    config_files_for,
    spec_for,
    validate_child_relpath,
    validate_content,
)
from coffer.domain.agent.types import AgentType
from coffer.domain.errors import ConfigFileFormatInvalid, ConfigFileNotAllowed


def test_claude_code_allowlist(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    specs = config_files_for(AgentType.CLAUDE_CODE)
    keys = [s.key for s in specs]
    assert keys == ["settings", "settings_local", "global", "instructions", "subagents"]
    by_key = {s.key: s for s in specs}
    assert by_key["settings"].path == tmp_path / ".claude" / "settings.json"
    assert by_key["settings"].format is ConfigFileFormat.JSON
    # The global config lives at the home root, not under ~/.claude.
    assert by_key["global"].path == tmp_path / ".claude.json"
    assert by_key["instructions"].path == tmp_path / ".claude" / "CLAUDE.md"
    assert by_key["instructions"].format is ConfigFileFormat.MARKDOWN


def test_codex_allowlist(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    specs = config_files_for(AgentType.CODEX)
    by_key = {s.key: s for s in specs}
    assert set(by_key) == {"config", "instructions", "hooks"}
    assert by_key["config"].path == tmp_path / ".codex" / "config.toml"
    assert by_key["config"].format is ConfigFileFormat.TOML
    assert by_key["instructions"].path == tmp_path / ".codex" / "AGENTS.md"


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


def test_validate_yaml_accepts_well_formed():
    validate_content(ConfigFileFormat.YAML, "model: gpt\nmcp_servers:\n  fs:\n    command: npx\n")


def test_validate_yaml_rejects_malformed():
    with pytest.raises(ConfigFileFormatInvalid) as ei:
        validate_content(ConfigFileFormat.YAML, "key: [unclosed\n")
    assert ei.value.format == "yaml"


@pytest.mark.parametrize("fmt", [ConfigFileFormat.MARKDOWN, ConfigFileFormat.TEXT])
def test_validate_freeform_always_ok(fmt):
    validate_content(fmt, "anything # at all\n```\nnot json\n```")


# ---------------------------------------------------------------------------
# v2 allowlist tests
# ---------------------------------------------------------------------------


def test_claude_allowlist_v2_keys() -> None:
    keys = [s.key for s in config_files_for(AgentType.CLAUDE_CODE)]
    assert keys == ["settings", "settings_local", "global", "instructions", "subagents"]
    sub = spec_for(AgentType.CLAUDE_CODE, "subagents")
    assert sub.kind is ConfigFileKind.DIRECTORY
    assert sub.path.name == "agents"


def test_codex_allowlist_v2_keys() -> None:
    keys = [s.key for s in config_files_for(AgentType.CODEX)]
    assert keys == ["config", "instructions", "hooks"]
    hooks = spec_for(AgentType.CODEX, "hooks")
    assert hooks.kind is ConfigFileKind.FILE
    assert hooks.path.name == "hooks.json"


def test_memory_key_is_gone() -> None:
    with pytest.raises(ConfigFileNotAllowed):
        spec_for(AgentType.CLAUDE_CODE, "memory")


def test_no_credential_files_in_any_allowlist() -> None:
    forbidden = {"auth.json", ".env"}
    for t in AgentType:
        for spec in config_files_for(t):
            assert spec.path.name not in forbidden, (t, spec.key, spec.path)


@pytest.mark.parametrize(
    "bad", ["../x.md", "/abs.md", "a/../../b.md", "note.txt", "", "a\\b.md", ".hidden/x.md", "x.MD"]
)
def test_child_relpath_rejected(bad: str) -> None:
    with pytest.raises((ConfigFileNotAllowed, ConfigFileFormatInvalid)):
        validate_child_relpath(pathlib.Path("/tmp/root"), bad)


def test_child_relpath_ok_nested() -> None:
    p = validate_child_relpath(pathlib.Path("/tmp/root"), "team/reviewer.md")
    assert p == pathlib.Path("/tmp/root/team/reviewer.md")


def test_child_relpath_ok_bare_and_normalised() -> None:
    root = pathlib.Path("/tmp/root")
    assert validate_child_relpath(root, "x.md") == root / "x.md"
    # redundant separators normalise rather than reject
    assert validate_child_relpath(root, "a//b.md") == root / "a" / "b.md"


def test_child_relpath_requires_absolute_root() -> None:
    with pytest.raises(ValueError):
        validate_child_relpath(pathlib.Path("rel"), "x.md")
