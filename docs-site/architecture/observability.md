# Observability

For the audit trail and invocation records (who did what, who called what), see [Audit & accountability](/architecture/audit).

## The problem this solves

A developer registers twenty MCP servers and delegates tool calls to them from Claude Code, Codex, and a custom script — all simultaneously. Without operational observability, diagnosing live problems becomes opaque: "Why is this server suddenly returning errors?" "What exactly happened during that failing request?" Structured logs and trace correlation answer these questions without requiring the user to run a separate monitoring stack.

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

Log lines never contain secret material. Secrets are confined to the OS keychain and are never passed as log fields — so no scrub processor is needed or present. The structlog pipeline is: `merge_contextvars`, `add_log_level`, `TimeStamper`, `_add_trace_id`, `JSONRenderer`.

## Trace correlation

Every HTTP response from the daemon carries an `X-Coffer-Trace` header with a request-scoped UUID. This UUID appears in the daemon's structured logs for that request, in any audit entries produced during the request, and in any invocation records from that request. Correlation is mechanical: take the trace ID from the error response and grep `~/.coffer/logs/` for it.

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
