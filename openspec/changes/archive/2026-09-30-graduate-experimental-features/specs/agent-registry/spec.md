## RENAMED Requirements

- FROM: `### Requirement: Connect an agent to Coffer in one action`
- TO: `### Requirement: Connect an agent to Coffer in one action (before graduation)`

- FROM: `### Requirement: Report an agent's Coffer connection part by part`
- TO: `### Requirement: Report an agent's Coffer connection part by part (before graduation)`

- FROM: `### Requirement: Disconnect an agent from Coffer`
- TO: `### Requirement: Disconnect an agent from Coffer (before graduation)`

## REMOVED Requirements

### Requirement: Connect an agent to Coffer in one action (before graduation)
**Reason**: The memory hook no longer depends on a feature switch, so the scenario "connect leaves out a part whose feature is off" no longer holds. A MODIFIED block cannot drop a scenario, so the requirement is renamed out of the way, removed, and added again under its own title (see ADDED below).
**Migration**: Its marker is deleted.

### Requirement: Report an agent's Coffer connection part by part (before graduation)
**Reason**: Moved with "Connect an agent to Coffer in one action" so the connection requirements stay together. A MODIFIED block cannot drop a scenario, so the requirement is renamed out of the way, removed, and added again under its own title (see ADDED below).
**Migration**: None: every scenario keeps its name.

### Requirement: Disconnect an agent from Coffer (before graduation)
**Reason**: Moved with "Connect an agent to Coffer in one action" so the connection requirements stay together. A MODIFIED block cannot drop a scenario, so the requirement is renamed out of the way, removed, and added again under its own title (see ADDED below).
**Migration**: None: every scenario keeps its name.

## ADDED Requirements

### Requirement: Connect an agent to Coffer in one action
Users MUST be able to connect an agent to Coffer in one action, from the REST API (`POST /api/v1/agents/{uid}/coffer-connection`), the CLI (`coffer agent connect <name>`) and the web UI. Connecting MUST install every **part** Coffer writes into the agent's own configuration for that agent's type:

- `mcp` — the gateway MCP entry of "Install Coffer's MCP server into an agent in one action", for every agent type;
- `memory_hook` — the memory delivery hook of [memory](../memory/spec.md) "Install delivery hooks explicitly and removably", for every agent type with a hook adapter.

The gateway entry MUST be installed first, so that a connect refused for want of a shim writes nothing. Every part MUST be installed through its own atomic write with a `.bak` and record its own audit event, as it does when installed alone. Connecting MUST be idempotent: connecting a connected agent rewrites each entry in place and never duplicates one.

#### Scenario: connect installs every part that applies
- **GIVEN** a registered Claude Code agent with neither the gateway entry nor the memory hook
- **WHEN** the user connects it to Coffer
- **THEN** the agent's `.claude.json` carries the `coffer` MCP entry and its `settings.json` carries Coffer's marked hook entry
- **AND** one `agent_mcp_installed` and one `memory_delivery_installed` audit entry name the user as actor, and the connection reports `connected` with both parts installed

### Requirement: Report an agent's Coffer connection part by part
The system MUST report an agent's Coffer connection (`GET /api/v1/agents/{uid}/coffer-connection`, `coffer_connection` in `coffer agent show <name> [--json]`) as the list of parts its type has — each with its key, whether it is installed, and the installed command when it is — and a state: `connected` when every listed part is installed, `disconnected` when none is, and `partial` otherwise. The report MUST be read from the agent's own configuration files on demand, never stored, and MUST write nothing and record no audit event.

#### Scenario: report a partly installed connection
- **GIVEN** a registered agent carrying the gateway entry but not the memory hook
- **WHEN** the user reads its Coffer connection
- **THEN** the state is `partial`, the `mcp` part is installed with its shim command and the `memory_hook` part is not installed
- **AND** connecting again installs the missing hook and the state becomes `connected`

### Requirement: Disconnect an agent from Coffer
Users MUST be able to disconnect an agent from Coffer in one action (`DELETE /api/v1/agents/{uid}/coffer-connection`, `coffer agent disconnect <name>`, the web UI). Disconnecting MUST remove every part the agent type has, taking out only Coffer's own marked entries and leaving every other entry, key and hook in those files as it was. A part that is absent MUST be a no-op that writes no file and records no audit event.

#### Scenario: disconnect removes only Coffer's entries
- **GIVEN** a connected Claude Code agent whose `.claude.json` also carries another MCP server and whose `settings.json` also carries a foreign hook on the same event
- **WHEN** the user disconnects it from Coffer
- **THEN** the `coffer` MCP entry and Coffer's hook entry are gone, the other MCP server and the foreign hook are untouched, and the connection reports `disconnected`
- **AND** disconnecting again writes no file and records no audit entry
