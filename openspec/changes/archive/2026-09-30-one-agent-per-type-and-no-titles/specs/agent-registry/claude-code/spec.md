## MODIFIED Requirements

### Requirement: Locate Claude Code at ~/.claude
The `claude_code` type's standard config directory MUST be `~/.claude/`, which is the value `config_dir` defaults to under [agent-registry](../spec.md) "Validate agent configuration against the agent schema". That directory and the `claude` program on the agent's `PATH` MUST be the two signals of [agent-registry](../spec.md) "Detect an agent by its program and its config directory" — the version is what `claude --version` prints (`2.1.281 (Claude Code)`) — and [agent-registry](../spec.md) "Allow one agent per name and per config directory"'s one-agent-per-config-directory rule follows from it, and [agent-registry](../spec.md) "Keep one agent per type, named by it" makes Claude Code registrable once, at this directory unless the user chooses another. An overridden `config_dir` is the directory Claude Code is run against through its `CLAUDE_CONFIG_DIR` environment variable — the only way Claude Code reads a config directory other than `~/.claude` — and that is why "Allowlist exactly the files Claude Code reads" places `.claude.json` differently for it. Every Claude Code process Coffer itself starts for such an agent — a chat or channel turn, per [chat](../../chat/spec.md) "Ship Claude Code and Codex subprocess providers on the type's one agent" — MUST carry `CLAUDE_CONFIG_DIR=<config_dir>`, so the turn reads the skills, MCP entry and settings Coffer put in that directory; for the default `~/.claude` the variable is left unset.

#### Scenario: discover Claude Code by its config directory
- **GIVEN** a home directory containing `~/.claude/`, the `claude` program on the agent's `PATH`, and no agent registered
- **WHEN** the user runs discovery
- **THEN** a `claude_code` candidate is reported in state `installed_active` whose `config_dir` is `~/.claude`
- **AND** a `claude_code` agent registered without a `config_dir` resolves to `~/.claude`
