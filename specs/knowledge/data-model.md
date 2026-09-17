# Data Model — Knowledge Layer

The layer's state is a directory. This document describes what is on disk —
the two lanes, the frontmatter contract, the naming rule — plus the one database
row a collection still occupies and the in-memory value objects the surfaces
answer with. Authority is [`spec.md`](./spec.md) and
[Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md).

## There is no schema

**The knowledge layer owns no table** (FR-046, SC-004). Markdown files are the
whole of it, and nothing derives anything from them into a database: no
`documents` row, no chunks, no full-text index, no embeddings — therefore no
content hash to compare, no reindex, and no reconciliation of any kind (FR-001).

`topics/` is derived, but it is derived into the same directory as everything
else, and its provenance is a frontmatter key on the source rather than a row.
That is why there is no curation state table and no scan journal: the one thing
Coffer needs to remember about a source is when it last consumed it, and the
honest place for that is the file itself, where the answer cannot disagree with
the disk.

The only database presence a collection has is the same one every Resource has:
a row in the kind-agnostic `resources` table. That row carries the collection's
name, its `enabled` flag and its per-agent `scope`, and nothing about its
contents.

## On-disk layout

```text
~/.coffer/knowledge/
├── shopee/                         # a collection = a top-level folder = one Resource
│   ├── README.md                   # first paragraph = the collection's description
│   ├── sources/                    # what people and agents contribute
│   │   ├── account/                # the person's own filing; the system assigns it no meaning
│   │   │   └── session-ownership.md
│   │   ├── q3-review.pdf           # an upload's own bytes, visible, beside…
│   │   └── q3-review.md            # …the Markdown extracted from it
│   └── topics/                     # what the curation pass derives, and all an agent reads
│       ├── account/                # curation's filing, not the person's
│       │   └── login-sessions.md
│       └── gateway-routing.md
└── coffer/
    ├── README.md
    ├── sources/
    └── topics/
```

- `~/.coffer/knowledge/` is the root; `$COFFER_KNOWLEDGE_ROOT` overrides it for
  tests. Path construction lives in exactly one module,
  `infrastructure/knowledge/paths.py` (FR-006), which also owns the lane names.
- A **collection** is a top-level subdirectory *and* one `knowledge` Resource.
  It is created deliberately, with both lanes, and nothing provisions one from a
  read, a write, or an agent's working directory (FR-008). There is no `global`,
  no `project-<ULID>`, no git-root resolution and no scope-to-project-root table
  (FR-009).
- **The two lanes are directories because they mean *who may write here*** —
  the one property a key inside a file cannot carry. A person, an upload and
  `coffer__write` write `sources/`; the curation pass writes `topics/` and
  nothing else does (FR-013, FR-021). Every path resolution asserts its lane,
  so the rule is enforced where it cannot be forgotten rather than in each
  caller.
- Below a lane the nesting is free, and the system neither requires nor creates
  one: under `sources/` it is the person's, under `topics/` it is curation's
  (FR-004).
- **Dot-prefixed entries are invisible**, and Coffer now writes none of its own
  (FR-005). `.history/` is gone because a topic document is no longer the only
  copy of what it says, and `.raw/` is gone because the only thing hiding an
  uploaded original bought was keeping it out of a retrieval index that no
  longer exists. Hidden segments are still *refused* by the path guard rather
  than merely skipped, so nothing the user hides for their own reasons becomes
  addressable through a surface.

### `README.md`

A collection describes itself in a `README.md` at its own root, outside both
lanes and curated by nothing (FR-007). Its first paragraph is the collection's
one-line description everywhere one is shown (FR-011), read off disk on every
listing so it cannot drift from what the person browsing the folder reads.
`POST /api/v1/knowledge/collections` writes one when given a `description`.

That paragraph does more work than it used to: it is also what the delivered
skill's frontmatter description draws on, which is the only part of this layer
always in a model's context. A collection that fails to describe itself is a
collection an agent never recognises.

## The file

Every Markdown file in either lane carries a `---`-fenced YAML frontmatter
block, written and read only by `infrastructure/knowledge/frontmatter.py` (the
one place PyYAML lives). A non-Markdown file in `sources/` — an uploaded
original — carries none; it is bytes, and the Markdown extracted from it carries
the metadata.

```markdown
---
title: Session ownership
description: Which service owns a login session, and what reads it.
actor: agent
created_at: '2026-09-12T04:18:33Z'
updated_at: '2026-09-12T04:18:33Z'
coffer_ingested_at: '2026-09-17T09:02:11Z'
---

Login state is owned by `account.session`.
```

| Key | Type | Notes |
| --- | --- | --- |
| `title` | `str` | Human-readable. Also the source of the file name on creation. |
| `description` | `str` | **Required** (FR-003). It is what curation reads first when deciding where material belongs, and what an agent chooses by in the catalogue. |
| `actor` | `agent` \| `user` | Who last wrote it. From the `X-Coffer-Actor` header on the write, or the tool's own actor. |
| `created_at` | ISO-8601 `str` | Preserved across a replace, so a file keeps its own history even though nothing but the file records it. |
| `updated_at` | ISO-8601 `str` | Set on every write. |
| `coffer_ingested_at` | ISO-8601 `str` | **Sources only** (FR-003, FR-028). Coffer's watermark: when curation last consumed this file. Nothing else reads it and no surface shows it. |

**And nothing else** (FR-003). There is no `id` — the path is the identity
(FR-002) — and no `lane`, `source_path`, `source_sha256`, `source_format`,
`source_mode`, `converter`, `embed_status` or `content_sha256`: each of those
described machinery that no longer exists. The lane in particular is not a key,
because a key cannot say who may write a file.

Frontmatter parsing degrades rather than raising: a file with no fence, or with
malformed YAML inside one, yields empty frontmatter and its body, so one
hand-edited file with a stray colon cannot break a whole lane walk.

### The watermark, and why there is no state file

`coffer_ingested_at` is written by `fs.mark_ingested` after a pass completes,
and the sweep finds work by comparing it with the file's own modification time
(FR-022). Two consequences are worth stating because they are the reason this
design has no table:

- **A person's edit is the trigger.** Touching a source in any editor moves its
  mtime past its stamp, and the next sweep picks it up. Nothing has to be told.
- **The stamping cannot re-trigger itself.** Writing the stamp is a modification,
  so `mark_ingested` sets the file's mtime back to the stamp it just wrote —
  without that, every source would come back pending on every sweep forever.

A pass that raises leaves the stamp unset, so the material is curated later
rather than lost to a pass that half-ran.

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

An uploaded original goes through the same slug on its stem and keeps its own
extension, with the same numeric suffix on a collision: two files that happen to
share a name are two files, and one is never overwritten by the other.

### The traversal guard

Every segment that becomes a path component passes `paths.check_segment`
(FR-006): non-empty, not all dots, not dot-prefixed, and matching
`[A-Za-z0-9._\- ]` or CJK. A resolution additionally asserts its lane —
`require_lane` refuses a knowledge path that is in neither, and a caller that
knows which lane it is entitled to names it. A violation is
`UnsafeKnowledgePath` (`KNOWLEDGE_PATH_UNSAFE`, HTTP 400). Writes are atomic —
same-directory temp file, then `replace`.

## Value objects (`backend/coffer/domain/knowledge/entry.py`)

These are the **shape of an answer, never the shape of a row**: a level is
produced by walking the directory and reading frontmatter at call time, so none
of them is persisted and none of them can be stale.

| Type | Fields | What it is |
| --- | --- | --- |
| `CollectionEntry` | `name`, `description`, `source_count`, `topic_count` | One collection. The two lanes are counted apart because they answer different questions — how much material a person has contributed, and how much of it an agent can currently read. A collection with sources and no topics has not been curated yet, and no single number could say that. |
| `DirectoryEntry` | `path`, `name`, `file_count` | A subdirectory at the level being listed. `path` is relative to the root — pass it back to descend. |
| `FileEntry` | `path`, `title`, `description`, `actor`, `updated_at` | One file as a listing or a catalogue shows it: enough to judge relevance without reading the body. |
| `CatalogueLevel` | `path`, `directories`, `files` | **One level of one lane**, never the whole tree. |
| `KnowledgeFile` | the frontmatter fields + `path`, `body`, `file_path`, `folder_path`, `ingested_at` | A file in full. The two absolute paths are what the UI needs to offer open-in-editor and reveal-in-file-manager (FR-041); `ingested_at` is empty for a topic document, which has no watermark. |
| `GrepMatch` | `path`, `line_number`, `line` | One literal hit. |
| `GrepOutcome` | `matches`, `truncated` | A bounded run of them. |

Constants: `ACTOR_AGENT = "agent"`, `ACTOR_USER = "user"`.

The last two survive the removal of `coffer__grep` because ripgrep survives it
as an **internal** mechanism: `KnowledgeService.match_topics` is how a curation
pass finds which existing documents a new source might belong to (FR-023), and
it is reachable by nothing outside the process. There is no `SearchHit`,
`SearchOutcome` or `SearchService` any more — the module that held them is
deleted with the tool it served.

`Conversion` (`domain/knowledge/converter.py`) is what a converter returns for an
uploaded document: the `markdown`, a `title` (the document's first H1, falling
back to its file name, FR-017), and which `converter` ran — carried so a caller
knows whose output it is looking at, reported on the upload response and written
nowhere on disk.

The HTTP wire models in `surfaces/http/knowledge/schemas.py` mirror the domain
types one for one and add the shapes that describe an answer no domain type does:
`CollectionCreate`, `FileWrite` (which names exactly one of `path` or
`collection` and never a lane), `CurationRequest` / `CurationOut` (a pass's
status and its counts), and `IngestedDocumentOut` (the extracted file's path,
title, description, which converter produced it, and the original's path in
`sources/`). The mirroring is deliberate rather than redundant: the domain types
describe what is on disk and the wire models describe what a client is promised,
so removing a field from the wire never means hiding one from the layer.

## The `knowledge` Resource

`make_knowledge_kind()` declares `supports_scope=True` — per-agent authorization
is the whole reason a collection is a Resource (FR-010) — and
`generic_create_allowed=False`, because a collection is a directory as much as a
row and the generic `POST /resources` path would create the row with no folder
behind it.

**The scope no longer gates a retrieval tool, because there is none.** It bites
in two other places. At **delivery**: the skill rendered for an agent names only
the collections activated for it, so an unauthorized collection's name,
description, catalogue and paths never appear in that agent's file at all. And at
`coffer__write`, which refuses a write into a collection the calling agent is not
activated for, using the handshake identity the gateway writes in.

`KnowledgeConfig` (`domain/knowledge/config.py`) is **empty and forbids unknown
keys**. A collection has no settings at all: no retrieval modes, no chunk size,
no entry-length cap, no embedding fields, no auto-update flag, no display label
(FR-046). Anything that used to be configured per scope was configuring
machinery that no longer exists.

Enforcement is **non-disclosure, not access control**. An agent that also holds
shell or file-read tools can read anything under `~/.coffer/knowledge/`: the
scope prevents mistaken retrieval, not deliberate access, and the system says so
rather than implying an isolation it does not provide (FR-012). Moving the
enforcement point from the tool to the skill changed nothing about that — the
previous point was equally bypassable.

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

`UnsafeKnowledgePath` carries the lane rule as well as the traversal one, for the
same reason both belong to path construction: a write aimed at `topics/` and a
path aimed at `../etc/passwd` are both a caller asking for somewhere it may not
go, and a single guard is one that cannot be forgotten by one surface.

The two curation errors are refusals of a *model's* write rather than a user's,
which is why they exist as codes at all: a pass reports what it was stopped from
doing. `TopicReferencesFile` is FR-027 enforced at `write_topic` — a topic naming
another knowledge file is the mechanism that produced 343 broken links, so it is
refused rather than discouraged in a prompt. `CurationBoundExceeded` is FR-025's
eight-write ceiling, which is what keeps one source from triggering a corpus-wide
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
a PDF with no text layer, say something actionable about why.

A pass requested while one is already in flight over the same collection answers
`UPKEEP_ALREADY_RUNNING` / 409 (FR-030). It is refused rather than queued because
the caller asked to *start* a pass, and no pass is going to start.

## Audit and invocation records

Unchanged in shape and still database-backed, because they are not knowledge —
they are Coffer's own bookkeeping. `coffer__write` records one `mcp_invocations`
row (tool, actor, duration, outcome — never arguments, never content) and one
`audit_log` event naming the calling agent (FR-014); a delete records one too.
A completed curation pass records `KNOWLEDGE_CURATED`.

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
| `auto_curate_enabled` | the switch, **default true** — curation is the only path from a source to something an agent can read, so an installation where it never runs has an empty `topics/` lane forever |
| `curate_interval_s` | the timer; null means the built-in cadence |
| `curate_owner_machine_id` | the one machine allowed to run the sweep. Null means a single-machine vault, where "here" is the only answer there is |

The default inverts tidy's, and the inversion is the point rather than a change
of mind about unattended rewriters. Tidy rewrote the user's own files, so it was
something an operator should switch on deliberately; curation cannot touch them
at all, and the thing it rewrites is rebuildable from what it may not touch.

The switch and the owner are read **together, on every sweep**, so the setting
means *on, here* rather than merely *on*. All three govern only the background
worker, which re-reads them every tick so a change needs no daemon restart; the
manual trigger consults none of them. The whole row is synced state, so every
machine agrees on who the owner is.

## What migration 0085 does

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
  folder all go (FR-042). The skill is generated per agent now, and a registered
  shared master left behind would keep being delivered beside the generated
  copy — the same layer described twice, one of the descriptions wrong.

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
