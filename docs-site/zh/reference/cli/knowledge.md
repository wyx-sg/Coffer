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

本页与 `coffer knowledge --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
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
| [`knowledge upload`](#knowledge-upload) | Upload files into a collection; each becomes a source, its original kept. |

## knowledge list

Every collection.

<p class="cli-label">概要</p>

```sh
coffer knowledge list [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## knowledge show

One collection: its config, reach and state.

<p class="cli-label">概要</p>

```sh
coffer knowledge show [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The knowledge's name or uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## knowledge update

Change a collection. Body: name, title, description, config.

<p class="cli-label">概要</p>

```sh
coffer knowledge update [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The knowledge's name or uid |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## knowledge delete

Delete a collection.

<p class="cli-label">概要</p>

```sh
coffer knowledge delete [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The knowledge's name or uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## knowledge collections

Every collection with its description, page, source, waiting-source and finding counts.

<p class="cli-label">概要</p>

```sh
coffer knowledge collections [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## knowledge create

Create a collection. Body: name, description.

<p class="cli-label">概要</p>

```sh
coffer knowledge create [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## knowledge describe

Rewrite a collection's description. Body: description.

<p class="cli-label">概要</p>

```sh
coffer knowledge describe [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The knowledge's name or uid |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## knowledge check

A collection's mechanical findings: dead links, orphan pages, waiting sources.

<p class="cli-label">概要</p>

```sh
coffer knowledge check [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The knowledge's name or uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## knowledge tree

One level of the knowledge tree.

<p class="cli-label">概要</p>

```sh
coffer knowledge tree [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--path` <span class="cli-chip">选项</span> | text |  | A folder under the root |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## knowledge changes

Recent changes across collections, newest first.

<p class="cli-label">概要</p>

```sh
coffer knowledge changes [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--collection` <span class="cli-chip">选项</span> | text |  |  |
| `--limit` <span class="cli-chip">选项</span> | integer |  |  |
| `--cursor` <span class="cli-chip">选项</span> | text |  |  |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## knowledge restore

Restore what a delete removed (from the changes feed).

<p class="cli-label">概要</p>

```sh
coffer knowledge restore [OPTIONS] VERSION
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `VERSION` <span class="cli-chip">参数</span> | text | 必填 | version |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## knowledge tidy-handoff

The prompt that hands tidying knowledge to an agent.

<p class="cli-label">概要</p>

```sh
coffer knowledge tidy-handoff [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## knowledge upload

Upload files into a collection; each becomes a source, its original kept.

<p class="cli-label">概要</p>

```sh
coffer knowledge upload [OPTIONS] COLLECTION FILES...
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `COLLECTION` <span class="cli-chip">参数</span> | text | 必填 | The collection's folder name |
| `FILES` <span class="cli-chip">参数</span> | path（可变个数） | 必填 | Files to keep as sources |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
