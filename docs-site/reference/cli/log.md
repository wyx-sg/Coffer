---
title: coffer log
description: "Read Coffer's records: the audit log, MCP calls and the daemon log"
---

# coffer log

Part of the [CLI reference](/reference/cli), generated from the CLI's own command tree; regenerate it with `make docs-reference`, never by hand.

```sh
coffer log [OPTIONS] COMMAND [ARGS]...
```

Read Coffer's records: the audit log, MCP calls and the daemon log

## log audit

```sh
coffer log audit [OPTIONS]
```

Read the audit log, newest first, one page at a time.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--kind` | option | text |  | Only this resource kind |
| `--name` | option | text |  | Only this resource (needs --kind) |
| `--event-type` | option | text |  | Only this event type |
| `--since` | option | text |  | ISO 8601 instant, or an age such as 30m, 1h, 2d |
| `--limit` | option | integer (1-500) | `50` | Most entries to print |
| `--cursor` | option | text |  | Read the page after this one: the next_cursor a previous read printed |
| `--json` | option | flag |  | JSON output for scripts |

## log mcp

```sh
coffer log mcp [OPTIONS]
```

Read the MCP invocation log, newest first.

Without --server this is the log the Activity page shows, Coffer's own calls (server ``coffer``) and deleted servers' rows (``deleted:<name>``) included.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--server` | option | text |  | One server; omit for every server |
| `--status` | option | text |  | ok \| error |
| `--since` | option | text |  | ISO 8601 instant, or an age such as 30m, 1h, 2d |
| `--limit` | option | integer (1-500) | `20` | Most calls to print |
| `--cursor` | option | text |  | Read the page after this one: the next_cursor a previous read printed |
| `--json` | option | flag |  | JSON output for scripts |

## log daemon

```sh
coffer log daemon [OPTIONS]
```

Read the tail of the daemon log, newest first, normalised as the Activity page shows it.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--since` | option | text |  | ISO 8601 instant, or an age such as 30m, 1h, 2d |
| `--errors` | option | flag |  | Only errors |
| `--limit` | option | integer (1-500) | `100` | Most records to print |
| `--json` | option | flag |  | JSON output for scripts |

## log prune

```sh
coffer log prune [OPTIONS]
```

Prune every registered log table now (or only --table), by its retention period.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--table` | option | text |  | Prune only this table |
