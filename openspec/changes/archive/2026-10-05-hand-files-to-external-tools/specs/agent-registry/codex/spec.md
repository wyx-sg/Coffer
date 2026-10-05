## MODIFIED Requirements

### Requirement: Uninstall a Codex plugin by editing config.toml
The uninstall strategy of [agent-registry](../spec.md) "Uninstall a plugin by the type's own strategy" for this type MUST be a config edit: remove the `[plugins."…"]` entry from `config.toml` (atomic, with the backup of [agent-registry](../spec.md) "Back up and compare-and-swap every write Coffer makes to an agent's config") and delete that plugin's cache directory. There is no CLI to delegate to and none is required, so `can_uninstall` is true whenever the entry exists.

#### Scenario: uninstall a Codex plugin
- **GIVEN** a registered `codex` agent with an installed plugin
- **WHEN** the user uninstalls it
- **THEN** the `[plugins."…"]` entry is removed from `config.toml` (atomic + backup), the plugin's cache directory under `~/.codex/plugins/cache/` is deleted, and an `agent_plugin_uninstalled` audit entry is recorded

### Requirement: Never expose Codex's credential file
`<config_dir>/auth.json` MUST never enter the allowlist, any config-file listing, or any facet's parse. It is a credential file: no config-file route lists or reads it — Coffer serves no config file's content at all ([agent-registry](../spec.md) "List an agent's config files with their locations") — and neither the MCP-entry nor the plugin parser opens it.

#### Scenario: refuse to read auth.json
- **GIVEN** a registered `codex` agent whose config directory holds an `auth.json`
- **WHEN** the user lists the agent's config files and then requests `auth.json` under the config-file routes
- **THEN** the listing does not include it
- **AND** the request is answered `404` with no filesystem read
