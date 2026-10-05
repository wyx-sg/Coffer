## MODIFIED Requirements

### Requirement: Install Coffer's MCP entry into Claude Code's .claude.json
The `McpInjectionSpec` [agent-registry](../spec.md) "Install Coffer's MCP server into an agent in one action" installs through MUST write `mcpServers.coffer` in the agent's `global` file — `~/.claude.json` for the default config directory, `<config_dir>/.claude.json` for a custom one, per "Allowlist exactly the files Claude Code reads" — a command-map entry whose `command` is the resolved absolute shim path and whose `args` carry `--agent-uid <uid>`. Because the whole JSON document is reserialized on write, the backup of [agent-registry](../spec.md) "Back up and compare-and-swap every write Coffer makes to an agent's config" is what makes that diff recoverable. The MCP-entry target of the unified reconciler MUST read and repair an agent's entry only in that agent's own `global` file: a `coffer` entry in a file the agent does not read is not the agent's entry, and the target neither moves it nor installs one on its account.

#### Scenario: install Coffer's MCP into an agent
- **GIVEN** a registered `claude_code` agent and a resolvable `coffer-mcp-shim` binary
- **WHEN** the user installs Coffer's MCP
- **THEN** a `coffer` entry is written into `~/.claude.json` `mcpServers` with `command` set to the absolute shim path, the prior file is backed up under `~/.coffer/config-backups/`, an `agent_mcp_installed` audit entry is recorded, and install status reports `installed=true`

### Requirement: Expose personal subagents as a directory entry
`agents/` MUST be the type's directory entry ([agent-registry](../spec.md) "List directory config entries"): one Markdown file per personal subagent, nested paths allowed, each listed by its entry-relative path and opened or revealed like any other config file ([agent-registry](../spec.md) "Open config files in an external editor or reveal them").

#### Scenario: list nested subagent files in the agents directory
- **GIVEN** a registered `claude_code` agent whose `agents/` directory holds a subagent file at its top level and another in a nested folder
- **WHEN** the user lists the `agents` config entry
- **THEN** the entry reports `kind=directory` and both files by their entry-relative paths, the nested one included
