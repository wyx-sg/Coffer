# Data Model — Knowledge Layer

The layer's state is a directory. This document describes what is on disk —
one tree of documents per collection, the hidden inbox new material waits in,
the frontmatter contract, the naming rule — plus the one database row a
collection still occupies and the in-memory value objects the surfaces answer
with. Authority is [`spec.md`](spec.md) and
[Knowledge Is Plain Files](../../../docs/decisions/knowledge-is-plain-files.md).

## There is no schema

**The knowledge layer owns no table** (FR-046, SC-004). Markdown files are the
whole of it, and nothing derives anything from them into a database: no
`documents` row, no chunks, no full-text index, no embeddings — therefore no
content hash to compare, no reindex, and no reconciliation of any kind (FR-001).

Curation's state lives in the same directory as everything else. What is still
waiting to be merged is a file in the collection's hidden `.inbox/`; what a
person has edited since curation last saw it is a document whose modification
time is newer than the `coffer_curated_at` stamp in its own frontmatter. That is
why there is no curation state table and no scan journal: both questions the
sweep asks are answered by the disk itself, where the answer cannot disagree
with the disk.

The only database presence a collection has is the same one every Resource has:
a row in the kind-agnostic `resources` table. That row carries the collection's
name and its `enabled` flag, and nothing about its contents. There is no
per-agent reach column in play for this kind (FR-010): the row's one switch is
`enabled`.

## On-disk layout

```text
~/.coffer/knowledge/
├── shopee/                         # a collection = a top-level folder = one Resource
│   ├── README.md                   # first paragraph = the collection's description; not a document
│   ├── account/                    # nesting chosen by a person or by curation
│   │   └── login-sessions.md
│   ├── gateway-routing.md          # a document: read by agents, edited by people and curation
│   └── .inbox/                     # hidden: material waiting to be merged
│       └── q3-review.md            # an upload's extracted text, deleted once merged
└── coffer/
    ├── README.md
    └── release-process.md
```

- `~/.coffer/knowledge/` is the root; `$COFFER_KNOWLEDGE_ROOT` overrides it for
  tests. Path construction lives in exactly one module,
  `infrastructure/knowledge/paths.py` (FR-006), which also owns the inbox name.
- A **collection** is a top-level subdirectory *and* one `knowledge` Resource.
  It is created deliberately, as one directory, and nothing provisions one from
  a read, a write, or an agent's working directory (FR-008). There is no
  `global`, no `project-<ULID>`, no git-root resolution and no
  scope-to-project-root table (FR-009).
- **A collection is one tree of documents**, co-written by people and the
  curation pass (FR-001). There is no directory that means "who may write
  here": a person edits any document in their own editor, an agent may edit one
  with its own file tools, and curation rewrites documents as it merges new
  material. The nesting is free and the system neither requires nor creates one
  — whoever files a document chooses where (FR-004).
- **Dot-prefixed entries are invisible** (FR-005), and Coffer writes exactly one
  of its own: `.inbox/`, where submitted material waits until a pass folds it
  in, and from which each item is deleted the moment it has been. It is hidden
  because it is not knowledge yet — no listing, catalogue or count of documents
  includes it; the collection list reports it separately as `pending_count`.
  `.history/` and `.raw/` stay gone. Hidden segments are still *refused* by the
  path guard rather than merely skipped, so neither the inbox nor anything the
  user hides for their own reasons is addressable through a surface.

### `README.md`

A collection describes itself in a `README.md` at its own root, which is not a
document: it is never curated, listed as content or counted (FR-007). Its first
paragraph is the collection's one-line description everywhere one is shown
(FR-011), read off disk on every listing so it cannot drift from what the person
browsing the folder reads. `POST /api/v1/knowledge/collections` writes one when
given a `description`.

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
coffer_curated_at: '2026-09-23T04:18:33Z'
---

Login state is owned by `account.session`.
```

| Key | Type | Notes |
| --- | --- | --- |
| `title` | `str` | Human-readable. Also the source of the file name on creation. |
| `description` | `str` | **Required** (FR-003). It is what curation reads first when deciding where material belongs, and what an agent chooses by in the catalogue. |
| `actor` | `agent` \| `user` | Who last wrote it. From the `X-Coffer-Actor` header on a submission, or the tool's own actor. |
| `created_at` | ISO-8601 `str` | Preserved across a rewrite, so a document keeps its own history even though nothing but the file records it. |
| `updated_at` | ISO-8601 `str` | Set on every write Coffer makes. |
| `coffer_curated_at` | ISO-8601 `str` | Written by Coffer (FR-003, FR-028): when curation last had this document in front of it. Absent on a document curation has never seen. |

These are the keys **Coffer writes**, not the only keys a document may carry.
A person who adds `tags:` or `reviewed_by:` in their own editor keeps it: every
rewrite Coffer makes — a pass's `write_document`, the stamp `mark_curated`
adds — renders the known keys in a fixed order and then everything else
unharmed, values carried through as parsed rather than stringified. There is
still no `id` — the path is the identity (FR-002) — and none of the keys that
described retired machinery (`lane`, `source_path`, `source_sha256`,
`source_format`, `source_mode`, `converter`, `embed_status`, `content_sha256`,
`coffer_ingested_at`).

Frontmatter parsing degrades rather than raising: a file with no fence, or with
malformed YAML inside one, yields empty frontmatter and its body, so one
hand-edited file with a stray colon cannot break a whole collection walk.

### What the sweep owes a collection, and why there is no state file

`curate.pending_items` answers it from the disk, in this order (FR-022):

1. **Inbox material**, oldest first by modification time (`fs.inbox_items`).
   Material first, because until it is merged it is knowledge no agent can read.
2. **Edited documents** (`fs.edited_documents`): every visible Markdown document
   whose modification time is newer than its own `coffer_curated_at` — or that
   has no stamp at all, like a document a person wrote from scratch. An edit in
   any editor moves the mtime past the stamp, and the next sweep hands the
   document to a pass, which carries the edit into the rest of the collection
   and never reverts it (FR-026). Nothing has to be told.

Two consequences keep this honest:

- **Curation's own output does not come back.** A pass's `write_document` writes
  with `curated=True`, which stamps the document; and because writing a stamp is
  itself a modification, `fs.mark_curated` and the curated write both set the
  file's mtime back to the stamp they just wrote. Without that, every document
  would be pending on every sweep forever.
- **An item is settled only after its pass completes** (FR-028). Material is
  deleted from the inbox (`fs.discard_material`) and an edited document stamped
  (`fs.mark_curated`) after the loop returns; a pass that raises leaves both as
  they were, so a later sweep retries rather than losing what one half-ran over.

With no internal model configured there is nothing to merge with, so material
does not wait (FR-029): `KnowledgeService.submit` promotes it on the spot
(`fs.promote` — a document of its own at the collection root, stamped curated),
and a pass run with no model promotes whatever is still in the inbox and reports
`no_model` with the `promoted` paths.

### Naming

A file's name is a readable slug of its title, not an opaque id, because with no
index mapping an id to a title the name is what a human reads in Finder and what
an agent sees in the catalogue (FR-002). `infrastructure/knowledge/naming.py`
owns it:

- NFKC-normalize, lowercase, collapse whitespace / `_` / `/` / `\` to `-`, drop
  everything that is not `A-Za-z0-9-` or CJK, collapse runs of `-`, trim to 80
  characters. **CJK is kept, never transliterated** — a romanized name would be
  one neither party recognises. An empty result becomes `untitled`.
- `unique_name` appends `-2`, `-3`, … only when `<slug>.md` is already taken.
  Inbox items are named the same way and never written onto an existing item:
  two submissions of the same title are two pieces of material.

### The traversal guard

Every segment that becomes a path component passes `paths.check_segment`
(FR-006): non-empty, not all dots, not dot-prefixed, and matching
`[A-Za-z0-9._\- ]` or CJK. A path that must name a document additionally passes
`paths.require_document`, which refuses the collection itself and its
`README.md`; the inbox is out of reach already, because it is dot-prefixed. A
violation is `UnsafeKnowledgePath` (`KNOWLEDGE_PATH_UNSAFE`, HTTP 400). The
resolved path is checked against the root too, on its nearest existing
ancestor, so a symlink inside the root cannot carry a read or a write out of it.
Writes are atomic — same-directory temp file opened `O_NOFOLLOW | O_EXCL`, then
`replace`.

## Value objects (`backend/coffer/domain/knowledge/entry.py`)

These are the **shape of an answer, never the shape of a row**: a level is
produced by walking the directory and reading frontmatter at call time, so none
of them is persisted and none of them can be stale.

| Type | Fields | What it is |
| --- | --- | --- |
| `CollectionEntry` | `uid`, `name`, `description`, `document_count`, `pending_count` | One collection. `document_count` is what an agent can read today; `pending_count` is material still in the inbox — counted apart because it is exactly what an agent cannot see yet. |
| `DirectoryEntry` | `path`, `name`, `file_count` | A subdirectory at the level being listed. `path` is relative to the root — pass it back to descend. |
| `FileEntry` | `path`, `title`, `description`, `actor`, `updated_at` | One file as a listing or a catalogue shows it: enough to judge relevance without reading the body. |
| `CatalogueLevel` | `path`, `directories`, `files` | **One level of one collection**, never the whole tree. |
| `KnowledgeFile` | the frontmatter fields + `path`, `body`, `file_path`, `folder_path`, `curated_at` | A file in full. The two absolute paths are what the UI needs to offer open-in-editor and reveal-in-file-manager (FR-041); `curated_at` is empty for a document curation has never seen. |
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
(FR-023), and it is reachable by nothing outside the process. It never searches
the inbox — ripgrep skips hidden directories, and material there is not a
document yet. There is no `SearchHit`, `SearchOutcome` or `SearchService` any
more.

`Conversion` (`domain/knowledge/converter.py`) is what a converter returns for an
uploaded document: the `markdown`, a `title` (the document's first H1, falling
back to its file name, FR-017), and which `converter` ran — reported on the
upload response and written nowhere on disk.

The HTTP wire models in `surfaces/http/knowledge/schemas.py` mirror the domain
types and add the shapes that describe an answer no domain type does:
`CollectionCreate`; `MaterialIn` (`collection`, `title`, `description`, `body`)
and `SubmissionOut` (`status` `pending` | `written`, `collection`, `title`, and
`path` when written); `CurationRequest` (an optional `document`) and
`CurationOut` (`status`, `collection`, `item`, `model`, `written`, `retired`,
`refused`, `documents_before`, `documents_after`, `limit`, `promoted`); and
`IngestedDocumentOut` (`path` or null, `title`, `description`, `converter`,
`pending`). There is no write-a-document model: a person edits a document in
their own editor, and every other entrance submits material. The mirroring is
deliberate rather than redundant: the domain types describe what is on disk and
the wire models describe what a client is promised, so removing a field from the
wire never means hiding one from the layer.

## The `knowledge` Resource

`make_knowledge_kind()` leaves `supports_scope` at the Kind default of `False`
and declares `generic_create_allowed=False`, because a collection is a directory
as much as a row and the generic `POST /resources` path would create the row with
no folder behind it. Being a Resource buys the collection a lifecycle, an audit
trail and one switch — not a reach.

**`enabled` is that switch, and it bites in two places.** At **delivery**: a
disabled collection's name, description, catalogue and paths appear nowhere in
the rendered `coffer-guide` skill every agent reads, while an enabled one appears
in all of it. And at
`coffer__write`, which refuses a write naming a collection that does not exist or
is disabled, answering with the ones that are available.

The per-agent reach that used to sit here is withdrawn (FR-010). It was never
set — every collection's scope was null in the live vault — and it could not have
withheld anything it was asked to: the skill it narrows hands the agent the
absolute knowledge root and tells it to grep. `PUT .../scope` on this kind is now
refused with `SCOPE_INVALID`, and migration `0088` cleared the column for every
`knowledge` row.

`KnowledgeConfig` (`domain/knowledge/config.py`) is **empty and forbids unknown
keys**. A collection has no settings at all: no retrieval modes, no chunk size,
no entry-length cap, no embedding fields, no auto-update flag, no display label
(FR-046). Anything that used to be configured per scope was configuring
machinery that no longer exists.

What the layer serves is **files on disk**, and `enabled` gates their
**delivery** rather than their readability (FR-012). An agent that also holds
shell or file-read tools can read anything under `~/.coffer/knowledge/`, so a
collection left out of a skill is one no agent is told about, not one no process
can open — and the system says so rather than implying an isolation it does not
provide. The per-agent reach this row used to carry is withdrawn for the same
reason taken one step further: an allow-list that withholds a path from a
reader already holding the root withheld nothing at all (FR-010).

## Errors

The failure modes are a directory's, plus curation's two, plus the ones its one
external binary and its converter library have. `domain/knowledge/errors.py`
holds the first group:

| Class | Code | HTTP |
| --- | --- | --- |
| `CollectionNotFound` | `KNOWLEDGE_COLLECTION_NOT_FOUND` | 404 |
| `CollectionExists` | `KNOWLEDGE_COLLECTION_EXISTS` | 409 |
| `KnowledgeFileNotFound` | `KNOWLEDGE_FILE_NOT_FOUND` | 404 |
| `UnsafeKnowledgePath` | `KNOWLEDGE_PATH_UNSAFE` | 400 |
| `UploadTooLarge` | `KNOWLEDGE_UPLOAD_TOO_LARGE` | 413 |
| `TopicReferencesFile` | `KNOWLEDGE_TOPIC_REFERENCES_FILE` | 400 |
| `CurationBoundExceeded` | `KNOWLEDGE_CURATION_BOUND` | 400 |
| `KnowledgeError` (base) | `KNOWLEDGE_ERROR` | 400 |

A collection an agent is not authorized for answers
`KNOWLEDGE_COLLECTION_NOT_FOUND`, not a 403: telling an unauthorized caller that
the name exists is itself a disclosure, so "not visible to you" and "not there"
are the same answer.

`UnsafeKnowledgePath` carries the document rule as well as the traversal one,
for the same reason both belong to path construction: a delete aimed at a
collection's `README.md` and a path aimed at `../etc/passwd` are both a caller
asking for something it may not reach, and a single guard is one that cannot be
forgotten by one surface.

The two curation errors are refusals of a *model's* write rather than a user's,
which is why they exist as codes at all: a pass reports what it was stopped from
doing. `TopicReferencesFile` (the name predates the one-tree layout; the code is
unchanged) is FR-027 enforced at `write_document` — a document naming another
knowledge file is the mechanism that produced 343 broken links, so it is refused
rather than discouraged in a prompt. `CurationBoundExceeded` is FR-025's
eight-write ceiling, which is what keeps one item from triggering a corpus-wide
rewrite however confident the model is.

`domain/kb_errors.py` holds two more, re-exported through `domain/errors.py`:

| Class | Code | HTTP | When |
| --- | --- | --- | --- |
| `GrepPatternInvalid` | `GREP_PATTERN_INVALID` | 400 | the matcher rejected the pattern (ripgrep exit 2, or a regex the fallback cannot compile). Now reachable only through candidate selection, where without it an `rg` failure would masquerade as "no candidates" |
| `EngineUnavailable` | `ENGINE_UNAVAILABLE` | 503 | a binary or converter library the call needs is absent — `ripgrep` with no Python fallback available, or one of MarkItDown's format backends. The daemon stays up and the caller gets a per-format answer |

And the two ingest refusals are not `CofferError`s at all. `UnsupportedDocument`
and `EmptyConversion` (`domain/knowledge/converter.py`) carry the *rejected type*
rather than a code, and the upload route turns both into `INGEST_REJECTED` / 400,
distinguished by `details.reason` — `unsupported_type`, or `scanned_pdf` /
`empty_conversion` — so a surface can name the format it will not take and, for
a PDF with no text layer, say something actionable about why. Either way nothing
is submitted: no inbox item, no document (FR-019).

A pass requested while one is already in flight over the same collection answers
`UPKEEP_ALREADY_RUNNING` / 409 (FR-030). It is refused rather than queued because
the caller asked to *start* a pass, and no pass is going to start.

## Audit and invocation records

Unchanged in shape and still database-backed, because they are not knowledge —
they are Coffer's own bookkeeping. `coffer__write` records one `mcp_invocations`
row (tool, actor, duration, outcome — never arguments, never content) and every
submission — from the tool, the CLI, the REST route, an upload or a channel —
records one `KNOWLEDGE_WRITTEN` `audit_log` event naming the caller, with the
document path when it was promoted and `pending` when it waits (FR-014); a
delete records `KNOWLEDGE_DELETED`. A completed curation pass records
`KNOWLEDGE_CURATED` with the item, the model and its counts.

Losing the read tools lost the invocation record for reads, and with it the
ability to answer "is this layer being used" from `mcp_invocations`. That is a
deliberate cost: the replacement measurement is the agents' own transcripts,
which Coffer already reads for other reasons and which are retroactive, so
nothing is lost by not having built it yet.

## The installation-wide curation setting

The one setting the layer has is not the layer's. Three columns on the singleton
`internal_engine_config` row carry it (FR-032):

| column | notes |
| --- | --- |
| `auto_curate_enabled` | the switch, **default true** — curation is what merges new material into the documents and carries a person's edit through the rest of the collection, so an installation where it never runs has material waiting in the inbox forever |
| `curate_interval_s` | the timer; null means the built-in cadence (60 s) |
| `curate_owner_machine_id` | the one machine allowed to run the sweep. Null means a single-machine vault, where "here" is the only answer there is |

The switch and the owner are read **together, on every sweep**, so the setting
means *on, here* rather than merely *on*. All three govern only the background
worker, which re-reads them every tick so a change needs no daemon restart; the
manual trigger consults none of them. A sweep runs at most five passes per
collection, one item each, and stops a collection's sweep early on `no_model` or
`failed`. The whole row is synced state, so every machine agrees on who the
owner is.

## What migration 0101 does

`20260923_0101_knowledge_one_tree.py`, with the on-disk rewrite frozen beside it
in `migrations/knowledge_tree_0101.py` (FR-042, FR-043). It turns 0085's two
lanes into one tree by **re-distilling everything**: nothing in the old tree is
renamed into the new one.

- **The backup comes first.** Before a single file moves, the whole knowledge
  root is copied to a sibling directory, `<root>.pre-0101.bak`, and the path is
  logged. A second run reuses that backup rather than photographing a tree this
  pass has already rewritten.
- **Every Markdown file in both lanes becomes inbox material.** `topics/` first,
  because those documents are already organised by subject and the first passes
  lay down a structure; then `sources/`, in the order they were last modified.
  Each file lands in the collection's `.inbox/` under a flat name that still
  says where it came from (`topics-account-login-sessions.md`,
  `sources-q3-review.md`), suffixed on a collision, and its mtime is set to its
  place in the queue — one second apart, ending now — so the sweep drains it in
  exactly that order.
- **What is not Markdown is dropped.** An upload's original bytes lived beside
  their extracted text in `sources/`; the new layer keeps knowledge, not the
  documents it arrived in, so those files survive only in the backup.
- **Both lanes are removed.** `README.md` stays at the collection root.

Nothing in the database changes: the curation settings 0085 seeded — on, owned
by the machine that migrated — are the ones the sweep that drains the inbox
reads. `downgrade` changes nothing in the database either and does not put the
tree back; the backup is the way back, by hand. The pass is idempotent — a
collection with neither lane is walked past — and a vault with no internal model
still ends up readable, because the sweep's no-model pass promotes each item to
a document as it stands.

## What migration 0085 did

*History.* 0085 introduced the `sources/` ÷ `topics/` lanes that 0101 above
retired; its rewrite is described here because 0101 runs on top of what it left.

`20260917_0085_knowledge_two_lanes.py`, with the on-disk rewrite frozen beside it
in `migrations/knowledge_tree_0085.py` (FR-042, FR-043).

**Order.** The rewrite runs FIRST, before any DDL. It is the only step that
touches writing the user cannot get back, so running it first means a failure
anywhere in the revision leaves the database exactly as it was. **And the backup
comes before the rewrite**: the whole knowledge root is copied to a sibling
directory named after the revision and the path is logged, before a single file
moves. An existing backup is kept rather than refreshed — by the time a second
run happens, refreshing would replace the only pre-migration copy with a tree
this pass has already rewritten.

The rewrite is not a classification problem. **Everything that exists today is a
source**: nothing in the old tree was derived, because there was no pass to
derive it. So every content file moves into `sources/` with its nesting intact,
and `topics/` is created empty. `.raw/` originals move into `sources/` as
ordinary visible files beside the Markdown extracted from them, suffixed rather
than overwritten on a name collision; `.history/` is deleted outright, with the
reason it existed. `README.md` stays at the collection root. The whole rewrite is
idempotent — a collection already in the new shape is walked past, so a second
upgrade neither backs up again nor moves anything.

Then the DDL and the data fixes, each guarded so a database missing a column, a
table or the row still upgrades:

- `auto_tidy_enabled` / `tidy_owner_machine_id` / `tidy_interval_s` are renamed
  to `auto_curate_enabled` / `curate_owner_machine_id` / `curate_interval_s`.
  SQLite cannot rename a column in place, so all three go through one
  `batch_alter_table` rebuild rather than three.
- The switch flips **on** and the owner is seeded with this machine, read from
  `daemon-config.json` beside the database (FR-044). Without it the upgrade would
  take the corpus away and give nothing back. The owner is only written when it
  is currently NULL: a user who already chose a machine chose it for the same
  corpus.
- `knowledge_tidied` audit rows are **rewritten** to `knowledge_curated`, not
  purged. Unlike the events revisions 0069 and 0077 dropped, this one still has a
  writer — the pass was renamed, not retired — so the history stays readable
  under the name the code now uses. The value is inlined rather than imported
  from `AuditEventType`: a migration must mean the same thing forever.
- The shared `coffer-knowledge` skill Resource, its agent bindings and its master
  folder all go (FR-042). At that revision the skill was generated per agent, and
  a registered shared master left behind would have kept being delivered beside
  the generated copy — the same layer described twice, one of the descriptions
  wrong.
- Revision `0089` finishes that retirement from the other end. The catalogue now
  rides Coffer's own `coffer-guide` skill, which *is* a registered Resource with
  a master folder, so what has to go is the per-agent delivery `0085` left in
  place: the migration sweeps each registered agent's resolved skill directory
  and removes `skills/coffer-knowledge` when it is a symlink or a directory
  holding the `SKILL.md`/`README.md` pair that delivery always wrote, and leaves
  anything else at that name alone (FR-034). Nothing else can clean it up —
  there was never a binding to reclaim from — and a manual that will never be
  rewritten again is worse than none.

`downgrade` raises, and **no compatibility shim is left behind anywhere**:
nothing reads the old column names, the old audit value or the old tree shape
after this.

### What 0066 left behind

`20260912_0066_knowledge_is_plain_files.py` is the revision 0085 rewrites on top
of, and its helpers stay frozen in the tree because a migration describes one
moment in history. It turned `<scope>/{notes,docs}/<ULID>.md` into
`<collection>/<slug-of-title>.md` — reading `documents.title` before dropping the
eleven tables that held it — and produced the flat collection with a hidden
`.raw/` and `.history/` beside it that 0085 splits into lanes. Its own `.raw/`
handling is not 0085's: the lane it deleted held copies of files that had never
been converted at all.
