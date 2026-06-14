"""Agent-workspace domain errors (specs 004/005 amendment).

Split out of ``coffer.domain.errors`` for the file-size limit. These cover the
workspace facets of the agent and skill kinds: MCP config entries, plugins,
per-child config-file edits, and unmanaged-skill adoption.
"""

from __future__ import annotations

from coffer.domain.error_base import CofferError


class McpEntryNotFound(CofferError):  # noqa: N818
    """A named MCP config entry does not exist in any agent config file. Maps to 404."""

    code = "MCP_ENTRY_NOT_FOUND"

    def __init__(self, entry: str) -> None:
        super().__init__(f"MCP entry not found: {entry}")
        self.entry = entry


class McpEntryToggleUnsupported(CofferError):  # noqa: N818
    """The agent type does not support a per-entry enabled flag. Maps to 422."""

    code = "MCP_ENTRY_TOGGLE_UNSUPPORTED"

    def __init__(self, agent_type: str) -> None:
        super().__init__(f"per-entry enabled flag is not supported by {agent_type}")
        self.agent_type = agent_type


class McpEntryProtected(CofferError):  # noqa: N818
    """The entry is Coffer's own gateway entry and must not be mutated directly. Maps to 422."""

    code = "MCP_ENTRY_PROTECTED"

    def __init__(self, entry: str) -> None:
        super().__init__(
            f"entry {entry!r} is Coffer's own gateway entry; use the mcp-install operations"
        )
        self.entry = entry


class McpEntrySourceAmbiguous(CofferError):  # noqa: N818
    """The entry exists in multiple config files; the caller must name the source. Maps to 422."""

    code = "MCP_ENTRY_SOURCE_AMBIGUOUS"

    def __init__(self, entry: str) -> None:
        super().__init__(f"entry {entry!r} exists in multiple config files; specify the source")
        self.entry = entry


class AdoptSecretUnresolved(CofferError):  # noqa: N818
    """Secret-like env keys in a config snippet have no keychain mapping. Maps to 422."""

    code = "ADOPT_SECRET_UNRESOLVED"

    def __init__(self, keys: list[str]) -> None:
        self.keys = sorted(keys)
        super().__init__("secret-like env keys need a keychain mapping: " + ", ".join(self.keys))


class AgentConfigParseError(CofferError):
    """An agent config file could not be parsed. Maps to 422."""

    code = "AGENT_CONFIG_PARSE_ERROR"

    def __init__(self, path: str, detail: str) -> None:
        super().__init__(f"cannot parse {path}: {detail}")
        self.path = path
        self.detail = detail


class PluginNotFound(CofferError):  # noqa: N818
    """A plugin identifier does not match any installed plugin. Maps to 404."""

    code = "PLUGIN_NOT_FOUND"

    def __init__(self, plugin_id: str) -> None:
        super().__init__(f"plugin not found: {plugin_id}")
        self.plugin_id = plugin_id


class PluginUninstallUnsupported(CofferError):  # noqa: N818
    """The agent type requires its own tooling to uninstall plugins. Maps to 422."""

    code = "PLUGIN_UNINSTALL_UNSUPPORTED"

    def __init__(self, agent_type: str) -> None:
        super().__init__(f"{agent_type} plugins must be uninstalled with the agent's own tooling")
        self.agent_type = agent_type


class PluginToggleUnsupported(CofferError):  # noqa: N818
    """The agent type does not support enabling/disabling plugins via Coffer. Maps to 422."""

    code = "PLUGIN_TOGGLE_UNSUPPORTED"

    def __init__(self, agent_type: str) -> None:
        super().__init__(f"{agent_type} plugins cannot be toggled through Coffer")
        self.agent_type = agent_type


class McpInstallUnsupported(CofferError):  # noqa: N818
    """The agent type does not declare an MCP injection target. Maps to 422."""

    code = "MCP_INSTALL_UNSUPPORTED"

    def __init__(self, agent_type: str) -> None:
        super().__init__(f"agent type {agent_type!r} does not support Coffer MCP install")
        self.agent_type = agent_type


class ConfigFileStale(CofferError):  # noqa: N818
    """The file changed on disk since it was read; re-read and retry. Maps to 409."""

    code = "CONFIG_FILE_STALE"

    def __init__(self, key: str) -> None:
        super().__init__(f"config file {key!r} changed on disk since last read; re-read and retry")
        self.key = key


class UnmanagedSkillNotFound(CofferError):  # noqa: N818
    """An unmanaged skill name does not correspond to any discovered skill. Maps to 404."""

    code = "UNMANAGED_SKILL_NOT_FOUND"

    def __init__(self, name: str) -> None:
        super().__init__(f"unmanaged skill not found: {name}")
        self.name = name


class UnmanagedSkillInvalid(CofferError):  # noqa: N818
    """An unmanaged skill cannot be adopted because its folder is invalid. Maps to 422."""

    code = "UNMANAGED_SKILL_INVALID"

    def __init__(self, name: str, reason: str) -> None:
        super().__init__(f"unmanaged skill {name!r} cannot be adopted: {reason}")
        self.name = name
        self.reason = reason


class SkillDeliveryUnsupported(CofferError):  # noqa: N818
    """The agent's skill-delivery mode is a recognized but not-yet-delivered
    extension point (Cursor ``rules_mdc`` / Hermes ``external_dir``). Coffer
    refuses to mis-deliver via the folder model. Maps to 422."""

    code = "SKILL_DELIVERY_UNSUPPORTED"

    def __init__(self, agent_type: str, mode: str) -> None:
        super().__init__(
            f"skill delivery for agent type {agent_type!r} (mode {mode!r}) is not yet supported"
        )
        self.agent_type = agent_type
        self.mode = mode
