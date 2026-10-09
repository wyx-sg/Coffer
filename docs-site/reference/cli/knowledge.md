---
title: coffer knowledge
description: "Knowledge collections (documents are plain files you edit directly)."
pageClass: cli-ref
---

# coffer knowledge

Knowledge collections (documents are plain files you edit directly).

```sh
coffer knowledge [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer knowledge --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`knowledge list`](#knowledge-list) | Every collection. |
| [`knowledge show`](#knowledge-show) | One collection: its config, reach and state. |
| [`knowledge update`](#knowledge-update) | Change a collection. |
| [`knowledge delete`](#knowledge-delete) | Delete a collection. |
| [`knowledge collections`](#knowledge-collections) | Every collection with its description, page, source, waiting-source and finding counts. |
| [`knowledge create`](#knowledge-create) | Create a collection. |
| [`knowledge describe`](#knowledge-describe) | Rewrite a collection's description. |
| [`knowledge check`](#knowledge-check) | A collection's mechanical findings: dead links, orphan pages, waiting sources. |
| [`knowledge tree`](#knowledge-tree) | One level of the knowledge tree. |
| [`knowledge changes`](#knowledge-changes) | Recent changes across collections, newest first. |
| [`knowledge restore`](#knowledge-restore) | Restore what a delete removed (from the changes feed). |
| [`knowledge tidy-handoff`](#knowledge-tidy-handoff) | The prompt that hands tidying knowledge to an agent. |
| [`knowledge upload`](#knowledge-upload) | Upload files into a collection; each is kept as a Markdown source. |

## knowledge list

Every collection.

<p class="cli-label">Synopsis</p>

```sh
coffer knowledge list [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## knowledge show

One collection: its config, reach and state.

<p class="cli-label">Synopsis</p>

```sh
coffer knowledge show [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The knowledge's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## knowledge update

Change a collection. Body: name, description, config.

<p class="cli-label">Synopsis</p>

```sh
coffer knowledge update [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The knowledge's name or uid |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## knowledge delete

Delete a collection.

<p class="cli-label">Synopsis</p>

```sh
coffer knowledge delete [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The knowledge's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## knowledge collections

Every collection with its description, page, source, waiting-source and finding counts.

<p class="cli-label">Synopsis</p>

```sh
coffer knowledge collections [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## knowledge create

Create a collection. Body: name, description.

<p class="cli-label">Synopsis</p>

```sh
coffer knowledge create [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## knowledge describe

Rewrite a collection's description. Body: description.

<p class="cli-label">Synopsis</p>

```sh
coffer knowledge describe [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The knowledge's name or uid |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## knowledge check

A collection's mechanical findings: dead links, orphan pages, waiting sources.

<p class="cli-label">Synopsis</p>

```sh
coffer knowledge check [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The knowledge's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## knowledge tree

One level of the knowledge tree.

<p class="cli-label">Synopsis</p>

```sh
coffer knowledge tree [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--path` <span class="cli-chip">option</span> | text |  | A folder under the root |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## knowledge changes

Recent changes across collections, newest first.

<p class="cli-label">Synopsis</p>

```sh
coffer knowledge changes [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--collection` <span class="cli-chip">option</span> | text |  |  |
| `--limit` <span class="cli-chip">option</span> | integer |  |  |
| `--cursor` <span class="cli-chip">option</span> | text |  |  |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## knowledge restore

Restore what a delete removed (from the changes feed).

<p class="cli-label">Synopsis</p>

```sh
coffer knowledge restore [OPTIONS] VERSION
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `VERSION` <span class="cli-chip">argument</span> | text | required | version |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## knowledge tidy-handoff

The prompt that hands tidying knowledge to an agent.

<p class="cli-label">Synopsis</p>

```sh
coffer knowledge tidy-handoff [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## knowledge upload

Upload files into a collection; each is kept as a Markdown source.

<p class="cli-label">Synopsis</p>

```sh
coffer knowledge upload [OPTIONS] COLLECTION FILES...
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `COLLECTION` <span class="cli-chip">argument</span> | text | required | The collection's folder name |
| `FILES` <span class="cli-chip">argument</span> | path (variadic) | required | Files to keep as sources |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
