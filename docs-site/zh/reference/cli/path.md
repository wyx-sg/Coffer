---
title: coffer path
description: "Print where Coffer's files live (knowledge, memory, skills, agents, logs, vault)"
pageClass: cli-ref
---

# coffer path

Print where Coffer's files live (knowledge, memory, skills, agents, logs, vault)

```sh
coffer path [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer path --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON object keyed by what each path is |

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`path knowledge`](#path-knowledge) | The knowledge root, or one collection's directory of Markdown documents. |
| [`path memory`](#path-memory) | The memory root, or one partition's directory (MEMORY.md, notes/, RETIRED.md). |
| [`path skill`](#path-skill) | A skill's master folder, which a person edits in place. |
| [`path agent`](#path-agent) | An agent's own files: its config files, native memory stores, or transcript folders. |
| [`path logs`](#path-logs) | The log directory and the daemon.log in it (COFFER_LOG_DIR moves both). |
| [`path vault`](#path-vault) | The vault repository: configuration, knowledge and skill masters, in git. |

## path knowledge

The knowledge root, or one collection's directory of Markdown documents.

<p class="cli-label">概要</p>

```sh
coffer path knowledge [OPTIONS] [COLLECTION]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `COLLECTION` <span class="cli-chip">参数</span> | text |  | A collection; omit for the knowledge root |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON object keyed by what each path is |

## path memory

The memory root, or one partition's directory (MEMORY.md, notes/, RETIRED.md).

<p class="cli-label">概要</p>

```sh
coffer path memory [OPTIONS] [PARTITION]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `PARTITION` <span class="cli-chip">参数</span> | text |  | A partition; omit for the memory root |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON object keyed by what each path is |

## path skill

A skill's master folder, which a person edits in place.

<p class="cli-label">概要</p>

```sh
coffer path skill [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Skill name |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON object keyed by what each path is |

## path agent

An agent's own files: its config files, native memory stores, or transcript folders.

<p class="cli-label">概要</p>

```sh
coffer path agent [OPTIONS] NAME config|memory|transcripts
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Agent name |
| `CONFIG|MEMORY|TRANSCRIPTS` <span class="cli-chip">参数</span> | text | 必填 |  |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON object keyed by what each path is |

## path logs

The log directory and the daemon.log in it (COFFER_LOG_DIR moves both).

<p class="cli-label">概要</p>

```sh
coffer path logs [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON object keyed by what each path is |

## path vault

The vault repository: configuration, knowledge and skill masters, in git.

<p class="cli-label">概要</p>

```sh
coffer path vault [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON object keyed by what each path is |
