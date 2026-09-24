## MODIFIED Requirements

### Requirement: Install Coffer's MCP entry into Claude Code's .claude.json
The `McpInjectionSpec` [agent-registry](../spec.md) "Install Coffer's MCP server into an agent in one action" installs through MUST write `mcpServers.coffer` in the agent's `global` file — `~/.claude.json` for the default config directory, `<config_dir>/.claude.json` for a custom one, per "Allowlist exactly the files Claude Code reads" — a command-map entry whose `command` is the resolved absolute shim path and whose `args` carry `--agent-uid <uid>`. Because the whole JSON document is reserialized on write, the `.bak` of [agent-registry](../spec.md) "Write config files atomically with a backup and an audit entry" is what makes that diff recoverable. An entry a Coffer that predates the custom-directory rule wrote into `~/.claude.json` for a custom-directory agent — recognisable by that agent's uid in its `--agent-uid` argument — MUST be moved into the agent's own `.claude.json` once, at daemon start: installed there unless that file already carries a `coffer` entry, then removed from `~/.claude.json`, each write backed up and audited as install and uninstall are. Claude Code under that directory never reads the home file, so left in place the entry would report the custom agent as not installed and the default agent as installed under another agent's identity. The move is idempotent, and it never touches an entry carrying any other uid or none, any non-Coffer entry, or a file that does not parse — an unparseable file on either side is logged and both are left as they are.

#### Scenario: install Coffer's MCP into an agent
- **GIVEN** a registered `claude_code` agent and a resolvable `coffer-mcp-shim` binary
- **WHEN** the user installs Coffer's MCP
- **THEN** a `coffer` entry is written into `~/.claude.json` `mcpServers` with `command` set to the absolute shim path, the prior file is backed up to `.bak`, an `agent_mcp_installed` audit entry is recorded, and install status reports `installed=true`

#### Scenario: an entry installed before the config dir was honoured moves to the agent's own file
- **GIVEN** a `claude_code` agent registered with a custom `config_dir`, and a `coffer` entry in `~/.claude.json` whose `args` carry that agent's uid
- **WHEN** the daemon starts
- **THEN** `<config_dir>/.claude.json` holds the `coffer` entry with the agent's uid, the entry is gone from `~/.claude.json` with every other key there intact, both files keep a `.bak`, and install status for the agent reports `installed=true`
- **AND** an entry in `~/.claude.json` carrying the default agent's uid is left untouched, and a second start changes nothing
