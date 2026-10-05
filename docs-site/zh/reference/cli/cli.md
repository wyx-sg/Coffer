---
title: coffer cli
description: "Command-line tools Coffer manages for skills."
pageClass: cli-ref
---

# coffer cli

Command-line tools Coffer manages for skills.

```sh
coffer cli [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer cli --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`cli list`](#cli-list) | List every command-line tool Coffer manages, problems first. |
| [`cli show`](#cli-show) | One tool: where it is found, its version, its login state, who needs it. |
| [`cli add`](#cli-add) | Add a tool by hand. |
| [`cli preview`](#cli-preview) | What Coffer finds for a command before it is added. |
| [`cli update`](#cli-update) | Change a tool. |
| [`cli remove`](#cli-remove) | Remove a tool added by hand. |
| [`cli check`](#cli-check) | Look for one tool again. |
| [`cli check-all`](#cli-check-all) | Look for every tool again. |

## cli list

List every command-line tool Coffer manages, problems first.

The tools Coffer runs itself (git), the tools skills require, the launchers MCP servers start with, and the tools the developer added by hand: what each is for, who needs it, and whether it is ready, missing, outdated or logged out on this machine as of Coffer's last check. --json carries the full rows, including the prompt for an agent to install, update or log in to one that needs it.

<p class="cli-label">概要</p>

```sh
coffer cli list [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## cli show

One tool: where it is found, its version, its login state, who needs it.

<p class="cli-label">概要</p>

```sh
coffer cli show [OPTIONS] COMMAND
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `COMMAND` <span class="cli-chip">参数</span> | text | 必填 | command |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## cli add

Add a tool by hand. Body: command, title, description, min_version, login_check.

<p class="cli-label">概要</p>

```sh
coffer cli add [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## cli preview

What Coffer finds for a command before it is added. Body: command.

<p class="cli-label">概要</p>

```sh
coffer cli preview [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## cli update

Change a tool. Body: title, description, min_version, login_check.

<p class="cli-label">概要</p>

```sh
coffer cli update [OPTIONS] COMMAND
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `COMMAND` <span class="cli-chip">参数</span> | text | 必填 | command |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## cli remove

Remove a tool added by hand.

<p class="cli-label">概要</p>

```sh
coffer cli remove [OPTIONS] COMMAND
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `COMMAND` <span class="cli-chip">参数</span> | text | 必填 | command |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## cli check

Look for one tool again.

<p class="cli-label">概要</p>

```sh
coffer cli check [OPTIONS] COMMAND
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `COMMAND` <span class="cli-chip">参数</span> | text | 必填 | command |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## cli check-all

Look for every tool again.

<p class="cli-label">概要</p>

```sh
coffer cli check-all [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
