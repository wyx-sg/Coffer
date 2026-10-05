---
title: coffer vault
description: "The vault's history and the hand edits it refused."
pageClass: cli-ref
---

# coffer vault

The vault's history and the hand edits it refused.

```sh
coffer vault [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer vault --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`vault problems`](#vault-problems) | List hand edits that were refused: still on disk, not in effect until fixed. |
| [`vault history`](#vault-history) | A vault path's versions, newest first, each with its writer. |
| [`vault diff`](#vault-diff) | One version's diff. |
| [`vault restore`](#vault-restore) | Write a version back as a new commit. |

## vault problems

List hand edits that were refused: still on disk, not in effect until fixed.

<p class="cli-label">Synopsis</p>

```sh
coffer vault problems [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |

## vault history

A vault path's versions, newest first, each with its writer.

<p class="cli-label">Synopsis</p>

```sh
coffer vault history [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--path` <span class="cli-chip">option</span> | text |  | A path under the vault |
| `--limit` <span class="cli-chip">option</span> | integer |  |  |
| `--cursor` <span class="cli-chip">option</span> | text |  |  |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## vault diff

One version's diff.

<p class="cli-label">Synopsis</p>

```sh
coffer vault diff [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--path` <span class="cli-chip">option</span> | text |  |  |
| `--version` <span class="cli-chip">option</span> | text |  |  |
| `--against` <span class="cli-chip">option</span> | text |  | previous or current |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## vault restore

Write a version back as a new commit. Body: path, version, expected_current.

<p class="cli-label">Synopsis</p>

```sh
coffer vault restore [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
