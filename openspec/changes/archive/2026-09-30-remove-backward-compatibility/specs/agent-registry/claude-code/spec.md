## MODIFIED Requirements

### Requirement: Install Coffer's MCP entry into Claude Code's .claude.json
The `McpInjectionSpec` [agent-registry](../spec.md) "Install Coffer's MCP server into an agent in one action" installs through MUST write `mcpServers.coffer` in the agent's `global` file — `~/.claude.json` for the default config directory, `<config_dir>/.claude.json` for a custom one, per "Allowlist exactly the files Claude Code reads" — a command-map entry whose `command` is the resolved absolute shim path and whose `args` carry `--agent-uid <uid>`. Because the whole JSON document is reserialized on write, the `.bak` of [agent-registry](../spec.md) "Write config files atomically with a backup and an audit entry" is what makes that diff recoverable. The MCP-entry target of the unified reconciler MUST read and repair an agent's entry only in that agent's own `global` file: a `coffer` entry in a file the agent does not read is not the agent's entry, and the target neither moves it nor installs one on its account.

#### Scenario: install Coffer's MCP into an agent
- **GIVEN** a registered `claude_code` agent and a resolvable `coffer-mcp-shim` binary
- **WHEN** the user installs Coffer's MCP
- **THEN** a `coffer` entry is written into `~/.claude.json` `mcpServers` with `command` set to the absolute shim path, the prior file is backed up to `.bak`, an `agent_mcp_installed` audit entry is recorded, and install status reports `installed=true`

#### Scenario: an entry installed before the config dir was honoured moves to the agent's own file
- **GIVEN** a `claude_code` agent registered with a custom `config_dir`, and a `coffer` entry in `~/.claude.json` whose `args` carry that agent's uid
- **WHEN** the daemon starts, or any reconcile pass runs
- **THEN** `<config_dir>/.claude.json` holds the `coffer` entry with the agent's uid, the entry is gone from `~/.claude.json` with every other key there intact, both files keep a `.bak`, and install status for the agent reports `installed=true`
- **AND** an entry in `~/.claude.json` carrying the default agent's uid is left untouched, and a second pass changes nothing

