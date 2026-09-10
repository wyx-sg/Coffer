# Observability

For the audit trail and invocation records (who did what, who called what), see [Audit & accountability](/architecture/audit).

## The problem this solves

A developer runs a busy vault: a couple dozen MCP servers, turns running against several coding agents, and a connected messaging channel — all in flight at once. Without operational observability, diagnosing live problems becomes opaque: "Why is this server suddenly returning errors?" "What exactly happened during that failing request or agent turn?" Structured logs and trace correlation answer these questions without requiring the user to run a separate monitoring stack.

Coffer's approach is deliberately lean: structured local logs, not a metrics pipeline. All observability stays on-device and within the `~/.coffer/` backup footprint.

## Logging: structlog JSON-per-line

The daemon uses `structlog` configured for JSON output to `~/.coffer/logs/`. Each log line is one complete JSON object with a fixed set of top-level keys plus event-specific fields:

```json
{
  "timestamp": "2026-05-20T14:23:01.123Z",
  "level": "info",
  "logger": "coffer.surfaces.http.resource",
  "event": "resource_registered",
  "trace_id": "b3d8e2f1-...",
  "resource_ref": "mcp_server:filesystem",
  "actor": "cli",
  "duration_ms": 12
}
```

A `contextvar` carries the `trace_id` through the full async call stack for a request. When a FastAPI handler calls an application service which calls a repository which calls the ORM, every log line emitted at any depth shares the same `trace_id` from the outer request. This makes it possible to reconstruct a complete per-request trace from raw log lines without a distributed tracing system.

Log files are in `~/.coffer/logs/`. Rotation is handled by Python's `logging.handlers.RotatingFileHandler` (size-based: 10 MB per file, 3 backup files kept). Logs are subject to the same `~/.coffer/` backup footprint as the database.

### What lands where

| File | Holds |
| ---- | ----- |
| `daemon.log` | Coffer's own structured records. Bounded by the rotating handler. |
| `upstream/<server>.log` | One upstream MCP server's stderr, plus one rolled-aside `.log.1`. |
| `shim-<pid>-<ts>.log` | One shim process's diagnostics. Created lazily — a run that logs nothing leaves no file. |

**Upstreams get their own files because they used to drown the daemon's.** The MCP SDK writes each stdio server's stderr to the daemon's own stderr, which lands in `daemon.log`; upstreams are chatty and Coffer is not. A measured daemon log held 4,277 lines of which **62** were Coffer's — all one error type — and rotation had carried everything older away inside two months.

**Every audited event is also logged.** `AuditService.record` emits an INFO line for each entry it writes, so the operations the audit table considers worth recording are legible to whoever is tailing a log rather than querying SQLite. The `details` payload is deliberately *not* logged: the audit table applies each kind's redactor before storing it, and re-deriving that in the logger would duplicate the one place that knows which fields carry secrets.

### Retention

Log files age out on the same cadence as the audit and invocation tables — the retention worker prunes `shim-*.log` and rolled-aside `upstream/*.log.1` older than 7 days. `daemon.log` and its rotations are deliberately excluded: the handler holds an open descriptor, and deleting a file underneath it would break logging until the next restart.

This exists because nothing deleted anything before: 2,137 shim logs (40 MB) had accumulated over three months, one per process start, with no rotation and no prune.

Log lines never contain secret material. Secrets live only as ciphertext in the credential store, and their plaintext is never passed as a log field — so no scrub processor is needed or present. The structlog pipeline is: `merge_contextvars`, `add_log_level`, `TimeStamper`, `_add_trace_id`, `JSONRenderer`.

## Trace correlation

Every HTTP response from the daemon carries an `X-Coffer-Trace` header with a request-scoped UUID. This UUID appears in the daemon's structured logs for that request, in any audit entries produced during the request, and in any invocation records from that request. Correlation is mechanical: take the trace ID from the error response and grep `~/.coffer/logs/` for it.

The same structured-logging and trace-id correlation now spans the rest of the vault too — chat turns, channel events, and sync runs all flow through the same `contextvar`-propagated trace IDs and land in the same JSON log lines.

::: tip CLI usage
When running `coffer` with the `--verbose` flag, the CLI prints the `X-Coffer-Trace` ID alongside the human-readable error. For scripted workflows that need to correlate CLI output with daemon logs, this is the handle.
:::

## Errors: uniform response envelope

All surfaces return errors in the same shape:

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "No mcp_server named 'my-server'.",
    "details": {}
  }
}
```

The `code` is a stable UPPER_SNAKE_CASE string defined in `domain/errors.py`. The `message` is a human-readable sentence aimed at the developer. The `details` field carries structured context (e.g., the list of registered kind names when a kind is not found, or the constraint that was violated on a validation error).

## See also

- [Audit & accountability](/architecture/audit) — audit log, invocation log, and retention
- [Architecture reference](/reference/project/architecture) — Errors and Logging entries in the cross-cutting concerns table
- [Spec 001 reference](/reference/specs/001-mcp-gateway/spec) — token authentication and `X-Coffer-Actor` header semantics
