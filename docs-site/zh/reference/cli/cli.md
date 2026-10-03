---
title: coffer cli
description: "Add and check command-line tools"
pageClass: cli-ref
---

# coffer cli

Add and check command-line tools

```sh
coffer cli [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer cli --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`cli list`](#cli-list) | List every command-line tool — added by hand or required — problems first. |
| [`cli add`](#cli-add) | Add a command-line tool by hand; no skill is needed. |
| [`cli edit`](#cli-edit) | Change a tool you added by hand (only the options you give change). |
| [`cli rm`](#cli-rm) | Remove a tool you added by hand. |
| [`cli show`](#cli-show) | Show one command-line tool: where it is, its version, login state and what needs it. |
| [`cli check`](#cli-check) | Probe the required commands again (or one of them). |
| [`cli prompt`](#cli-prompt) | Print the prompt to give your agent for a command that needs you. |

## cli list

List every command-line tool — added by hand or required — problems first.

<p class="cli-label">概要</p>

```sh
coffer cli list [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## cli add

Add a command-line tool by hand; no skill is needed.

<p class="cli-label">概要</p>

```sh
coffer cli add [OPTIONS] COMMAND
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `COMMAND` <span class="cli-chip">参数</span> | text | 必填 | A command name (jq) or the absolute path of an executable |
| `--title` <span class="cli-chip">选项</span> | text |  | A display name |
| `--description` <span class="cli-chip">选项</span> | text |  | What it is for |
| `--min-version` <span class="cli-chip">选项</span> | text |  | Oldest wanted, like "2.40" |
| `--login-check` <span class="cli-chip">选项</span> | text |  | A command line that exits 0 when logged in, like "gh auth status" |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## cli edit

Change a tool you added by hand (only the options you give change).

<p class="cli-label">概要</p>

```sh
coffer cli edit [OPTIONS] COMMAND
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `COMMAND` <span class="cli-chip">参数</span> | text | 必填 | A tool you added, e.g. jq |
| `--title` <span class="cli-chip">选项</span> | text |  | A display name; '' clears it |
| `--description` <span class="cli-chip">选项</span> | text |  | '' clears it |
| `--min-version` <span class="cli-chip">选项</span> | text |  | '' clears it |
| `--login-check` <span class="cli-chip">选项</span> | text |  | '' clears it |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## cli rm

Remove a tool you added by hand. A skill that requires it keeps it listed.

<p class="cli-label">概要</p>

```sh
coffer cli rm [OPTIONS] COMMAND
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `COMMAND` <span class="cli-chip">参数</span> | text | 必填 | A tool you added, e.g. jq |
| `--force, --yes, -f, -y` <span class="cli-chip">选项</span> | 开关 |  | Do not ask |

## cli show

Show one command-line tool: where it is, its version, login state and what needs it.

<p class="cli-label">概要</p>

```sh
coffer cli show [OPTIONS] COMMAND
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `COMMAND` <span class="cli-chip">参数</span> | text | 必填 | The command, e.g. gh |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## cli check

Probe the required commands again (or one of them).

<p class="cli-label">概要</p>

```sh
coffer cli check [OPTIONS] [COMMAND]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `[COMMAND]` <span class="cli-chip">参数</span> | text |  | One command only |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## cli prompt

Print the prompt to give your agent for a command that needs you.

<p class="cli-label">概要</p>

```sh
coffer cli prompt [OPTIONS] COMMAND
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `COMMAND` <span class="cli-chip">参数</span> | text | 必填 | The command, e.g. jq |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |
