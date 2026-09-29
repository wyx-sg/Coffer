## ADDED Requirements

### Requirement: Read Codex's hooks from hooks.json
The hooks of [agent-registry](../spec.md) "List every hook in the agent's native config" MUST be read, for `codex`, from the config directory's `hooks.json` (source `user`) — the file Codex's hooks feature reads, in the same event-keyed shape as Claude Code's — and from the `hooks/hooks.json` of each enabled installed plugin, where one exists. Coffer's own delivery hook sits on `UserPromptSubmit` in `hooks.json`.

#### Scenario: read Codex hooks from hooks.json
- **GIVEN** a Codex agent whose `hooks.json` carries Coffer's marked hook
- **WHEN** the user lists its hooks
- **THEN** the hook is listed from `hooks.json` with source `user` and marked as Coffer's

## MODIFIED Requirements

### Requirement: Locate Codex at ~/.codex
The `codex` type's standard config directory MUST be `~/.codex/`, which is the value `config_dir` defaults to under [agent-registry](../spec.md) "Validate agent configuration against the agent schema". That directory and the `codex` program on the agent's `PATH` MUST be the two signals of [agent-registry](../spec.md) "Detect an agent by its program and its config directory" — the version is what `codex --version` prints (`codex-cli 0.155.1`) — and [agent-registry](../spec.md) "Allow one agent per name and per config directory"'s one-agent-per-config-directory rule follows from it: Codex is registrable once unless the user overrides the path. An overridden `config_dir` is the directory Codex is run against through its `CODEX_HOME` environment variable — the only way Codex reads a home other than `~/.codex`, and the root of its `config.toml`, `auth.json`, sessions and memories. Every Codex process Coffer itself starts for such an agent — a chat or channel turn, per [chat](../../chat/spec.md) "Ship Claude Code and Codex subprocess providers", and the `model/list` probe of "Read Codex models from model/list and config.toml" — MUST carry `CODEX_HOME=<config_dir>`; for the default `~/.codex` the variable is left unset.

#### Scenario: discover Codex by its config directory
- **GIVEN** a home directory containing `~/.codex/`, the `codex` program on the agent's `PATH`, and no agent registered
- **WHEN** the user runs discovery
- **THEN** a `codex` candidate is reported in state `installed_active` whose `config_dir` is `~/.codex`
- **AND** a `codex` agent registered without a `config_dir` resolves to `~/.codex`
