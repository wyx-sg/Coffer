# Data Model — Knowledge Layer

> 中文版: [data-model.zh.md](./data-model.zh.md)

The layer's state is a directory. This document describes what is on disk —
the tree, the frontmatter contract, the naming rule — plus the one database row
a collection still occupies and the in-memory value objects the surfaces answer
with. Authority is [`spec.md`](./spec.md) and
[Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md).

## There is no schema

**The knowledge layer owns no table** (FR-081, SC-004). Markdown files are the
sole source of truth, and nothing derives anything from them: no `documents`
row, no chunks, no full-text index, no embeddings — therefore no content hash
to compare, no reindex, and no reconciliation of any kind (FR-001).

The only database presence a collection has is the same one every Resource has:
a row in the kind-agnostic `resources` table. That row carries the collection's
name, its `enabled` flag and its per-agent `scope`, and nothing about its
contents.

## On-disk layout

```text
~/.coffer/knowledge/
├── shopee/                         # a collection = a top-level folder = one Resource
│   ├── README.md                   # first paragraph = the collection's description
│   ├── account/                    # the human's own filing; the system assigns it no meaning
│   │   └── session-ownership.md
│   ├── gateway-routing.md
│   └── .history/                   # revisions the tidy pass superseded (hidden)
└── coffer/
    ├── README.md
    └── release-process.md
```

- `~/.coffer/knowledge/` is the root; `$COFFER_KNOWLEDGE_ROOT` overrides it for
  tests. Path construction lives in exactly one module,
  `infrastructure/knowledge/paths.py` (FR-006).
- A **collection** is a top-level subdirectory *and* one `knowledge` Resource.
  It is created deliberately; nothing provisions one from a read, a write, or
  an agent's working directory (FR-010). There is no `global`, no
  `project-<ULID>`, no git-root resolution and no scope-to-project-root table
  (FR-011).
- Inside a collection the nesting is the human's business. Subdirectories are
  optional, arbitrarily deep, and mean nothing to the system, which never
  requires or creates one (FR-004).
- **Dot-prefixed entries are invisible** to the catalogue and to grep (FR-005).
  `.history/` is the only one Coffer itself writes (FR-052). Hidden segments
  are *refused* by the path guard rather than merely skipped: handing back a
  `.history/` revision would answer with content the live file has replaced.

### `README.md`

A collection describes itself in a `README.md` in its own directory; the
catalogue's one-line description of a collection is that file's first paragraph,
and is empty when there is no README (FR-013). It is never stored in the
database, so it cannot drift from what the person browsing the folder reads.
`POST /api/v1/knowledge/collections` writes one when given a `description`.

## The file

Every file is Markdown with a `---`-fenced YAML frontmatter block, written and
read only by `infrastructure/knowledge/frontmatter.py` (the one place PyYAML
lives).

```markdown
---
title: Session ownership
description: Which service owns a login session, and what reads it.
actor: agent
created_at: '2026-09-12T04:18:33Z'
updated_at: '2026-09-12T04:18:33Z'
---

Login state is owned by `account.session`.
```

| Key | Type | Notes |
| --- | --- | --- |
| `title` | `str` | Human-readable. Also the source of the file name on creation. |
| `description` | `str` | **Required** (FR-003). With no ranked index the catalogue is the retrieval surface, so a file that fails to describe itself is unfindable. |
| `actor` | `agent` \| `user` | Who last wrote it. From the `X-Coffer-Actor` header on the write, or the tool's own actor. |
| `created_at` | ISO-8601 `str` | Preserved across a replace, so a file keeps its own history even though nothing but the file records it. |
| `updated_at` | ISO-8601 `str` | Set on every write. |

**And nothing else** (FR-003). There is no `id` — the path is the identity
(FR-002) — and no `lane`, `source_path`, `source_sha256`, `source_format`,
`source_mode`, `converter`, `embed_status` or `content_sha256`: each of those
described machinery that no longer exists.

Frontmatter parsing degrades rather than raising: a file with no fence, or with
malformed YAML inside one, yields empty frontmatter and its body, so one
hand-edited file with a stray colon cannot break a whole catalogue walk.

### Naming

A file's name is a readable slug of its title, not an opaque id, because with no
index mapping an id to a title the name is what a human reads in Finder and what
an agent reads in a grep result (FR-002). `infrastructure/knowledge/naming.py`
owns it:

- NFKC-normalize, lowercase, collapse whitespace / `_` / `/` / `\` to `-`, drop
  everything that is not `A-Za-z0-9-` or CJK, collapse runs of `-`, trim to 80
  characters. **CJK is kept, never transliterated** — a romanized name would be
  one neither party recognises. An empty result becomes `untitled`.
- `unique_name` appends `-2`, `-3`, … only when `<slug>.md` is already taken.

### The traversal guard

Every segment that becomes a path component passes `paths.check_segment`
(FR-006): non-empty, not all dots, not dot-prefixed, and matching
`[A-Za-z0-9._\- ]` or CJK. A violation is `UnsafeKnowledgePath`
(`KNOWLEDGE_PATH_UNSAFE`, HTTP 400). Writes are atomic — same-directory temp
file, then `replace`.

## Value objects (`backend/coffer/domain/knowledge/entry.py`)

These are the **shape of an answer, never the shape of a row**: a catalogue
level is produced by walking the directory and reading frontmatter at call time
(FR-020), so none of them is persisted and none of them can be stale.

| Type | Fields | What it is |
| --- | --- | --- |
| `CollectionEntry` | `name`, `description`, `file_count` | One collection at the catalogue's top level. `description` is the README's first paragraph; `file_count` is recursive, hidden entries excluded. |
| `DirectoryEntry` | `path`, `name`, `file_count` | A subdirectory at the level being listed. `path` is relative to the root — pass it back to descend. |
| `FileEntry` | `path`, `title`, `description`, `actor`, `updated_at` | One file as the catalogue shows it: enough to judge relevance without reading the body. |
| `CatalogueLevel` | `path`, `directories`, `files` | **One level**, never the whole tree (FR-021). |
| `KnowledgeFile` | the five frontmatter fields + `path`, `body`, `file_path`, `folder_path` | A file in full. The two absolute paths are what the UI needs to offer open-in-editor and reveal-in-file-manager (FR-062). |
| `GrepMatch` | `path`, `line_number`, `line` | One ripgrep hit. |
| `GrepOutcome` | `matches`, `truncated` | A bounded run; `truncated` says whether `max_matches` cut it short (FR-022). |

Constants: `ACTOR_AGENT = "agent"`, `ACTOR_USER = "user"`.

The HTTP wire models in `surfaces/http/knowledge/schemas.py` mirror these one
for one. The mirroring is deliberate rather than redundant: the domain types
describe what is on disk and the wire models describe what a client is
promised, so removing a field from the wire never means hiding one from the
layer.

## The `knowledge` Resource

`make_knowledge_kind()` declares `supports_scope=True` — per-agent
authorization is the whole reason a collection is a Resource (FR-012). An agent
sees, greps, reads and writes exactly the collections activated for it, with no
rule that leaves an authorized collection out of a default.

`KnowledgeConfig` (`domain/knowledge/config.py`) is **empty and forbids unknown
keys**. A collection has no settings at all: no retrieval modes, no chunk size,
no entry-length cap, no embedding fields, no auto-update flag, no display label
(FR-081). Anything that used to be configured per scope was configuring
machinery that no longer exists.

Enforcement is at the MCP tool surface only. An agent that also holds shell or
file-read tools can read anything under `~/.coffer/knowledge/` directly: the
scope prevents mistaken retrieval, not deliberate access, and the system says so
rather than implying an isolation it does not provide (FR-014).

## Errors (`domain/knowledge/errors.py`)

The failure modes are a directory's.

| Class | Code | HTTP |
| --- | --- | --- |
| `CollectionNotFound` | `KNOWLEDGE_COLLECTION_NOT_FOUND` | 404 |
| `CollectionExists` | `KNOWLEDGE_COLLECTION_EXISTS` | 409 |
| `KnowledgeFileNotFound` | `KNOWLEDGE_FILE_NOT_FOUND` | 404 |
| `UnsafeKnowledgePath` | `KNOWLEDGE_PATH_UNSAFE` | 400 |
| `KnowledgeError` (base) | `KNOWLEDGE_ERROR` | 400 |

## Audit and invocation records

Unchanged and still database-backed, because they are not knowledge — they are
Coffer's own bookkeeping. A built-in tool call records one `mcp_invocations`
row (tool, actor, duration, outcome — never arguments, never content), and a
write or delete additionally records an `audit_log` event with the agent as
actor (FR-041).

## The installation-wide tidy setting

The one setting the layer has is not the layer's: `auto_tidy_enabled` is a
boolean column on `internal_engine_config`, **default false** (FR-051). It
governs only whether the background worker runs the tidy pass on an interval;
the manual trigger never consults it.

## What migration 0066 did

`20260912_0066_knowledge_is_plain_files.py` (FR-070, FR-071). **The order is
the whole point**: a document's title lived only in `documents.title`, so the
on-disk rewrite runs FIRST, reading the rows it is about to destroy.

The rewrite turns `<scope>/{notes,docs}/<ULID>.md` into
`<collection>/<slug-of-title>.md` carrying exactly the five frontmatter keys
above; `global` lands in `shopee` and every `project-<ULID>` scope in `coffer`;
`.raw/` — whose 50 files were byte-identical to their lane counterparts — is
deleted; emptied scope directories are removed; each collection gets a
`README.md`; and the `knowledge` Resource rows are re-pointed from scopes to
collections.

Then eleven tables are dropped, each guarded so a database missing any of them
still upgrades: `documents`, `chunks`, the six `documents_fts*` tables (the
virtual table's drop takes its shadows with it; the explicit shadow drops cover
an already-orphaned case), `embedding_config`, `knowledge_scope_labels` and
`knowledge_scope_project_roots`.

`downgrade` raises. The migration is one-way by design — ULID names and the
`.raw/` copies cannot be reconstructed — and **no compatibility shim is left
behind anywhere**. The rewrite is idempotent: a re-run finds no lane
directories and does nothing.
