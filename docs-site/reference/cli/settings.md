---
title: coffer settings
description: "Settings: approvals, secret storage, features, data, upkeep."
pageClass: cli-ref
---

# coffer settings

Settings: approvals, secret storage, features, data, upkeep.

```sh
coffer settings [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer settings --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`settings features`](#settings-features) | The experimental features and whether each is on. |
| [`settings approvals`](#settings-approvals) | Whether a secret going somewhere new waits for approval. |
| [`settings approvals show`](#settings-approvals-show) | Whether a new secret destination waits for approval. |
| [`settings approvals set`](#settings-approvals-set) | Switch approvals. |
| [`settings secrets`](#settings-secrets) | Where the master key is kept. |
| [`settings secrets show`](#settings-secrets-show) | Where the master key is kept. |
| [`settings secrets set`](#settings-secrets-set) | Move the master key. |
| [`settings feature`](#settings-feature) | Switch one experimental feature on this machine. |
| [`settings feature set`](#settings-feature-set) | Switch a feature. |
| [`settings feature reset`](#settings-feature-reset) | Forget this machine's choice. |
| [`settings engine`](#settings-engine) | Coffer's own model: transcription and upkeep passes. |
| [`settings engine show`](#settings-engine-show) | The engine's transcription model and upkeep passes. |
| [`settings engine transcribe-model`](#settings-engine-transcribe-model) | Choose the transcription model. |
| [`settings engine upkeep`](#settings-engine-upkeep) | Switch or schedule an upkeep pass. |
| [`settings retention`](#settings-retention) | How long each log is kept. |
| [`settings retention list`](#settings-retention-list) | How long each log is kept. |
| [`settings retention set`](#settings-retention-set) | Set how long a log is kept. |
| [`settings retention preview`](#settings-retention-preview) | What a shorter period would delete. |
| [`settings retention prune`](#settings-retention-prune) | Prune every log to its period now. |
| [`settings call-content`](#settings-call-content) | Whether tool calls record their arguments and results. |
| [`settings call-content show`](#settings-call-content-show) | Whether tool calls record their arguments and results. |
| [`settings call-content set`](#settings-call-content-set) | Switch recording a call's content. |
| [`settings storage`](#settings-storage) | What Coffer stores, and clearing its caches. |
| [`settings storage show`](#settings-storage-show) | What Coffer stores and how much. |

## settings features

The experimental features and whether each is on.

<p class="cli-label">Synopsis</p>

```sh
coffer settings features [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## settings approvals

Whether a secret going somewhere new waits for approval.

<p class="cli-label">Synopsis</p>

```sh
coffer settings approvals [OPTIONS] COMMAND [ARGS]...
```

Subcommands: `show`, `set`.

## settings approvals show

Whether a new secret destination waits for approval.

<p class="cli-label">Synopsis</p>

```sh
coffer settings approvals show [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## settings approvals set

Switch approvals. Body: require_approval. Off waits for an approval itself.

<p class="cli-label">Synopsis</p>

```sh
coffer settings approvals set [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## settings secrets

Where the master key is kept.

<p class="cli-label">Synopsis</p>

```sh
coffer settings secrets [OPTIONS] COMMAND [ARGS]...
```

Subcommands: `show`, `set`.

## settings secrets show

Where the master key is kept.

<p class="cli-label">Synopsis</p>

```sh
coffer settings secrets show [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## settings secrets set

Move the master key. Body: master_key_storage.

<p class="cli-label">Synopsis</p>

```sh
coffer settings secrets set [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## settings feature

Switch one experimental feature on this machine.

<p class="cli-label">Synopsis</p>

```sh
coffer settings feature [OPTIONS] COMMAND [ARGS]...
```

Subcommands: `set`, `reset`.

## settings feature set

Switch a feature. Body: enabled.

<p class="cli-label">Synopsis</p>

```sh
coffer settings feature set [OPTIONS] KEY
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `KEY` <span class="cli-chip">argument</span> | text | required | key |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## settings feature reset

Forget this machine's choice.

<p class="cli-label">Synopsis</p>

```sh
coffer settings feature reset [OPTIONS] KEY
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `KEY` <span class="cli-chip">argument</span> | text | required | key |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## settings engine

Coffer's own model: transcription and upkeep passes.

<p class="cli-label">Synopsis</p>

```sh
coffer settings engine [OPTIONS] COMMAND [ARGS]...
```

Subcommands: `show`, `transcribe-model`, `upkeep`.

## settings engine show

The engine's transcription model and upkeep passes.

<p class="cli-label">Synopsis</p>

```sh
coffer settings engine show [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## settings engine transcribe-model

Choose the transcription model. Body: model.

<p class="cli-label">Synopsis</p>

```sh
coffer settings engine transcribe-model [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## settings engine upkeep

Switch or schedule an upkeep pass. Body: pass, enabled, interval_s, use_default_interval.

<p class="cli-label">Synopsis</p>

```sh
coffer settings engine upkeep [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## settings retention

How long each log is kept.

<p class="cli-label">Synopsis</p>

```sh
coffer settings retention [OPTIONS] COMMAND [ARGS]...
```

Subcommands: `list`, `set`, `preview`, `prune`.

## settings retention list

How long each log is kept.

<p class="cli-label">Synopsis</p>

```sh
coffer settings retention list [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## settings retention set

Set how long a log is kept. Body: retention_days.

<p class="cli-label">Synopsis</p>

```sh
coffer settings retention set [OPTIONS] TABLE_NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `TABLE_NAME` <span class="cli-chip">argument</span> | text | required | table name |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## settings retention preview

What a shorter period would delete.

<p class="cli-label">Synopsis</p>

```sh
coffer settings retention preview [OPTIONS] TABLE_NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `TABLE_NAME` <span class="cli-chip">argument</span> | text | required | table name |
| `--days` <span class="cli-chip">option</span> | integer |  |  |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## settings retention prune

Prune every log to its period now.

<p class="cli-label">Synopsis</p>

```sh
coffer settings retention prune [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## settings call-content

Whether tool calls record their arguments and results.

<p class="cli-label">Synopsis</p>

```sh
coffer settings call-content [OPTIONS] COMMAND [ARGS]...
```

Subcommands: `show`, `set`.

## settings call-content show

Whether tool calls record their arguments and results.

<p class="cli-label">Synopsis</p>

```sh
coffer settings call-content show [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## settings call-content set

Switch recording a call's content. Body: enabled.

<p class="cli-label">Synopsis</p>

```sh
coffer settings call-content set [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## settings storage

What Coffer stores, and clearing its caches.

<p class="cli-label">Synopsis</p>

```sh
coffer settings storage [OPTIONS] COMMAND [ARGS]...
```

Subcommands: `show`.

## settings storage show

What Coffer stores and how much.

<p class="cli-label">Synopsis</p>

```sh
coffer settings storage show [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
