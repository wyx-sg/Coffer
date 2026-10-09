---
title: coffer log
description: "Read Coffer's audit, MCP and daemon logs."
pageClass: cli-ref
---

# coffer log

Read Coffer's audit, MCP and daemon logs.

```sh
coffer log [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer log --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`log audit`](#log-audit) | Read the audit log, newest first, one page at a time. |
| [`log mcp`](#log-mcp) | Read the MCP invocation log, newest first. |
| [`log call`](#log-call) | Read one tool call with its arguments and result, secrets masked. |
| [`log daemon`](#log-daemon) | Read the tail of the daemon log, newest first, normalised as the Activity page shows it. |

## log audit

Read the audit log, newest first, one page at a time.

<p class="cli-label">概要</p>

```sh
coffer log audit [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--kind` <span class="cli-chip">选项</span> | text |  | Only this resource kind |
| `--name` <span class="cli-chip">选项</span> | text |  | Only this resource (needs --kind) |
| `--event-type` <span class="cli-chip">选项</span> | text |  | Only this event type |
| `--since` <span class="cli-chip">选项</span> | text |  | ISO 8601 instant, or an age such as 30m, 1h, 2d |
| `--limit` <span class="cli-chip">选项</span> | integer (1-500) | `50` | Most entries to print |
| `--cursor` <span class="cli-chip">选项</span> | text |  | Read the page after this one: the next_cursor a previous read printed |
| `--trace` <span class="cli-chip">选项</span> | text |  | Only records of one request or turn: the trace id an audit row, an MCP call, a log line or an X-Coffer-Trace header carries |
| `--q` <span class="cli-chip">选项</span> | text |  | Only the records holding this text, in any case (the page's search box): event code, resource name, actor and details |
| `--q-type` <span class="cli-chip">选项</span> | text（可重复） |  | With --q: an event type that also matches, as the page adds the events whose translated wording holds the text (repeatable) |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## log mcp

Read the MCP invocation log, newest first.

Without --server this is the log the Activity page shows, Coffer's own calls (server ``coffer``) and the rows of servers since deleted included.

<p class="cli-label">概要</p>

```sh
coffer log mcp [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--server` <span class="cli-chip">选项</span> | text |  | One server; omit for every server |
| `--status` <span class="cli-chip">选项</span> | text |  | ok \| error \| timeout \| denied, or failed for every outcome but ok |
| `--since` <span class="cli-chip">选项</span> | text |  | ISO 8601 instant, or an age such as 30m, 1h, 2d |
| `--limit` <span class="cli-chip">选项</span> | integer (1-500) | `20` | Most calls to print |
| `--cursor` <span class="cli-chip">选项</span> | text |  | Read the page after this one: the next_cursor a previous read printed |
| `--trace` <span class="cli-chip">选项</span> | text |  | Only records of one request or turn: the trace id an audit row, an MCP call, a log line or an X-Coffer-Trace header carries |
| `--q` <span class="cli-chip">选项</span> | text |  | Only the records holding this text, in any case (the page's search box): tool, error, session, outcome and server name |
| `--agent-uid` <span class="cli-chip">选项</span> | text |  | Only the calls made by this agent's sessions (its uid) |
| `--uid` <span class="cli-chip">选项</span> | text |  | Only the calls written under this server uid — the reserved coffer, or a server since deleted, which --server cannot name |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## log call

Read one tool call with its arguments and result, secrets masked.

<p class="cli-label">概要</p>

```sh
coffer log call [OPTIONS] INVOCATION_ID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `INVOCATION_ID` <span class="cli-chip">参数</span> | integer | 必填 | The call's id, as `coffer log mcp` prints it |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## log daemon

Read the tail of the daemon log, newest first, normalised as the Activity page shows it.

``--trace`` keeps the lines of one request or turn, the same id ``coffer log audit --trace`` and ``coffer log mcp --trace`` filter on. This reads through the daemon, starting it if it is not running; to read the file with no daemon, open the one ``coffer path logs`` names.

<p class="cli-label">概要</p>

```sh
coffer log daemon [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--since` <span class="cli-chip">选项</span> | text |  | ISO 8601 instant, or an age such as 30m, 1h, 2d |
| `--errors` <span class="cli-chip">选项</span> | 开关 |  | Only errors |
| `--limit` <span class="cli-chip">选项</span> | integer (1-500) | `100` | Most records to print |
| `--trace` <span class="cli-chip">选项</span> | text |  | Only records of one request or turn: the trace id an audit row, an MCP call, a log line or an X-Coffer-Trace header carries |
| `--level` <span class="cli-chip">选项</span> | text |  | Only records at or above this severity: debug, info, warning, error, critical |
| `--q` <span class="cli-chip">选项</span> | text |  | Only the records holding this text, in any case (the page's search box): message, logger, level and folded lines |
| `--cursor` <span class="cli-chip">选项</span> | text |  | Read the page after this one: the next_cursor a previous read printed |
| `--with-total` <span class="cli-chip">选项</span> | 开关 |  | Also count the matching records in the log's recent tail |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |
