import coffer.domain.workspace_errors as derr
from coffer.domain.errors import (
    CofferError,
    ConfigValidationError,
    ResourceAlreadyExists,
    ResourceNotFound,
    UnknownKind,
)


def test_resource_not_found_carries_what_was_looked_for():
    """The error echoes the caller's own SUBJECT, not a canonical identifier.

    Replaces an assertion that it carried `kind` and `name`: a lookup by uid
    has no name to report, and one that started from a label the user typed
    must say that label back or the message helps nobody.
    """
    by_uid = ResourceNotFound("9f2c1a7b4e8d4c1fa0b3d5e6f7081920")
    assert by_uid.subject == "9f2c1a7b4e8d4c1fa0b3d5e6f7081920"
    assert "9f2c1a7b4e8d4c1fa0b3d5e6f7081920" in str(by_uid)

    by_name = ResourceNotFound.named("mcp_server", "filesystem")
    assert "mcp_server" in str(by_name)
    assert "filesystem" in str(by_name)

    assert isinstance(by_uid, CofferError)
    assert by_uid.code == "RESOURCE_NOT_FOUND"


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
    assert derr.McpEntryProtected("coffer").code == "MCP_ENTRY_PROTECTED"
    assert derr.McpEntrySourceAmbiguous("jira").code == "MCP_ENTRY_SOURCE_AMBIGUOUS"
    assert derr.AdoptSecretUnresolved(["API_TOKEN"]).code == "ADOPT_SECRET_UNRESOLVED"
    assert derr.AgentConfigParseError("p", "bad").code == "AGENT_CONFIG_PARSE_ERROR"
    assert derr.PluginNotFound("a@b").code == "PLUGIN_NOT_FOUND"
    assert derr.PluginToggleUnsupported("claude_code").code == "PLUGIN_TOGGLE_UNSUPPORTED"
    assert derr.PluginUninstallUnsupported("claude_code").code == "PLUGIN_UNINSTALL_UNSUPPORTED"
    assert derr.PluginUninstallFailed("a@b", "exit 1").code == "PLUGIN_UNINSTALL_FAILED"
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
