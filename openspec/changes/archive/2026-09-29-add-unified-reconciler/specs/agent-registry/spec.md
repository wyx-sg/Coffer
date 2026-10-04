## MODIFIED Requirements

### Requirement: Keep the Coffer MCP install idempotent and report its status
Installing the `mcp` part MUST be idempotent — re-installing updates the existing `coffer` entry in place and never creates a duplicate. Whether it is installed MUST be reported as that part of the agent's Coffer connection ("Report an agent's Coffer connection part by part"), derived from the agent's MCP config file, never stored. An installed entry MUST also be judged by its parameters — the shim path in `command` and the `--agent-uid` in `args` — against what an install would write now, by the MCP-entry target of the unified reconciler ([resource-framework](../resource-framework/spec.md) "Converge what Coffer writes outside its database with one reconciler"): on every pass a stale entry is rewritten in place, backed up and audited as an install, and an entry that carries another registered agent's uid in a file that agent does not read is moved into that agent's own file. The target never adds an entry to an agent that holds none — connecting is the user's act — and while the shim cannot be found the drift is reported as blocked and nothing is written.

#### Scenario: report Coffer-MCP install status
- **GIVEN** a registered agent whose MCP config does not contain a `coffer` server entry
- **WHEN** the user checks the agent's Coffer connection
- **THEN** the `mcp` part reports `installed=false`

#### Scenario: install Coffer's MCP is idempotent
- **GIVEN** an agent that already has Coffer's MCP installed
- **WHEN** the user connects it again
- **THEN** the existing `coffer` entry is updated in place (never duplicated) and the `mcp` part still reports `installed=true`

#### Scenario: agent show reports the Coffer MCP status
- **GIVEN** one registered agent with Coffer's MCP installed and one without
- **WHEN** the user runs `coffer agent show <name> --json` for each
- **THEN** the first carries `coffer_connection` whose `mcp` part reports installed and the second `coffer_connection` whose state is `disconnected`
- **AND** `coffer_connection` has the shape `GET /api/v1/agents/{uid}/coffer-connection` answers

#### Scenario: a stale Coffer MCP entry is repaired with its current parameters
- **GIVEN** a registered agent whose `coffer` entry names a shim path this build no longer installs, or an `--agent-uid` that is not the agent's
- **WHEN** a reconcile pass runs
- **THEN** the entry is rewritten with the current shim path and the agent's uid, every other entry in the file is left as it was, and an `agent_mcp_installed` audit entry is recorded with actor `system`
- **AND** an agent with no `coffer` entry is not given one
