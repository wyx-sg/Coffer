## ADDED Requirements

### Requirement: Correlate the audit log, the MCP invocation log and the daemon log by one trace id
Every record the daemon writes for a unit of work — an HTTP request, or a chat
or channel turn — MUST carry that unit's correlation id, `trace_id`, so its
audit rows, its MCP invocations and its daemon log lines can be read as one
story rather than lined up by time. An HTTP request's id is its
`X-Coffer-Trace` (the client's, sanitised, or one the daemon mints; spec
[daemon](../daemon/spec.md) "Answer the status probe without a token" is
answered with one like every other route). A turn carries a `conversation_id`
and a fresh `turn_id` of its own, and keeps the trace id of the request that
started it; a turn no request started — a channel message that arrived over a
websocket or a long poll — uses its turn id as its trace id. The ids MUST
follow the work into the tasks it starts, so a turn's renderer and a request's
background write carry them too.

- An audit row MUST store `trace_id`, and `conversation_id` and `turn_id` when a
  turn wrote it; a row written with nothing bound (a boot pass, a periodic
  worker) stores none, and no id is invented for a row written before the
  columns existed.
- An MCP invocation MUST store the `/mcp` request's `trace_id` beside its
  session id, and the audit rows the call causes carry the same `trace_id`.
- Every daemon log line MUST carry `trace_id` (`-` when none is bound), and
  `session_id`, `conversation_id` and `turn_id` when it was written inside an
  MCP call or a turn.

`GET /api/v1/audit`, `GET /api/v1/mcp/invocations` (and one server's
invocations) and `GET /api/v1/daemon/logs` MUST each take a `trace_id` filter,
and `coffer log audit`, `coffer log mcp` and `coffer log daemon` MUST take it
as `--trace`, the audit and MCP tables showing each row's trace id. The
Activity page's record drawer MUST show a change's and a call's trace id when
the record has one.

#### Scenario: a request's audit rows carry its trace id
- **GIVEN** a request sent with `X-Coffer-Trace: req-a1` that creates a resource
- **WHEN** the audit log is read with `trace_id=req-a1`
- **THEN** it returns that request's `resource_created` row, carrying `trace_id: "req-a1"`, and no row another request wrote
- **AND** the daemon log read with `trace_id=req-a1` returns the lines that request wrote

#### Scenario: an MCP call's records carry its session and trace id
- **GIVEN** an MCP session that calls `coffer__write` on a `/mcp` request sent with `X-Coffer-Trace: mcp-call-7`
- **WHEN** the invocation log, the audit log and the daemon log are each read with `trace_id=mcp-call-7`
- **THEN** the invocation carries the session id and `mcp-call-7`, the audit rows the write made carry `mcp-call-7`, and the log lines carry both the trace id and the session id

#### Scenario: a turn's records carry its conversation and turn
- **GIVEN** a chat turn that records an audit event while it runs, with no HTTP request behind it
- **WHEN** the row and the turn's log lines are read back
- **THEN** each carries the conversation's id and the turn's own id, and the trace id is the turn id
- **AND** a second turn of the same conversation carries a different turn id, and a turn a request started keeps that request's trace id

#### Scenario: the command line filters each log by trace id
- **GIVEN** an MCP call made with trace id `cli-trace-3` that wrote to the audit log
- **WHEN** the user runs `coffer log audit --trace cli-trace-3`, `coffer log mcp --trace cli-trace-3 --json` and `coffer log daemon --trace cli-trace-3 --json`
- **THEN** each prints only the records carrying `cli-trace-3`, the audit table showing the id on each row

#### Scenario: the Activity drawer shows a record's trace id
- **GIVEN** an audit row and an MCP call that each carry a trace id
- **WHEN** the user opens each in the Activity page's drawer
- **THEN** the drawer shows a "Trace id" fact with that id
- **AND** a record with no trace id shows no such fact
