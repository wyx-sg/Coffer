# Data Model — Knowledge Layer

The layer's state is a directory. This document describes what is on disk —
one wiki per collection, its kept `sources/`, edited `pages/` and the
`assets/` an upload's pictures land in, the hidden `.inbox/` drop zone, the
frontmatter contract, the naming rule — plus the one resource file a
collection has, the machine-local store of uploaded originals, and the
in-memory value objects the surfaces answer with. Authority is [`spec.md`](spec.md),
[Knowledge Is Plain Files](../../../docs/decisions/knowledge-is-plain-files.md) and
[Knowledge Is a Wiki of Pages Compiled From Kept Sources](../../../docs/decisions/knowledge-is-a-wiki-of-pages-compiled-from-kept-sources.md) and
[Knowledge Sources Keep Their Images; Originals Stay on This Mac](../../../docs/decisions/knowledge-sources-keep-their-images-and-originals-stay-on-this-mac.md).

## There is no schema

**The knowledge layer owns no table** (see "Add no table and no directory
outside the knowledge root"). Markdown files are the whole of it, and nothing
derives anything from them into a database: no `documents` row, no chunks, no
full-text index, no embeddings — therefore no content hash to compare, no
reindex, and no reconciliation of any kind (see "Store each collection as one
tree of Markdown files").

The sweep needs no record either. What it adopts is a file in a collection's
hidden `.inbox/`; what it files is a Markdown document outside `pages/`,
`sources/` and `assets/`; what it commits is whatever differs on disk from the vault's
`HEAD`. Nothing remembers which sources were integrated: a source waits while
no page cites it, which is read off the pages every time (see "Derive which
sources wait from the pages that cite them"). Judgement over pages is the
agent's, done through its own file tools (see "Teach writing and tidying in the
guide").

Beyond its tree, a collection is one resource file,
`vault/resources/knowledge/<name>.json` (spec resource-framework), carrying the
collection's name and nothing about its contents. There is no per-agent reach
and no `enabled` switch in play for this kind (see "Serve every collection to
every agent"): the kind is non-toggleable, and it is always enabled.

A **linked folder** (see "Link a folder the person keeps themselves") has no
tree under the knowledge root at all. It is one resource file whose config is
`{"folder": "<absolute path>"}`, filed in the machine-local class at
`local/resources/knowledge/<name>.json` with the home written as `${HOME}`, and
never in the vault (ADR linked-knowledge-folders-are-read-only-and-machine-local).
The folder it names is the person's: Coffer reads it in place and writes
nothing into it, so it has no `sources/`, `pages/`, `.inbox/` or history of
Coffer's (see "Leave a linked folder to its own tools").

## On-disk layout

```text
~/.coffer/vault/knowledge/
├── shopee/                         # a collection = a top-level folder = one Resource
│   ├── README.md                   # the schema: verify_after_days, types_without_sources, the description, page types, rules; listed, not a page
│   ├── index.md                    # the collection's own file (navigation): listed, links checked, never a page; never moved
│   ├── sources/                    # what arrived, kept as Markdown; never edited
│   │   └── q3-review.md            # a source: converted Markdown + frontmatter
│   ├── assets/                     # pictures taken out of uploads; visible, so they sync
│   │   └── q3-review-1a2b3c4d/     # one folder per upload: <title-slug>-<first 8 hex of its sha256>
│   │       ├── image-1.png         # linked from the source as ../assets/q3-review-1a2b3c4d/image-1.png
│   │       └── image-2.jpg
│   │   └── confluence-42-v7/       # one folder per imported Confluence page and version
│   │       └── arch.png            # an attachment the page shows
│   ├── pages/                      # the wiki: read by agents, edited by people and agents
│   │   ├── account/                # nesting chosen by whoever files a page
│   │   │   └── login-sessions.md
│   │   └── gateway-routing.md
│   └── .inbox/                     # hidden drop zone: the next sweep adopts it into sources/
│       └── notes.md
└── coffer/
    ├── README.md
    └── pages/
        └── release-process.md
```

- `~/.coffer/vault/knowledge/` is the root, inside the vault repository, so a
  collection's history is the vault's history under `knowledge/`. There is no
  override: the root is resolved from `HOME` at every call, because a tree
  outside the vault would be a tree its history cannot see. Path construction
  lives in exactly one module,
  `infrastructure/knowledge/paths.py` (see "Guard every path through one
  module"), which also owns the inbox name the sweep reads.
- A **collection** is a top-level subdirectory *and* one `knowledge` Resource.
  It is created deliberately, as one directory, and nothing provisions one from
  a read, a write, or an agent's working directory (see "Create collections only
  deliberately"). There is no `global`, no `project-<ULID>`, no git-root
  resolution and no scope-to-project-root table (see "Derive no boundary from
  the working directory").
- **A collection is a wiki**: `sources/` keeps what arrived and `pages/`
  holds what people and agents write from it (see "Keep sources and pages apart
  in each collection"). `paths.kind_of` names a Markdown file under `pages/` a
  **page**, one under `sources/` a **source**, and anything else a plain
  **file**, listed but neither catalogued nor checked — the pictures under
  `assets/` among them. A person edits any page in
  their own editor and an agent edits one with its own file tools; nobody edits a
  source. Below the two folders the nesting is free — whoever files a page
  chooses where (see "Allow nesting without giving it meaning"). A Markdown
  document left outside them and `assets/` is filed into `pages/` by the sweep.
- **`assets/` holds an upload's pictures** (see "Keep the pictures of an
  upload beside its source"): one folder per upload,
  `assets/<title-slug>-<first 8 hex of the upload's SHA-256>/`, holding
  `image-1.<ext>`, `image-2.<ext>` … in the order the Markdown first shows
  them, written in the same commit as the source. The source links each by
  relative path, `../assets/<folder>/image-N.<ext>`. The folder is visible on
  purpose: the vault's `.git/info/exclude` leaves every hidden entry under
  `knowledge/` out of git, and the pictures must sync and keep history like
  the source. Nothing deletes a folder when its source is deleted.
  `assets.py` owns the layout, the links and the read route's guard;
  `converters/images.py` owns extraction and its bounds (48 px minimum side,
  5 MB per picture, repeats kept once, 40 per upload, non-web formats
  re-encoded as PNG).
- **Dot-prefixed entries are invisible** (see "Hide every dot-prefixed entry").
  Coffer's own surfaces list none of them and the read route refuses every
  hidden segment, through the path guard rather than by skipping. `.inbox/` is
  one of them: an ordinary hidden entry, a drop zone where an agent, another
  machine or an older guide may leave a Markdown file. The next sweep normalises
  its frontmatter and keeps it as a source under `sources/` (see
  "Adopt a file dropped into the inbox"), and no surface shows or counts what
  waits there.

### `README.md`

A collection describes itself in a `README.md` at its own root, which is not a
page or a source: it is never listed as content or counted (see "Keep the
collection README out of the corpus"). Its first paragraph before its first
`##` section is the collection's one-line description everywhere one is shown
(see "Read a collection's description from its README"), read off disk on every
listing so it cannot drift from what the person browsing the folder reads.
The README is also the collection's **schema**: the page types and rules it
names win over the guide's defaults, which the guide tells agents.
`POST /api/v1/knowledge/collections` writes it with the defaults spelled out
(see "Start a collection's README with its rules written out"):

```markdown
---
verify_after_days: 90
types_without_sources: [overview]
---

# shopee

How the shop is built.

## Page types

- `overview`: where to start. …
- `concept`, `entity`, `how-to`, `decision`: …

## Rules

- One subject per page. Link related pages with `[[slug]]`, or with an ordinary
  relative link …
```

| README key | Type | Notes |
| --- | --- | --- |
| `verify_after_days` | `int` | Days a page's `verified` date holds before it is a `stale_page` finding (see "Ask for a recheck of a page after the collection's interval"). Absent, negative or not a whole number → 90; `0` turns the check off. `review_after_days` is read the same way. |
| `types_without_sources` | list of `str` | Page types that need neither `sources` nor `evidence` (see "Check a collection mechanically on every read"). Absent → `[overview]`. |

That paragraph does more work than it used to: it is also what the delivered
skill's frontmatter description draws on, which is the only part of this layer
always in a model's context. A collection that fails to describe itself is a
collection an agent never recognises.

## The file

Every page and source carries a `---`-fenced YAML frontmatter
block, written and read only by `infrastructure/knowledge/frontmatter.py` (the
one place PyYAML lives). A page, as the guide tells agents to write it:

```markdown
---
title: Session ownership
type: concept
description: Which service owns a login session, and what reads it.
sources: [q3-review]
aliases: [sessions]
actor: agent
created_at: '2026-09-12T04:18:33Z'
updated_at: '2026-09-23T04:18:33Z'
---

Login state is owned by `account.session`; see [[gateway-routing]].
```

A source, as Coffer writes it from an uploaded PDF:

```markdown
---
title: Q3 review
description: The quarter's incidents and the follow-ups agreed.
actor: user
created_at: '2026-09-12T04:18:33Z'
updated_at: '2026-09-12T04:18:33Z'
original: q3-review.pdf
original_sha256: 1a2b3c4d…
---

…the text…

## Images

Page 2:

![Page 2](../assets/q3-review-1a2b3c4d/image-1.png)
```

| Key | Type | Notes |
| --- | --- | --- |
| `title` | `str` | Human-readable. Also the source of the file name on creation. |
| `description` | `str` | **Required** (see "Carry title, description and actor in frontmatter"). It is what an agent chooses by in the catalogue, so it says what question the document answers. |
| `actor` | `agent` \| `user` | Who last wrote it. From the `X-Coffer-Actor` header on a submission, the actor a dropped file reports, or `agent` for a document an agent wrote. |
| `created_at` | ISO-8601 `str` | Preserved across a rewrite, so a document keeps its own history even though nothing but the file records it. |
| `updated_at` | ISO-8601 `str` | Set on every write Coffer makes. |
| `type` | `str` | A page's type: `concept`, `entity`, `how-to`, `decision` or `overview` by default, or one the README defines; any value is a type, none refused as unknown. Missing → `incomplete_page`. |
| `sources` | list of `str` | A page's sources, by slug. Empty, with no `evidence` and a type `types_without_sources` does not list → `unsourced_page`; a slug no source has → `missing_source`. |
| `evidence` | list of `str` | What a page's facts rest on when it is not a source: code, configuration, an observation (`code: <repo>/<path>`, `observed: <date>, <where>`). Kept apart from `sources`; answers `unsourced_page`. |
| `verify_after_days` | `int` | A page's own recheck interval, winning over the README's for that page; `review_after_days` is read the same way; `0` turns its check off. |
| `aliases` | list of `str` | More names a page answers to in a `[[link]]`. |
| `verified` | `YYYY-MM-DD` `str` | When the page was last checked against its sources or the code; returned on a page's read as written. Missing, null, unreadable or older than the interval → `stale_page`. Coffer never writes it. |
| `ingest` | `skipped` | Set by an agent on a source with nothing worth keeping, so it stops waiting. |
| `superseded_by` | `str` | A source's replacement, by slug, set by an agent or a person (see "Mark a source superseded by the one that replaces it"), or by Coffer when a page is imported again with `replace`. The source stops waiting; a page citing it and no later source in the chain → `superseded_source`; a slug no source has → `missing_source` on the source. |
| `summary` | `str` | A source's one or two sentences on what it says, written by an agent as it integrates or tidies; shown in the catalogue and in Contents. |
| `original` | `str` | The name of the file an upload was converted from, written by Coffer (see "Keep an upload's original on this Mac only"). Absent on a Markdown or text upload, which is its own source, unless converting it rewrote it. An imported Confluence page's original is its export. |
| `original_sha256` | hex `str` | The SHA-256 of that file, written by Coffer; it names the copy kept in `~/.coffer/local/knowledge-originals/` on the Mac that uploaded it. |
| `origin` | mapping | An imported page's provenance, written by Coffer (see "Import a Confluence page as a readable source with its attachments"): `system` (`confluence`), `url`, `page_id`, `space`, `version`, `fetched_at` and `format` (`confluence-storage`). A fetch date, never a `verified`. |
| `import_report` | mapping | How an import ended, written by Coffer: `body` (`converted` or `partial`), `complete`, `attachments_kept`, and `missing` / `unsupported`, each a list of `<name>: <why>`. |
| *any other key* | | An upload's own frontmatter is kept on its source (an export's `version`, `retrieved_at`, `redacted`…), Coffer's keys aside, so a source never carries a second block in its body. |

A page's **slug** is its file stem; so is a source's. A `[[slug]]` or
`[[slug|text]]` outside code in a page's body resolves case-insensitively, after
NFKC, against page slugs and aliases first and then source slugs
(`infrastructure/knowledge/wiki.py`); none is a dead link, two or more an
ambiguous one. An ordinary Markdown link, picture or reference definition by
relative path, in a page, a source's neighbour or any of the collection's own
Markdown files, is followed from that file — a leading `/` from the collection
root — inside the knowledge root (`infrastructure/knowledge/links.py`): no file
there, or a hidden one, is a dead link; a path out of the knowledge root an
`outside_link`; a link with a scheme or an anchor alone is not a file link (see
"Link pages by slug or relative path and check every link").

These are the keys **Coffer writes**, not the only keys a document may carry. A
person who adds `tags:` or `reviewed_by:` in their own editor keeps it: every
rewrite Coffer makes — a collection's description edit, say — renders the known keys in a fixed order and then everything else unharmed,
values carried through as parsed rather than stringified. There is still no `id`
— the path is the identity (see "Use the file path as a document's identity") —
and none of the keys that described retired machinery (`lane`, `source_path`,
`source_sha256`, `source_format`, `source_mode`, `converter`, `embed_status`,
`content_sha256`, `coffer_ingested_at`, `coffer_curated_at`).

Frontmatter parsing degrades rather than raising: a file with no fence, or with
malformed YAML inside one, yields empty frontmatter and its body, so one
hand-edited file with a stray colon cannot break a whole collection walk.

### What the sweep does

The knowledge sweep runs when a file under `knowledge/` changes (and every 10 minutes otherwise) and does three mechanical things, calling no
model (see "Sweep the knowledge root on its mechanical duties"):

1. **Adopt and promote `.inbox/` files**: each Markdown file in a collection's
   `.inbox/` is normalised and kept (`inbox.promote`) as a source under
   `sources/`, recorded with one `KNOWLEDGE_WRITTEN` audit event.
2. **Commit edits found on disk** as `disk` writes, so an edit in any editor is
   a version of its own and is never counted as Coffer's.
3. **Re-render and re-seed the guide**, so a page added by hand is catalogued.

It moves nothing: a file stays at the path its writer gave it, wherever in the
collection that is (see "Sweep the knowledge root on its mechanical duties").
The `layout` operation below names only the commits an earlier version made
when it still filed loose documents into `pages/`.

The sweep takes no lock against a sync round: what it promotes is written
through the vault's ordinary writer, and it keeps no machine-local record.

`KnowledgeService.submit` promotes at once as well (see "Promote submitted
material at once"): an upload becomes a source under `sources/`, with
frontmatter filled from its opening prose, and its pictures land under
`assets/` in the same commit. The uploaded file itself is not stored in the
collection; it is kept on this Mac only (below). The source then waits until a
page cites it.

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
  A promoted file is named the same way and never written onto an existing
  document: two submissions of the same title are two documents.

### The traversal guard

Every segment that becomes a path component passes `paths.check_segment` (see
"Guard every path through one module"): non-empty, not all dots, not
dot-prefixed, and matching `[A-Za-z0-9._\- ]` or CJK. A path that must name a
document additionally passes `paths.require_document`, which refuses the
collection itself and its `README.md`; the inbox is out of reach for every
surface, because it is dot-prefixed. A
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
| `CollectionEntry` | `uid`, `name`, `description`, `page_count`, `source_count`, `waiting_source_count`, `finding_count`, `findings`, `folder_path`, `updated_at`, `linked`, `note_count`, `rules_file` | One collection, with the counts and findings its wiki graph gives. For a linked folder `linked` is true, `note_count` counts its Markdown files, `rules_file` names the first of `AGENTS.md`, `CLAUDE.md` and `README.md` at its root (empty when none), and the wiki counts are zero. |
| `DirectoryEntry` | `path`, `name`, `file_count` | A subdirectory at the level being listed. `path` is relative to the root — pass it back to descend. |
| `FileEntry` | `path`, `title`, `description`, `actor`, `updated_at`, `kind`, `page_type`, `waiting`, `stale`, `superseded_by`, `summary`, `cited_count`, `skipped` | One file as a listing or a catalogue shows it: enough to judge relevance without reading the body. `stale` marks a page due a recheck; a source's `superseded_by` is the path its replacement resolves to (the slug as written when it names none), `cited_count` how many pages cite it and `skipped` whether it is marked `ingest: skipped`. |
| `CatalogueLevel` | `path`, `directories`, `files` | **One level of one collection**, never the whole tree. |
| `Finding` | `kind`, `path`, `target`, `others` | One mechanical finding (see "Check a collection mechanically on every read"): `dead_link`, `ambiguous_link`, `outside_link`, `duplicate_slug`, `missing_source`, `superseded_source` (`others` = the newest replacement), `incomplete_page`, `unsourced_page`, `stale_page` (`target` = `verified` as written, none when missing), `orphan_page` or `waiting_source`. |
| `SourceRef`, `LinkRef`, `PageRef` | `slug`/`target`, `path`, `title`/`ambiguous` | A page's `sources` entry or `[[link]]` with what it resolves to; a page that cites a source. |
| `KnowledgeFile` | the frontmatter fields + `path`, `body`, `file_path`, `folder_path`, `kind`, `page_type`, `aliases`, `verified`, `stale`, `sources`, `links`, `cited_by`, `waiting`, `superseded_by`, `summary`, `original`, `original_path`, `readable_body`, `origin`, `import_report` | A file in full; a source's `superseded_by` is a `SourceRef`, `None` when it is current. `links` holds every `[[link]]` and link by relative path as a `LinkRef` (`target`, `path`, `ambiguous`, `kind` `wiki` or `path`, `outside`). `readable_body` is the body as an import would write it now when the file still carries an export's own frontmatter or Confluence storage markers, else `None`; `origin` an imported page's provenance as strings, read from its `origin` or that older frontmatter; `import_report` the report its frontmatter keeps. `original` is the source's `original` (empty when none) and `original_path` the absolute path of that file on this Mac, `None` when it is not here. The two absolute paths are what the UI needs to offer open-in-editor and reveal-in-file-manager (see "Return absolute paths on reads"); Coffer serves a document's bytes only to be shown: no route saves them (see "Treat a direct file edit as a complete change"). |

Constants: `ACTOR_AGENT = "agent"`, `ACTOR_USER = "user"`.

`KnowledgeService.submit` answers with a `Submission` (`collection`, `title`,
and the `document` — the `KnowledgeFile` it was promoted into). `IngestService.ingest`
answers with an `IngestedDocument` (`path`, `title`, `description`,
`converter`, and for a structured import its `report`, the `page_id`, the
older sources it `replaces`, the `files` it keeps and whether it was only a
`preview`).

Locating a document by literal text is an ordinary file search the agent does
with its own tools; no part of Coffer ranks or matches documents for it. There is
no `SearchHit`, `SearchOutcome`, `SearchService` or grep value object.

`Conversion` (`domain/knowledge/converter.py`) is what a converter returns for
an uploaded document: the `markdown`, a `title` (the document's first H1,
falling back to its file name; see "Fill frontmatter on converted material"),
which `converter` ran — reported on the upload response and written nowhere
on disk — and the `images` it took out (`ConvertedImage`: a `name` such as
`image-1.png`, which the Markdown links until the source is written, and the
`data`). The Markdown becomes the source and the images its `assets/` folder;
the uploaded file itself is kept on this Mac only, unless the `passthrough`
converter ran, which keeps a Markdown or text upload as it stands and keeps no
original unless it also returns a `report` (an export's markers expanded). A conversion may also carry `metadata` (frontmatter the document
carried or the converter read: a Markdown upload's own block, an imported
page's `origin`), other `files` (`ConvertedFile`: attachments) kept in the `asset_folder` it names, and a `report`
(`ImportReport`: the `body` as `converted` or `partial`, and each attachment
and macro as an `ImportItem` with a `name`, a `status` — `kept`, `converted`,
`dropped`, `missing`, `unsupported` or `skipped` — a `reason`
and where it is kept; `complete` when nothing is missing or unsupported). The
`confluence` converter (`infrastructure/knowledge/converters/confluence/`)
claims a `.json` upload by its content (see "Import a Confluence page as a
readable source with its attachments").

The HTTP wire models in `surfaces/http/knowledge/schemas.py` mirror the domain
types and add the shapes that describe an answer no domain type does:
`CollectionCreate`; `CollectionLink` (`folder`, the absolute path, and an
optional `name`) for `POST /knowledge/collections/link` (see "Link a folder the
person keeps themselves"); `MaterialIn` (`collection`, `title`, `description`, `body`);
`HandoffOut` (`prompt` and the facts it was written from), carried on a
collection's read as `tidy_handoff` and answered by
`GET /knowledge/tidy-handoff` for all collections (see "Hand a tidy to the
agent"); a collection's read also carries `tidy_running`, whether an agent has
a tidy of it open (see "Record a tidy as one change"), and `linked`,
`note_count` and `rules_file` as on `CollectionEntry`; `CheckOut`
(`collection`, `findings` of `FindingOut`), answered by
`GET /knowledge/collections/{uid}/check`; `CollectionFilesOut` (`files` of
`FileSummaryOut`), answered by `GET /knowledge/collections/{uid}/files` (see
"Show a collection's contents by page type"); `TidyStatusOut` (`collection`,
`running`, `started_at`), answered by `POST .../tidy/start`; `TidyFinishIn`
(`summary`, the agent's report) and `TidyFinishOut` (`change`, null when the
tidy changed nothing) for `POST .../tidy/finish`; `UndoIn` (`force`) for
`POST /knowledge/changes/{version}/undo` (see "Undo a tidy"); and
`IngestedDocumentOut` (`path`, `title`, `description`, `converter`,
`report` as `ImportReportOut` of `ImportItemOut`, `page_id`, `replaces`,
`files`, `preview`), answered by `POST /knowledge/upload`, which also takes the
form fields `replace` and `preview`; and
`FileOut`, a file's read, which carries the `KnowledgeFile` fields, `original`
and `original_path` among them. `GET /knowledge/asset?path=` answers a
picture's bytes with its media type (`png`, `jpg`, `jpeg`, `gif`, `webp`,
`svg`, up to 10 MB) rather than a wire model, and 404 for anything else. There is no
write-a-document model: every entrance submits material, which becomes a
document at once, and a person's own text reaches a document through their
editor. The mirroring is
deliberate rather than redundant: the domain types describe what is on disk and
the wire models describe what a client is promised, so removing a field from the
wire never means hiding one from the layer.

## Uploaded originals (machine-local)

The file a person uploads is kept on the Mac that uploaded it only (see "Keep
an upload's original on this Mac only"), outside the vault and never synced:

```text
~/.coffer/local/knowledge-originals/
└── <sha256><.ext>      # mode 0600; one file per content, however often it is uploaded
```

- The name is the upload's SHA-256 plus its lower-cased extension, so keeping
  is idempotent and the source's `original_sha256` finds the copy again.
- It is written after the source is committed: a failure to keep it loses the
  local copy, never the upload.
- A Markdown or text upload keeps none.
- Nothing deletes an original when its source goes; a source brought back by
  Undo or a history restore finds its original again. Losing the Mac loses its
  originals, while the source and its pictures survive in the vault.
- `infrastructure/knowledge/originals.py` owns the store. A read resolves
  `original_path` from the source's `original` and `original_sha256`; on a Mac
  without the copy it is `None`, and the Knowledge page says the original is on
  the Mac it was uploaded from.

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

`KnowledgeConfig` (`domain/knowledge/config.py`) **forbids unknown keys** and
holds one optional field, `folder`, the absolute path a linked folder names; a
collection Coffer keeps leaves it unset and its config stays `{}` on disk. The
kind's `storage_row` hook files a row that names a folder in the machine-local
class. A collection Coffer keeps has no settings at all: no retrieval modes, no chunk size,
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
vault repository (see "Commit every knowledge write naming its writer"; ADR every-vault-write-is-a-validated-commit-naming-its-writer): the
knowledge history is the vault's history pathspec-limited to `knowledge/`, with
every path handed back knowledge-root-relative (`KnowledgeHistory`,
`infrastructure/knowledge/history.py`, a view over the process's one vault
writer). The vault's `.git/info/exclude` ignores every
hidden entry under `knowledge/`, so a promoted file's document is the commit and
the hidden drop zone is never versioned.

There is still no table and no index: the history is git's, read with `git log`
by a person or an agent; the daemon reads it for one thing, the changes feed
behind a delete's Undo, a tidy's Undo and a collection's Change log
(`GET /knowledge/changes`, `POST /knowledge/changes/{version}/restore`,
`POST /knowledge/changes/{version}/undo`).

**One commit per operation.** A person's upload, delete or Undo of a delete, or description edit; material
promoted on arrival; a collection created, renamed or removed. Before any of them, whatever changed under
`knowledge/` that no open operation owns is committed first as a `disk` write,
so a person's own editor is never counted as Coffer's; the sweep and every
read of the changes feed do the same. A sync round's merge is a `sync` commit by
construction.

**A tidy is one commit.** While an agent has a tidy of a collection open
(`coffer knowledge tidy-start`), the vault writer *pauses* the collection's
path prefix: no settle — the vault scanner, the sweep, a sync round, another
Coffer write — commits its edits. Closing the tidy (`tidy-finish`, or the sweep
after the collection sat unchanged for 30 minutes) commits them all as one
commit by the `agent` writer, operation `tidy`, the agent's report as its
summary and `Coffer-Status: reported` (or `expired`, with no report). The open
tidies are a registry in the daemon's memory (`infrastructure/knowledge/tidy_runs.py`),
not stored: a restart forgets an open tidy, and its edits are then committed as
ordinary `disk` writes (see "Record a tidy as one change"). Undoing a change is
one commit by the `user` writer, operation `restore`, carrying `Coffer-Undoes`
(see "Undo a tidy").

**Trailers.** Each commit's message is a summary line and the vault's trailers
(spec vault-storage), with the knowledge history's own four added:

| Trailer | Value |
| --- | --- |
| `Coffer-Writer` | `user`, `agent` (a tidy, or material an agent submitted), `sync` or `disk`; `curation`, and `daemon` (filing loose documents), on commits an earlier version of Coffer made |
| `Coffer-Operation` | `save`, `delete`, `submit`, `promote`, `restore`, `edit`, `sync`, `create`, `rename`, `remove`, `baseline`, `tidy`; `pass`, `undo` and `layout` on commits an earlier version made |
| `Coffer-Actor` | the audit actor of the operation |
| `Coffer-Machine` | the machine that made the commit |
| `Coffer-Agent` | an agent writer's name |
| `Coffer-Collection` | the collection's name |
| `Coffer-Restored-From` | the commit a restore reverses to (an Undo, or an agent's restore of the history hand-off) |
| `Coffer-Status` | a tidy's `reported` (its agent finished it with a report) or `expired` (the sweep closed it) |
| `Coffer-Undoes` | the change an Undo of a tidy put back |

Commits an earlier version of Coffer made as curation passes keep their
`Coffer-Item`, `Coffer-Status` and `Coffer-Undoes` trailers in the history and
are read back under their writer's label.

The value objects the changes feed reads back — `Change`, `DocumentChange`,
`ChangesPage` — are in `backend/coffer/domain/knowledge/history.py`. A change's
`version` is its commit id.

## Errors

The failure modes are a directory's, plus the ones its converter library has. `domain/knowledge/errors.py`
holds the first group:

| Class | Code | HTTP |
| --- | --- | --- |
| `CollectionNotFound` | `KNOWLEDGE_COLLECTION_NOT_FOUND` | 404 |
| `CollectionExists` | `KNOWLEDGE_COLLECTION_EXISTS` | 409 |
| `KnowledgeFileNotFound` | `KNOWLEDGE_FILE_NOT_FOUND` | 404 |
| `UnsafeKnowledgePath` | `KNOWLEDGE_PATH_UNSAFE` | 400 |
| `UploadTooLarge` | `KNOWLEDGE_UPLOAD_TOO_LARGE` | 413 |
| `KnowledgeHistoryUnavailable` | `KNOWLEDGE_HISTORY_UNAVAILABLE` | 503 |
| `KnowledgeError` (base) | `KNOWLEDGE_ERROR` | 400 |

`KNOWLEDGE_COLLECTION_NOT_FOUND` answers a name no registered collection holds.
A uid-addressed route given a uid no resource answers to gives the generic
`RESOURCE_NOT_FOUND` (404) instead.

`UnsafeKnowledgePath` carries the document rule as well as the traversal one,
for the same reason both belong to path construction: a delete aimed at a
collection's `README.md` and a path aimed at `../etc/passwd` are both a caller
asking for something it may not reach, and a single guard is one that cannot be
forgotten by one surface.

`domain/kb_errors.py` holds one more, re-exported through `domain/errors.py`:

| Class | Code | HTTP | When |
| --- | --- | --- | --- |
| `EngineUnavailable` | `ENGINE_UNAVAILABLE` | 503 | a converter library the call needs is absent — one of MarkItDown's format backends. The daemon stays up and the caller gets a per-format answer |

And the two ingest refusals are not `CofferError`s at all. `UnsupportedDocument`
and `EmptyConversion` (`domain/knowledge/converter.py`) carry the *rejected
type* rather than a code, and the upload route turns both into `INGEST_REJECTED`
/ 400, distinguished by `details.reason` — `unsupported_type`, or `scanned_pdf`
/ `empty_conversion` — so a surface can name the format it will not take and,
for a PDF with no text layer, say something actionable about why. Either way
nothing is submitted: no document (see "Bound uploads and leave
nothing behind on failure").

## Audit and invocation records

Unchanged in shape and still database-backed, because they are not knowledge —
they are Coffer's own bookkeeping. Every submission — an inbox file dropped by an
agent (recorded by the sweep when it adopts the file), an upload or a
channel — records one `KNOWLEDGE_WRITTEN` `audit_log` event naming the caller
(`actor_reported: true` when the actor came from the file's own frontmatter),
with the document path it was promoted to (see "Adopt a file dropped into the
inbox"); an Undo of a delete records
`KNOWLEDGE_EDITED` with the path and `restored_from`; starting and finishing a
tidy each record `KNOWLEDGE_EDITED` (`tidy: started`, or `tidy: finished` with
the change's version and file count); an Undo of a tidy records
`KNOWLEDGE_EDITED` with `undoes`, its paths and the later edits it discarded; a delete records `KNOWLEDGE_DELETED`. `KNOWLEDGE_CURATED` rows an
earlier version of Coffer recorded for curation passes stay in the audit log and
keep rendering under their label.

Losing the read tools lost the invocation record for reads, and with it the
ability to answer "is this layer being used" from `mcp_invocations`. That is a
deliberate cost: the replacement measurement is the agents' own transcripts,
which Coffer already reads for other reasons and which are retroactive, so
nothing is lost by not having built it yet.
