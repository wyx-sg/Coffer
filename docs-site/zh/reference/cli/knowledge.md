---
title: coffer knowledge
description: "Manage Coffer's knowledge collections, the Markdown under ~/.coffer/vault/knowledge/<collection>/ (`coffer path knowledge` prints it)."
pageClass: cli-ref
---

# coffer knowledge

Manage Coffer's knowledge collections, the Markdown under ~/.coffer/vault/knowledge/&lt;collection&gt;/ (`coffer path knowledge` prints it). Each collection is one tree of documents you and Coffer write together: read, grep and edit them with your own tools, and add new knowledge with `write` or `upload`: it waits as an item until Coffer curates it into the documents. `history`, `changes` and `undo` show and reverse what changed.

```sh
coffer knowledge [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer knowledge --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`knowledge list`](#knowledge-list) | List every collection, with its documents and the items waiting to be curated. |
| [`knowledge show`](#knowledge-show) | Show one collection, by name or uid. |
| [`knowledge add`](#knowledge-add) | Create a collection. |
| [`knowledge edit`](#knowledge-edit) | Rename a collection (its directory moves with it) or rewrite its description. |
| [`knowledge rm`](#knowledge-rm) | Remove a collection and its directory (`restore --deleted` brings it back). |
| [`knowledge write`](#knowledge-write) | Add new knowledge as an item. |
| [`knowledge upload`](#knowledge-upload) | Convert a document to Markdown and add what it says to a collection. |
| [`knowledge curate`](#knowledge-curate) | Curate a collection now: one pass per pending item until none is left. |
| [`knowledge history`](#knowledge-history) | List a document's versions, newest first, with who wrote each. |
| [`knowledge restore`](#knowledge-restore) | Put one version of a document back, as a new version — or, with `--deleted`, bring back a deleted document or collection. |
| [`knowledge changes`](#knowledge-changes) | Recent changes to knowledge across collections, and the items waiting. |
| [`knowledge undo`](#knowledge-undo) | Undo a curation pass as a whole: every document it wrote or retired goes back to how it was. |

## knowledge list

List every collection, with its documents and the items waiting to be curated.

<p class="cli-label">概要</p>

```sh
coffer knowledge list [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## knowledge show

Show one collection, by name or uid.

<p class="cli-label">概要</p>

```sh
coffer knowledge show [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Name or uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## knowledge add

Create a collection. Nothing else creates one.

<p class="cli-label">概要</p>

```sh
coffer knowledge add [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Collection name (one path segment) |
| `--description, -d` <span class="cli-chip">选项</span> | text | `""` | Written as the opening paragraph of its README.md |

## knowledge edit

Rename a collection (its directory moves with it) or rewrite its description.

<p class="cli-label">概要</p>

```sh
coffer knowledge edit [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Name or uid |
| `--name` <span class="cli-chip">选项</span> | text |  | New name (the folder moves) |
| `--description, -d` <span class="cli-chip">选项</span> | text |  | Rewrite the opening paragraph of its README.md |

## knowledge rm

Remove a collection and its directory (`restore --deleted` brings it back).

<p class="cli-label">概要</p>

```sh
coffer knowledge rm [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Name or uid |
| `--force, --yes, -f, -y` <span class="cli-chip">选项</span> | 开关 |  | Do not ask |

## knowledge write

Add new knowledge as an item. Coffer curates it into the documents.

<p class="cli-label">概要</p>

```sh
coffer knowledge write [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--title, -t` <span class="cli-chip">选项</span> | text | 必填 |  |
| `--description, -d` <span class="cli-chip">选项</span> | text | 必填 | What it is about |
| `--body, -b` <span class="cli-chip">选项</span> | text | `""` |  |
| `--collection` <span class="cli-chip">选项</span> | text | 必填 | Collection to add it to |

## knowledge upload

Convert a document to Markdown and add what it says to a collection.

The extracted text becomes an item that curation folds into the documents; neither the original nor the extracted file is kept.

<p class="cli-label">概要</p>

```sh
coffer knowledge upload [OPTIONS] FILE
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `FILE` <span class="cli-chip">参数</span> | path | 必填 | Document to ingest |
| `--collection` <span class="cli-chip">选项</span> | text | 必填 | Collection to ingest it into |

## knowledge curate

Curate a collection now: one pass per pending item until none is left.

Items waiting in the inbox go first, oldest first, then documents edited since curation last saw them. Each pass is bounded and reports its status — ok, truncated (cut off; its item stays pending), too_large, failed — and the run stops at the first failed pass, leaving the rest pending. With no model configured, the inbox becomes documents as it stands (no_model). A run already curating the same collection is refused rather than queued.

<p class="cli-label">概要</p>

```sh
coffer knowledge curate [OPTIONS] COLLECTION
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `COLLECTION` <span class="cli-chip">参数</span> | text | 必填 | Collection to curate |
| `--document` <span class="cli-chip">选项</span> | text | `""` | Curate just this document (a path under the collection) |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## knowledge history

List a document's versions, newest first, with who wrote each.

<p class="cli-label">概要</p>

```sh
coffer knowledge history [OPTIONS] PATH
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `PATH` <span class="cli-chip">参数</span> | text | 必填 | A document, e.g. shopee/infra/cache.md |
| `--version` <span class="cli-chip">选项</span> | text | `""` | Print this version's diff |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## knowledge restore

Put one version of a document back, as a new version — or, with `--deleted`, bring back a deleted document or collection.

<p class="cli-label">概要</p>

```sh
coffer knowledge restore [OPTIONS] [PATH] [VERSION]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `PATH` <span class="cli-chip">参数</span> | text | `""` | The document to restore |
| `VERSION` <span class="cli-chip">参数</span> | text | `""` | The version to put back (from `history`) |
| `--deleted` <span class="cli-chip">选项</span> | text | `""` | Bring back what this delete removed, a document or a whole collection (the delete's version, from `changes`) |

## knowledge changes

Recent changes to knowledge across collections, and the items waiting.

<p class="cli-label">概要</p>

```sh
coffer knowledge changes [OPTIONS] [VERSION]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `VERSION` <span class="cli-chip">参数</span> | text | `""` | Show this change in full, with each document's diff |
| `--collection` <span class="cli-chip">选项</span> | text | `""` | Only this collection |
| `--limit` <span class="cli-chip">选项</span> | integer | `20` | How many changes |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## knowledge undo

Undo a curation pass as a whole: every document it wrote or retired goes back to how it was. Refused, naming the document, if one has changed since.

<p class="cli-label">概要</p>

```sh
coffer knowledge undo [OPTIONS] VERSION
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `VERSION` <span class="cli-chip">参数</span> | text | 必填 | The curation pass to undo (from `changes`) |
