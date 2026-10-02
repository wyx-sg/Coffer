---
title: coffer knowledge
description: "Manage Coffer's knowledge collections, the Markdown under ~/.coffer/vault/knowledge/<collection>/ (`coffer path knowledge` prints it)."
---

# coffer knowledge

Part of the [CLI reference](/reference/cli), generated from the CLI's own command tree; regenerate it with `make docs-reference`, never by hand.

```sh
coffer knowledge [OPTIONS] COMMAND [ARGS]...
```

Manage Coffer's knowledge collections, the Markdown under ~/.coffer/vault/knowledge/&lt;collection&gt;/ (`coffer path knowledge` prints it). Each collection is one tree of documents you and Coffer write together: read, grep and edit them with your own tools, and add new knowledge with `write` or `upload`: it waits as an item until Coffer curates it into the documents. `history`, `changes` and `undo` show and reverse what changed.

## knowledge list

```sh
coffer knowledge list [OPTIONS]
```

List every collection, with its documents and the items waiting to be curated.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--json` | option | flag |  | JSON output for scripts |

## knowledge show

```sh
coffer knowledge show [OPTIONS] NAME
```

Show one collection, by name or uid.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Name or uid |
| `--json` | option | flag |  | JSON output for scripts |

## knowledge add

```sh
coffer knowledge add [OPTIONS] NAME
```

Create a collection. Nothing else creates one.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Collection name (one path segment) |
| `--description, -d` | option | text | `""` | Written as the opening paragraph of its README.md |

## knowledge edit

```sh
coffer knowledge edit [OPTIONS] NAME
```

Rename a collection (its directory moves with it) or rewrite its description.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Name or uid |
| `--name` | option | text |  | New name (the folder moves) |
| `--description, -d` | option | text |  | Rewrite the opening paragraph of its README.md |

## knowledge rm

```sh
coffer knowledge rm [OPTIONS] NAME
```

Remove a collection and its directory (`restore --deleted` brings it back).

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Name or uid |
| `--force, --yes, -f, -y` | option | flag |  | Do not ask |

## knowledge write

```sh
coffer knowledge write [OPTIONS]
```

Add new knowledge as an item. Coffer curates it into the documents.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--title, -t` | option | text | required |  |
| `--description, -d` | option | text | required | What it is about |
| `--body, -b` | option | text | `""` |  |
| `--collection` | option | text | required | Collection to add it to |

## knowledge upload

```sh
coffer knowledge upload [OPTIONS] FILE
```

Convert a document to Markdown and add what it says to a collection.

The extracted text becomes an item that curation folds into the documents; neither the original nor the extracted file is kept.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `FILE` | argument | path | required | Document to ingest |
| `--collection` | option | text | required | Collection to ingest it into |

## knowledge curate

```sh
coffer knowledge curate [OPTIONS] COLLECTION
```

Curate a collection now: one pass per pending item until none is left.

Items waiting in the inbox go first, oldest first, then documents edited since curation last saw them. Each pass is bounded and reports its status — ok, truncated (cut off; its item stays pending), too_large, failed — and the run stops at the first failed pass, leaving the rest pending. With no model configured, the inbox becomes documents as it stands (no_model). A run already curating the same collection is refused rather than queued.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `COLLECTION` | argument | text | required | Collection to curate |
| `--document` | option | text | `""` | Curate just this document (a path under the collection) |
| `--json` | option | flag |  | JSON output for scripts |

## knowledge history

```sh
coffer knowledge history [OPTIONS] PATH
```

List a document's versions, newest first, with who wrote each.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `PATH` | argument | text | required | A document, e.g. shopee/infra/cache.md |
| `--version` | option | text | `""` | Print this version's diff |
| `--json` | option | flag |  | JSON output for scripts |

## knowledge restore

```sh
coffer knowledge restore [OPTIONS] [PATH] [VERSION]
```

Put one version of a document back, as a new version — or, with `--deleted`, bring back a deleted document or collection.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `PATH` | argument | text | `""` | The document to restore |
| `VERSION` | argument | text | `""` | The version to put back (from `history`) |
| `--deleted` | option | text | `""` | Bring back what this delete removed, a document or a whole collection (the delete's version, from `changes`) |

## knowledge changes

```sh
coffer knowledge changes [OPTIONS] [VERSION]
```

Recent changes to knowledge across collections, and the items waiting.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `VERSION` | argument | text | `""` | Show this change in full, with each document's diff |
| `--collection` | option | text | `""` | Only this collection |
| `--limit` | option | integer | `20` | How many changes |
| `--json` | option | flag |  | JSON output for scripts |

## knowledge undo

```sh
coffer knowledge undo [OPTIONS] VERSION
```

Undo a curation pass as a whole: every document it wrote or retired goes back to how it was. Refused, naming the document, if one has changed since.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `VERSION` | argument | text | required | The curation pass to undo (from `changes`) |
