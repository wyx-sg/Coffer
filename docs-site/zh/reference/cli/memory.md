---
title: coffer memory
description: "Memory sync into each agent's own memory: state, sync now, preview, undo, curate."
pageClass: cli-ref
---

# coffer memory

Memory sync into each agent's own memory: state, sync now, preview, undo, curate.

```sh
coffer memory [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer memory --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`memory state`](#memory-state) | The sync, its pending preview, the hub's projects and each agent's state. |
| [`memory sync`](#memory-sync) | Sync memory now. |
| [`memory preview-write`](#memory-preview-write) | Write exactly what the pending preview lists. |
| [`memory preview-cancel`](#memory-preview-cancel) | Drop the pending preview. |
| [`memory undo`](#memory-undo) | Remove every unedited copy Coffer wrote on this machine and turn automatic sync off. |
| [`memory codex-import`](#memory-codex-import) | Say whether Codex imports Claude Code's memories itself. |
| [`memory entries`](#memory-entries) | A project's memories with their origin and where each was written. |
| [`memory curate`](#memory-curate) | Ask an agent to consolidate its own memory now. |

## memory state

The sync, its pending preview, the hub's projects and each agent's state.

<p class="cli-label">概要</p>

```sh
coffer memory state [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## memory sync

Sync memory now.

<p class="cli-label">概要</p>

```sh
coffer memory sync [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## memory preview-write

Write exactly what the pending preview lists.

<p class="cli-label">概要</p>

```sh
coffer memory preview-write [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## memory preview-cancel

Drop the pending preview.

<p class="cli-label">概要</p>

```sh
coffer memory preview-cancel [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## memory undo

Remove every unedited copy Coffer wrote on this machine and turn automatic sync off.

<p class="cli-label">概要</p>

```sh
coffer memory undo [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## memory codex-import

Say whether Codex imports Claude Code's memories itself. Body: value (true, false, null).

<p class="cli-label">概要</p>

```sh
coffer memory codex-import [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## memory entries

A project's memories with their origin and where each was written.

<p class="cli-label">概要</p>

```sh
coffer memory entries [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--project` <span class="cli-chip">选项</span> | text |  | The project key, or global |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## memory curate

Ask an agent to consolidate its own memory now. Body: agent_type.

<p class="cli-label">概要</p>

```sh
coffer memory curate [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
