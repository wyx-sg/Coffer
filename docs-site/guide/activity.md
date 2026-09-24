# Activity

Coffer keeps three records of itself, and `/activity` is where you read them. They answer three different questions — *what changed in my vault*, *what did an agent ask the gateway for*, and *what did the daemon itself do* — and they come from three different stores: the `audit_log` table, the `mcp_invocations` table, and the file `~/.coffer/logs/daemon.log`.

That is why the page is three tabs rather than one table. A merged table could only carry the columns all three share, and that is almost nothing: an invocation's duration and status, and a log record's level and logger, would have had nowhere to go, and a single "Detail" column would have meant three different things. Reading *across* the three is an agent's job, not a filter's — see [`coffer__diagnose`](#the-daemon-tab-and-coffer__diagnose) below.

The tab lives in the URL (`?tab=mcp`, `?tab=daemon`), so a link can land on the daemon log and a reload comes back where it was. The old `/audit` and `/observability` routes redirect here. Each tab fetches only while it is in front, and there is no refresh button: a record of what already happened is not a live console.

For how these records are designed and why the audit list is deliberately short, see [Audit & accountability](/architecture/audit) and [Observability](/architecture/observability).

## Changes — the accountability record

The **Changes** tab is the audit log: three columns, *Time*, *Activity* and *Actor*, newest first. The Activity column is the event rendered as a sentence in your interface language ("Memory delivery hook fired for claude-code"); expanding a row shows the stored record verbatim, including the `details` payload.

A row is written **before the response returns to the caller**, and only for changes that meet one of three tests: the change landed outside Coffer (a file written into an agent's own config), it is irreversible or security-sensitive (a delete, a credential read, a master-key export), or it is a low-frequency configuration change that current state cannot reveal (a retention window, a capability turned off). The event types are the members of `AuditEventType` — `resource_enabled`, `credential_read`, `skill_bound`, `knowledge_curated`, `provider_switched`, `sync_run` and the rest — and the list is short on purpose. Runtime telemetry ("the daemon started", "a turn completed") is a log line, not a durable record.

Each row carries the event type, the resource it happened to (kind and name **as they were at the time**, plus the resource's stable row id, so a rename does not rewrite history), the actor, a UTC timestamp and a structured `details` payload. The `details` are redacted per kind before they are stored — `credential_set` records *that* a secret was written, never the secret.

The **Actor** filter is the one filter this record affords that the other two do not. `cli`, `ui` and `api` come from the `X-Coffer-Actor` header each surface sets — the CLI sends `cli`, the web UI sends `ui`, and a caller that sends nothing is recorded as `api`. `system` is the daemon acting on its own, and `user`, `agent` and `channel` are domain actors the backend records directly.

The tab asks the daemon for at most 500 rows with the time window applied server-side; the actor and the free-text box then narrow those rows in the browser. The same query from a terminal:

```bash
coffer audit list --limit 50
coffer audit list --kind mcp_server --name filesystem
coffer audit list --event-type credential_read --since 2026-09-01T00:00:00Z
coffer audit list --json            # for scripts
```

`--kind`, `--name`, `--event-type` and `--since` are all optional and combine; `--limit` accepts 1–500 and defaults to 50. Over HTTP the same query is `GET /api/v1/audit`, which additionally takes `event_prefix` for a whole family (`sync_`, `skill_`).

### Did my memory delivery hook actually fire?

This is the question the Changes tab exists to answer, and the reason the event is audited at all. Coffer writes a session-start hook into an agent's own settings file; whether that hook *ran* is the only thing that distinguishes an installed hook from no feature at all, so the delivery layer records `memory_delivery_fired` when it actually serves the context — never when the hook is merely installed or inspected.

```bash
coffer audit list --event-type memory_delivery_fired --limit 20
coffer audit list --kind agent --name claude-code
```

The row's actor is the **agent's own name**, because nobody clicked anything: the hook ran because that agent started a session. Its siblings `memory_delivery_installed` and `memory_delivery_removed` record Coffer writing into, or cleaning out of, that settings file.

## MCP calls — what went through the gateway

Every tool call, resource read and prompt fetch the gateway routes produces one row: *Time*, *Server*, *Type*, *Key*, *Duration* and *Status*, with the error message under the status badge when there is one. Filters are free text (matching the capability key and the server name), a time window, and the status. This is the same table as the **Invocations** tab on a single MCP server's detail page — here it is unscoped, with the server column in front.

The row says who called what, when, and with what outcome, and nothing more. **Call arguments and return contents are never stored** — the table has no column for them. That is permanent: storing them would turn the invocation log into an exfiltration channel and a retention problem with no good answer.

`status` has four values, and the distinctions are the point:

| Status    | What actually happened                                                                 |
| --------- | --------------------------------------------------------------------------------------- |
| `ok`      | The upstream answered within the timeout, and did not flag the result as an error.       |
| `error`   | The call raised, **or** the tool answered with an in-band error.                          |
| `timeout` | The upstream did not answer in time; its connection is torn down.                         |
| `denied`  | Coffer refused before the upstream was reached — the capability is disabled, or the server is out of scope for that session. Recorded with a duration of 0. |

The honest caveat is in `error`. An MCP tool that fails does not raise: per the spec it returns a well-formed result with `isError` set, which a transport-only recorder would count as a success. Coffer inspects that flag for `tools/call` and records `error` — but the message it stores is a fixed, Coffer-authored marker (`upstream tool returned an error result (isError)`), not the upstream's own text, because that text is upstream-controlled and may echo the arguments. So the log tells you a tool failed; it does not tell you why. `resources/read` and `prompts/get` have no equivalent flag, so a resource that returns useless content is recorded as `ok`.

From a terminal, the same log reads across every server or for one:

```bash
coffer mcp invocations --limit 50                     # every server, as the tab shows it
coffer mcp invocations --status error --json
coffer mcp invocations filesystem --since 2026-09-14T00:00:00Z
```

Without a server the rows include Coffer's own built-in calls (`coffer`) and those of a server deleted before the log was re-keyed (`deleted:<name>`), and the table gains a *Server* column. The cross-server view is `GET /api/v1/mcp/invocations` (with `uid`, `status`, `since` and `limit`); one server's is `GET /api/v1/resources/mcp_server/{uid}/invocations`.

## The daemon tab, and `coffer__diagnose`

The **Daemon** tab is the tail of `~/.coffer/logs/daemon.log` — *Time*, *Level*, *Logger*, *Message*, newest first. This is the tab to open when **Coffer itself** is misbehaving, rather than something Coffer proxied. The level control is a floor, not a toggle: *All levels*, *Debug and above*, *Info and above*, *Warnings and errors*, *Errors only*. A floor rather than "errors only" because a warning is the level most worth noticing *before* something breaks, and an errors-only switch hid exactly that.

Two things about this file are worth knowing before you read it. First, **everything the daemon itself writes is one format** — one JSON object per line carrying the time, the level, the module and the message, whether the record came from Coffer's own code or from a library logging beside it — but the file is also where the daemon's stdout and stderr are redirected, so uvicorn and every stdio upstream that writes to that stderr write their own shapes into it too. `application/log_reader.py` normalises all of them onto `timestamp` / `level` / `logger` / `event`, strips ANSI escapes, and keeps a line that fits no format whole rather than dropping it — including lines from before the daemon's own format was fixed, which is why a long-lived log still reads correctly. Second, a traceback is folded into the record that raised it instead of becoming rows of its own, and a line that carries no time of its own borrows the timestamp of the record beside it — or renders a dash, rather than claiming a time it does not have.

Every audited event is *also* a log line, so the vocabulary is shared: an event code you saw on the Changes tab is greppable here.

The agent-facing half of the same material is `coffer__diagnose`, and it is deliberately **two** of the three records, not all three: it returns the audit log (`changes`) and the daemon log (`log`) on one newest-first timeline, because an agent hitting a failure does not know which of the two it needs. It defaults to the last 60 minutes (7 days maximum) and 40 records, takes `errors_only`, and never returns secret material. Point an agent at it before sending anyone to find a log file by hand.

## Retention — all three are pruned, on different clocks

Nothing here grows forever, and the defaults differ because the records do. A background worker sweeps on start and every six hours after.

| Policy                  | Default   | What it does                                            |
| ----------------------- | --------- | ------------------------------------------------------- |
| `audit_log`             | 365 days  | Deletes rows older than the window.                     |
| `mcp_invocations`       | 30 days   | Deletes rows older than the window.                     |
| `sync_runs`             | 90 days   | Deletes converge-round history.                         |
| `conversations_archive` | 7 days    | Archives chats idle for this long (archives, not deletes). |
| `conversations`         | 30 days   | Deletes archived chats this long after archival.        |

```bash
coffer retention list
coffer retention set audit_log --days 730
coffer retention set mcp_invocations --forever
```

`--forever` stops pruning that table entirely; a window of zero is refused, and the change is itself audited as `retention_updated`. The same rows are in the app under **Settings → Data**, where edits auto-save and *shortening* a window asks first — that is the one edit that costs data. Over HTTP: `GET /api/v1/retention/policies`, `PATCH /api/v1/retention/policies/{table_name}`.

The daemon log is the exception: it is a file, not a table, so it has no policy row. `daemon.log` is bounded by its rotating handler (10 MB, three backups) and is never deleted underneath the open handle that writes it. What the retention worker *does* prune from `~/.coffer/logs/` is stray shim logs and rolled-aside upstream logs older than **7 days**, a fixed window rather than a setting.

## None of this leaves the machine

The audit log, the invocation log and the daemon logs are all machine-local: [Sync](/guide/sync) never publishes them, and a merged history of two machines' activity would be a different feature with a different shape. They are also never sent anywhere else — everything above is read out of `~/.coffer/`, which is also what your backup already covers.

[Web UI →](/guide/web-ui)
