## MODIFIED Requirements

### Requirement: Read Claude Code's hooks from its settings files and plugins
The hooks of [agent-registry](../spec.md) "List every hook in the agent's native config" MUST be read, for `claude_code`, from the config directory's `settings.json` and `settings.local.json` (source `user`) and from the `hooks/hooks.json` of each enabled installed plugin (source `plugin`).

#### Scenario: read Claude Code hooks from both settings files and an enabled plugin
- **GIVEN** a Claude Code agent with hooks in `settings.json`, in `settings.local.json`, and in an enabled plugin's `hooks/hooks.json`
- **WHEN** the user lists its hooks
- **THEN** each hook is listed with the file that declares it, the plugin's ones with source `plugin` and the plugin's id
