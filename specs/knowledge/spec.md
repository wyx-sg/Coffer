# Feature Specification: Knowledge Layer

**Status**: Accepted
**Folder name**: this spec lives at `specs/knowledge/`, the spec id every inbound link and `scripts/audit_acceptance.py` keys on. It keeps that name although the layer merged with what used to be a separate Knowledge Base: the name is an identifier other documents and the acceptance audit resolve, not a description. The layer's revision history lives in the roadmap's revision log.

**Input**: Coffer holds **knowledge about the user's working environment**: their repositories, services, projects, the people they work with, the decisions and traps worth surviving a session. It is what the human uploads and what the human and an agent write together, filed into **collections**. It is a **directory of Markdown files** — the files are the sole truth, and a human finds what they need by opening a folder. An agent finds it by reading a catalogue, grepping a line, or asking which files a phrase appears in. See [Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md).

**Knowledge is not memory.** Knowledge is about the world — a platform's API contract, a service's ownership, a document someone published — and it arrives because a person put it there. Memory is about the user and their projects, and it accrues on its own as agents work. They differ in every dimension that matters — who authors them, how they are partitioned, how they are delivered, and whether an entry can be *superseded* — so they are two layers: this one, filed by collection and **pulled** when needed, and spec [memory](../memory/spec.md), partitioned by project and **pushed** at session start.

## The principle this layer answers to

**Knowledge is managed by the human and the agent together.** Every decision below follows from it: metadata lives in the file rather than a database row because only the file is visible to both; the catalogue is generated rather than stored because a stored one would drift away from what the human sees in their file manager; the human's editor and the agent's `write` reach the same bytes with nothing in between.

## What this layer is not

Everything below is a **standing constraint**, not a phase that has passed. Each
one names a mechanism this layer refuses to hold and why the refusal is
load-bearing; the ADR
[Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md)
carries the audit of the live installation that produced them.

**No derived index of any kind.** No vectors, no sidecar, no FTS5, no chunking,
no fusion, no reindex — lazy or explicit — and no per-scope retrieval
configuration. `search` is a literal match read off disk at call time, promoted
from fallback to the answer: at hundreds of files an agent that reads a catalogue
and greps a phrase is already finding what it came for, and a ranking layer buys
it very little against a second thing to keep level with the disk, a dependency
on a connection some installations do not have, and file text leaving the machine
on a read. What the refusal buys is that **nothing derived stands between a query
and a file**: nothing to rebuild, nothing to be stale, nothing to reconcile,
nothing to exclude from a backup. Embeddings may earn their way back at a corpus
size that needs them (see Assumptions); that would be a later decision, not a
deferred piece of this one.

**No second retrieval surface on the web page.** A collection *is* a folder, so
its page browses it and nothing else: one tree on the left, one read-only
preview on the right, the same two panes a skill's Files tab is (FR-061). A
search box sitting where the tree should be would be a second way to reach a
file, with its own rules, stacked on top of the folder it was querying. The
`search` route itself keeps the callers it was built for — `coffer__search` for
agents, `coffer knowledge search` for the CLI.

**No structure that carries meaning.** Properties are not directories: there are
no `notes/` ÷ `docs/` lanes, no `global` ÷ `project-<ULID>` ÷ collection axis, no
cwd-derived scope, no auto-provisioning and no scope display labels. A collection
is a folder the human made on purpose, and the nesting inside it is theirs.

**No source tracking around an ingested document.** The original is kept under
`.raw/` so a bad conversion can be redone (FR-035) and that is all: no
`source_mode`, no re-conversion lock, no external-source table, no re-conversion
on a schedule.

**Ingestion is an additional entrance, never a required one.** Putting a Markdown
file in the directory stays a complete way to add knowledge (FR-032). Upload
exists because the filesystem is only reachable while the user is sitting at the
machine, and their live entrance is a phone: a channel already accepts
attachments and already extracts them for a turn (spec
[channels](../channels/spec.md) FR-030), so sending a document to Coffer from
that chat and having it land in a collection is the entrance this layer would
otherwise lack — and it makes the Web upload the same path's other end.

## User Scenarios & Testing

### User Story 1 — One knowledge store, every agent (Priority: P1)

The developer works with Claude Code in the morning and Codex in the afternoon. In the morning an agent records that a service's login state is owned by `account.session`. In the afternoon a different agent finds it, because both read the same directory. No copy diverges, because there is only one copy.

**Independent Test**: from one MCP client write a fact; from a second client with a different agent identity, list the catalogue and read the file back.

### User Story 2 — Collections are the human's filing, and the unit of authorization (Priority: P1)

Some knowledge is a company's internal detail and must not reach every agent the developer runs; some is about a side project and may reach any of them. The developer creates a collection deliberately, puts the sensitive material in it, and authorizes only the agents that may see it. Inside a collection they nest folders however they like; Coffer neither knows nor cares.

**Independent Test**: create two collections, authorize one for a single agent, and confirm the other agent's catalogue and reads do not include it. Create a nested folder by hand and confirm the catalogue walks into it.

### User Story 3 — Find the right file without an index (Priority: P1)

An agent needs a fact it has no exact words for. It lists the collections, reads the one-line description of each, descends into the likely one, reads the titles and descriptions there, and either reads a file outright or greps for a literal string it now knows to look for.

**Independent Test**: with a populated collection, call the catalogue at each level and confirm titles and descriptions come back; grep a CJK string and confirm the matching file and line.

### User Story 4 — The human curates in their own tools (Priority: P2)

The developer drops a Markdown file into a collection from Finder, corrects a wrong line in their editor, and deletes one that went stale. Every change is live for the next agent call with no import step, because the file *is* the knowledge.

**Independent Test**: add a file out-of-band and confirm it appears in the catalogue and in grep; edit one and confirm the new bytes are what `read` returns.

### User Story 5 — The agent knows the layer exists (Priority: P1)

A skill Coffer delivers tells the agent this layer is here and how to work it. It arrives through the same channel that already delivers Coffer's other skills, so every managed agent gets it without a hook and without anything being written into the agent's own memory.

**Independent Test**: with a managed agent bound, confirm the knowledge skill is present in its skill directory and names the catalogue-then-grep motion.

### User Story 6 — Tidy, when the human asks for it (Priority: P3)

Notes accumulate and duplicate. The developer triggers a tidy pass that merges and rewrites them, having first archived every prior revision. They may also let it run on a timer, but only after switching it on — and, once the vault is synced, only on the one machine named as the tidy owner.

**Independent Test**: run a tidy pass over a collection holding duplicates; confirm `.history/` holds the prior revisions and that the archived copies never appear in grep results.

### User Story 7 — A document gets into the vault from wherever the user is (Priority: P1)

The developer is handed a PDF in a chat. They forward it to their Coffer channel, say which collection it belongs in, and it lands there as Markdown with its title and description filled in, the original kept aside. At the desk they do the same thing by dropping the file on the Knowledge page. Either way it is a file in a collection afterwards, indistinguishable from one they wrote by hand.

**Independent Test**: upload a non-Markdown document through the REST surface and confirm a Markdown file appears in the collection with frontmatter, the original under `.raw/`, and the converted text readable by `read`.

### User Story 8 — Get the file, not the line (Priority: P1)

An agent knows a distinctive word or phrase and wants the *files* it appears in — and it cannot afford to page through a catalogue first. It searches for that phrase and gets back the handful of files that contain it, each with its title, description and the lines that matched, so it can tell what it found before reading any of them. Matching is literal, so a question phrased in the agent's own words finds nothing; the tool's description and the delivered skill both say so.

**Independent Test**: write a file containing a distinctive phrase, search for it, and confirm the file comes back with its title, description and the matching line; search for wording that appears nowhere and confirm an empty result rather than an error.

## Acceptance Scenarios

### Scenario: a written note lands as a markdown file with a readable name

- **Given** a `shopee` collection created through
  `coffer knowledge create`
- **When** `coffer knowledge write --in shopee` runs
  against the daemon with the title `Account Gateway`, a description and
  a body
- **Then** the command exits 0 and the note is on disk at
  `~/.coffer/knowledge/shopee/account-gateway.md` — the file name is the
  title's own slug, and no id appears in it anywhere

### Scenario: frontmatter carries title, description and actor

- **Given** an empty `shopee` collection
- **When** a file is written into it with a title, a description and `actor`
  `user`
- **Then** the file's YAML frontmatter holds exactly `title`, `description`,
  `actor`, `created_at` and `updated_at` and nothing besides, carries the
  title and the actor it was given, and the body follows the fence unchanged

### Scenario: a file added out-of-band is visible to the next call

- **Given** a Markdown file carrying `title` and `description` frontmatter
  placed straight into the `shopee` collection as `dropped-by-hand.md`, by a
  file manager rather than by Coffer
- **When** the catalogue of `shopee` is listed, with no import, registration
  or reindex step in between
- **Then** the file's title is among that level's files and a `read` of
  `shopee/dropped-by-hand.md` returns its body

### Scenario: the catalogue lists collections with their README description

- **Given** a collection created with the description "First description",
  whose `README.md` is then edited by hand to open with "Edited by hand."
- **When** `coffer knowledge collections --json` runs
- **Then** the collection's `description` is the README's first paragraph as
  edited, not the string the creation call supplied — the description is read
  off disk on every listing, never out of a row

### Scenario: the catalogue lists one level of a collection

- **Given** a collection holding one file at its root and a second file inside
  a subdirectory of it
- **When** the catalogue is listed for the collection itself — through
  `list_level`, and through the `/knowledge` page in a real browser
- **Then** the root file's title and the subdirectory's name come back, the
  subdirectory reporting its file count of 1, and the nested file's own title
  is absent from the level and from the page

### Scenario: the catalogue walks into a nested directory

- **Given** a file written into `shopee/account/core`, two directories below
  the collection root
- **When** the catalogue is listed at `shopee/account/core`
- **Then** the level reports that exact path and the one file in it, so
  nesting the human made is walkable rather than merely tolerated

### Scenario: grep matches a literal string across a collection

- **Given** two collections — `shopee` activated for `claude-code` alone and
  `personal` activated for every agent — each holding a file whose body
  contains 登录态
- **When** `grep` is run for that string as `claude-code`, then again as
  `codex`
- **Then** the first call matches files in both collections and the second
  only in `personal`: one grep spans every collection the calling agent is
  authorized for, and no others

### Scenario: grep matches CJK content

- **Given** a note written through the CLI whose body reads
  `account.session 负责登录态 token`
- **When** `coffer knowledge grep 登录态 --json` runs
- **Then** the command exits 0 and the matches name `shopee/session.md` — no
  tokenizer, and nothing built between the write and the search

### Scenario: grep skips hidden directories

- **Given** a file whose body says `登录态 old revision`, archived into
  its collection's `.history/` and then deleted from the collection itself
- **When** `grep` is run for `old revision`
- **Then** no match comes back at all: the archived revision is still on disk,
  and `.history/` is never searched

### Scenario: read returns a file by path

- **Given** a note in `shopee` whose body is the one line
  `account.session owns login state`
- **When** `coffer knowledge read shopee/session.md` runs
- **Then** the command exits 0 and that whole body is in its output — a path
  is the only handle a read takes, and there is no chunk or passage in the
  answer

### Scenario: creating a collection registers a knowledge resource

- **Given** a running daemon over an empty knowledge root
- **When** `coffer knowledge create shopee` runs with the
  description "Internal systems"
- **Then** `coffer knowledge collections --json` lists exactly
  `shopee` — the listing intersects the directory with the enabled `knowledge`
  Resource rows, so appearing there is the registration — and its description
  is the one given, now written into the collection's `README.md`

### Scenario: an unknown collection is an error, never auto-created

- **Given** a knowledge root with no `typo` collection in it
- **When** `coffer knowledge ls typo --json` runs
- **Then** the command exits non-zero and no `typo` directory exists
  afterwards: a read never provisions a collection

### Scenario: a collection outside an agent's scope is absent from its catalogue

- **Given** `shopee` activated for `claude-code` alone and `personal`
  activated for every agent
- **When** the collection list is asked for as `claude-code`, then as `codex`
- **Then** the first answer names both collections and the second names only
  `personal` — the restricted one is simply not in the other agent's catalogue

### Scenario: a collection outside an agent's scope cannot be read

- **Given** the same two collections, and a file inside `shopee`
- **When** `codex` reads that file by its exact path, and lists the `shopee`
  level
- **Then** both raise `CollectionNotFound` — not a forbidden error, because
  naming a collection the caller may not have is itself the disclosure — while
  the same read as `claude-code` returns the file

### Scenario: write creates a file and replaces an existing one

- **Given** a file created by a first write into `shopee`
- **When** a second write targets that file's own path with a new description
  and a new body
- **Then** the path is unchanged, the body is the new one, `created_at` still
  says when the file was first written rather than now, and the collection
  still holds exactly one file

### Scenario: delete removes the file from disk

- **Given** a note on disk at `~/.coffer/knowledge/shopee/stale.md`
- **When** `coffer knowledge delete shopee/stale.md` runs
- **Then** the command exits 0 and the file no longer exists on disk

### Scenario: a path escaping the knowledge root is rejected

- **Given** the single path-construction module every surface resolves through
- **When** it is asked to resolve `../etc/passwd`, `shopee/../../outside`, or
  any path naming a hidden entry — `.history/old.md`,
  `shopee/.raw/original.pdf`
- **Then** each one raises `UnsafeKnowledgePath` rather than returning a
  location outside the root or inside a directory the system keeps for itself

### Scenario: the six built-in knowledge tools appear in the client tool list

- **Given** a real daemon with an upstream MCP server registered, driven over
  its `/mcp` endpoint by the MCP SDK so the SDK's own models validate every
  frame
- **When** the client initializes and calls `tools/list`
- **Then** `coffer__list`, `coffer__grep`, `coffer__read`, `coffer__search`,
  `coffer__write` and `coffer__delete` are all in the listing, beside the
  upstream server's own tools
- **And** `coffer__write` followed by `coffer__grep` over that same session
  lands a note in a collection and finds it back, so the built-ins are
  callable over the wire rather than merely advertised

### Scenario: search returns the files a phrase appears in, with the lines that matched

- **Given** a collection holding a file titled `Session Ownership`,
  described as which service owns a login session, whose body is the one line
  `account.session owns login state`
- **When** `POST /api/v1/knowledge/search` is given that whole phrase,
  and `coffer knowledge search` is given part of it
- **Then** both answer with that file's own path among `results` — 200 for the
  route, exit 0 for the CLI — and the route's hit carries the file's `title`,
  its `description` and a non-empty list of the lines that matched, a file at
  a time with no score or rank on it

### Scenario: search spans only the collections the caller may see

- **Given** two collections whose files both contain `login state`, the
  second narrowed to the agent `only-agent` through the Resource framework's
  own scope route
- **When** the built-in `coffer__search` tool is called with the `agent`
  argument the gateway writes in set to an unrelated agent
- **Then** the results carry paths from the open collection and not one from
  the narrowed one

### Scenario: an uploaded document lands as markdown with frontmatter

- **Given** a collection and a document sent into it — `notes.md` through the
  ingest service, `Runbook.txt` through `POST /api/v1/knowledge/upload`
- **When** the upload is accepted (201 from the route)
- **Then** it lands at a slug path inside the collection, its frontmatter
  carries `actor: user` with the title taken from the document and a
  description filled in, and a following `read` returns the converted text —
  indistinguishable afterwards from a hand-written file
- **And** the collection's file count is 1: the converted file is the only
  thing the catalogue sees

### Scenario: an uploaded original is kept under .raw/ and stays out of retrieval

- **Given** a document uploaded into `shopee` whose bytes carry a marker word
  the converted Markdown does not
- **When** the collection's catalogue, its `tree` route and a grep for that
  marker are read afterwards
- **Then** the original sits at the collection's own `.raw/` root under the
  converted file's name, byte-identical to what was sent and with its absolute
  path reported as `raw_path`
- **And** the catalogue's file list, the collection's file count, the `tree`
  response and the grep result all carry nothing under `.raw/`

### Scenario: an upload of an unsupported type is refused with its reason

- **Given** a collection, and a file whose type no converter handles —
  `archive.bin` at the service, `payload.exe` at the route
- **When** it is uploaded
- **Then** the service raises `UnsupportedDocument` and the route answers 400
  `INGEST_REJECTED` whose details name `reason` `unsupported_type` and
  `doc_type` `exe`, and the collection is left with no file and no `.raw/`
  directory at all

### Scenario: a document is never stored half-converted

- **Given** a document whose converter succeeds but yields no text, as an
  image-only PDF does
- **When** it is uploaded
- **Then** the upload is refused with the reason naming the document type, and
  neither the converted file nor the original is written

### Scenario: a document forwarded to a channel lands in a collection

- **Given** a paired channel whose owner has just sent `note.txt` as an
  attachment, and one existing collection named `research`
- **When** the owner follows it with the plain text `/save research`
- **Then** the ingest service is called exactly once — that collection, that
  file name, those bytes, `actor` `user` and the channel's own default agent —
  and the channel replies with a confirmation naming both the file and the
  collection

### Scenario: tidy archives the prior revision before rewriting

- **Given** a collection holding one file whose body is
  `the original body`, an internal connection configured, and a pass
  whose agent overwrites the first file it is shown
- **When** the pass runs
- **Then** it reports `ok`, the collection's `.history/` holds exactly one
  archived file and that copy still contains the original body, and the live
  file at the same path now holds the rewritten one

### Scenario: tidy is a no-op when no internal model is configured

- **Given** a collection with a file in it and no internal model connection at
  all
- **When** a tidy pass is run over it
- **Then** it reports `no_model` and no `.history/` directory is created — the
  pass did nothing, rather than failing part way through

### Scenario: the tidy worker stays off unless enabled

- **Given** the interval worker over one collection, with its enabled check
  answering false
- **When** a sweep runs
- **Then** no collection is tidied at all; and with the same check switched to
  true and the sweep repeated, that collection is tidied — the switch is read
  per sweep rather than captured when the worker was built

### Scenario: a second tidy pass over the same collection is refused while the first is running

- **Given** two collections, and a pass already in flight over `shopee` held
  in the daemon's in-flight registry
- **When** a tidy is requested for `shopee` over the route that starts one
- **Then** it is refused 409 `UPKEEP_ALREADY_RUNNING` rather than queued,
  while the same request for the other collection answers 200 — the bound is
  per collection, not vault-wide
- **And** once the in-flight record is released the previously refused request
  answers 200

### Scenario: the knowledge skill is delivered to a managed agent

- **Given** a fresh installation whose daemon has completed one startup
- **When** Coffer's master skill store under `~/.coffer/skills/` is inspected
- **Then** the knowledge skill has a directory there holding a `SKILL.md` that
  declares the skill's name in its frontmatter and names `coffer__list`,
  `coffer__read`, `coffer__grep` and `coffer__write` in its body, so
  catalogue-then-grep is what an agent reads rather than a bare list of tools

### Scenario: the viewer renders content read-only and offers open and reveal

- **Given** a collection page whose tree holds one file
- **When** that file's row in the tree is clicked
- **Then** its body renders in the pane beside the tree, together with an
  open-in-editor button and a reveal button, and the page carries no textbox
  for the body or the content and no tab at all — one tree rather than a lane
  pair, and every edit leaves the app

### Scenario: migration rewrites ULID documents into named files in collections

- **Given** a pre-0066 vault — ULID-named files under `global/docs` and
  `project-01ABC/notes`, a `.raw/` duplicate beside them, and a `documents`
  row whose title, a Chinese gloss of the service, exists nowhere but that row
- **When** the database is upgraded to `0066`
- **Then** the document is a named file under a `shopee` collection whose file
  name carries the title's words and no ULID, and whose frontmatter holds that
  title with `actor: user` and neither `source_filename` nor `converter`
- **And** the hand-written note is under a `coffer` collection keeping its own
  title and `actor: agent`; `global/`, `project-01ABC/` and every `.raw/`
  directory are gone; `documents`, `chunks`, `documents_fts` and
  `embedding_config` no longer exist; and the `knowledge` Resource rows are
  exactly `shopee` and `coffer`

## Requirements

### Storage

- **FR-001**: Knowledge MUST be stored as Markdown files under `~/.coffer/knowledge/<collection>/`. The files are the **sole source of truth**, and nothing derived may stand between a query and them: the system MUST NOT keep a retrieval index of any kind — no vectors, no sidecar, no cache — so every answer is read off disk at call time.
- **FR-002**: A file's **path is its identity**. There MUST be no separate id field in frontmatter and no id-to-path mapping anywhere. File names MUST be human-readable slugs derived from the title; a collision appends a short suffix.
- **FR-003**: Every file MUST carry YAML frontmatter with `title`, `description`, `actor` (`agent` | `user`), `created_at` and `updated_at`, and nothing else. `description` is **required**, not optional: search matches literally, so the catalogue is the retrieval surface for anything the caller cannot quote, and a file that fails to describe itself is unfindable.
- **FR-004**: A collection MAY contain arbitrarily nested subdirectories. The system MUST NOT assign them meaning, MUST NOT require them, and MUST NOT create them.
- **FR-005**: Hidden entries (dot-prefixed) MUST be excluded from the catalogue and from grep. `.history/` is the only one the system itself writes.
- **FR-006**: Every name that becomes a path segment MUST pass a traversal guard, and path construction MUST live in exactly one module.

### Collections

- **FR-010**: A **collection** is a top-level subdirectory of the knowledge root and is one `knowledge` Resource. It MUST be created deliberately — through the REST/CLI/UI surface — and MUST NOT be provisioned by a read, a write, or an agent's working directory.
- **FR-011**: The system MUST NOT derive any boundary from the agent's cwd. There MUST be no `global` scope, no `project-<ULID>` naming, no git-root resolution and no scope-to-project-root mapping table.
- **FR-012**: A collection MUST support the Resource framework's **per-agent scope**: an agent sees, greps, reads and writes only the collections activated for it. An agent's calls MUST span **every** collection it is authorized for — there MUST be no rule that leaves an authorized collection out of a default. The identity a call is authorized as MUST be the session's handshake identity (spec [mcp-gateway](../mcp-gateway/spec.md) FR-021), written into the call by the gateway as an `agent` argument that no tool advertises in its input schema; a value a client supplies under that name MUST be discarded, never honoured.
- **FR-013**: A collection's one-line description MUST be the first paragraph of a `README.md` in its directory, absent when there is none. It MUST NOT be stored in the database.
- **FR-014**: Per-agent authorization is enforced at the MCP tool surface only, and the system MUST describe it as such: it prevents mistaken retrieval, not deliberate filesystem access.

### Retrieval

- **FR-020**: The catalogue MUST be **generated at call time** by walking the directory and reading frontmatter. The system MUST NOT materialize it to a file or a table.
- **FR-021**: `list` MUST walk **one level at a time**: with no path it returns every collection the caller may see, each with its README description and its file count; with a path it returns that directory's immediate subdirectories and files, each file with its `title` and `description`.
- **FR-022**: `grep` MUST run ripgrep over the files of the collections the caller may see, matching literally or by regex, recursively, and returning file, line number and matching line. Matches MUST be bounded and the response MUST flag truncation. Ripgrep is preferred, not required: on a machine with no `rg` on the `PATH` the same search MUST run in a built-in Python walk over the same files with the same semantics — hidden entries skipped, regex per line, the same bounds and the same truncation flag — so a caller sees no difference beyond speed, and the daemon MUST log the fallback once.
- **FR-023**: `read` MUST return a file's full text by path. There MUST be no chunking, no passage granularity and no `top_k`.
- **FR-024**: `search` MUST answer a text query with the **files** the query appears in, each with its path, `title`, `description` and the lines that matched, bounded to a handful of files and a few matched lines each. It MUST use the same matcher `grep` uses — a regular expression, case-sensitive — over the same files; the two tools differ only in what they report, `grep` a line at a time and `search` a file at a time. There MUST be no score, no ranking, no heading, no retrieval *mode* on any surface and no second way an answer can be reached. Because matching is literal, `search` MUST say so where a caller reads it: the tool's own description MUST tell the agent to give it a distinctive word or exact phrase rather than a question in its own words.
- **FR-028**: A file MUST be searchable the instant it lands, with no reindex step — not because a freshness rule keeps an index level with the disk, but because there is no index to keep level. `search` reads the files themselves at call time, so a file written by an editor, a channel, `write` or `git` is found by the next call.
- **FR-029**: `search` MUST be confined to the files under the collections the caller may see and MUST skip hidden directories (`.history/`, `.raw/`). It MUST NOT send a file's content anywhere: search runs entirely on this machine and needs no connection of any kind.

### Writing and ingestion

- **FR-030**: `write` MUST create a file from `title`, `description` and body text, or replace one when given an existing path. A write MUST be a plain file write — no LLM, no conversion, no indexing step.
- **FR-031**: `delete` MUST remove a file from disk.
- **FR-032**: Placing a Markdown file in the directory MUST remain a complete way to add knowledge — no import, no registration, no conversion step. Ingestion below is an additional entrance for the cases where the filesystem is out of reach, never a required one.
- **FR-033**: The system MUST accept a document upload into a named collection and convert it to Markdown. Supported inputs MUST be exactly what `markitdown` handles plus plain text and CSV; an unsupported type MUST be refused with the type named, never stored half-converted.
- **FR-034**: A converted document MUST land as an ordinary Markdown file, indistinguishable afterwards from one written by hand: a readable slug for a name, and FR-003's frontmatter — `title` from the document (falling back to its file name) and `description` filled in, by the internal connection when one is configured and from the document's opening prose when not.
- **FR-035**: The uploaded original MUST be kept under a single hidden `.raw/` directory at the **collection's root**, at the converted file's path relative to that root, so a bad conversion can be redone from the bytes the user sent. `.raw/` MUST be excluded from the catalogue, from grep and from search, and MUST be removed when its converted file is deleted. Coffer MUST NOT re-convert it on a schedule or track it as an external source; both mechanisms existed once and neither was ever used.
- **FR-036**: A document sent to a Coffer channel MUST be ingestible into a collection through the same conversion path, so the phone and the Knowledge page are two ends of one entrance (spec [channels](../channels/spec.md)). The channel MUST confirm the collection with the owner before storing, and MUST NOT store anything from a non-owner.
- **FR-037**: Upload MUST be bounded: one file per call, a size ceiling, and a refusal that names the limit. A conversion failure MUST leave neither a Markdown file nor a `.raw/` original behind.

### Tools and delivery

- **FR-040**: Coffer's MCP gateway MUST expose exactly **six** built-in knowledge tools under the `coffer__` prefix: `list`, `grep`, `read`, `search`, `write`, `delete`. Upload is not among them — a document enters through a human surface (the Knowledge page or a channel), not through an agent's tool call.
- **FR-041**: Built-in invocations MUST continue to record one `mcp_invocations` row (tool, actor, duration, outcome — no arguments, no content). A write or delete MUST additionally record an audit event with the agent as actor.
- **FR-042**: Coffer MUST deliver a **knowledge skill** through the existing skill-delivery channel (spec [skill-manager](../skill-manager/spec.md)), teaching the catalogue-then-grep motion and when to reach for `search` instead. This layer MUST NOT push anything into a session of its own accord and MUST NOT write into any agent's own memory files: knowledge is pulled. Session-start delivery belongs to spec [memory](../memory/spec.md), which carries its own budget and its own consent.

### Tidy

- **FR-050**: The system MUST provide a bounded agentic **tidy** pass over a collection, driven by the internal model connection, whose tool surface is the four file operations — `list`, `read`, `write`, `delete`. It MUST copy a file's prior revision into `.history/` before any overwrite or merge. With no internal connection configured it MUST be a clean no-op.
- **FR-051**: Tidy MUST be triggerable by hand from the UI and from `coffer knowledge organize`. A background worker MAY run it on an interval, governed by one **installation-wide setting that is off by default**, and that setting MUST **name a machine**. It is a pair on the singleton `internal_engine_config` row: `auto_tidy_enabled`, the switch, and `tidy_owner_machine_id`, a `machine_id` from the sync machine registry (spec [vault-sync](../vault-sync/spec.md)) that is null until an owner is chosen. The worker MUST read both on every tick, so the switch reads as *on, here* rather than merely *on*. Both the switch and the interval MUST be settable by the operator and MUST be read per pass rather than at boot, so a change takes effect without a daemon restart (spec [provider-switching](../provider-switching/spec.md) E3a).
- **FR-052**: `.history/` MUST be dot-prefixed and therefore excluded from the catalogue and from grep.
- **FR-053**: The tidy setting MUST be **synced state**, travelling with the vault in the `internal-engine` document that already carries it, so every machine agrees on who the owner is. A pass MUST run only on the machine the setting names and MUST be a clean no-op on every other. Without that rule two machines rewrite one corpus independently: each merges the same pair of notes into a topic document, but into a *different* one, and git merges the result cleanly — both machines agree the originals are deleted, and the two topic documents are additions at different paths — so the vault ends up holding the same knowledge twice with nothing reported as a conflict. If the owner machine is off, no tidy happens at all, which is the accepted trade for a background nicety.
- **FR-054**: A tidy pass and a converge round MUST NOT overlap. Both write the vault, and an export taken mid-rewrite is a torn snapshot, so they MUST take the same lock. A pass MUST additionally be skipped while a conflict or a pending confirmation is outstanding, so a rewrite is never piled onto an unresolved divergence.
- **FR-055**: Where the owner's pass deleted a file that another machine edited, the **edit MUST win**: the file survives with its edit, the deletion is dropped, and the round MUST NOT report a conflict. A fresh edit is something a person or an agent just decided; the deletion is a housekeeping judgement the next pass will simply make again.
- **FR-056**: Only **one tidy pass per collection** may run at a time, whoever started it. The pass runs for minutes and rewrites the collection's files, so a second pass over the same collection is not a faster tidy but two writers over one directory. A manual trigger that arrives while a pass is in flight MUST be **refused** rather than queued (`UPKEEP_ALREADY_RUNNING`, 409) — the caller asked to start a pass, and no pass is going to start — and the interval worker MUST **skip** a collection that is already being tidied rather than wait behind it, since its next sweep comes round again anyway. Which collections are being rewritten right now MUST be readable, so a surface that opens mid-pass shows the pass instead of an idle button that invites the second click. The record is per-daemon and does not outlive it: a pass lives in the process that was asked for it, so a restart ends it and the reading comes back empty, which is the truth rather than a lost record.

### Surfaces

- **FR-060**: The REST API under `/api/v1/knowledge` and the `coffer knowledge` CLI group MUST cover: create a collection, list the catalogue at a path, read a file, search, upload a document, write a file, delete one, and trigger tidy. Collection deletion goes through the Resource framework (`DELETE /api/v1/resources/knowledge/{name}`). There MUST be no index, reindex, check-sources, update-source, embedding-configuration or per-scope settings endpoint.
- **FR-061**: The web UI MUST present a collection as a **two-pane file browser**, the same one a skill's folder gets (spec [skill-manager](../skill-manager/spec.md)): a **single tree** on the left — no lane tabs, opened a directory at a time as FR-021 lists it — and the file chosen from it on the right, rendered **read-only** through the unified file preview with open-in-external-editor and reveal-in-file-manager on it and its folder. There MUST be no in-app editor. It MUST offer upload into the collection in view. The page MUST NOT carry a retrieval box of its own: the one input beside the tree narrows the names already on screen, client-side, and reading the files themselves is `search` and `grep`, whose callers are the agents' tools and the CLI. There is nothing to report about index freshness and no rebuild to offer.
- **FR-062**: Read responses MUST carry the file's absolute path and its containing folder's absolute path.

### Migration

- **FR-070**: One migration MUST drop every knowledge-specific table — `documents`, `chunks`, the six `documents_fts*` tables, `embedding_config`, `knowledge_scope_labels`, `knowledge_scope_project_roots` — guarded so a database missing any of them still upgrades.
- **FR-071**: Before those tables are dropped, a data migration MUST rewrite the on-disk corpus: each document's `title`, which lived only in the database, becomes its file name and its frontmatter, files move out of `notes/` and `docs/` into collections, and `.raw/` is deleted. Existing scopes land as two collections: `shopee` for the documents about internal systems and `coffer` for the project's own. The migration MUST be one-way, with **no compatibility shim left behind**.

### Constraints

- **FR-080**: This layer MUST carry **no vector-store or embedding-model dependency**: `sqlite-vec`, `fastembed`, mem0, chroma and LlamaIndex MUST NOT appear in the dependency set, and no vector may be computed, fetched or stored anywhere. Search is ripgrep where the machine has it and the built-in literal walk of FR-022 where it does not — neither is an index. `markitdown` is this layer's converter as well as the channel's; the importlinter contract MUST admit exactly those two consumers and no others.
- **FR-081**: The knowledge layer MUST NOT add any table to `coffer.db`, and MUST NOT create a directory of its own outside the knowledge root. A collection is a row in the kind-agnostic `resources` table like every other Resource; everything else this layer holds is a file the human can open.

## Success Criteria

- **SC-001**: A fact written by one agent is readable by a different agent through the catalogue, with no index step in between.
- **SC-002**: A file the human adds or edits outside Coffer is returned by the next call with no import, reindex or reconciliation.
- **SC-003**: An agent authorized for one collection cannot see another through any built-in tool.
- **SC-004**: The layer holds no knowledge-specific table in `coffer.db` and keeps no derived copy of a file's content anywhere.
- **SC-005**: A grep over the corpus returns matching file and line, including for CJK content, without a tokenizer.
- **SC-006**: A file added out-of-band is returned by the next `search` with nothing rebuilt in between: the installation holds no index directory, no sidecar and no reindex command to find.
- **SC-007**: A document sent from a channel is a Markdown file in the intended collection afterwards, with its original recoverable, and the agent reads it the same way as any other file.
- **SC-008**: `search` works on a fresh installation with nothing configured at all — no connection, no index, no setting.

## Assumptions

- The corpus stays in the hundreds of files. The catalogue still fits an agent's context at that size and ripgrep over that many files is instant, so `search` is an addition to catalogue-then-grep rather than a replacement. Tens of thousands of files, or a corpus an agent genuinely cannot navigate by name, would be a different design and a different decision — and the place embeddings would be reconsidered.
- Tidy rewrites files with no review step, so `.history/` is the whole safety net. It ships off by default for that reason.
- The internal connection is the one place user content may leave the machine, exactly as spec [channels](../channels/spec.md) FR-022 already establishes for voice. Search never uses it — it reads no further than the disk — so the only knowledge text that goes there is what a tidy pass (FR-050) or an ingested document's generated description (FR-034) sends.
