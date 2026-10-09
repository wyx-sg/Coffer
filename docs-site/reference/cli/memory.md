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

This page matches what `coffer memory --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
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

<p class="cli-label">Synopsis</p>

```sh
coffer memory state [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## memory sync

Sync memory now.

<p class="cli-label">Synopsis</p>

```sh
coffer memory sync [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## memory preview-write

Write exactly what the pending preview lists.

<p class="cli-label">Synopsis</p>

```sh
coffer memory preview-write [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## memory preview-cancel

Drop the pending preview.

<p class="cli-label">Synopsis</p>

```sh
coffer memory preview-cancel [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## memory undo

Remove every unedited copy Coffer wrote on this machine and turn automatic sync off.

<p class="cli-label">Synopsis</p>

```sh
coffer memory undo [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## memory codex-import

Say whether Codex imports Claude Code's memories itself. Body: value (true, false, null).

<p class="cli-label">Synopsis</p>

```sh
coffer memory codex-import [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## memory entries

A project's memories with their origin and where each was written.

<p class="cli-label">Synopsis</p>

```sh
coffer memory entries [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--project` <span class="cli-chip">option</span> | text |  | The project key, or global |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## memory curate

Ask an agent to consolidate its own memory now. Body: agent_type.

<p class="cli-label">Synopsis</p>

```sh
coffer memory curate [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
