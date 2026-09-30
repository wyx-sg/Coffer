---
title: coffer path
description: "Print where Coffer's files live (knowledge, memory, skills, agents, logs, vault)"
---

# coffer path

属于 [CLI 参考](/zh/reference/cli)，由 CLI 自己的命令树生成；用 `make docs-reference` 重新生成，不要手工编辑。

```sh
coffer path [OPTIONS] COMMAND [ARGS]...
```

Print where Coffer's files live (knowledge, memory, skills, agents, logs, vault)

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON object keyed by what each path is |

## path knowledge

```sh
coffer path knowledge [OPTIONS] [COLLECTION]
```

The knowledge root, or one collection's directory of Markdown documents.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `COLLECTION` | 参数 | text |  | A collection; omit for the knowledge root |
| `--json` | 选项 | 开关 |  | JSON object keyed by what each path is |

## path memory

```sh
coffer path memory [OPTIONS] [PARTITION]
```

The memory root, or one partition's directory (MEMORY.md, notes/, RETIRED.md).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `PARTITION` | 参数 | text |  | A partition; omit for the memory root |
| `--json` | 选项 | 开关 |  | JSON object keyed by what each path is |

## path skill

```sh
coffer path skill [OPTIONS] NAME
```

A skill's master folder, which a person edits in place.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Skill name |
| `--json` | 选项 | 开关 |  | JSON object keyed by what each path is |

## path agent

```sh
coffer path agent [OPTIONS] NAME config|memory|transcripts
```

An agent's own files: its config files, native memory stores, or transcript folders.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Agent name |
| `CONFIG|MEMORY|TRANSCRIPTS` | 参数 | text | 必填 |  |
| `--json` | 选项 | 开关 |  | JSON object keyed by what each path is |

## path logs

```sh
coffer path logs [OPTIONS]
```

The log directory and the daemon.log in it (COFFER_LOG_DIR moves both).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON object keyed by what each path is |

## path vault

```sh
coffer path vault [OPTIONS]
```

The vault repository: configuration, knowledge and skill masters, in git.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON object keyed by what each path is |
