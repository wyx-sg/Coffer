---
title: coffer memory
description: "Memory, one Markdown file per topic in the vault: projects, topics, tidy."
pageClass: cli-ref
---

# coffer memory

Memory, one Markdown file per topic in the vault: projects, topics, tidy.

```sh
coffer memory [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer memory --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`memory state`](#memory-state) | The projects that hold memories, whether a tidy is open, and the Tidy prompt. |
| [`memory topics`](#memory-topics) | A project's memory files, with what breaks the format in each. |
| [`memory show`](#memory-show) | One memory file's text. |
| [`memory tidy-start`](#memory-tidy-start) | Open a tidy: until it finishes, the edits under memory/ are kept for one commit. |
| [`memory tidy-finish`](#memory-tidy-finish) | Close the tidy and commit its edits as one commit. |
| [`memory session-start`](#memory-session-start) | Print the memories a session started here is handed (the agents' hook runs it). |

## memory state

The projects that hold memories, whether a tidy is open, and the Tidy prompt.

<p class="cli-label">概要</p>

```sh
coffer memory state [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## memory topics

A project's memory files, with what breaks the format in each.

<p class="cli-label">概要</p>

```sh
coffer memory topics [OPTIONS] PROJECT
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `PROJECT` <span class="cli-chip">参数</span> | text | 必填 | The project's folder (from coffer memory state) |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## memory show

One memory file's text.

<p class="cli-label">概要</p>

```sh
coffer memory show [OPTIONS] PROJECT NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `PROJECT` <span class="cli-chip">参数</span> | text | 必填 | The project's folder |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | The file's name (from coffer memory topics) |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## memory tidy-start

Open a tidy: until it finishes, the edits under memory/ are kept for one commit.

<p class="cli-label">概要</p>

```sh
coffer memory tidy-start [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## memory tidy-finish

Close the tidy and commit its edits as one commit. Body: summary (the agent's report).

<p class="cli-label">概要</p>

```sh
coffer memory tidy-finish [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## memory session-start

Print the memories a session started here is handed (the agents' hook runs it).

Reads the hook's JSON from standard input for the session's working directory, falling back to the current directory. Prints nothing outside a repository, and nothing in a session Coffer started itself, whose system prompt already carries them. Never fails a session: any error prints nothing and exits 0. Needs no running daemon.

<p class="cli-label">概要</p>

```sh
coffer memory session-start [OPTIONS]
```
