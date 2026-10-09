## MODIFIED Requirements

### Requirement: Install Coffer's MCP server into an agent in one action
Connecting an agent to Coffer ("Connect an agent to Coffer in one action") MUST install Coffer's own MCP server into it as the connection's `mcp` part. The install writes a `coffer` stdio MCP-server entry into the agent's MCP config, using the shape declared by that agent's manifest `McpInjectionSpec` and named by that type's child spec.

- `command` is the absolute path of the `coffer-mcp-shim` binary. A `COFFER_MCP_SHIM_PATH` environment override takes precedence over all. An installed build MUST then name the shim it deployed, `~/.coffer/bin/coffer-mcp-shim`, whenever that exists, whether its daemon was started by the desktop app, a terminal or the login service, so every daemon on the machine writes the same entry ([An Installed Daemon Names the Deployed Shim](../../../docs/decisions/an-installed-daemon-names-the-deployed-shim.md)). Otherwise the shim is resolved on `PATH`, then the running interpreter's scripts directory — so a venv-installed shim is found even when the daemon's `PATH` lacks the venv — then the bundled binary, then `~/.coffer/bin/coffer-mcp-shim`; a deployed shim found by any of these is named by that public path, never by the versioned directory behind it.
- The install additionally writes `--agent-uid <uid>` in the entry shape's argument slot — the agent's immutable uid, never its mutable name, because the entry is written once into a file Coffer does not otherwise revisit and a name would go stale on the first rename — so the gateway can attribute the session to this agent for per-agent scope enforcement ([Per-Agent Resource Scope](../../../docs/decisions/per-agent-resource-scope.md)).
- If the shim cannot be resolved, the connect is rejected with `SHIM_NOT_FOUND`, an error naming the missing binary, and nothing is written. Finding or reinstalling the shim depends on how Coffer got onto this machine, so the refusal MUST carry, in its details as `handoff.prompt`, a hand-off prompt (see [skill-manager](../skill-manager/spec.md) "Hand a required command to an agent with a prompt" for the shape every hand-off takes) asking the person's agent to find or reinstall `coffer-mcp-shim` so it resolves at `~/.coffer/bin/coffer-mcp-shim` or one of the places Coffer looks, naming every place it looked, then to have the person choose Connect again. The web UI's Connect review MUST offer that prompt through **Copy prompt** (and **Ask an agent** while a managed agent is available) beside Retry, and its refusal copy MUST name no environment variable or command.

#### Scenario: refuse the Coffer MCP install when the shim cannot be resolved
- **GIVEN** a registered agent and no resolvable `coffer-mcp-shim` binary
- **WHEN** the user connects the agent to Coffer
- **THEN** the connect is rejected with an error naming the missing binary
- **AND** the agent's MCP config file is not written

#### Scenario: a missing shim is refused with a prompt that hands finding it to an agent
- **GIVEN** no `coffer-mcp-shim` at the override `COFFER_MCP_SHIM_PATH` names, on the daemon's `PATH`, in the interpreter's scripts directory or beside the running executable
- **WHEN** the shim is resolved for a connect
- **THEN** the refusal carries a hand-off prompt asking to find or reinstall `coffer-mcp-shim` so it resolves at `~/.coffer/bin/coffer-mcp-shim`
- **AND** the prompt names every place Coffer looked and ends by asking the person to choose Connect again

#### Scenario: connect an agent to Coffer over REST
- **GIVEN** a registered agent whose MCP config has no `coffer` entry and a resolvable `coffer-mcp-shim` binary
- **WHEN** the user connects the agent with `POST /api/v1/agents/{uid}/coffer-connection`
- **THEN** the agent's MCP config carries a `coffer` entry whose arguments name the agent's uid
- **AND** an `agent_mcp_installed` audit entry is recorded
- **AND** the response lists each part of the connection and whether it is installed

#### Scenario: an installed daemon writes the same shim path however it was started
- **GIVEN** an installed Coffer whose shim is deployed at `~/.coffer/bin/coffer-mcp-shim`, and another `coffer-mcp-shim` earlier on the login service's `PATH`
- **WHEN** an agent is connected once by a daemon the desktop app started, once by one started from a terminal, and once by one the login service started
- **THEN** each writes `~/.coffer/bin/coffer-mcp-shim` as the entry's `command`
