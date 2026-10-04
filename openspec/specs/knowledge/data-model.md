# Data Model — Knowledge Layer

The layer's state is a directory. This document describes what is on disk —
one tree of documents per collection, the hidden inbox new material waits in,
the frontmatter contract, the naming rule — plus the one resource file a
collection has, curation's machine-local record, and the in-memory value
objects the surfaces answer with. Authority is [`spec.md`](spec.md) and
[Knowledge Is Plain Files](../../../docs/decisions/knowledge-is-plain-files.md).

## There is no schema

**The knowledge layer owns no table** (see "Add no table and no directory
outside the knowledge root"). Markdown files are the whole of it, and nothing
derives anything from them into a database: no `documents` row, no chunks, no
full-text index, no embeddings — therefore no content hash to compare, no
reindex, and no reconciliation of any kind (see "Store each collection as one
tree of Markdown files").

Curation needs two answers, and neither is a table. What is still waiting to
be merged is a file in the collection's hidden `.inbox/`. What a person has
edited since curation last saw it is a document whose blob at the vault's
`HEAD` differs from the blob curation last settled it as — recorded in
`~/.coffer/local/curation.json` — and whose newest commit is not a `curation`
or `sync` write. Modification time never decides.

Beyond its tree, a collection is one resource file,
`vault/resources/knowledge/<name>.json` (spec resource-framework), carrying the
collection's name and nothing about its contents. There is no per-agent reach
and no `enabled` switch in play for this kind (see "Serve every collection to
every agent"): the kind is non-toggleable, and it is always enabled.

## On-disk layout

```text
~/.coffer/vault/knowledge/
├── shopee/                         # a collection = a top-level folder = one Resource
│   ├── README.md                   # first paragraph = the collection's description; not a document
│   ├── account/                    # nesting chosen by a person or by curation
│   │   └── login-sessions.md
│   ├── gateway-routing.md          # a document: read by agents, edited by people and curation
│   └── .inbox/                     # hidden: items waiting to be curated
│       └── q3-review.md            # an upload's extracted text, deleted once curated
└── coffer/
    ├── README.md
    └── release-process.md
```

- `~/.coffer/vault/knowledge/` is the root, inside the vault repository, so a
  collection's history is the vault's history under `knowledge/`. There is no
  override: the root is resolved from `HOME` at every call, because a tree
  outside the vault would be a tree its history cannot see. Path construction
  lives in exactly one module,
  `infrastructure/knowledge/paths.py` (see "Guard every path through one
  module"), which also owns the inbox name.
- A **collection** is a top-level subdirectory *and* one `knowledge` Resource.
  It is created deliberately, as one directory, and nothing provisions one from
  a read, a write, or an agent's working directory (see "Create collections only
  deliberately"). There is no `global`, no `project-<ULID>`, no git-root
  resolution and no scope-to-project-root table (see "Derive no boundary from
  the working directory").
- **A collection is one tree of documents**, co-written by people and the
  curation pass (see "Store each collection as one tree of Markdown files").
  There is no directory that means "who may write here": a person edits any
  document in their own editor, an agent may edit one with its own file tools,
  and curation rewrites documents as it merges new material. The nesting is free
  and the system neither requires nor creates one — whoever files a document
  chooses where (see "Allow nesting without giving it meaning").
- **Dot-prefixed entries are invisible** (see "Hide dot-prefixed entries except
  the inbox"), and Coffer writes exactly one of its own: `.inbox/`, where
  submitted material waits until a pass folds it in, and from which each item is
  deleted the moment it has been. It is hidden because it is not knowledge yet —
  no catalogue or count of documents includes it; the collection list reports
  it separately as `pending_count`. It is
  the one hidden entry a surface shows, read-only: the tree lists a
  collection root's non-empty `.inbox` as a directory and its items as files,
  and the read route reads an item, each marked `inbox: true`. Every other
  hidden segment is still *refused* by the path guard rather than merely
  skipped. Coffer's own surfaces never write or delete an inbox item (a pass
  deletes one once folded in); an agent adds one by writing a Markdown file there
  with its own file tools, and the sweep normalises its frontmatter (see
  "Submit material by writing a file into the inbox").

### `README.md`

A collection describes itself in a `README.md` at its own root, which is not a
document: it is never curated, listed as content or counted (see "Keep the
collection README out of the corpus"). Its first paragraph is the collection's
one-line description everywhere one is shown (see "Read a collection's
description from its README"), read off disk on every listing so it cannot drift
from what the person browsing the folder reads.
`POST /api/v1/knowledge/collections` writes one when given a `description`.

That paragraph does more work than it used to: it is also what the delivered
skill's frontmatter description draws on, which is the only part of this layer
always in a model's context. A collection that fails to describe itself is a
collection an agent never recognises.

## The file

Every document and every inbox item carries a `---`-fenced YAML frontmatter
block, written and read only by `infrastructure/knowledge/frontmatter.py` (the
one place PyYAML lives).

```markdown
---
title: Session ownership
description: Which service owns a login session, and what reads it.
actor: agent
created_at: '2026-09-12T04:18:33Z'
updated_at: '2026-09-23T04:18:33Z'
---

Login state is owned by `account.session`.
```

| Key | Type | Notes |
| --- | --- | --- |
| `title` | `str` | Human-readable. Also the source of the file name on creation. |
| `description` | `str` | **Required** (see "Carry title, description and actor in frontmatter"). It is what curation reads first when deciding where material belongs, and what an agent chooses by in the catalogue. |
| `actor` | `agent` \| `user` | Who last wrote it. From the `X-Coffer-Actor` header on a submission, or the tool's own actor. |
| `created_at` | ISO-8601 `str` | Preserved across a rewrite, so a document keeps its own history even though nothing but the file records it. |
| `updated_at` | ISO-8601 `str` | Set on every write Coffer makes. |

When curation last had a document in front of it is **not** in the document:
it is `local/curation.json` (below), so settling a document changes no file and
makes no commit.

These are the keys **Coffer writes**, not the only keys a document may carry. A
person who adds `tags:` or `reviewed_by:` in their own editor keeps it: every
rewrite Coffer makes — a pass's `write_document` — renders the known keys in a fixed order and then everything else unharmed,
values carried through as parsed rather than stringified. There is still no `id`
— the path is the identity (see "Use the file path as a document's identity") —
and none of the keys that described retired machinery (`lane`, `source_path`,
`source_sha256`, `source_format`, `source_mode`, `converter`, `embed_status`,
`content_sha256`, `coffer_ingested_at`, `coffer_curated_at`).

Frontmatter parsing degrades rather than raising: a file with no fence, or with
malformed YAML inside one, yields empty frontmatter and its body, so one
hand-edited file with a stray colon cannot break a whole collection walk.

### What the sweep owes a collection, and curation's one local file

`curate.pending_items` answers it from the disk, in this order (see "Run
curation on a sweep and on demand"):

1. **Inbox material**, oldest first by modification time (`inbox.inbox_items`).
   Material first, because until it is merged it is knowledge no agent can read.
2. **Edited documents** (`curation_state.edited_documents`): every visible
   Markdown document whose blob at `HEAD` differs from the one
   `local/curation.json` settled — or that curation never settled, like a
   document a person wrote from scratch — and whose newest commit's writer is
   not `curation` or `sync`, oldest change first. Edits still on disk are
   committed first as `disk` writes, so an edit in any editor is judged by the
   same `HEAD`; the next sweep hands the document to a pass, which carries the
   edit into the rest of the collection as a newer statement (see "Let the newer or
   better-evidenced statement win"). Nothing has to be told, and a
   checkout, a restore from backup or a clock change that only moves
   modification times makes nothing pending.

`~/.coffer/local/curation.json` is machine-local (it can be rebuilt by letting
curation look at everything once), never committed and never synced:

```json
{ "documents": { "<collection>/<path>.md": { "blob": "<git blob id>", "at": "<iso time>" } } }
```

A collection rename moves its documents' entries with it.

Two consequences keep this honest:

- **Curation's own output does not come back.** A pass's `write_document` writes
  with `curated=True`, which records the blob it wrote in `local/curation.json`,
  and its commit's writer is `curation` — either is enough to keep the document
  out of the next sweep.
- **An item is settled only after its pass completes** (see "Settle an item only
  after its pass completes"). Material is deleted from the inbox
  (`inbox.discard_material`) and an edited document recorded as settled
  (`fs.mark_curated`) after the loop returns; a pass that raises leaves both as they were, so a
  later sweep retries rather than losing what one half-ran over.

With no internal model configured there is nothing to merge with, so material
does not wait (see "Promote material directly when no model is configured"):
`KnowledgeService.submit` promotes it on the spot (`inbox.promote` — a document of
its own at the collection root, recorded as settled), and a pass run with no model
promotes whatever is still in the inbox and reports `no_model` with the
`promoted` paths.

### Naming

A file's name is a readable slug of its title, not an opaque id, because with no
index mapping an id to a title the name is what a human reads in Finder and what
an agent sees in the catalogue (see "Use the file path as a document's
identity"). `infrastructure/knowledge/naming.py`
owns it:

- NFKC-normalize, lowercase, collapse whitespace / `_` / `/` / `\` to `-`, drop
  everything that is not `A-Za-z0-9-` or CJK, collapse runs of `-`, trim to 80
  characters. **CJK is kept, never transliterated** — a romanized name would be
  one neither party recognises. An empty result becomes `untitled`.
- `unique_name` appends `-2`, `-3`, … only when `<slug>.md` is already taken.
  Inbox items are named the same way and never written onto an existing item:
  two submissions of the same title are two pieces of material.

### The traversal guard

Every segment that becomes a path component passes `paths.check_segment` (see
"Guard every path through one module"): non-empty, not all dots, not
dot-prefixed, and matching `[A-Za-z0-9._\- ]` or CJK. A path that must name a
document additionally passes `paths.require_document`, which refuses the
collection itself and its `README.md`; the inbox is out of reach already,
because it is dot-prefixed. The one allowance is `paths.inbox_parts`, which
recognises `<collection>/.inbox` and `<collection>/.inbox/<item>` for the tree
and read routes alone — spelled out beside the guard rather than made by
loosening it, so every write, delete and settle still refuses the inbox. A
violation is `UnsafeKnowledgePath`
(`KNOWLEDGE_PATH_UNSAFE`, HTTP 400). The resolved path is checked against the
root too, on its nearest existing ancestor, so a symlink inside the root cannot
carry a read or a write out of it. Writes are atomic — same-directory temp file
opened `O_NOFOLLOW | O_EXCL`, then `replace`.

## Value objects (`backend/coffer/domain/knowledge/entry.py`)

These are the **shape of an answer, never the shape of a row**: a level is
produced by walking the directory and reading frontmatter at call time, so none
of them is persisted and none of them can be stale.

| Type | Fields | What it is |
| --- | --- | --- |
| `CollectionEntry` | `uid`, `name`, `description`, `document_count`, `pending_count` | One collection. `document_count` is what an agent can read today; `pending_count` is material still in the inbox — counted apart because it is exactly what an agent cannot see yet. |
| `DirectoryEntry` | `path`, `name`, `file_count`, `inbox` | A subdirectory at the level being listed. `path` is relative to the root — pass it back to descend. `inbox` marks a collection's `.inbox`. |
| `FileEntry` | `path`, `title`, `description`, `actor`, `updated_at`, `inbox` | One file as a listing or a catalogue shows it: enough to judge relevance without reading the body. `inbox` marks an item waiting in the inbox. |
| `CatalogueLevel` | `path`, `directories`, `files` | **One level of one collection**, never the whole tree. |
| `KnowledgeFile` | the frontmatter fields + `path`, `body`, `file_path`, `folder_path`, `curated_at`, `fingerprint`, `inbox` | A file in full. The two absolute paths are what the UI needs to offer open-in-editor and reveal-in-file-manager (see "Return absolute paths on reads"); `curated_at` is empty for a document curation has never seen; `fingerprint` is the sha256 of the file's bytes, which a save hands back (see "Save a document edited in the web UI"); `inbox` marks an inbox item, which is read-only. |
| `Pending` | `material` \| `document` | One item a pass can take — exactly one field set. `material` is an inbox item's file name, never a path a caller could aim elsewhere; `document` is a knowledge-root-relative document path. |
| `GrepMatch` | `path`, `line_number`, `line` | One literal hit. |
| `GrepOutcome` | `matches`, `truncated` | A bounded run of them. |

Constants: `ACTOR_AGENT = "agent"`, `ACTOR_USER = "user"`.

`KnowledgeService.submit` answers with a `Submission` (`collection`, `title`,
and exactly one of `document` — the `KnowledgeFile` it was promoted into — or
`pending`, the inbox item's name). `IngestService.ingest` answers with an
`IngestedDocument` (`path` or `None`, `title`, `description`, `converter`,
`pending`).

The two grep types survive the removal of `coffer__grep` because ripgrep
survives it as an **internal** mechanism: `KnowledgeService.match_documents` is
how a curation pass finds which existing documents a new item might belong to
(see "Assemble a pass from a bounded context"), and it is reachable by nothing
outside the process. It never searches the inbox — ripgrep skips hidden
directories, and material there is not a document yet. There is no `SearchHit`,
`SearchOutcome` or `SearchService` any more.

`Conversion` (`domain/knowledge/converter.py`) is what a converter returns for
an uploaded document: the `markdown`, a `title` (the document's first H1,
falling back to its file name; see "Fill frontmatter on converted material"),
and which `converter` ran — reported on the upload response and written nowhere
on disk.

The HTTP wire models in `surfaces/http/knowledge/schemas.py` mirror the domain
types and add the shapes that describe an answer no domain type does:
`CollectionCreate`; `MaterialIn` (`collection`, `title`, `description`, `body`)
and `SubmissionOut` (`status` `pending` | `written`, `collection`, `title`, and
`path` when written); `CurationRequest` (an optional `document`) and
`CurationOut` (`status`, `collection`, `item`, `model`, `written`, `retired`,
`refused`, `documents_before`, `documents_after`, `limit`, `promoted`,
`gave_up`, `stamped`), one per pass, inside the `CurationRunOut` the curate
route answers (`collection`, `status` `ok` | `failed` | `no_model` |
`up_to_date`, `total`, `passes`); and
`IngestedDocumentOut` (`path` or null, `title`, `description`, `converter`,
`pending`). The one write-a-document model is `FileSave` (`path`, `body`,
`expected_fingerprint`): a person's edited body, saved over a document whose
frontmatter is kept verbatim, refused with `KNOWLEDGE_FILE_CONFLICT` when the
file's fingerprint moved since the read (see "Save a document edited in the web
UI"). Every other entrance submits material. The mirroring is
deliberate rather than redundant: the domain types describe what is on disk and
the wire models describe what a client is promised, so removing a field from the
wire never means hiding one from the layer.

## The `knowledge` Resource

`make_knowledge_kind()` leaves `supports_scope` at the Kind default of `False`
and declares `generic_create_allowed=False`, because a collection is a directory
as much as a resource file and the generic `POST /resources` path would create
the file with no folder behind it. Being a Resource buys the collection a lifecycle, an audit
trail — not a switch and not a reach.

**Every collection is served to every agent** (see "Serve every collection to
every agent"). The kind declares itself non-toggleable, so the generic
enable/disable route refuses it; the layer does not read `enabled` at all, and
the sweep lists every registered collection. Every
registered collection's name, description, catalogue and paths appear in the
rendered `coffer-guide` skill every agent reads; a file an agent writes into a
directory that is not a collection is left alone and is not catalogued.

The per-agent reach that used to sit here is withdrawn too. It was never set — every collection's scope was null in
the live vault — and it could not have withheld anything it was asked to: the
skill it narrows hands the agent the absolute knowledge root and tells it to
grep. `PUT .../scope` on this kind is refused with `SCOPE_INVALID`.

`KnowledgeConfig` (`domain/knowledge/config.py`) is **empty and forbids unknown
keys**. A collection has no settings at all: no retrieval modes, no chunk size,
no entry-length cap, no embedding fields, no auto-update flag, no display label
(see "Add no table and no directory outside the knowledge root"). Anything that
used to be configured per scope was configuring machinery that no longer exists.

What the layer serves is **files on disk** (see "Present knowledge as files on
disk"). An agent that also holds shell or file-read tools can read anything
under `~/.coffer/vault/knowledge/`, which is why neither a per-agent reach nor an
enabled switch is offered: an allow-list that withholds a path from a reader
already holding the root withholds nothing at all.

## The history

Every accepted write to a collection is one commit, naming its writer, in the
vault repository (see "Keep every document's history and undo a pass as a
whole"; ADR every-vault-write-is-a-validated-commit-naming-its-writer): the
knowledge history is the vault's history pathspec-limited to `knowledge/`, with
every path handed back knowledge-root-relative (`KnowledgeHistory`,
`infrastructure/knowledge/history.py`, a view over the process's one vault
writer). The vault's `.git/info/exclude` ignores every
hidden entry under `knowledge/` except `.inbox/`, so a submission is a commit
and the text a pass consumed stays in history after the inbox file is deleted.

There is still no table and no index: the history is git's, read back through
`git log` when a surface asks.

**One commit per operation.** A person's save, delete, restore or undo; material
promoted on arrival; a collection created, renamed or removed; one curation pass
(everything it wrote and retired). Before any of them, whatever changed under
`knowledge/` that no open operation owns is committed first as a `disk` write,
so a person's own editor is never counted as Coffer's; the sweep and every
history read do the same. A sync round's merge is a `sync` commit by
construction.

**Trailers.** Each commit's message is a summary line and the vault's trailers
(spec vault-storage), with the knowledge history's own four added:

| Trailer | Value |
| --- | --- |
| `Coffer-Writer` | `user`, `agent`, `curation`, `sync` or `disk` |
| `Coffer-Operation` | `save`, `delete`, `submit`, `promote`, `pass`, `restore`, `undo`, `edit`, `sync`, `create`, `rename`, `remove`, `baseline` |
| `Coffer-Actor` | the audit actor of the operation |
| `Coffer-Machine` | the machine that made the commit |
| `Coffer-Agent` | an agent writer's name; for a pass, who submitted the item — from its `knowledge_written` event, which names the inbox `item` |
| `Coffer-Collection` | the collection's name |
| `Coffer-Item` | the item a pass curated (an inbox path or a document) |
| `Coffer-Status` | the pass's outcome status |
| `Coffer-Restored-From`, `Coffer-Undoes` | the commit a restore or an undo reverses to |

The value objects a surface reads back — `Change`, `DocumentChange`,
`DocumentVersion`, `DocumentDiff`, `ChangeDetail`, `WaitingItem`,
`ChangesPage` — are in `backend/coffer/domain/knowledge/history.py`. A change's
`version` is its commit id.

## Errors

The failure modes are a directory's, plus curation's two, plus the ones its one
external binary and its converter library have. `domain/knowledge/errors.py`
holds the first group:

| Class | Code | HTTP |
| --- | --- | --- |
| `CollectionNotFound` | `KNOWLEDGE_COLLECTION_NOT_FOUND` | 404 |
| `CollectionExists` | `KNOWLEDGE_COLLECTION_EXISTS` | 409 |
| `KnowledgeFileNotFound` | `KNOWLEDGE_FILE_NOT_FOUND` | 404 |
| `KnowledgeFileConflict` | `KNOWLEDGE_FILE_CONFLICT` | 409 |
| `UnsafeKnowledgePath` | `KNOWLEDGE_PATH_UNSAFE` | 400 |
| `UploadTooLarge` | `KNOWLEDGE_UPLOAD_TOO_LARGE` | 413 |
| `KnowledgeHistoryUnavailable` | `KNOWLEDGE_HISTORY_UNAVAILABLE` | 503 |
| `KnowledgeVersionNotFound` | `KNOWLEDGE_VERSION_NOT_FOUND` | 404 |
| `KnowledgeNotAPass` | `KNOWLEDGE_NOT_A_PASS` | 400 |
| `KnowledgeUndoConflict` | `KNOWLEDGE_UNDO_CONFLICT` | 409 |
| `KnowledgeError` (base) | `KNOWLEDGE_ERROR` | 400 |

`KNOWLEDGE_COLLECTION_NOT_FOUND` answers a name no registered collection holds.
`KNOWLEDGE_FILE_CONFLICT` answers a save whose `expected_fingerprint` no longer
matches the file's bytes; the file is left untouched, and `details` carries
`saved: false` with the document's `current_body` and `current_fingerprint`.
`KNOWLEDGE_UNDO_CONFLICT` names, in `details.document`, the document a later
commit changed, and `details.later_version` that commit. A uid-addressed route given a uid no resource answers to gives the generic
`RESOURCE_NOT_FOUND` (404) instead.

`UnsafeKnowledgePath` carries the document rule as well as the traversal one,
for the same reason both belong to path construction: a delete aimed at a
collection's `README.md` and a path aimed at `../etc/passwd` are both a caller
asking for something it may not reach, and a single guard is one that cannot be
forgotten by one surface.

The two curation refusals (a document naming another knowledge file, "Refuse
file-name references in documents", and the eight-write ceiling, "Bound a pass to
eight writes") are not errors: they are enforced in the curation tools
(`application/knowledge/curate_tools.py`) and returned to the model as tool
results, so a pass reports what it was stopped from doing without an error
code.

`domain/kb_errors.py` holds two more, re-exported through `domain/errors.py`:

| Class | Code | HTTP | When |
| --- | --- | --- | --- |
| `GrepPatternInvalid` | `GREP_PATTERN_INVALID` | 400 | the matcher rejected the pattern (ripgrep exit 2, or a regex the fallback cannot compile). Now reachable only through candidate selection, where without it an `rg` failure would masquerade as "no candidates" |
| `EngineUnavailable` | `ENGINE_UNAVAILABLE` | 503 | a binary or converter library the call needs is absent — `ripgrep` with no Python fallback available, or one of MarkItDown's format backends. The daemon stays up and the caller gets a per-format answer |

And the two ingest refusals are not `CofferError`s at all. `UnsupportedDocument`
and `EmptyConversion` (`domain/knowledge/converter.py`) carry the *rejected
type* rather than a code, and the upload route turns both into `INGEST_REJECTED`
/ 400, distinguished by `details.reason` — `unsupported_type`, or `scanned_pdf`
/ `empty_conversion` — so a surface can name the format it will not take and,
for a PDF with no text layer, say something actionable about why. Either way
nothing is submitted: no inbox item, no document (see "Bound uploads and leave
nothing behind on failure").

A pass requested while one is already in flight over the same collection answers
`UPKEEP_ALREADY_RUNNING` / 409 (see "Run one pass per collection at a time"). It
is refused rather than queued because the caller asked to *start* a pass, and no
pass is going to start.

## Audit and invocation records

Unchanged in shape and still database-backed, because they are not knowledge —
they are Coffer's own bookkeeping. Every submission — an inbox file an agent
wrote (recorded by the sweep when it first sees the file), an upload or a
channel — records one `KNOWLEDGE_WRITTEN` `audit_log` event naming the caller
(`actor_reported: true` when the actor came from the file's own frontmatter), with the
inbox `item`, the document path when it was promoted and `pending`
when it waits (see "Submit material by writing a file into the inbox"); a save from the web UI records
`KNOWLEDGE_EDITED` with the path, and so do a restore (with `restored_from`)
and an undo (with `undo` and its `documents`); a delete records
`KNOWLEDGE_DELETED`. A
completed curation pass records `KNOWLEDGE_CURATED` with the item, the model and
its counts.

Losing the read tools lost the invocation record for reads, and with it the
ability to answer "is this layer being used" from `mcp_invocations`. That is a
deliberate cost: the replacement measurement is the agents' own transcripts,
which Coffer already reads for other reasons and which are retroactive, so
nothing is lost by not having built it yet.

## The installation-wide curation setting

The one setting the layer has is not the layer's. Three fields of the engine's
settings document, `vault/state/settings/internal-engine.json` (spec
internal-engine), carry it (see "Curate on one owner machine only"):

| field | notes |
| --- | --- |
| `upkeep.curate.enabled` | the switch, **default true** — curation is what merges new material into the documents and carries a person's edit through the rest of the collection, so an installation where it never runs has material waiting in the inbox forever |
| `upkeep.curate.interval_s` | the timer; null means the built-in cadence (one hour); a stored value is kept as chosen |
| `curate_owner_machine_id` | the one machine allowed to run the sweep. Null means a single-machine vault, where "here" is the only answer there is |

The switch and the owner are read **together, on every sweep**, so the setting
means *on, here* rather than merely *on*. All three govern only the background
worker, which re-reads them every tick so a change needs no daemon restart; the
manual trigger consults none of them. A sweep runs at most five passes per
collection, one item each, and stops a collection's sweep early on `no_model` or
`failed`. The document is in the vault, so every machine agrees on who the
owner is.
