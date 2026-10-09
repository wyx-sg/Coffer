## MODIFIED Requirements

### Requirement: Read Codex's hooks from hooks.json
The hooks of [agent-registry](../spec.md) "List every hook in the agent's native config" MUST be read, for `codex`, from two places: the config directory's `hooks.json` (source `user`), and the `hooks/hooks.json` of each enabled installed plugin, where one exists. `hooks.json` is the file Codex's hooks feature reads, in the same event-keyed shape as Claude Code's.

#### Scenario: read Codex hooks from hooks.json
- **GIVEN** a Codex agent whose `hooks.json` carries a `UserPromptSubmit` hook of its own
- **WHEN** the user lists its hooks
- **THEN** it is listed from `hooks.json` with source `user`

## REMOVED Requirements

### Requirement: Report whether Codex will run Coffer's hook
**Reason**: Coffer installs no hook into Codex, so there is no approval of Coffer's hook to read from `config.toml`.
**Migration**: None. Codex's `[hooks.state.*]` tables stay untouched ("Leave Codex's internal-state tables untouched").
