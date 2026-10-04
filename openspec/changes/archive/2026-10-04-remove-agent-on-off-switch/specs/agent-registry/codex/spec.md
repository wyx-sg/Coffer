## MODIFIED Requirements

### Requirement: Locate Codex at ~/.codex
The `codex` type's standard config directory MUST be `~/.codex/`, which is the value `config_dir` defaults to under [agent-registry](../spec.md) "Validate agent configuration against the agent schema". That directory and the `codex` program on the agent's `PATH` MUST be the two signals of [agent-registry](../spec.md) "Detect an agent by its program and its config directory" — the version is what `codex --version` prints (`codex-cli 0.155.1`) — and [agent-registry](../spec.md) "Allow one agent per name and per config directory"'s one-agent-per-config-directory rule follows from it, and [agent-registry](../spec.md) "Keep one agent per type, named by it" makes Codex registrable once, at this directory unless the user chooses another. An overridden `config_dir` is the directory Codex is run against through its `CODEX_HOME` environment variable — the only way Codex reads a home other than `~/.codex`, and the root of its `config.toml`, `auth.json`, sessions and memories. Every Codex process Coffer itself starts for such an agent — a chat or channel turn, per [chat](../../chat/spec.md) "Run Claude Code and Codex as subprocess providers on the type's one agent", and the `model/list` probe of "Read Codex models from model/list and config.toml" — MUST carry `CODEX_HOME=<config_dir>`; for the default `~/.codex` the variable is left unset.

#### Scenario: discover Codex by its config directory
- **GIVEN** a home directory containing `~/.codex/`, the `codex` program on the agent's `PATH`, and no agent registered
- **WHEN** the user runs discovery
- **THEN** a `codex` candidate is reported in state `installed_active` whose `config_dir` is `~/.codex`
- **AND** a `codex` agent registered without a `config_dir` resolves to `~/.codex`
