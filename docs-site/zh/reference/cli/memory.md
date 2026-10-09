---
title: coffer memory
description: "Memory partitions (notes are plain files you edit directly)."
pageClass: cli-ref
---

# coffer memory

Memory partitions (notes are plain files you edit directly).

```sh
coffer memory [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer memory --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`memory list`](#memory-list) | Every partition. |
| [`memory show`](#memory-show) | One partition: its config, reach and state. |
| [`memory update`](#memory-update) | Change a partition. |
| [`memory delete`](#memory-delete) | Delete a partition. |
| [`memory partitions`](#memory-partitions) | Every memory partition. |
| [`memory notes`](#memory-notes) | A partition's notes and their paths (read them with your own tools). |
| [`memory files`](#memory-files) | A partition's files. |
| [`memory delivered`](#memory-delivered) | What the partition delivers to agents. |
| [`memory retired`](#memory-retired) | Notes retired from delivery. |
| [`memory reading`](#memory-reading) | Which agents' memory Coffer reads, and where. |
| [`memory sync`](#memory-sync) | Read the agents' memory again now. |
| [`memory tidy-handoff`](#memory-tidy-handoff) | The prompt that hands tidying memory to an agent. |

## memory list

Every partition.

<p class="cli-label">概要</p>

```sh
coffer memory list [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## memory show

One partition: its config, reach and state.

<p class="cli-label">概要</p>

```sh
coffer memory show [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The memory's name or uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## memory update

Change a partition. Body: name, description, config.

<p class="cli-label">概要</p>

```sh
coffer memory update [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The memory's name or uid |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## memory delete

Delete a partition.

<p class="cli-label">概要</p>

```sh
coffer memory delete [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The memory's name or uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## memory partitions

Every memory partition.

<p class="cli-label">概要</p>

```sh
coffer memory partitions [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## memory notes

A partition's notes and their paths (read them with your own tools).

<p class="cli-label">概要</p>

```sh
coffer memory notes [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The memory's name or uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## memory files

A partition's files.

<p class="cli-label">概要</p>

```sh
coffer memory files [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The memory's name or uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## memory delivered

What the partition delivers to agents.

<p class="cli-label">概要</p>

```sh
coffer memory delivered [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The memory's name or uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## memory retired

Notes retired from delivery.

<p class="cli-label">概要</p>

```sh
coffer memory retired [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The memory's name or uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## memory reading

Which agents' memory Coffer reads, and where.

<p class="cli-label">概要</p>

```sh
coffer memory reading [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## memory sync

Read the agents' memory again now.

<p class="cli-label">概要</p>

```sh
coffer memory sync [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## memory tidy-handoff

The prompt that hands tidying memory to an agent.

<p class="cli-label">概要</p>

```sh
coffer memory tidy-handoff [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
