## MODIFIED Requirements

### Requirement: Run Claude Code and Codex as subprocess providers on the type's one agent
System MUST ship subprocess-backed agent providers for Claude Code and Codex.
Each runs in a working directory (its `agent_config.cwd`); when a turn supplies
none, the provider MUST default to the Coffer-managed workspace
`~/.coffer/content/workspace` (created on first use) rather than reject the turn — so a
client with no configured workspace works out of the box. An
explicitly-supplied cwd MUST be an existing directory or the configuration is
rejected. Availability MUST reflect two things: whether the agent's binary is
resolvable on the user's PATH (the login shell's PATH merged with the daemon's
inherited one), and whether an **agent of that type is registered** with
Coffer; an agent failing either is unavailable and is not offered (see "Offer
and run only managed agents").

A turn MUST stream the tool's line-delimited JSON output mapped onto the
platform's turn events, and persist the upstream session id so the next turn
continues the same session. Claude Code is driven through the Claude Agent SDK
and Codex through `codex app-server` (JSON-RPC 2.0 over stdio, NDJSON-framed);
both run with full permissions — owner pairing
([channels](../channels/spec.md)) is the security gate.

Both MUST emit the reply as text increments *as it is written*, not as one
block at the end of the turn, otherwise a live surface has nothing to grow and
a reply lands all at once after a long silence. The Claude Agent SDK does this
only when asked (`include_partial_messages`), and it then delivers BOTH the
increments and the finished assistant message, so the adapter MUST subtract
what it already emitted and send the reply exactly once.

Every tool the agent runs MUST arrive as a tool call and its result — for Codex
not only commands and file changes but MCP tools, dynamic tools, sub-agent
calls, web searches and image tools, an MCP tool named
`mcp__<server>__<tool>` as Claude Code names it — because a tool event is what
separates the narration before it from the answer after it. Where the agent
says where one of its messages ends and whether it is narration, the adapter
MUST pass that on as `MessageEnd` (`commentary` set for Codex's `commentary`
phase; a message with no phase is answer text).

A turn MUST run against the config directory of its type's one agent
([agent-registry](../agent-registry/spec.md) "Keep one agent per type, named by
it") — the same one whose models the pickers offer
([agent-registry](../agent-registry/spec.md) "Serve each agent type's model
catalogue from its one agent"); a type with
no registered agent has no turn at all. Coffer delivers skills, installs its
MCP entry and edits config files in that directory, so a turn that read any
other one would not see them. When that agent's `config_dir` is not its type's
standard location, the spawned process's environment MUST carry the variable the
product reads it from — `CLAUDE_CONFIG_DIR=<config_dir>` for Claude Code,
`CODEX_HOME=<config_dir>` for Codex — merged with the daemon's own environment;
for the standard location the environment MUST be left as the daemon's own, so
the process behaves as when the user runs the CLI themselves. No provider key
rides the environment: an API-key connection is reached through Coffer's model
proxy.

#### Scenario: a streamed reply reaches the consumer exactly once
- **GIVEN** a Claude Code turn whose SDK delivers the reply as streamed increments and then as the finished assistant message
- **WHEN** the adapter maps the turn onto platform events
- **THEN** the reply arrives as one text delta per increment, in order
- **AND** the joined deltas equal the reply once, not doubled by the finished message
- **AND** the stream ends with a terminal turn-done

#### Scenario: a turn on an agent with its own config directory runs against that directory
- **GIVEN** a `claude_code` agent registered with a `config_dir` other than `~/.claude`, and a `codex` agent registered with a `config_dir` other than `~/.codex`
- **WHEN** a turn runs on each
- **THEN** the Claude Code process is started with `CLAUDE_CONFIG_DIR` set to the agent's `config_dir`, and the Codex app-server with `CODEX_HOME` set to its `config_dir`, the rest of the daemon's environment intact
- **AND** a turn on an agent whose `config_dir` is its type's standard location starts its process with the environment untouched

#### Scenario: every Codex tool separates narration from the answer
- **GIVEN** a Codex turn that writes a commentary message, calls an MCP tool, and
  writes its final answer
- **WHEN** its notifications are mapped
- **THEN** the commentary message ends with `MessageEnd(commentary=true)`, the MCP
  tool arrives as a tool call named `mcp__<server>__<tool>` with its result, and
  the final answer's message ends with `MessageEnd(commentary=false)`
