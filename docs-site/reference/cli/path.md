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

This page matches what `coffer path --help` prints. Add `--help` to any command below to see its options in the terminal.

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON object keyed by what each path is |

## Commands

| Command | What it does |
| --- | --- |
| [`path knowledge`](#path-knowledge) | The knowledge root, or one collection's directory of Markdown documents. |
| [`path memory`](#path-memory) | The memory root, or one partition's directory (MEMORY.md, notes/, RETIRED.md). |
| [`path skill`](#path-skill) | A skill's master folder, which a person edits in place. |
| [`path agent`](#path-agent) | An agent's own files: its config files, native memory stores, or transcript folders. |
| [`path logs`](#path-logs) | The log directory and the daemon.log in it (COFFER_LOG_DIR moves both). |
| [`path vault`](#path-vault) | The vault repository: configuration, knowledge and skill masters, in git. |

## path knowledge

The knowledge root, or one collection's directory of Markdown documents.

<p class="cli-label">Synopsis</p>

```sh
coffer path knowledge [OPTIONS] [COLLECTION]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `COLLECTION` <span class="cli-chip">argument</span> | text |  | A collection; omit for the knowledge root |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON object keyed by what each path is |

## path memory

The memory root, or one partition's directory (MEMORY.md, notes/, RETIRED.md).

<p class="cli-label">Synopsis</p>

```sh
coffer path memory [OPTIONS] [PARTITION]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `PARTITION` <span class="cli-chip">argument</span> | text |  | A partition; omit for the memory root |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON object keyed by what each path is |

## path skill

A skill's master folder, which a person edits in place.

<p class="cli-label">Synopsis</p>

```sh
coffer path skill [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Skill name |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON object keyed by what each path is |

## path agent

An agent's own files: its config files, native memory stores, or transcript folders.

<p class="cli-label">Synopsis</p>

```sh
coffer path agent [OPTIONS] NAME config|memory|transcripts
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Agent name |
| `CONFIG|MEMORY|TRANSCRIPTS` <span class="cli-chip">argument</span> | text | required |  |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON object keyed by what each path is |

## path logs

The log directory and the daemon.log in it (COFFER_LOG_DIR moves both).

<p class="cli-label">Synopsis</p>

```sh
coffer path logs [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON object keyed by what each path is |

## path vault

The vault repository: configuration, knowledge and skill masters, in git.

<p class="cli-label">Synopsis</p>

```sh
coffer path vault [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON object keyed by what each path is |
