---
title: Activity and audit
description: Read what changed in your vault, what agents called through the gateway, and what the daemon logged, and control how long each record is kept.
---

# Activity and audit

Coffer keeps three records of itself: an audit log of what changed in the vault, an invocation log of every call routed through the MCP gateway, and the daemon's own log. This page shows where to read each one, from the web UI, the CLI and an agent, how to tie a failed request to its log lines, and how long each record is kept.

## Three records, three questions

| Record | Answers | Stored in | Where to read it |
| --- | --- | --- | --- |
| Audit log | What changed, and who changed it? | `audit_log` table in `runs.db` | **Activity → Changes**, `coffer log audit` |
| MCP invocations | What did an agent call, and how did it go? | `mcp_invocations` table | **Activity → Tool calls**, `coffer log mcp` |
| Daemon log | What happened inside Coffer, including what broke? | `~/.coffer/logs/daemon.log` | **Activity → Daemon log**, `coffer log daemon`, `coffer path logs` |

All three stay on the machine that wrote them. [Vault sync](/guides/vault-sync) never publishes them, and Coffer sends them nowhere.

## The Activity page

Open **Activity** in the sidebar. The header carries a **Live** mark (a dot and the word; **Reconnecting…** while the daemon's change feed is closed, which means new records are not streaming in) and an **Export** menu. Four tabs follow, without counts: **Everything**, the default, **Changes**, **Tool calls** and **Daemon log**. A tab whose log could not be read shows a warning icon.

- **Everything** — changes, tool calls and the daemon's warnings and errors merged into one stream, newest first. Columns: **Time**, **Event**, **By** and **Took**.
- **Changes** — the audit log: **Time**, **Event** (the change as a sentence, such as "Stored a secret") and **By** (who made it).
- **Tool calls** — one row per tool call, resource read or prompt fetch the gateway routed: **Time**, **Agent** (whose session made it), **Server · tool**, **Took** and **Status**.
- **Daemon log** — the tail of `daemon.log`: **Time**, **Level**, **Logger** and **Message**. Open it when Coffer itself misbehaves rather than something it proxied. The line above the rows names the file, says "newest first" and "following" while the feed is open, and **Open in Finder** reveals the file.

Rows are grouped under a heading for their day ("Today · Sep 29"), and there is no summary line above them. The active tab is part of the URL (`/activity?tab=mcp`, `/activity?tab=daemon`; Everything is `/activity`).

**Filters.** Every tab filters in one row: the search first (press `/` to jump to it), then the time range and the pills, with **Clear filters** at the far right while anything is set. None of it shows result counts. The search matches a record's text, and on a call a server's name, so there is no separate server filter. The tabs add what their records carry:

- Everything: **By** and **Kind**.
- Changes: **By** and **Kind**.
- Tool calls: a segmented **All / OK / Failed** first (Failed is an error, a timeout or a denial), then **By**.
- Daemon log: a segmented **All / Info / Warnings / Errors** level first, then **Logger**.

The time range offers **Last hour**, **Last 24 h**, **Last 7 days**, **Last 30 days** or a custom range picked on a calendar (optional times, an end of "now", at most 90 days back). A tab opens on the last hour, the Daemon log on the last 24 hours, until you pick a range.

**By** takes several values at once, and a record is shown when it matches any of them. It lists your agents, then, under "Not an agent", you (the web UI or the Coffer app), the command line, Coffer itself and sync; on Tool calls it lists agents only. **Kind** on Everything is three values: **Tool calls**, **Changes** and **Daemon records**. On Changes it lists the eleven kinds of change: a kind of resource, or secrets, sync, settings and CLIs for a change that names no resource. The filters, the search and the range are all kept in the address (`q`, `range`, `by`, `kind`, `status`, `level`, `logger`), so a link such as `/activity?tab=mcp&q=github` opens already searching, and **View in Activity** on another page uses it. Moving to another tab keeps the search, the range and **By**, and drops the filters only the old tab had.

**Details.** Select a row on Everything, Changes or Tool calls to open it in a drawer 640 pixels wide beside the page; **Esc**, a click outside or the ✕ closes it, and **↑** and **↓** step to the previous or next record. A failed call leads with its error and how its server has been doing (since when it has been failing and how many errors it had in the last 24 hours); a change says who made it and what it touched, then shows the configuration before and after as a diff (secret values are never recorded). Below come the facts, the records written within five minutes of it, and the raw record, folded until you ask for it. A call shows its metadata only: its arguments and results are never stored. The footer holds the next step: **Open** the resource, beside **Copy details**.

On the **Daemon log** a row opens in place instead, under its own line, with its traceback, **Copy record** and, when the record names a server and a tool, **Show the tool call**, which switches to Tool calls searching for that call.

**Handing a failure to an agent.** Only a failure that depends on this machine offers **Hand off to &lt;Agent&gt; ▾**: a call whose server never answered, in its drawer, and an opened daemon error about an external service or the environment. A denied call, an error the server itself returned and a Coffer-internal error offer no hand-off; such a daemon error offers **Copy record** alone.

**New records arrive on their own.** While you are at the top of the list with nothing open, new records appear at the top as they are written. Once you scroll down or open a record the list holds still, and an **↑ N new** button counts what is waiting; choose it, or scroll back to the top, to bring them in. There is no pause or refresh button. A tab whose log fails to load shows one warning banner with the error and **Retry** for that log only; the other records keep working, and on Everything the banner says which records below are complete.

**Older records.** Each tab loads records a page at a time. The last row of the box says "Showing 30 of 1,204" and offers **Load 50 more**; once everything kept is shown it says so, with how long tool calls and changes are kept and a link to **Settings › Data**.

**First run.** With nothing recorded at all there is nothing to filter, so the page hides the filter row and **Export** and says "Changes you make in Coffer and the tools agents call through it show up here." with **Connect an agent** and **Add an MCP server**. An empty time range while older records exist is not the first run: the filters stay.

**Export.** The header's **Export ⌄** menu has **JSON** and **CSV**. Either writes every record of the visible tab that matches its current filters, not just the ones loaded, up to 10,000 records, to a file you save. A record's hand-off prompt is not part of it.

## What an audit entry records

Each entry holds:

| Field | Meaning |
| --- | --- |
| `timestamp` | When it happened, in UTC. |
| `event_type` | What happened, for example `resource_created`, `resource_scope_updated`, `secret_revealed`, `skill_bound`, `provider_switched`, `sync_run`, `token_rotated`. |
| `resource_kind`, `resource_name` | The resource it happened to, as it was named at that moment. |
| `resource_uid` | The resource's uid, so its history survives a rename. |
| `actor` | Who did it (below). |
| `details` | A structured payload, redacted per kind before it is stored. A `secret_set` records that a secret was written, never the secret. |

The **actor** is one of:

| Actor | Shown as | Source |
| --- | --- | --- |
| `ui` | You (web UI) | The web UI sends `X-Coffer-Actor: ui`. |
| `desktop` | You (Coffer app) | An action the desktop app confirmed. |
| `cli` | CLI | The CLI sends `X-Coffer-Actor: cli`. |
| `api` | API | A REST caller that sent no `X-Coffer-Actor` header. |
| `system` | Coffer | The daemon acting on its own, such as a background pass. |
| `sync` | Sync | A sync round applying what another machine changed. |
| `channel` | Channel | An action taken from a chat channel. |
| `human` | human | A change to a vault file that no Coffer operation made — your editor, a shell, an agent's own file tools, a `git commit` of your own. It is audited as `vault_file_edited`, one entry per file, once the vault has committed it (see [Editing the vault by hand](/guides/vault-files)). |
| an agent's name | the name | An agent's own action, such as its memory hook delivering a note (`memory_delivery_fired`, whose details name the moment, the session and the notes). |

Not every event is audited. The log keeps changes that land outside Coffer (a file written into an agent's configuration), that are irreversible or security-sensitive (a deletion, a secret revealed in the desktop app or resolved by `coffer run`, an approval, a master-key backup), or that current state cannot reveal later (a retention window). Every change to the vault is also a commit that names its writer, so the vault's git history (`git log -- <path>` in the vault folder) answers who changed a file even for what the audit log leaves out. Routine runtime events are log lines, not audit rows. Every audited event is also written to the daemon log under the same event name, so you can search either one for it.

## Query the audit log from the CLI

```sh
coffer log audit                                   # newest 50
coffer log audit --kind mcp_server --name filesystem
coffer log audit --event-type secret_resolved --since 2026-09-01T00:00:00Z
coffer log audit --event-type memory_delivery_fired --limit 20
coffer log audit --trace 44e10b60da1b4f26         # one request's or turn's rows
coffer log audit --json
```

| Option | Meaning |
| --- | --- |
| `--kind` | Resource kind, such as `mcp_server`, `agent`, `skill`. |
| `--name` | Resource name. Needs `--kind`. |
| `--event-type` | One event type. |
| `--since` | ISO 8601 lower bound, or an age such as `30m`, `1h`, `2d`. |
| `--trace` | Only the rows of one request or turn: its trace id, the one the drawer, an `X-Coffer-Trace` header or a daemon log line shows. `coffer log mcp` and `coffer log daemon` take it too. |
| `--limit` | 1–500, default 50. |
| `--json` | Machine-readable output. |

Over REST the same query is `GET /api/v1/audit`, which also accepts `event_prefix` to select a family of events such as `sync_` or `skill_`.

## Query MCP invocations from the CLI

```sh
coffer log mcp                              # every server, newest 20
coffer log mcp --server filesystem          # one server
coffer log mcp --status error --since 1d --json
```

Without `--server` the output includes Coffer's own built-in tool calls (server `coffer`) and rows of servers since deleted (shown by their uid). `--limit` accepts 1–500. A [custom tool](/guides/custom-tools#environments)'s call also names the environment it was made in: the Activity page shows it beside the tool (`@live`) and in the drawer, and `--json` carries it as `environment`. No header, variable or credential is recorded.

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
curl -si -H "X-Coffer-Token: $TOKEN" http://127.0.0.1:38470/api/v1/resources/nope \
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
| `sync_runs` | 90 days | Deletes older sync-round history. |

Set each window in **Settings → Data → History**.

A number of days must be at least 1. The web UI's **History** block shows the two a person usually tunes — **Changes** (`audit_log`) and **Tool calls** (`mcp_invocations`); the other policies keep the defaults above. Shortening a window asks for confirmation first, because the next prune deletes the older rows, and the confirmation counts them; **Clear expired data now** applies every policy immediately. A policy change is itself audited as `retention_updated`.

The daemon log is a file, not a table, so it has no policy: `daemon.log` rotates at 10 MB and keeps three rotations. Per-process shim logs and rolled-aside upstream logs in `~/.coffer/logs/` are deleted after seven days.

## How it works

Why the audit list is short, how the log reader normalises every writer's format, and how trace ids reach log lines are covered in [Observability](/architecture/observability).

## Related

- [Troubleshooting](/guides/troubleshooting)
- [Running the daemon](/guides/daemon#logs)
- [MCP servers](/guides/mcp-servers)
- [MCP tools reference](/reference/mcp-tools)
- Specs: [resource-framework](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/resource-framework/spec.md), [daemon](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/daemon/spec.md)
