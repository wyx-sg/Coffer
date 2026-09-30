---
title: Activity and audit
description: Read what changed in your vault, what agents called through the gateway, and what the daemon logged, and control how long each record is kept.
---

# Activity and audit

Coffer keeps three records of itself: an audit log of what changed in the vault, an invocation log of every call routed through the MCP gateway, and the daemon's own log. This page shows where to read each one, from the web UI, the CLI and an agent, how to tie a failed request to its log lines, and how long each record is kept.

## Three records, three questions

| Record | Answers | Stored in | Where to read it |
| --- | --- | --- | --- |
| Audit log | What changed, and who changed it? | `audit_log` table in `coffer.db` | **Activity → Changes**, `coffer log audit` |
| MCP invocations | What did an agent call, and how did it go? | `mcp_invocations` table | **Activity → MCP calls**, `coffer log mcp` |
| Daemon log | What happened inside Coffer, including what broke? | `~/.coffer/logs/daemon.log` | **Activity → Daemon log**, `coffer log daemon`, `coffer path logs` |

All three stay on the machine that wrote them. [Vault sync](/guides/vault-sync) never publishes them, and Coffer sends them nowhere.

## The Activity page

Open **Activity** in the sidebar. The green dot beside the title means new records are streaming in. It has four tabs, each with the number of records it holds in the chosen time range (a tab with none, or whose log could not be read, shows no number):

- **Everything** — the default: changes, MCP calls and the daemon's warnings and errors merged into one stream, newest first. Columns: **Time**, **Event**, **By** and **Took**.
- **Changes** — the audit log: **Time**, **Event** (the change as a sentence, such as "Stored a secret") and **By** (who made it).
- **MCP calls** — one row per tool call, resource read or prompt fetch the gateway routed: **Time**, **Agent** (whose session made it), **Server · tool**, **Took** and **Status**. A server's own **Invocations** tab reads the same log for that one server.
- **Daemon log** — the tail of `daemon.log`: **Time**, **Level**, **Logger** and **Message**. Open it when Coffer itself misbehaves rather than something it proxied. The line above the rows names the file, and **Open log file** opens it in your editor.

Above the rows a line says what the list holds: on Everything, the errors and warnings in the window ("1 error and 1 warning in the last hour"), or how many records are loaded of how many there are; on MCP calls, the calls, failed calls and denied calls in the window.

The active tab is part of the URL (`/activity?tab=mcp`, `/activity?tab=daemon`; Everything is `/activity`), so a link can land on the daemon log.

**Filters.** Every tab filters by time range and free text; press `/` to jump to the text box. The time range offers the last 15 minutes, hour, 24 hours or 7 days, **Everything kept**, or a custom From and To (leave To empty for now). A tab opens on the last hour, the Daemon log on the last 24 hours, until you pick a range. The tabs add what their records carry: **Agent** on Everything, Changes and MCP calls; **Server** on Everything and MCP calls; **Kind** on Everything and Changes; **Status** on MCP calls; a level (**All**, **Info**, **Warnings**, **Errors**) and **Logger** on the Daemon log.

**Agent** and **Kind** take several values at once, each listed with how many loaded records carry it, and a record is shown when it matches any of them. **Agent** lists your agents, then who else makes changes: **You** (the web UI or the Coffer app), **CLI**, **Coffer** itself and **Sync**. **Kind** lists **MCP calls**, **Changes** with each kind of change under it (MCP servers, skills, agents, secrets, sync, settings, knowledge, memory and so on), and **Daemon records**. Choosing agents or kinds narrows the list; the tab counts stay the same.

**Details.** Select a row to open it in a drawer beside the list. A failed call leads with its error and how its server has been doing — since when it has been failing and how many errors it had in the last 24 hours; a change says who made it and what it touched, then shows the configuration before and after as a diff (secret values are never recorded); a daemon record shows its message and traceback. Below come the facts — agent, session, server and transport, tool, how long it took, the call's id — the records written within five minutes of it, and the raw record. A call shows its metadata only: its arguments and results are never stored. The arrows step to the previous or next record, and the footer holds the next step: **Open** the resource, **Daemon log records** for a failed call's server, or copy the record.

On the **Daemon log** a row opens in place instead, under its own line, with its traceback, **Copy record** and — when the record names a server and a tool — **Show the MCP call**, which switches to MCP calls looking for that call.

**New records arrive on their own.** While you are at the top of the list with nothing open, new records appear at the top as they are written. Once you scroll down or open a record the list holds still, and an **↑ N new** button counts what is waiting; choose it, or scroll back to the top, to bring them in. There is no pause or refresh button. The newest records of each log are re-read every few seconds, and a change the daemon announces on its [event stream](/architecture/event-stream) brings the audit log's in at once.

**Older records.** Each tab loads 200 records at a time; **Load older** at the bottom fetches the next page by the log's cursor, until the time range is exhausted. Beside it Coffer says how long MCP calls and changes are kept, with a link to **Settings › Data** where that is set.

**Export.** The **⋯** menu next to the title, **Export filtered records…**, has **Export as JSON** and **Export as CSV**. Either writes every record of the visible tab that matches its current filters — not just the ones loaded — up to 10,000 records, to a file you save.

## What an audit entry records

Each entry holds:

| Field | Meaning |
| --- | --- |
| `timestamp` | When it happened, in UTC. |
| `event_type` | What happened, for example `resource_created`, `resource_scope_updated`, `credential_revealed`, `skill_bound`, `provider_switched`, `sync_run`, `token_rotated`. |
| `resource_kind`, `resource_name` | The resource it happened to, as it was named at that moment. |
| `resource_id` | The resource's stable row id, so its history survives a rename. |
| `actor` | Who did it (below). |
| `details` | A structured payload, redacted per kind before it is stored. A `credential_set` records that a secret was written, never the secret. |

The **actor** is one of:

| Actor | Shown as | Source |
| --- | --- | --- |
| `ui` | You (web UI) | The web UI sends `X-Coffer-Actor: ui`. |
| `desktop` | You (Coffer app) | An action the desktop app confirmed. |
| `cli` | CLI | The CLI sends `X-Coffer-Actor: cli`. |
| `api` | API | A REST caller that sent no `X-Coffer-Actor` header. |
| `system` | Coffer | The daemon acting on its own, such as a background pass. |
| `sync` | Sync | A converge round applying what another machine changed. |
| `channel` | Channel | An action taken from a chat channel. |
| an agent's name | the name | An agent's own action, such as its memory hook delivering a note (`memory_delivery_fired`, whose details name the moment, the session and the notes). |

Not every event is audited. The log keeps changes that land outside Coffer (a file written into an agent's configuration), that are irreversible or security-sensitive (a deletion, a secret revealed in the desktop app or resolved by `coffer run`, an approval, a master-key backup), or that current state cannot reveal later (a retention window). Routine runtime events are log lines, not audit rows. Every audited event is also written to the daemon log under the same event name, so you can search either one for it.

## Query the audit log from the CLI

```sh
coffer log audit                                   # newest 50
coffer log audit --kind mcp_server --name filesystem
coffer log audit --event-type secret_resolved --since 2026-09-01T00:00:00Z
coffer log audit --event-type memory_delivery_fired --limit 20
coffer log audit --json
```

| Option | Meaning |
| --- | --- |
| `--kind` | Resource kind, such as `mcp_server`, `agent`, `skill`. |
| `--name` | Resource name. Needs `--kind`. |
| `--event-type` | One event type. |
| `--since` | ISO 8601 lower bound, or an age such as `30m`, `1h`, `2d`. |
| `--limit` | 1–500, default 50. |
| `--json` | Machine-readable output. |

Over REST the same query is `GET /api/v1/audit`, which also accepts `event_prefix` to select a family of events such as `sync_` or `skill_`. See the [REST API reference](/reference/rest-api).

## Query MCP invocations from the CLI

```sh
coffer log mcp                              # every server, newest 20
coffer log mcp --server filesystem          # one server
coffer log mcp --status error --since 1d --json
```

Without `--server` the output includes Coffer's own built-in tool calls (server `coffer`) and rows of deleted servers (`deleted:<name>`). `--limit` accepts 1–500.

An invocation has one of four statuses:

| Status | Meaning |
| --- | --- |
| `ok` | The upstream answered in time and did not flag an error. |
| `error` | The server would not start, the call raised, or the tool returned a result with `isError` set. |
| `timeout` | The upstream did not answer within the server's request timeout. |
| `denied` | Coffer refused before reaching the upstream: the server or the capability is disabled, or the server is outside that agent's reach. |

::: info Arguments and results are never stored
The invocation log records who called what, when, for how long and with what outcome. It has no column for call arguments or return values. For a tool that reported `isError`, the stored message is Coffer's fixed text `upstream tool returned an error result (isError)`, not the upstream's own message, which may echo the arguments. To see why a tool failed, look at the server's stderr in `~/.coffer/logs/upstream/<server>.log`.
:::

## Read the daemon log from the CLI

```sh
coffer log daemon                           # newest 100 records
coffer log daemon --errors --since 1h
coffer log daemon --json
coffer path logs                            # the log directory and its daemon.log
```

`coffer log daemon` reads the tail of `daemon.log` normalised the way the **Daemon log** tab shows it. `--limit` accepts 1–500. `coffer path logs` prints where the file is (`COFFER_LOG_DIR` moves it), so you can `grep` it directly.

## Let an agent look into Coffer

When something goes wrong in a session, the agent can read Coffer's history itself, with the same commands: `coffer log audit`, `coffer log mcp` and `coffer log daemon --errors --since 1h` from its shell, or a `grep` over the daemon log that `coffer path logs` names. None of them returns a secret value. A prompt such as "my Jira tool keeps failing, check Coffer's logs" is enough: the `coffer-guide` skill tells the agent where to look, so it does not ask you to find a file.

## Correlate a failed request with the log: `X-Coffer-Trace`

Every HTTP request the daemon serves gets a trace id. The daemon stamps it as `trace_id` on every log record the request produces and returns it in the `X-Coffer-Trace` header of every response, error responses included. To find what happened during one failed request:

```sh
curl -si -H "X-Coffer-Token: $TOKEN" http://127.0.0.1:8000/api/v1/resources/nope \
  | grep -i x-coffer-trace
# x-coffer-trace: 3f9c0a6e2b7d4e1f9a0c5b2d8e7f6a1c

grep 3f9c0a6e2b7d4e1f9a0c5b2d8e7f6a1c ~/.coffer/logs/daemon.log
```

A client can also send its own `X-Coffer-Trace` header so that several calls made for one action share one id; the `coffer` CLI and the MCP shim do not, so each of their requests has its own id. The value is capped at 64 characters and reduced to letters, digits and `._:-`; a value that does not survive that is replaced with a fresh id.

## Control how long records are kept

A background worker prunes on daemon start and every six hours after. Each record has a policy:

| Policy | Default | Effect |
| --- | --- | --- |
| `audit_log` | 365 days | Deletes older audit entries. |
| `mcp_invocations` | 30 days | Deletes older invocation rows. |
| `sync_runs` | 90 days | Deletes older converge-round history. |
| `conversations_archive` | 7 days | Archives chats with no new message for this long. |
| `conversations` | 30 days | Deletes archived chats (with their messages) this long after archival. |

::: code-group

```sh [CLI]
coffer config list retention.
coffer config set retention.audit_log 730
coffer config set retention.mcp_invocations forever   # never prune this table
coffer log prune                                      # apply every policy now
coffer log prune --table mcp_invocations
```

```text [Web UI]
Settings → Data → History
```

:::

A number of days must be at least 1. The web UI's **History** block shows the three a person usually tunes — **Changes** (`audit_log`), **MCP calls** (`mcp_invocations`) and **Conversations** (`conversations`); the others are set from the CLI. In the web UI, shortening a window asks for confirmation first, because the next prune deletes the older rows, and the confirmation counts them; **Clear expired data now** applies every policy immediately. A policy change is itself audited as `retention_updated`.

The daemon log is a file, not a table, so it has no policy: `daemon.log` rotates at 10 MB and keeps three rotations. Per-process shim logs and rolled-aside upstream logs in `~/.coffer/logs/` are deleted after seven days.

## How it works

Why the audit list is short, how the log reader normalises every writer's format, and how trace ids reach log lines are covered in [Observability](/architecture/observability).

## Related

- [Troubleshooting](/guides/troubleshooting)
- [Running the daemon](/guides/daemon#logs)
- [MCP servers](/guides/mcp-servers)
- [MCP tools reference](/reference/mcp-tools)
- Specs: [resource-framework](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/resource-framework/spec.md), [daemon](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/daemon/spec.md)
