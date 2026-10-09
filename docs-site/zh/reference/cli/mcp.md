---
title: coffer mcp
description: "MCP servers: register, change, test, their tools and logs."
pageClass: cli-ref
---

# coffer mcp

MCP servers: register, change, test, their tools and logs.

```sh
coffer mcp [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer mcp --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`mcp test`](#mcp-test) | Re-query a server's capabilities, then report whether it answers. |
| [`mcp list`](#mcp-list) | Every server. |
| [`mcp show`](#mcp-show) | One server: its config, reach and state. |
| [`mcp update`](#mcp-update) | Change a server. |
| [`mcp delete`](#mcp-delete) | Delete a server. |
| [`mcp enable`](#mcp-enable) | Switch a server on. |
| [`mcp disable`](#mcp-disable) | Switch a server off. |
| [`mcp reach`](#mcp-reach) | Set the agents a server reaches. |
| [`mcp add`](#mcp-add) | Register a server. |
| [`mcp test-config`](#mcp-test-config) | Test a config before adding it; nothing is saved. |
| [`mcp status`](#mcp-status) | Why a server is in its state, and what to do. |
| [`mcp tools`](#mcp-tools) | The server's tools, resources and prompts with their switches. |
| [`mcp tiering`](#mcp-tiering) | Which tools agents see listed and which they find by search. |
| [`mcp exposure`](#mcp-exposure) | Choose how one tool is exposed. |
| [`mcp exposure-all`](#mcp-exposure-all) | Choose how several tools are exposed. |
| [`mcp calls`](#mcp-calls) | One server's calls and errors since a moment, per agent and per tool. |
| [`mcp server-log`](#mcp-server-log) | The newest lines of the server's own log. |
| [`mcp builtin`](#mcp-builtin) | Coffer's own built-in tools. |
| [`mcp tool`](#mcp-tool) | Switch a server's tools, prompts and resources on or off. |
| [`mcp tool enable`](#mcp-tool-enable) | Switch one capability on. |
| [`mcp tool disable`](#mcp-tool-disable) | Switch one capability off. |
| [`mcp resource`](#mcp-resource) | Read one of a server's resources now. |
| [`mcp resource read`](#mcp-resource-read) | Read one resource now, as its row's details do. |
| [`mcp prompt`](#mcp-prompt) | Fill one of a server's prompts and show the messages it makes. |
| [`mcp prompt get`](#mcp-prompt-get) | Fill one prompt now, as its row's details do. |

## mcp test

Re-query a server's capabilities, then report whether it answers.

Exits 7 when the server does not answer. With ``--prompt``, a failure also prints the hand-off prompt the server's page offers for it: installing a launcher that is not found here, or finding why the server fails. ``--json`` prints the test's answer (``ok``, ``latency_ms``, ``error_message``, ``handoff``) with the refresh's counts under ``capabilities``; a failed test still exits 7.

<p class="cli-label">概要</p>

```sh
coffer mcp test [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Server name |
| `--prompt` <span class="cli-chip">选项</span> | 开关 |  | On a failure, also print the prompt to give your agent |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp list

Every server.

<p class="cli-label">概要</p>

```sh
coffer mcp list [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp show

One server: its config, reach and state.

<p class="cli-label">概要</p>

```sh
coffer mcp show [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The mcp_server's name or uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp update

Change a server. Body: name, description, config.

<p class="cli-label">概要</p>

```sh
coffer mcp update [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The mcp_server's name or uid |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp delete

Delete a server.

<p class="cli-label">概要</p>

```sh
coffer mcp delete [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The mcp_server's name or uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp enable

Switch a server on.

<p class="cli-label">概要</p>

```sh
coffer mcp enable [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The mcp_server's name or uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp disable

Switch a server off.

<p class="cli-label">概要</p>

```sh
coffer mcp disable [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The mcp_server's name or uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp reach

Set the agents a server reaches. Body: scope ({agents: [uid…]} or null).

<p class="cli-label">概要</p>

```sh
coffer mcp reach [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The mcp_server's name or uid |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp add

Register a server. Body: kind=mcp_server, name, description, config.transport (stdio: command, args, env, secret_refs, cwd; http: url, headers, secret_refs, auth_schemes).

<p class="cli-label">概要</p>

```sh
coffer mcp add [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp test-config

Test a config before adding it; nothing is saved. Body: transport, secret_values, spawn_timeout_seconds, request_timeout_seconds. Exits 7 when the answer says ok: false.

<p class="cli-label">概要</p>

```sh
coffer mcp test-config [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp status

Why a server is in its state, and what to do.

<p class="cli-label">概要</p>

```sh
coffer mcp status [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The mcp_server's name or uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp tools

The server's tools, resources and prompts with their switches.

<p class="cli-label">概要</p>

```sh
coffer mcp tools [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The mcp_server's name or uid |
| `--saved` <span class="cli-chip">选项</span> | 开关 |  | Read the saved list without connecting |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp tiering

Which tools agents see listed and which they find by search.

<p class="cli-label">概要</p>

```sh
coffer mcp tiering [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The mcp_server's name or uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp exposure

Choose how one tool is exposed. Body: {"mode": "listed"}; mode is auto, listed (in the tool list) or search (found with coffer__search_tools).

<p class="cli-label">概要</p>

```sh
coffer mcp exposure [OPTIONS] UID TOOL
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The mcp_server's name or uid |
| `TOOL` <span class="cli-chip">参数</span> | text | 必填 | tool |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp exposure-all

Choose how several tools are exposed. Body: {"tools": ["read_file"], "mode": "search"}; mode is auto, listed or search.

<p class="cli-label">概要</p>

```sh
coffer mcp exposure-all [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The mcp_server's name or uid |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp calls

One server's calls and errors since a moment, per agent and per tool.

<p class="cli-label">概要</p>

```sh
coffer mcp calls [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The mcp_server's name or uid |
| `--since` <span class="cli-chip">选项</span> | text |  | ISO time; 24 hours ago by default |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp server-log

The newest lines of the server's own log.

<p class="cli-label">概要</p>

```sh
coffer mcp server-log [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The mcp_server's name or uid |
| `--limit` <span class="cli-chip">选项</span> | integer |  |  |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp builtin

Coffer's own built-in tools.

<p class="cli-label">概要</p>

```sh
coffer mcp builtin [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp tool

Switch a server's tools, prompts and resources on or off.

<p class="cli-label">概要</p>

```sh
coffer mcp tool [OPTIONS] COMMAND [ARGS]...
```

子命令：`enable`, `disable`。

## mcp tool enable

Switch one capability on. Body: {"capability_key": "read_file"} (one key per call).

<p class="cli-label">概要</p>

```sh
coffer mcp tool enable [OPTIONS] UID CAPABILITY_TYPE
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The mcp_server's name or uid |
| `CAPABILITY_TYPE` <span class="cli-chip">参数</span> | text | 必填 | tool, prompt or resource |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp tool disable

Switch one capability off. Body: {"capability_key": "read_file"} (one key per call).

<p class="cli-label">概要</p>

```sh
coffer mcp tool disable [OPTIONS] UID CAPABILITY_TYPE
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The mcp_server's name or uid |
| `CAPABILITY_TYPE` <span class="cli-chip">参数</span> | text | 必填 | tool, prompt or resource |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp resource

Read one of a server's resources now.

<p class="cli-label">概要</p>

```sh
coffer mcp resource [OPTIONS] COMMAND [ARGS]...
```

子命令：`read`。

## mcp resource read

Read one resource now, as its row's details do. Body: uri.

<p class="cli-label">概要</p>

```sh
coffer mcp resource read [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The mcp_server's name or uid |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp prompt

Fill one of a server's prompts and show the messages it makes.

<p class="cli-label">概要</p>

```sh
coffer mcp prompt [OPTIONS] COMMAND [ARGS]...
```

子命令：`get`。

## mcp prompt get

Fill one prompt now, as its row's details do. Body: name, arguments.

<p class="cli-label">概要</p>

```sh
coffer mcp prompt get [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The mcp_server's name or uid |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
