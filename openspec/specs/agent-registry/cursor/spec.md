# Agent Registry — Cursor

## Purpose
This child of [`agent-registry`](../spec.md) says how the `cursor` agent type realises the facets its parent defines: where its config directory is, which of its files Coffer may read and write, the shape of the MCP entry Coffer installs, and where its skills are delivered. It is the prose reading of that type's one `AGENT_DESCRIPTORS` record. "Cursor" is the product: the editor and its command line (`cursor-agent`, also installed as `agent`), which read one shared `~/.cursor` directory and one shared `mcp.json`.

Cursor offers no custom model endpoint, keeps no memory on disk and documents no session storage, so this type has no provider projection, memory reader or session source; the surfaces hide those tabs for it (ADR [Cursor, OpenCode and DeepSeek Harness Are Supported Agents](../../../../docs/decisions/cursor-opencode-and-deepseek-harness-are-supported-agents.md)).

## Requirements

### Requirement: Locate Cursor at ~/.cursor
The `cursor` type's standard config directory MUST be `~/.cursor/`. That directory and the `cursor-agent` program on the agent's `PATH` MUST be the two signals of [agent-registry](../spec.md) "Detect an agent by its program and its config directory"; the version is what `cursor-agent --version` prints. An overridden `config_dir` is the directory Cursor's command line is run against through `CURSOR_CONFIG_DIR`.

#### Scenario: discover Cursor by its config directory
- **GIVEN** a home directory containing `~/.cursor/`, the `cursor-agent` program on the agent's `PATH`, and no agent registered
- **WHEN** the user runs discovery
- **THEN** a `cursor` candidate is reported whose `config_dir` is `~/.cursor`
- **AND** a `cursor` agent registered without a `config_dir` resolves to `~/.cursor`

### Requirement: Allowlist exactly Cursor's MCP, CLI config and hooks files
The curated allowlist for `cursor` MUST be exactly: `mcp.json` under the key `mcp`, `cli-config.json` under the key `cli_config`, and `hooks.json` under the key `hooks`, all format `json`. Cursor keeps its User Rules in the editor's settings rather than in a file, so this type has no `instructions` entry.

#### Scenario: list exactly Cursor's three config files
- **GIVEN** a registered `cursor` agent
- **WHEN** the user lists its config files
- **THEN** exactly `mcp.json`, `cli-config.json` and `hooks.json` are returned, each with format `json`

### Requirement: Install Coffer's MCP entry into mcp.json
The `McpInjectionSpec` for this type MUST write `mcpServers.coffer` in `<config_dir>/mcp.json`, whose `command` is the resolved absolute shim path and whose `args` are `["--agent-uid", "<uid>"]` — the command-map shape Claude Code's entry uses. The editor and the command line both read it. The entries [agent-registry](../spec.md) "List the MCP entries in the agent's own config files" lists are parsed from the same `mcpServers` map.

#### Scenario: install Coffer's MCP into Cursor's mcp.json
- **GIVEN** a registered `cursor` agent whose `mcp.json` already holds another server
- **WHEN** the user installs Coffer's MCP
- **THEN** `mcpServers.coffer` is written with the absolute shim path and `--agent-uid` and the agent's uid
- **AND** the other server is kept

### Requirement: Deliver Cursor's skills to the shared ~/.agents/skills
Skills MUST be delivered to `~/.agents/skills`, which Cursor reads, as one link shared with every other agent reading that directory ([skill-manager](../../skill-manager/spec.md), ADR [A Shared Skills Directory Holds One Link for Every Agent That Reads It](../../../../docs/decisions/a-shared-skills-directory-holds-one-link-for-every-reader.md)). Skills a person keeps in `~/.cursor/skills` are listed as unmanaged.

#### Scenario: deliver a skill for Cursor into ~/.agents/skills
- **GIVEN** a registered `cursor` agent and an enabled skill in scope for it
- **WHEN** skills are reconciled
- **THEN** `~/.agents/skills/<skill>` links to the skill's master folder
