"""Unit tests for the config-file allowlist + format validation.

Covers spec agent-registry scenarios: list curated files, allowlist enforcement, and
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


def test_claude_code_global_config_follows_a_custom_config_dir(monkeypatch, tmp_path):
    """Claude Code run with ``CLAUDE_CONFIG_DIR`` set keeps ``.claude.json``
    INSIDE that dir (probed against Claude Code 2.1.281: ``claude mcp add -s
    user`` wrote ``$CLAUDE_CONFIG_DIR/.claude.json`` and never read
    ``$HOME/.claude.json``), so the ``global`` key must follow it there."""
    monkeypatch.setenv("HOME", str(tmp_path))
    custom = tmp_path / "work-claude"
    by_key = {s.key: s for s in config_files_for(AgentType.CLAUDE_CODE, custom)}
    assert by_key["global"].path == custom / ".claude.json"
    # The config-dir files themselves are unaffected.
    assert by_key["settings"].path == custom / "settings.json"


def test_claude_code_global_config_for_the_default_dir_passed_explicitly(monkeypatch, tmp_path):
    """A registered agent carries its resolved ``config_dir`` even when it is
    the default ``~/.claude`` — that must still mean ``~/.claude.json``."""
    monkeypatch.setenv("HOME", str(tmp_path))
    default = tmp_path / ".claude"
    assert spec_for(AgentType.CLAUDE_CODE, "global", default).path == tmp_path / ".claude.json"


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


def test_validate_freeform_always_ok():
    validate_content(ConfigFileFormat.MARKDOWN, "anything # at all\n```\nnot json\n```")


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


@pytest.mark.acceptance(
    spec="agent-registry", scenario="key each type's instructions file as instructions"
)
def test_every_type_keys_one_markdown_instructions_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    formats = {"json", "toml", "markdown", "text"}
    types = list(AgentType)
    assert types, "no agent types to check"
    for agent_type in types:
        specs = config_files_for(agent_type)
        assert specs, agent_type
        for spec in specs:
            assert spec.key and spec.display_name, (agent_type, spec)
            assert spec.path.is_absolute(), (agent_type, spec)
            assert spec.format.value in formats, (agent_type, spec)
        instructions = [s for s in specs if s.key == "instructions"]
        assert len(instructions) == 1, agent_type
        assert instructions[0].format is ConfigFileFormat.MARKDOWN, agent_type
