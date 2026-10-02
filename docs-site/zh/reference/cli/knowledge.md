---
title: coffer knowledge
description: "Manage Coffer's knowledge collections, the Markdown under ~/.coffer/vault/knowledge/<collection>/ (`coffer path knowledge` prints it)."
---

# coffer knowledge

属于 [CLI 参考](/zh/reference/cli)，由 CLI 自己的命令树生成；用 `make docs-reference` 重新生成，不要手工编辑。

```sh
coffer knowledge [OPTIONS] COMMAND [ARGS]...
```

Manage Coffer's knowledge collections, the Markdown under ~/.coffer/vault/knowledge/&lt;collection&gt;/ (`coffer path knowledge` prints it). Each collection is one tree of documents you and Coffer write together: read, grep and edit them with your own tools, and add new knowledge with `write` or `upload`: it waits as an item until Coffer curates it into the documents. `history`, `changes` and `undo` show and reverse what changed.

## knowledge list

```sh
coffer knowledge list [OPTIONS]
```

List every collection, with its documents and the items waiting to be curated.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## knowledge show

```sh
coffer knowledge show [OPTIONS] NAME
```

Show one collection, by name or uid.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## knowledge add

```sh
coffer knowledge add [OPTIONS] NAME
```

Create a collection. Nothing else creates one.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Collection name (one path segment) |
| `--description, -d` | 选项 | text | `""` | Written as the opening paragraph of its README.md |

## knowledge edit

```sh
coffer knowledge edit [OPTIONS] NAME
```

Rename a collection (its directory moves with it) or rewrite its description.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--name` | 选项 | text |  | New name (the folder moves) |
| `--description, -d` | 选项 | text |  | Rewrite the opening paragraph of its README.md |

## knowledge rm

```sh
coffer knowledge rm [OPTIONS] NAME
```

Remove a collection and its directory (`restore --deleted` brings it back).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--force, --yes, -f, -y` | 选项 | 开关 |  | Do not ask |

## knowledge write

```sh
coffer knowledge write [OPTIONS]
```

Add new knowledge as an item. Coffer curates it into the documents.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--title, -t` | 选项 | text | 必填 |  |
| `--description, -d` | 选项 | text | 必填 | What it is about |
| `--body, -b` | 选项 | text | `""` |  |
| `--collection` | 选项 | text | 必填 | Collection to add it to |

## knowledge upload

```sh
coffer knowledge upload [OPTIONS] FILE
```

Convert a document to Markdown and add what it says to a collection.

The extracted text becomes an item that curation folds into the documents; neither the original nor the extracted file is kept.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `FILE` | 参数 | path | 必填 | Document to ingest |
| `--collection` | 选项 | text | 必填 | Collection to ingest it into |

## knowledge curate

```sh
coffer knowledge curate [OPTIONS] COLLECTION
```

Curate a collection now: one pass per pending item until none is left.

Items waiting in the inbox go first, oldest first, then documents edited since curation last saw them. Each pass is bounded and reports its status — ok, truncated (cut off; its item stays pending), too_large, failed — and the run stops at the first failed pass, leaving the rest pending. With no model configured, the inbox becomes documents as it stands (no_model). A run already curating the same collection is refused rather than queued.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `COLLECTION` | 参数 | text | 必填 | Collection to curate |
| `--document` | 选项 | text | `""` | Curate just this document (a path under the collection) |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## knowledge history

```sh
coffer knowledge history [OPTIONS] PATH
```

List a document's versions, newest first, with who wrote each.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `PATH` | 参数 | text | 必填 | A document, e.g. shopee/infra/cache.md |
| `--version` | 选项 | text | `""` | Print this version's diff |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## knowledge restore

```sh
coffer knowledge restore [OPTIONS] [PATH] [VERSION]
```

Put one version of a document back, as a new version — or, with `--deleted`, bring back a deleted document or collection.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `PATH` | 参数 | text | `""` | The document to restore |
| `VERSION` | 参数 | text | `""` | The version to put back (from `history`) |
| `--deleted` | 选项 | text | `""` | Bring back what this delete removed, a document or a whole collection (the delete's version, from `changes`) |

## knowledge changes

```sh
coffer knowledge changes [OPTIONS] [VERSION]
```

Recent changes to knowledge across collections, and the items waiting.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `VERSION` | 参数 | text | `""` | Show this change in full, with each document's diff |
| `--collection` | 选项 | text | `""` | Only this collection |
| `--limit` | 选项 | integer | `20` | How many changes |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## knowledge undo

```sh
coffer knowledge undo [OPTIONS] VERSION
```

Undo a curation pass as a whole: every document it wrote or retired goes back to how it was. Refused, naming the document, if one has changed since.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `VERSION` | 参数 | text | 必填 | The curation pass to undo (from `changes`) |
