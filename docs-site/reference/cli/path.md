---
title: coffer path
description: "Print where Coffer's files live (knowledge, memory, skills, agents, logs, vault)"
---

# coffer path

Part of the [CLI reference](/reference/cli), generated from the CLI's own command tree; regenerate it with `make docs-reference`, never by hand.

```sh
coffer path [OPTIONS] COMMAND [ARGS]...
```

Print where Coffer's files live (knowledge, memory, skills, agents, logs, vault)

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--json` | option | flag |  | JSON object keyed by what each path is |

## path knowledge

```sh
coffer path knowledge [OPTIONS] [COLLECTION]
```

The knowledge root, or one collection's directory of Markdown documents.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `COLLECTION` | argument | text |  | A collection; omit for the knowledge root |
| `--json` | option | flag |  | JSON object keyed by what each path is |

## path memory

```sh
coffer path memory [OPTIONS] [PARTITION]
```

The memory root, or one partition's directory (MEMORY.md, notes/, RETIRED.md).

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `PARTITION` | argument | text |  | A partition; omit for the memory root |
| `--json` | option | flag |  | JSON object keyed by what each path is |

## path skill

```sh
coffer path skill [OPTIONS] NAME
```

A skill's master folder, which a person edits in place.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Skill name |
| `--json` | option | flag |  | JSON object keyed by what each path is |

## path agent

```sh
coffer path agent [OPTIONS] NAME config|memory|transcripts
```

An agent's own files: its config files, native memory stores, or transcript folders.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Agent name |
| `CONFIG|MEMORY|TRANSCRIPTS` | argument | text | required |  |
| `--json` | option | flag |  | JSON object keyed by what each path is |

## path logs

```sh
coffer path logs [OPTIONS]
```

The log directory and the daemon.log in it (COFFER_LOG_DIR moves both).

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--json` | option | flag |  | JSON object keyed by what each path is |

## path vault

```sh
coffer path vault [OPTIONS]
```

The vault repository: configuration, knowledge and skill masters, in git.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--json` | option | flag |  | JSON object keyed by what each path is |
