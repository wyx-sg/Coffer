---
title: Activity and audit
description: Read what changed in your vault, what agents called through the gateway, and what the daemon logged, and control how long each record is kept.
---

# Activity and audit

Coffer keeps three records of itself: an audit log of what changed in the vault, an invocation log of every call routed through the MCP gateway, and the daemon's own log. This page shows where to read each one, from the web UI, the CLI and an agent, how to tie a failed request to its log lines, and how long each record is kept.

## Three records, three questions

| Record | Answers | Stored in | Where to read it |
| --- | --- | --- | --- |
| Audit log | What changed, and who changed it? | `audit_log` table in `coffer.db` | **Activity → Changes**, `coffer audit list`, `coffer__diagnose` |
| MCP invocations | What did an agent call, and how did it go? | `mcp_invocations` table | **Activity → MCP calls**, `coffer mcp invocations` |
| Daemon log | What happened inside Coffer, including what broke? | `~/.coffer/logs/daemon.log` | **Activity → Daemon**, `coffer__diagnose` |

All three stay on the machine that wrote them. [Vault sync](/guides/vault-sync) never publishes them, and Coffer sends them nowhere.

## The Activity page

Open **Activity** in the sidebar. It has one tab per record: **Changes**, **MCP calls** and **Daemon**, each newest first with its own filters. The active tab is part of the URL (`/activity?tab=mcp`, `/activity?tab=daemon`), so you can bookmark or share a link that lands on the daemon log. Each tab loads up to 500 rows for the chosen time range; the search box then narrows them in the page. There is no refresh button: switching tab, changing a filter or returning to the window reloads the data.

### Changes

The audit log, in three columns: **Time**, **Activity** and **Actor**. The Activity column renders the event as a sentence ("Stored a credential", "Updated reach for work-jira"); expand a row to see the stored record, including its `details`. Filter by **Actor**, time range and free text.

### MCP calls

One row per tool call, resource read or prompt fetch the gateway routed: **Time**, **Server**, **Type**, **Key**, **Duration** and **Status**. It is the same table as the **Invocations** tab on an MCP server's own page, across every server. Filter by status, time range and free text.

### Daemon

The tail of `daemon.log`: **Time**, **Level**, **Logger** and **Message**. The level control is a floor: **All levels**, **Debug and above**, **Info and above**, **Warnings and errors**, **Errors only**. Open this tab when Coffer itself misbehaves rather than something it proxied.

## What an audit entry records

Each entry holds:

| Field | Meaning |
| --- | --- |
| `timestamp` | When it happened, in UTC. |
| `event_type` | What happened, for example `resource_created`, `resource_scope_updated`, `credential_read`, `skill_bound`, `provider_switched`, `sync_run`, `token_rotated`. |
| `resource_kind`, `resource_name` | The resource it happened to, as it was named at that moment. |
| `resource_id` | The resource's stable row id, so its history survives a rename. |
| `actor` | Who did it (below). |
| `details` | A structured payload, redacted per kind before it is stored. A `credential_set` records that a secret was written, never the secret. |

The **actor** is one of:

| Actor | Shown as | Source |
| --- | --- | --- |
| `ui` | You (web UI) | The web UI sends `X-Coffer-Actor: ui`. |
| `cli` | CLI | The CLI sends `X-Coffer-Actor: cli`. |
| `api` | API | A REST caller that sent no `X-Coffer-Actor` header. |
| `system` | Coffer | The daemon acting on its own, such as a background pass. |
| `sync` | sync | A converge round applying what another machine changed. |
| `channel` | Channel | An action taken from a chat channel. |
| an agent's name | the name | An agent's own action, such as its session-start memory hook firing (`memory_delivery_fired`). |

Not every event is audited. The log keeps changes that land outside Coffer (a file written into an agent's configuration), that are irreversible or security-sensitive (a deletion, a credential read, a master-key export), or that current state cannot reveal later (a retention window). Routine runtime events are log lines, not audit rows. Every audited event is also written to the daemon log under the same event name, so you can search either one for it.

## Query the audit log from the CLI

```sh
coffer audit list                                   # newest 50
coffer audit list --kind mcp_server --name filesystem
coffer audit list --event-type credential_read --since 2026-09-01T00:00:00Z
coffer audit list --event-type memory_delivery_fired --limit 20
coffer audit list --json
```

| Option | Meaning |
| --- | --- |
| `--kind` | Resource kind, such as `mcp_server`, `agent`, `skill`. |
| `--name` | Resource name. |
| `--event-type` | One event type. |
| `--since` | ISO 8601 lower bound. |
| `--limit` | 1–500, default 50. |
| `--json` | Machine-readable output. |

Over REST the same query is `GET /api/v1/audit`, which also accepts `event_prefix` to select a family of events such as `sync_` or `skill_`. See the [REST API reference](/reference/rest-api).

## Query MCP invocations from the CLI

```sh
coffer mcp invocations                      # every server, newest 20
coffer mcp invocations filesystem           # one server
coffer mcp invocations --status error --since 2026-09-20T00:00:00Z --json
```

Without a server name the output includes Coffer's own built-in tool calls (server `coffer`) and rows of deleted servers (`deleted:<name>`). `--limit` accepts 1–500.

An invocation has one of four statuses:

| Status | Meaning |
| --- | --- |
| `ok` | The upstream answered in time and did not flag an error. |
| `error` | The call raised, or the tool returned a result with `isError` set. |
| `timeout` | The upstream did not answer within the server's request timeout. |
| `denied` | Coffer refused before reaching the upstream: the capability is disabled, or the server is outside that agent's reach. |

::: info Arguments and results are never stored
The invocation log records who called what, when, for how long and with what outcome. It has no column for call arguments or return values. For a tool that reported `isError`, the stored message is Coffer's fixed text `upstream tool returned an error result (isError)`, not the upstream's own message, which may echo the arguments. To see why a tool failed, look at the server's stderr in `~/.coffer/logs/upstream/<server>.log`.
:::

## Let an agent diagnose Coffer: `coffer__diagnose`

When something goes wrong in a session, the agent can read Coffer's history itself. `coffer__diagnose` is one of Coffer's built-in MCP tools. It returns two newest-first timelines in one answer: `changes` from the audit log and `log` from the daemon log. It is read-only and returns no secret values.

| Argument | Default | Meaning |
| --- | --- | --- |
| `since_minutes` | 60 | How far back to look, up to 10080 (seven days). |
| `limit` | 40 | Maximum entries per timeline, up to 200. |
| `errors_only` | false | Keep only error-level log records. The audit side is unaffected. |
| `event_type` | none | Filter the audit side to one event type. |
| `resource_kind` | none | Filter the audit side to one kind. |
| `resource_name` | none | Filter the audit side to one resource by its current name. Requires `resource_kind`. |

A prompt such as "my Jira tool keeps failing, check Coffer's logs" is enough: the agent calls the tool rather than asking you to find a file.

## Correlate a failed request with the log: `X-Coffer-Trace`

Every HTTP request the daemon serves gets a trace id. The daemon stamps it as `trace_id` on every log record the request produces and returns it in the `X-Coffer-Trace` header of every response, error responses included. To find what happened during one failed request:

```sh
curl -si -H "X-Coffer-Token: $TOKEN" http://127.0.0.1:8000/api/v1/resources/nope \
  | grep -i x-coffer-trace
# x-coffer-trace: 3f9c0a6e2b7d4e1f9a0c5b2d8e7f6a1c

grep 3f9c0a6e2b7d4e1f9a0c5b2d8e7f6a1c ~/.coffer/logs/daemon.log
```

A client can also send its own `X-Coffer-Trace` header so that several calls made for one action share one id. The value is capped at 64 characters and reduced to letters, digits and `._:-`; a value that does not survive that is replaced with a fresh id.

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
coffer retention list
coffer retention set audit_log --days 730
coffer retention set mcp_invocations --forever     # never prune this table
coffer retention prune-now                         # apply every policy now
coffer retention prune-now --table mcp_invocations
```

```text [Web UI]
Settings → Data → Data retention
```

:::

`--days` must be at least 1. In the web UI, shortening a window asks for confirmation first, because the next prune deletes the older rows; **Clear expired data now** applies every policy immediately. A policy change is itself audited as `retention_updated`.

The daemon log is a file, not a table, so it has no policy: `daemon.log` rotates at 10 MB and keeps three rotations. Per-process shim logs and rolled-aside upstream logs in `~/.coffer/logs/` are deleted after seven days.

## How it works

Why the audit list is short, how the log reader normalises every writer's format, and how trace ids reach log lines are covered in [Observability](/architecture/observability).

## Related

- [Troubleshooting](/guides/troubleshooting)
- [Running the daemon](/guides/daemon#logs)
- [MCP servers](/guides/mcp-servers)
- [MCP tools reference](/reference/mcp-tools)
- Specs: [resource-framework](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/resource-framework/spec.md), [daemon](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/daemon/spec.md)
