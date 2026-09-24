## ADDED Requirements

### Requirement: Clear inherited agent-home variables at start
The daemon MUST remove `CLAUDE_CONFIG_DIR` and `CODEX_HOME` — every agent type's home variable — from its own environment when it starts, before it spawns anything, and log once which ones it removed. A daemon started from a shell that exports one would otherwise hand it to every agent process it spawns, so an agent registered on the default directory would run against the exported one while Coffer delivers its skills, MCP entry and config into the default. An agent gets the variable only from its own registered config directory ([agent-registry](../agent-registry/spec.md)), set on that agent's process alone.

#### Scenario: a daemon started from a shell exporting an agent home does not pass it on
- **GIVEN** a shell that exports `CLAUDE_CONFIG_DIR` and `CODEX_HOME`
- **WHEN** the daemon is started from it
- **THEN** the daemon's environment holds neither variable and the daemon log names both once
- **AND** a turn for an agent on its default directory is spawned with neither variable, while an agent with a custom directory gets its own directory in its type's variable
