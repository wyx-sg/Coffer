## MODIFIED Requirements

### Requirement: Uninstall a Codex plugin by editing config.toml
The uninstall strategy of [agent-registry](../spec.md) "Uninstall a plugin by the type's own strategy" for this type MUST be a config edit: remove the `[plugins."…"]` entry from `config.toml` (atomic, with the backup of [agent-registry](../spec.md) "Write config files atomically with a backup and an audit entry") and delete that plugin's cache directory. There is no CLI to delegate to and none is required, so `can_uninstall` is true whenever the entry exists.

#### Scenario: uninstall a Codex plugin
- **GIVEN** a registered `codex` agent with an installed plugin
- **WHEN** the user uninstalls it
- **THEN** the `[plugins."…"]` entry is removed from `config.toml` (atomic + backup), the plugin's cache directory under `~/.codex/plugins/cache/` is deleted, and an `agent_plugin_uninstalled` audit entry is recorded

