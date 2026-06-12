import coffer.domain.errors as derr
from coffer.domain.errors import (
    CofferError,
    ConfigValidationError,
    ResourceAlreadyExists,
    ResourceNotFound,
    UnknownKind,
)


def test_resource_not_found_carries_ref():
    err = ResourceNotFound("mcp_server", "filesystem")
    assert err.kind == "mcp_server"
    assert err.name == "filesystem"
    assert "mcp_server:filesystem" in str(err)
    assert isinstance(err, CofferError)
    assert err.code == "RESOURCE_NOT_FOUND"


def test_resource_already_exists_carries_ref():
    err = ResourceAlreadyExists("mcp_server", "filesystem")
    assert err.kind == "mcp_server"
    assert err.name == "filesystem"
    assert err.code == "RESOURCE_ALREADY_EXISTS"


def test_unknown_kind_carries_kind():
    err = UnknownKind("nope")
    assert err.kind == "nope"
    assert err.code == "UNKNOWN_KIND"
    assert isinstance(err, CofferError)


def test_config_validation_error_is_coffer_error():
    err = ConfigValidationError("bad config")
    assert err.code == "CONFIG_INVALID"
    assert isinstance(err, CofferError)


def test_workspace_error_codes() -> None:
    assert derr.McpEntryNotFound("x").code == "MCP_ENTRY_NOT_FOUND"
    assert derr.McpEntryToggleUnsupported("claude_code").code == "MCP_ENTRY_TOGGLE_UNSUPPORTED"
    assert derr.McpEntryProtected("coffer").code == "MCP_ENTRY_PROTECTED"
    assert derr.McpEntrySourceAmbiguous("jira").code == "MCP_ENTRY_SOURCE_AMBIGUOUS"
    assert derr.AdoptSecretUnresolved(["API_TOKEN"]).code == "ADOPT_SECRET_UNRESOLVED"
    assert derr.AgentConfigParseError("p", "bad").code == "AGENT_CONFIG_PARSE_ERROR"
    assert derr.PluginNotFound("a@b").code == "PLUGIN_NOT_FOUND"
    assert derr.PluginUninstallUnsupported("claude_code").code == "PLUGIN_UNINSTALL_UNSUPPORTED"
    assert derr.ConfigFileStale("settings").code == "CONFIG_FILE_STALE"
    assert derr.UnmanagedSkillNotFound("s").code == "UNMANAGED_SKILL_NOT_FOUND"
    assert derr.UnmanagedSkillInvalid("s", "no SKILL.md").code == "UNMANAGED_SKILL_INVALID"


def test_workspace_error_messages_and_attrs() -> None:
    secrets = derr.AdoptSecretUnresolved(["B_TOKEN", "A_KEY"])
    assert secrets.keys == ["A_KEY", "B_TOKEN"]  # sorted, deterministic message
    assert "A_KEY, B_TOKEN" in str(secrets)
    assert "jira" in str(derr.McpEntrySourceAmbiguous("jira"))
    assert "coffer" in str(derr.McpEntryProtected("coffer"))
    assert "cannot parse p: bad" in str(derr.AgentConfigParseError("p", "bad"))
    assert "re-read and retry" in str(derr.ConfigFileStale("settings"))
    assert "no SKILL.md" in str(derr.UnmanagedSkillInvalid("s", "no SKILL.md"))
