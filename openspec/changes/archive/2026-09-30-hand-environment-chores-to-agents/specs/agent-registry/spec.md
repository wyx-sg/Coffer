## MODIFIED Requirements

### Requirement: Install Coffer's MCP server into an agent in one action
Connecting an agent to Coffer ("Connect an agent to Coffer in one action") MUST install Coffer's own MCP server into it as the connection's `mcp` part. The install writes a `coffer` stdio MCP-server entry into the agent's MCP config, using the shape declared by that agent's manifest `McpInjectionSpec` and named by that type's child spec.

- `command` is the absolute path of the `coffer-mcp-shim` binary, resolved on `PATH`, then the running interpreter's scripts directory — so a venv-installed shim is found even when the daemon's `PATH` lacks the venv — then the bundled binary; a `COFFER_MCP_SHIM_PATH` environment override takes precedence over all.
- The install additionally writes `--agent-uid <uid>` in the entry shape's argument slot — the agent's immutable uid, never its mutable name, because the entry is written once into a file Coffer does not otherwise revisit and a name would go stale on the first rename — so the gateway can attribute the session to this agent for per-agent scope enforcement ([Per-Agent Resource Scope](../../../docs/decisions/per-agent-resource-scope.md)).
- If the shim cannot be resolved, the connect is rejected with `SHIM_NOT_FOUND`, an error naming the missing binary, and nothing is written. Finding or reinstalling the shim depends on how Coffer got onto this machine, so the refusal MUST carry, in its details as `handoff.prompt`, a hand-off prompt (see [skill-manager](../skill-manager/spec.md) "Hand a required command to an agent with a prompt" for the shape every hand-off takes) asking the person's agent to find or reinstall `coffer-mcp-shim` so it resolves at `~/.coffer/bin/coffer-mcp-shim` or one of the places Coffer looks, naming every place it looked, then to have the person choose Connect again. The web UI's Connect review MUST offer that prompt through **Copy prompt** (and **Ask an agent** while a managed agent is available) beside Retry, and its refusal copy MUST name no environment variable or command; the command line MUST print the prompt under the error.

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

#### Scenario: connect an agent to Coffer from the command line
- **GIVEN** a registered agent whose MCP config has no `coffer` entry and a resolvable `coffer-mcp-shim` binary
- **WHEN** the user runs `coffer agent connect <name>`
- **THEN** the agent's MCP config carries a `coffer` entry whose arguments name the agent's uid
- **AND** an `agent_mcp_installed` audit entry is recorded
- **AND** the command prints each part of the connection and whether it is installed

## ADDED Requirements

### Requirement: Hand installing an agent's program to an agent
While an agent type's program is not found on the agent's real `PATH` — detection reads `config_only` or `missing` (see "Detect an agent by its program and its config directory") — the system MUST offer a hand-off prompt (see [skill-manager](../skill-manager/spec.md) "Hand a required command to an agent with a prompt" for the shape every hand-off takes) that asks the person's agent to install that type's program, or to reinstall it when an agent of the type is registered or its config directory is still there. The prompt MUST name the agent and this machine's OS and architecture; say that an existing config directory is kept with everything in it; name the program Coffer looks for and the `PATH` it looks on, and ask that the program be found there and confirmed with `<program> --version`; ask the person to come back and choose Check again; and leave signing in to the agent to the person. It MUST name no installer, package manager or install command. The prompt MUST be carried as `install_handoff` on each row of `GET /api/v1/agents/types` and on the agent record (`GET /api/v1/agents`, `GET /api/v1/agents/{uid}`), `null` while the program is found; the Overview attention item for a registered agent whose program is missing MUST carry the same prompt, with a reason sentence that names no command; and `coffer agent prompt <type>` MUST print it, exiting with a conflict when the program is found.

#### Scenario: a type that is not installed carries its install prompt
- **GIVEN** Codex's program is not on the agent's `PATH` and no Codex agent is registered
- **WHEN** the prompt for the Codex type is built
- **THEN** it asks to install OpenAI Codex on this machine, naming the machine, the `PATH` Coffer looks on, the program `codex` and `codex --version` to confirm, and ends with Check again and signing in left to the person
- **AND** it names no installer or package manager

#### Scenario: an agent whose program is gone carries a reinstall prompt that keeps its folder
- **GIVEN** a registered Claude Code agent whose config directory is still there and whose program is not on its `PATH`
- **WHEN** the prompt for it is built
- **THEN** it asks to reinstall Claude Code and to keep its config directory and everything in it, confirming with `claude --version`
- **AND** a registered agent whose directory is gone too gets a reinstall prompt saying so, and a found program gets no prompt

#### Scenario: an attention item for a missing program carries the reinstall prompt
- **GIVEN** an enabled registered agent whose program is not found
- **WHEN** the Overview attention list is read
- **THEN** its `agent_program_missing` item carries the reinstall prompt for that agent's type and config directory
- **AND** the item's reason names no command

#### Scenario: the command line prints an agent's install prompt
- **GIVEN** Claude Code's program is not found and Codex's is
- **WHEN** the user runs `coffer agent prompt claude-code`, then `coffer agent prompt codex`
- **THEN** the first prints the install prompt, the same text `--json` returns under `handoff`
- **AND** the second says there is nothing to hand off and exits with a conflict
