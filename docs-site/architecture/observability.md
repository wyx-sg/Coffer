# Observability

For the audit trail and invocation records (who did what, who called what), see [Audit & accountability](/architecture/audit).

## The problem this solves

A developer runs a busy vault: a couple dozen MCP servers, turns running against several coding agents, and a connected messaging channel — all in flight at once. Without operational observability, diagnosing live problems becomes opaque: "Why is this server suddenly returning errors?" "What exactly happened during that failing request or agent turn?" Structured logs and trace correlation answer these questions without requiring the user to run a separate monitoring stack.

Coffer's approach is deliberately lean: structured local logs, not a metrics pipeline. All observability stays on-device and within the `~/.coffer/` backup footprint.

## Logging: one JSON object per line

Every record produced inside the daemon process leaves as one JSON object in `~/.coffer/logs/`, with a fixed set of top-level keys plus whatever the call site passed as `extra={...}`. Coffer's own modules log through **stdlib** `logging.getLogger(...)` — all 119 call sites — and the shape is decided in one place: `structlog.stdlib.ProcessorFormatter`, a stdlib formatter, is attached to the daemon's handlers and runs a structlog processor chain over each record. So a library logging beside Coffer (alembic, asyncio, the MCP SDK) lands in the same shape without knowing anything about it:

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
| `daemon.log` | Coffer's own structured records — **and every other writer that ends up on the daemon's stdio** (see below). Bounded by the rotating handler. |
| `upstream/<server>.log` | One upstream MCP server's stderr, plus one rolled-aside `.log.1`. |
| `shim-<pid>-<ts>.log` | One shim process's diagnostics. Created lazily — a run that logs nothing leaves no file. |

**Upstreams get their own files because they used to drown the daemon's.** The MCP SDK writes each stdio server's stderr to the daemon's own stderr, which lands in `daemon.log`; upstreams are chatty and Coffer is not. A measured daemon log held 4,277 lines of which **62** were Coffer's — all one error type — and rotation had carried everything older away inside two months.

**What the daemon writes is one format; what other processes write is theirs.** `daemon.log` is also where a detached daemon's stdout and stderr are redirected, so every child the daemon holds a pipe to ends up in the same file in its own shape: uvicorn writes `ERROR:    …` (it keeps its own three loggers off the root), an upstream MCP server writes rich panels and `LEVEL - logger - message` lines, and the cloudflared child a tunnel respawns writes zerolog (`2026-09-14T06:29:20Z INF … key=value`) — some of it ANSI-coloured, because a child writing to a pipe is not always convinced it is not a terminal. `application/log_reader.py` is the one place that knows all of them: it tries Coffer's JSON first, normalises every other writer's line onto `timestamp` / `level` / `logger` / `event`, strips escape sequences, folds a traceback into the record that raised it under `continuation`, and keeps a line no format fits whole as `{"raw": …}`. Both readers — `coffer__diagnose` and `GET /api/v1/daemon/logs` behind the Activity page's Daemon tab — go through it, so they agree on what a record is.

Two things had to be fixed for that first sentence to be true, and both were visible on the Activity page. **A library may not change the daemon's format**: running a migration used to call alembic's `fileConfig`, which *replaces* the root logger's handlers — tearing out the rotating file handler and installing alembic's `%(levelname)-5.5s [%(name)s] %(message)s` console handler — so the format depended on whether a migration had run yet this boot, and the fields a record carried depended on that too. `env.py` no longer calls it and `alembic.ini` no longer carries logging sections. **And each record is written exactly once**: because the stdout/stderr redirect points at the same file as the rotating handler, a stderr handler wrote every Coffer record into it a second time and the page rendered two rows per record. The stderr handler is now attached only when stderr is not that file — compared by device and inode, since the redirect arrives as a descriptor with no readable path — which is the foreground case where it is the only way to see anything.

**Every audited event is also logged.** `AuditService.record` emits an INFO line for each entry it writes, so the operations the audit table considers worth recording are legible to whoever is tailing a log rather than querying SQLite. The `details` payload is deliberately *not* logged: the audit table applies each kind's redactor before storing it, and re-deriving that in the logger would duplicate the one place that knows which fields carry secrets.

### Retention

Log files age out on the same cadence as the audit and invocation tables — the retention worker prunes `shim-*.log` and rolled-aside `upstream/*.log.1` older than 7 days. `daemon.log` and its rotations are deliberately excluded: the handler holds an open descriptor, and deleting a file underneath it would break logging until the next restart.

This exists because nothing deleted anything before: 2,137 shim logs (40 MB) had accumulated over three months, one per process start, with no rotation and no prune.

Log lines never contain secret material. Secrets live only as ciphertext in the credential store, and their plaintext is never passed as a log field — so no scrub processor is needed or present. The processor chain, which is the only place the shape of a line is decided, is: `add_logger_name`, `add_log_level`, a timestamp taken from the record's own `created` rather than the clock at format time, `ExtraAdder`, `_add_trace_id`, `format_exc_info` — rendered as JSON by `ProcessorFormatter`. The last two are worth naming: `ExtraAdder` is why the ~106 call sites that pass `extra={...}` now put those fields on the line instead of having them formatted away, and `format_exc_info` is why an `exc_info=True` traceback stays *inside* one record (its newlines escaped) rather than becoming a run of rows with no time, level or logger of their own.

## Trace correlation

Every HTTP response from the daemon carries an `X-Coffer-Trace` header with a request-scoped UUID. This UUID appears on every log line emitted during that request, in any audit entries produced during the request, and in any invocation records from that request. Correlation is mechanical: take the trace ID from the error response and grep `~/.coffer/logs/` for it.

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
