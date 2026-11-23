# Agent Registry — Cursor

## Purpose
This child of [`agent-registry`](../spec.md) says how the `cursor` agent type realises the facets its parent defines: where its config directory is, which of its files Coffer may read and write, the shape of the MCP entry Coffer installs, and where its skills are delivered. It is the prose reading of that type's one `AGENT_DESCRIPTORS` record. "Cursor" is the product: the editor and its command line (`cursor-agent`, also installed as `agent`), which read one shared `~/.cursor` directory and one shared `mcp.json`.

Cursor offers no custom model endpoint and keeps no memory on disk, so this type has no provider projection or memory reader; the surfaces hide those for it (ADR [Cursor, OpenCode and DeepSeek Harness Are Supported Agents](../../../../docs/decisions/cursor-opencode-and-deepseek-harness-are-supported-agents.md)). Its chats are read from their stores ([agent-registry](../spec.md) "List the sessions an agent keeps in its own store"), and its hooks from `hooks.json`.

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

### Requirement: List Cursor's hooks from hooks.json
The `cursor` type's hook-carrying file MUST be `hooks.json` in its config directory (`~/.cursor/hooks.json`, run by the editor and its command line), read by [agent-registry](../spec.md) "List every hook in the agent's native config". Cursor lists each hook directly under its event, with the matcher on the hook (`{"version": 1, "hooks": {"<event>": [{"command": …, "matcher": …, "timeout": …}]}}`), so a hook's position is `hooks.<event>[i]`: its `group_index` is `i` and its `hook_index` is 0. A prompt hook (`"type": "prompt"`) is listed with its `prompt` where a command hook shows its command. Cursor's project, team and enterprise hook files are not read.

#### Scenario: Cursor's hooks are listed from its hooks.json
- **GIVEN** a Cursor `hooks.json` with a `beforeShellExecution` command hook that has a matcher and a timeout, and a `beforeSubmitPrompt` event holding a prompt hook and a command hook
- **WHEN** the user lists the agent's hooks
- **THEN** the three hooks are listed in file order with their events, matchers, timeouts and types, the prompt hook under its prompt, and their positions are `hooks.<event>[0]`, `[0]` and `[1]`
