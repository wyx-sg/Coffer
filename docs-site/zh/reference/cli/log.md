---
title: coffer log
description: "Read Coffer's records: the audit log, MCP calls and the daemon log"
---

# coffer log

属于 [CLI 参考](/zh/reference/cli)，由 CLI 自己的命令树生成；用 `make docs-reference` 重新生成，不要手工编辑。

```sh
coffer log [OPTIONS] COMMAND [ARGS]...
```

Read Coffer's records: the audit log, MCP calls and the daemon log

## log audit

```sh
coffer log audit [OPTIONS]
```

Read the audit log, newest first, one page at a time.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--kind` | 选项 | text |  | Only this resource kind |
| `--name` | 选项 | text |  | Only this resource (needs --kind) |
| `--event-type` | 选项 | text |  | Only this event type |
| `--since` | 选项 | text |  | ISO 8601 instant, or an age such as 30m, 1h, 2d |
| `--limit` | 选项 | integer (1-500) | `50` | Most entries to print |
| `--cursor` | 选项 | text |  | Read the page after this one: the next_cursor a previous read printed |
| `--trace` | 选项 | text |  | Only records of one request or turn: the trace id an audit row, an MCP call, a log line or an X-Coffer-Trace header carries |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## log mcp

```sh
coffer log mcp [OPTIONS]
```

Read the MCP invocation log, newest first.

Without --server this is the log the Activity page shows, Coffer's own calls (server ``coffer``) and the rows of servers since deleted included.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--server` | 选项 | text |  | One server; omit for every server |
| `--status` | 选项 | text |  | ok \| error |
| `--since` | 选项 | text |  | ISO 8601 instant, or an age such as 30m, 1h, 2d |
| `--limit` | 选项 | integer (1-500) | `20` | Most calls to print |
| `--cursor` | 选项 | text |  | Read the page after this one: the next_cursor a previous read printed |
| `--trace` | 选项 | text |  | Only records of one request or turn: the trace id an audit row, an MCP call, a log line or an X-Coffer-Trace header carries |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## log daemon

```sh
coffer log daemon [OPTIONS]
```

Read the tail of the daemon log, newest first, normalised as the Activity page shows it.

``--trace`` keeps the lines of one request or turn, the same id ``coffer log audit --trace`` and ``coffer log mcp --trace`` filter on.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--since` | 选项 | text |  | ISO 8601 instant, or an age such as 30m, 1h, 2d |
| `--errors` | 选项 | 开关 |  | Only errors |
| `--limit` | 选项 | integer (1-500) | `100` | Most records to print |
| `--trace` | 选项 | text |  | Only records of one request or turn: the trace id an audit row, an MCP call, a log line or an X-Coffer-Trace header carries |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## log prune

```sh
coffer log prune [OPTIONS]
```

Prune every registered log table now (or only --table), by its retention period.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--table` | 选项 | text |  | Prune only this table |
