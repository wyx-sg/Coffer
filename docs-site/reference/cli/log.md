---
title: coffer log
description: "Read Coffer's records: the audit log, MCP calls and the daemon log"
pageClass: cli-ref
---

# coffer log

Read Coffer's records: the audit log, MCP calls and the daemon log

```sh
coffer log [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer log --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`log audit`](#log-audit) | Read the audit log, newest first, one page at a time. |
| [`log mcp`](#log-mcp) | Read the MCP invocation log, newest first. |
| [`log daemon`](#log-daemon) | Read the tail of the daemon log, newest first, normalised as the Activity page shows it. |

## log audit

Read the audit log, newest first, one page at a time.

<p class="cli-label">Synopsis</p>

```sh
coffer log audit [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--kind` <span class="cli-chip">option</span> | text |  | Only this resource kind |
| `--name` <span class="cli-chip">option</span> | text |  | Only this resource (needs --kind) |
| `--event-type` <span class="cli-chip">option</span> | text |  | Only this event type |
| `--since` <span class="cli-chip">option</span> | text |  | ISO 8601 instant, or an age such as 30m, 1h, 2d |
| `--limit` <span class="cli-chip">option</span> | integer (1-500) | `50` | Most entries to print |
| `--cursor` <span class="cli-chip">option</span> | text |  | Read the page after this one: the next_cursor a previous read printed |
| `--trace` <span class="cli-chip">option</span> | text |  | Only records of one request or turn: the trace id an audit row, an MCP call, a log line or an X-Coffer-Trace header carries |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |

## log mcp

Read the MCP invocation log, newest first.

Without --server this is the log the Activity page shows, Coffer's own calls (server ``coffer``) and the rows of servers since deleted included.

<p class="cli-label">Synopsis</p>

```sh
coffer log mcp [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--server` <span class="cli-chip">option</span> | text |  | One server; omit for every server |
| `--status` <span class="cli-chip">option</span> | text |  | ok \| error |
| `--since` <span class="cli-chip">option</span> | text |  | ISO 8601 instant, or an age such as 30m, 1h, 2d |
| `--limit` <span class="cli-chip">option</span> | integer (1-500) | `20` | Most calls to print |
| `--cursor` <span class="cli-chip">option</span> | text |  | Read the page after this one: the next_cursor a previous read printed |
| `--trace` <span class="cli-chip">option</span> | text |  | Only records of one request or turn: the trace id an audit row, an MCP call, a log line or an X-Coffer-Trace header carries |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |

## log daemon

Read the tail of the daemon log, newest first, normalised as the Activity page shows it.

``--trace`` keeps the lines of one request or turn, the same id ``coffer log audit --trace`` and ``coffer log mcp --trace`` filter on.

<p class="cli-label">Synopsis</p>

```sh
coffer log daemon [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--since` <span class="cli-chip">option</span> | text |  | ISO 8601 instant, or an age such as 30m, 1h, 2d |
| `--errors` <span class="cli-chip">option</span> | flag |  | Only errors |
| `--limit` <span class="cli-chip">option</span> | integer (1-500) | `100` | Most records to print |
| `--trace` <span class="cli-chip">option</span> | text |  | Only records of one request or turn: the trace id an audit row, an MCP call, a log line or an X-Coffer-Trace header carries |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |
