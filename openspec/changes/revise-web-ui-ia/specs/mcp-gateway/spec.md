## MODIFIED Requirements

### Requirement: Record invocations without content
The system MUST record an invocation entry for every tool call, resource read, and prompt fetch — its target,
timestamp, duration and outcome — without recording arguments or return contents. Each entry MUST also carry
its row `id`, and MUST name the agent whose session made the call (`agent_uid`) when that session reported one
on its handshake (see "Take the agent identity from the handshake"); a session that reported none writes
entries naming no agent, never a guessed one. How long those entries are
kept, and the background pass that prunes them, are [resource-framework](../resource-framework/spec.md) "Prune each registered log table on its own retention period" — the retention contract
every log-writing kind inherits — not this spec's own rule. This spec contributes `mcp_invocations` to that
registry with a 30-day default. The record is read per server
(`GET /api/v1/resources/mcp_server/{uid}/invocations`, `coffer log mcp --server <server>`) or across every
server (`GET /api/v1/mcp/invocations`, `coffer log mcp` with no server), the cross-server read
including Coffer's own built-in calls (`coffer`) and deleted servers' rows (`deleted:<name>`). Both HTTP reads
can be narrowed to one agent's calls with `agent_uid`. Both reads
page newest first by cursor ([resource-framework](../resource-framework/spec.md) "Page growing lists by an opaque cursor"),
and both CLI forms take `--status`, `--since`, `--limit`, `--cursor` and `--json`.

#### Scenario: invocation log records calls without arguments
- **GIVEN** an MCP client has invoked tools,
- **WHEN** the user views the invocation log,
- **THEN** every call is present with timestamp, target capability, duration, and outcome, and **no call arguments or return contents are stored**.

#### Scenario: the command line reads the invocation log
- **GIVEN** a running daemon that has recorded invocations on two servers, on a Coffer built-in tool and on a deleted server
- **WHEN** the user runs `coffer log mcp --server <server>` and then `coffer log mcp --status error --json`
- **THEN** the first prints only that server's calls, newest first
- **AND** the second prints, under `invocations`, only failed calls across every server, each naming its server, including `coffer` and `deleted:<name>` rows

#### Scenario: the invocation log pages by cursor
- **GIVEN** a server with three recorded invocations
- **WHEN** its invocations are read with `limit=2` and then with the answer's `next_cursor`
- **THEN** the first page holds the two newest calls and the second the oldest, with a `null` `next_cursor`

#### Scenario: the invocation log names the calling agent
- **GIVEN** an agent's session connected through its shim made a call, and a session that reported no agent made another
- **WHEN** the invocation log is read, and read again with `agent_uid` set to that agent's uid
- **THEN** the first call's entry names that agent's uid and the second's names none
- **AND** the filtered read holds only the first call
