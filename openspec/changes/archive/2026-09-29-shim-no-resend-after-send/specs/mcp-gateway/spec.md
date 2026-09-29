## MODIFIED Requirements

### Requirement: Present Coffer as one MCP server
The system MUST present Coffer as a single MCP server to clients, over both an HTTP/SSE endpoint and a stdio
shim entry point.

Multiple MCP clients (for example Claude Code and Codex at the same time) MUST be able to connect
simultaneously without one disturbing the other, each getting an independent upstream subprocess set. If the
daemon crashes, running shim sessions MUST return a clean error to their MCP clients rather than hang on a
socket that will never answer. When the daemon restarts, a shim session MUST rebind to the new daemon and
MUST NOT run a `tools/call` twice: it resends a request after the restart only when the failure happened
before the request reached the daemon (the connection was refused or timed out), or when the method is not
`tools/call`, or when the old daemon rejected the request with 401. Any other `tools/call` failure MUST be
answered with a JSON-RPC error saying the daemon restarted mid-call and the call may or may not have run.
A tool call routed through Coffer SHOULD add no more than 50 ms of median
overhead compared with the same call made directly to the upstream, measured over 100 calls of a fast
in-process tool.

#### Scenario: aggregate tools across servers in one client
- **GIVEN** two MCP servers are registered and healthy,
- **WHEN** an MCP client connects through coffer's shim and lists tools,
- **THEN** every enabled tool from every registered server appears, named `<server>__<tool>`, and no two tools collide.

#### Scenario: concurrent clients
- **GIVEN** two MCP clients connect simultaneously,
- **WHEN** each lists and calls tools,
- **THEN** both succeed without interference, and each client receives a distinct upstream subprocess set (verified by counting entries in `~/.coffer/upstream-pids/`).

#### Scenario: gateway overhead stays under budget
- **GIVEN** an in-process fast tool reachable through coffer and directly,
- **WHEN** the same tool is called 100 times via coffer and 100 times directly,
- **THEN** the median per-call gateway overhead (coffer-mediated latency minus direct latency) is at most 50 ms.

#### Scenario: a tool call is not re-run after the daemon restarts mid-call
- **GIVEN** a shim session whose daemon receives a `tools/call` and then dies before replying, and a new daemon that has come up on another port
- **WHEN** the shim's POST fails with a read error
- **THEN** the shim rebinds to the new daemon and answers that request id with a JSON-RPC error saying the call may or may not have run, without sending the call to the new daemon
- **AND** a `tools/call` whose connection was refused, a `tools/list` that failed the same way, and a request the old daemon rejected with 401 are each sent once to the new daemon and answered from it
