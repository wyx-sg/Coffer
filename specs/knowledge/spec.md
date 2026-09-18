# Feature Specification: Knowledge Layer

**Status**: Accepted
**Folder name**: this spec lives at `specs/knowledge/`, the spec id every inbound link and `scripts/audit_acceptance.py` keys on. It keeps that name although the layer merged with what used to be a separate Knowledge Base: the name is an identifier other documents and the acceptance audit resolve, not a description. The layer's revision history lives in the roadmap's revision log.

**Input**: Coffer holds **knowledge about the user's working environment**: their repositories, services, projects, the people they work with, the decisions and traps worth surviving a session. It is a **directory of Markdown files** in two lanes. The human and the agents write **source material** into `sources/`; Coffer's internal model curates that material into **topic documents** under `topics/`, and `topics/` is what an agent reads — with its own `Read`, at an absolute path, through no tool of Coffer's. See [Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md).

**Knowledge is not memory.** Knowledge is about the world — a platform's API contract, a service's ownership, a document someone published — and it arrives because a person, or an agent working with them, put it there. Memory is about the user and their projects, and it accrues on its own as agents work. They differ in every dimension that matters — who authors them, how they are partitioned, how they are delivered — so they are two layers: this one, filed by collection and **pulled** through a skill, and spec [memory](../memory/spec.md), partitioned by project and **pushed** at session start through a hook.

## The principle this layer answers to

**What a person writes is source material; what an agent reads is curated.** Every decision below follows from it. The two lanes are directories rather than a property, because "who may write here" is the one thing only a directory can say. A topic document is derived, so it may be rewritten freely and rebuilt from scratch. A source is not derived, so nothing but a person ever changes it. Metadata lives in the file rather than a database row because only the file is visible to both parties.

## The four invariants

1. **Sources are truth; topics are derived.** Every topic document MUST be reconstructible from the sources behind it. A topic that is not is a defect.
2. **Write is split.** `sources/` is written only by a person, an upload, or `coffer__write`. `topics/` is written only by the curation pass. There is no third writer of either.
3. **A topic MUST NOT reference another file by name.** Topic paths are chosen by curation and change as the corpus is reorganised; a name written into prose is a link that rots. Name the subject, not the file.
4. **Retrieval is the agent's own.** Coffer exposes no tool for reading, listing, grepping or searching knowledge. It delivers a skill carrying a catalogue and an absolute path; the agent reads the files with the tools it already has.

## What this layer is not

Everything below is a **standing constraint**, not a phase that has passed.

**No derived index of any kind.** No vectors, no sidecar, no FTS5, no chunking, no reindex. Both lanes are files and nothing stands between a query and them. This survives the redesign unchanged and is the one place the constitution's Persistence constraint binds this layer directly.

**No retrieval tool.** Coffer used to expose `list`, `grep`, `read` and `search`. It exposes none of them. An audit of 448 Claude Code sessions after the corpus was built found the delivered skill had never once been loaded and no knowledge tool had ever been called from that agent: the failure was never that literal matching missed, it was that nothing carried a hook the model could recognise. A tool an agent does not remember to call is not retrieval. What the agent already has — `Read`, `Grep` — needs no remembering, so the layer's job narrows to putting the right paths in front of it.

**No second retrieval surface on the web page.** A collection *is* two folders, so its page browses them and nothing else. The page is where a person reads and edits `sources/`; `topics/` is read-only there because it is read-only everywhere outside curation.

**No structure that carries meaning beyond write ownership.** `sources/` ÷ `topics/` is the only division the system assigns meaning to, and it means exactly "who may write here". There is no `global` ÷ `project-<ULID>` axis, no cwd-derived scope, no auto-provisioning and no scope display labels. Inside `sources/` the nesting is the person's; inside `topics/` it is curation's.

**No source tracking beyond the lane itself.** A source is a file in `sources/`; that is the whole of its provenance. There is no `source_mode`, no external-source table, no re-conversion on a schedule, and no hidden `.raw/` — an uploaded original is an ordinary, visible file in `sources/` beside the text extracted from it.

**Ingestion is an additional entrance, never a required one.** Putting a Markdown file in `sources/` stays a complete way to add knowledge. Upload exists because the filesystem is only reachable while the user is at the machine, and their live entrance is a phone.

## User Scenarios & Testing

### User Story 1 — One knowledge store, every agent (Priority: P1)

The developer works with Claude Code in the morning and Codex in the afternoon. In the morning an agent records that a service's login state is owned by `account.session`. By the afternoon that fact is in a topic document, and the second agent reads it, because both read the same directory. No copy diverges, because there is only one.

**Independent Test**: write a source through one MCP client; run a curation pass; confirm a topic document holding the fact, and read it back from a second client with a different agent identity.

### User Story 2 — Collections are the human's filing, and `enabled` is the switch (Priority: P1)

Some knowledge is a company's internal detail; some is about a side project. The developer creates a collection deliberately, files the material into it, and decides one thing about it: whether it is served at all. A collection they are not ready to hand to their agents is **disabled**, and no agent's delivered skill mentions it, its catalogue or any path inside it. Every enabled collection reaches every agent — the per-agent variant of this switch was withdrawn, because the skill it trimmed hands the agent the absolute knowledge root in the same breath (FR-010).

**Independent Test**: create two collections, disable one, and confirm each agent's delivered skill names the enabled one and names neither the disabled collection nor any path inside it.

### User Story 3 — Find the right file without an index and without a tool (Priority: P1)

An agent needs a fact it has no exact words for. The skill's description, already in its context, names the domains the corpus covers; the agent recognises one, loads the skill, and gets the whole catalogue — every topic document's path, title and description — plus the absolute root. It then reads the file with its own `Read`.

**Independent Test**: with a populated collection, confirm the delivered skill body carries every topic document's path/title/description and the absolute knowledge root, and that a path named in it resolves to a readable file.

### User Story 4 — The human curates the sources, not the topics (Priority: P2)

The developer drops a Markdown file into `sources/` from Finder, corrects a wrong line in a source in their editor, and deletes one that went stale. Each change is picked up and folded into the topics within the minute. They do not edit `topics/` — a correction goes into a source, and curation carries it through.

**Independent Test**: add a source out-of-band, confirm the scan picks it up and a topic document reflects it; confirm `topics/` is never presented as editable on any surface.

### User Story 5 — The agent knows what is in the corpus, not merely that it exists (Priority: P1)

A skill Coffer delivers names the domains the corpus covers in its description — the part that is always in the agent's context — and carries the full catalogue in its body. It arrives through the same channel that already delivers Coffer's other skills, so every managed agent gets it without a hook and without anything being written into the agent's own memory.

**Independent Test**: with two collections and a managed agent bound, confirm the skill in that agent's directory is a real file (not a shared link), that its description names the collections' subjects, and that its body lists each topic document.

### User Story 6 — Knowledge arrives through a conversation (Priority: P1)

The developer and an agent work something out together — why a build fails, who owns a service, what a flag actually does. The agent writes it down with `coffer__write`. It lands in `sources/` as raw material, and the next curation pass merges it into whichever topic document owns that subject, deduplicating against what is already there.

**Independent Test**: write two sources stating overlapping facts; run curation; confirm one topic document holds both facts and neither source was modified.

### User Story 7 — A document gets into the vault from wherever the user is (Priority: P1)

The developer is handed a PDF in a chat. They forward it to their Coffer channel, say which collection it belongs in, and both the original and the text extracted from it land in `sources/`. At the desk they do the same by dropping the file on the Knowledge page.

**Independent Test**: upload a non-Markdown document through the REST surface and confirm both the original and a Markdown file appear in `sources/`, and that a following curation pass produces a topic document from it.

### User Story 8 — A correction is a fact with a date on it (Priority: P2)

A source says a service counts daily actives with a plain Set; the topic document says HyperLogLog, because an older source said so. Curation resolves it in favour of the newer source and leaves the correction visible in the prose, so a reader learns both what is true and that it changed.

**Independent Test**: curate a source contradicting an existing topic document; confirm the new fact is what the document asserts and that the superseded one is still legible as a correction.

## Acceptance Scenarios

### Scenario: a written note lands in the sources lane

- **Given** a `shopee` collection created through `coffer knowledge create`
- **When** `coffer__write` is called against the daemon with the title
  `Account Gateway`, a description and a body
- **Then** the note is on disk at
  `~/.coffer/knowledge/shopee/sources/account-gateway.md` — inside `sources/`,
  the file name is the title's own slug, and no id appears in it anywhere
- **And** nothing is written under `topics/` by that call

### Scenario: frontmatter carries title, description and actor

- **Given** an empty `shopee` collection
- **When** a source is written into it with a title, a description and `actor`
  `user`
- **Then** the file's YAML frontmatter holds `title`, `description`, `actor`,
  `created_at` and `updated_at`, carries the title and the actor it was given,
  and the body follows the fence unchanged

### Scenario: a source added out-of-band is curated by the next sweep

- **Given** a Markdown file placed straight into `shopee/sources/` as
  `dropped-by-hand.md`, by a file manager rather than by Coffer
- **When** the curation sweep runs, with no import or registration step in
  between
- **Then** a topic document under `shopee/topics/` carries the fact the file
  stated, and the source file's frontmatter has gained `coffer_ingested_at`

### Scenario: the catalogue lists collections with their README description

- **Given** a collection created with the description "First description",
  whose `README.md` is then edited by hand to open with "Edited by hand."
- **When** `coffer knowledge collections --json` runs
- **Then** the collection's `description` is the README's first paragraph as
  edited, not the string the creation call supplied — the description is read
  off disk on every listing, never out of a row

### Scenario: an unknown collection is an error, never auto-created

- **Given** a knowledge root with no `typo` collection in it
- **When** `coffer knowledge ls typo --json` runs
- **Then** the command exits non-zero and no `typo` directory exists
  afterwards: a read never provisions a collection

### Scenario: a disabled collection is absent from every agent's skill

- **Given** a disabled `shopee` collection and an enabled `personal` one, both
  holding topic documents
- **When** the skill is rendered for each of two agents and delivered
- **Then** neither copy names `shopee`, its catalogue, or any path inside it
- **And** both copies name `personal` and list its catalogue — `enabled` is the
  only thing that decides, and it decides the same way for every agent

### Scenario: the two agents' skill files are independent copies

- **Given** both agents registered, a symlink left at one agent's
  `skills/coffer-knowledge` by the previous shared-master delivery, and the
  knowledge skill delivered to each
- **When** each agent's `<config_dir>/skills/coffer-knowledge/SKILL.md` is read
- **Then** neither is a symlink, the stale link has been replaced rather than
  written through, and editing one does not change the other — the two copies
  carry the same text, and they are still two files, so one can be re-rendered,
  staled or removed without reaching through into the other

### Scenario: the skill body carries the catalogue and the absolute root

- **Given** a collection holding three topic documents
- **When** the skill is rendered for an agent
- **Then** its body carries each document's collection-relative path, title and
  description, and the absolute path of the knowledge root, and it instructs
  the agent to read those files with its own tools
- **And** the frontmatter `description` names the collection's subject, taken
  from the collection's own `README.md`, so a model matching on it has
  something to match

### Scenario: an upload lands both the original and its text in sources

- **Given** a collection and a document sent into it — `notes.md` through the
  ingest service, `Runbook.txt` through `POST /api/v1/knowledge/upload`
- **When** the upload is accepted (201 from the route)
- **Then** the original sits in `sources/` under its own name and extension,
  byte-identical to what was sent, and the extracted Markdown beside it with
  frontmatter carrying `actor: user`
- **And** an upload whose extraction *is* the upload — a `.md` file — lands as
  exactly one file, reported as its own original, rather than as two copies the
  curation pass would read as two sources
- **And** no hidden `.raw/` directory exists anywhere in the collection

### Scenario: an upload of an unsupported type is refused with its reason

- **Given** a collection, and a file whose type no converter handles —
  `archive.bin` at the service, `payload.exe` at the route
- **When** it is uploaded
- **Then** the service raises `UnsupportedDocument` and the route answers 400
  `INGEST_REJECTED` whose details name `reason` `unsupported_type` and
  `doc_type` `exe`, and the collection's `sources/` is left with no file at all

### Scenario: a document is never stored half-converted

- **Given** a document whose converter succeeds but yields no text, as an
  image-only PDF does
- **When** it is uploaded
- **Then** the upload is refused with the reason naming the document type, and
  neither the extracted Markdown nor the original is written

### Scenario: a document forwarded to a channel lands in a collection

- **Given** a paired channel whose owner has just sent `note.txt` as an
  attachment, and one existing collection named `research`
- **When** the owner follows it with the plain text `/save research`
- **Then** the ingest service is called exactly once — that collection, that
  file name, those bytes, `actor` `user` and the channel's own default agent —
  and the channel replies with a confirmation naming both the file and the
  collection

### Scenario: curation writes topics and never touches sources

- **Given** a collection holding two sources stating overlapping facts and an
  internal connection configured
- **When** a curation pass runs over it
- **Then** `topics/` holds a document carrying both facts, and both source
  files are byte-identical to what they were except for the
  `coffer_ingested_at` key added to their frontmatter

### Scenario: curation is a no-op when no internal model is configured

- **Given** a collection with a source in it and no internal model connection
  at all
- **When** a curation pass is run over it
- **Then** it reports `no_model`, no topic document is written, and the
  source's `coffer_ingested_at` is **not** set — so the material is curated
  once a model is configured rather than silently skipped forever

### Scenario: a pass is bounded to a handful of writes

- **Given** a collection holding twenty topic documents and one new source
- **When** a curation pass runs and its agent attempts eleven writes
- **Then** the pass stops at the eighth and reports the bound, and the writes
  that did land are complete files rather than truncated ones

### Scenario: a pass sees candidates and the catalogue, never the sources lane

- **Given** a collection whose `sources/` holds the triggering source and nine
  others
- **When** the pass is assembled
- **Then** the model is given the triggering source, at most five candidate
  topic documents in full, and every topic document's title and description —
  and the pass's tool surface offers no way to read, list or write anything
  under `sources/`

### Scenario: the pass is instructed that a contradicting source wins

- **Given** the instructions a curation pass hands its model
- **When** they are read
- **Then** they state that where a source contradicts a topic document the
  source wins, and that the superseded statement must stay legible with the
  date it changed — the rule lives in the instructions because no code can
  adjudicate a contradiction, so the instructions are what this scenario pins

### Scenario: a curated topic carries no file-name reference

- **Given** a pass whose model writes a document whose body names another
  document's file name
- **When** the write is applied
- **Then** it is refused and reported, because invariant 3 is enforced at the
  write rather than asked for in a prompt

### Scenario: a source is curated once, not on every sweep

- **Given** a source already carrying `coffer_ingested_at` later than its own
  modification time
- **When** the sweep runs
- **Then** no pass is started for it; and with the file touched afterwards, the
  next sweep does start one

### Scenario: a second curation pass over the same collection is refused while the first is running

- **Given** two collections, and a pass already in flight over `shopee` held
  in the daemon's in-flight registry
- **When** a pass is requested for `shopee` over the route that starts one
- **Then** it is refused 409 `UPKEEP_ALREADY_RUNNING` rather than queued,
  while the same request for the other collection answers 200
- **And** once the in-flight record is released the previously refused request
  answers 200

### Scenario: exactly one built-in knowledge tool appears in the client tool list

- **Given** a real daemon with an upstream MCP server registered, driven over
  its `/mcp` endpoint by the MCP SDK so the SDK's own models validate every
  frame
- **When** the client initializes and calls `tools/list`
- **Then** `coffer__write` is in the listing beside the upstream server's own
  tools, and `coffer__list`, `coffer__grep`, `coffer__read`, `coffer__search`
  and `coffer__delete` are **absent**
- **And** a `coffer__write` call over that same session lands a file in the
  collection's `sources/`

### Scenario: a path escaping the knowledge root is rejected

- **Given** the single path-construction module every surface resolves through
- **When** it is asked to resolve `../etc/passwd`, `shopee/../../outside`, or
  any path naming a hidden entry
- **Then** each one raises `UnsafeKnowledgePath` rather than returning a
  location outside the root

### Scenario: the viewer edits sources and renders topics read-only

- **Given** a collection page whose two trees hold one file each
- **When** each file's row is clicked
- **Then** the source offers open-in-editor, reveal and delete, and the topic
  document offers open and reveal only — no delete, no editor, and a note
  saying it is written by curation

### Scenario: migration moves the corpus into sources and clears topics

- **Given** a pre-migration vault — named Markdown files at a collection's
  root, a `.raw/` directory beside them and a `.history/` directory
- **When** the database is upgraded
- **Then** every Markdown file that was content is under that collection's
  `sources/`, every `.raw/` original is under `sources/` too as a visible file,
  `topics/` exists and is empty, and `.raw/` and `.history/` are gone
- **And** the collection's `README.md` stays at the collection root, outside
  both lanes

## Requirements

### Storage

- **FR-001**: Knowledge MUST be stored as files under `~/.coffer/knowledge/<collection>/` in exactly two lanes: `sources/`, holding the material a person or an agent contributed, and `topics/`, holding the documents curation derives from it. The files are the only copy; the system MUST NOT keep a retrieval index of any kind — no vectors, no sidecar, no cache — so every answer is read off disk at call time.
- **FR-002**: A file's **path is its identity** in both lanes. There MUST be no separate id field in frontmatter and no id-to-path mapping anywhere. File names MUST be human-readable slugs derived from the title; a collision appends a short suffix.
- **FR-003**: Every Markdown file in either lane MUST carry YAML frontmatter with `title`, `description`, `actor` (`agent` | `user`), `created_at` and `updated_at`. A file in `sources/` MAY additionally carry `coffer_ingested_at`, which Coffer writes and nothing else reads; no other key is permitted in either lane. A non-Markdown file in `sources/` carries no frontmatter, and the Markdown extracted from it carries the lane's.
- **FR-004**: `sources/` MAY contain arbitrarily nested subdirectories, and the system MUST NOT assign them meaning, require them, or create them. The nesting under `topics/` is **chosen by curation**, which MAY create and remove directories there.
- **FR-005**: Hidden entries (dot-prefixed) MUST be excluded from every listing. The system itself MUST write none: `.history/` and `.raw/` are removed, their jobs taken by `sources/` being the recoverable truth and being visible.
- **FR-006**: Every name that becomes a path segment MUST pass a traversal guard, and path construction MUST live in exactly one module.
- **FR-007**: A collection's `README.md` MUST sit at the collection root, outside both lanes, and MUST NOT be curated, listed as content, or counted.

### Collections

- **FR-008**: A **collection** is a top-level subdirectory of the knowledge root and is one `knowledge` Resource. It MUST be created deliberately — through the REST/CLI/UI surface — and MUST NOT be provisioned by a read, a write, or an agent's working directory. Creating one MUST create both lanes.
- **FR-009**: The system MUST NOT derive any boundary from the agent's cwd. There MUST be no `global` scope, no `project-<ULID>` naming, no git-root resolution and no scope-to-project-root mapping table.
- **FR-010**: A collection MUST NOT carry the Resource framework's **per-agent reach**. Every **enabled** collection MUST be named, catalogued and served to **every** agent, and a **disabled** collection MUST appear in no agent's delivered skill — not its name, not its catalogue, not its description, not a path inside it. The per-agent form is withdrawn because it never chose anything and could not have: in the live vault every collection's scope was null, and its only effect would have been to omit a collection from one agent's rendered skill while that same skill hands the agent the absolute knowledge root and tells it to grep the whole thing. It was non-disclosure, and it disclosed anyway. `enabled` is now the only gate on this layer, and it is a real one. `coffer__write` MUST refuse a write naming a collection that does not exist or is disabled, and MUST answer with the collections that **are** available.
- **FR-011**: A collection's one-line description MUST be the first paragraph of its `README.md`, absent when there is none, and MUST be read off disk on every listing. It MUST NOT be stored in the database — not even in the `resources` row's own generic `description` column, which for this kind stays empty: a copy written once and read by nothing is wrong from the first time the person edits the file. It is also what the delivered skill's own description draws on (FR-036), so a collection that fails to describe itself is a collection an agent never recognises.
- **FR-012**: What this layer serves is **files on disk**, and the system MUST describe it as such wherever it is presented: a delivered path is the whole of the access story, because an agent handed the knowledge root reads anything under it with the shell tools it already has. `enabled` is therefore a **delivery** gate, and MUST NOT be presented as a filesystem boundary either — a disabled collection is one no skill names, not one no process can open.

### The sources lane

- **FR-013**: `sources/` MUST be writable by exactly three entrances — a person using their own tools, an upload, and `coffer__write` — and by nothing else. Curation MUST NOT write, move or delete anything in it.
- **FR-014**: `coffer__write` MUST create a file in a named collection's `sources/` from `title`, `description` and body text, or replace one at an existing source path. A write MUST be a plain file write — no LLM, no conversion, no indexing step — and MUST record one `mcp_invocations` row and one audit event naming the calling agent, taken from the session's handshake identity (spec [mcp-gateway](../mcp-gateway/spec.md) FR-013) written in as an `agent` argument no tool advertises and no caller can set. A write naming a collection that does not exist or is disabled MUST be refused with the collections that **are** available: that names exactly what this agent's own delivered skill already lists, and it turns a dead end into a correction for a model that reached for the tool without opening the skill.
- **FR-015**: Placing a file in `sources/` MUST remain a complete way to add knowledge — no import, no registration, no conversion step. Ingestion below is an additional entrance, never a required one.
- **FR-016**: The system MUST accept a document upload into a named collection and convert it to Markdown. Supported inputs MUST be exactly what `markitdown` handles plus plain text and CSV; an unsupported type MUST be refused with the type named, never stored half-converted. Both the **original** and the extracted Markdown MUST land in `sources/`, the original under its own name and extension and byte-identical to what was sent — **except** when the extraction is the upload itself, as it is for a Markdown or plain-text file, where the file that landed *is* the original and a second copy would be one document in the lane twice and two curation passes over the same facts.
- **FR-017**: The extracted Markdown MUST carry FR-003's frontmatter — `title` from the document (falling back to its file name) and `description` filled in, by the internal connection when one is configured and from the document's opening prose when not.
- **FR-018**: A document sent to a Coffer channel MUST be ingestible into a collection through the same path, so the phone and the Knowledge page are two ends of one entrance (spec [channels](../channels/spec.md)). The channel MUST confirm the collection with the owner before storing, and MUST NOT store anything from a non-owner.
- **FR-019**: Upload MUST be bounded: one file per call, a size ceiling, and a refusal that names the limit. A conversion failure MUST leave neither file behind.
- **FR-020**: Deleting a source MUST be a person's action, offered on the REST, CLI and web surfaces. No agent-facing tool may delete anything in either lane.

### Curation

- **FR-021**: Curation MUST be the **only** writer of `topics/`. It is a bounded agentic pass driven by the internal model connection, whose tool surface is exactly `list_topics`, `read_topic`, `write_topic` and `retire_topic`. Nothing in that surface may reach `sources/`.
- **FR-022**: A pass MUST be triggered when material changes: immediately for the entrances Coffer serves itself (`coffer__write`, upload, channel ingest), and by a **sweep on an interval** that finds files changed out-of-band by comparing each source's modification time with its `coffer_ingested_at`. The interval MUST be read per sweep rather than captured at boot.
- **FR-023**: A pass MUST be assembled from a **bounded** context: the triggering source in full, at most **five** candidate topic documents in full, and the collection's full catalogue of titles and descriptions. Candidates MUST be selected by literal matching of distinctive strings drawn from the source against `topics/`; the catalogue is present so the model can conclude that none of the candidates is the right home and open a new document instead.
- **FR-024**: A pass MUST preserve every fact it is shown. Merging MUST integrate rather than regenerate, and `retire_topic` MUST be permitted only for a document whose content the same pass has written elsewhere.
- **FR-025**: A pass MUST be bounded to at most **eight** writes and to a recursion limit, and MUST report reaching either. A single source MUST NOT be able to trigger a corpus-wide rewrite.
- **FR-026**: Where a source contradicts a topic document, the **source wins**, and the resulting document MUST keep the superseded statement legible as a correction with the date it changed. A contradiction is knowledge about the world changing, and when it changed is itself worth keeping.
- **FR-027**: A topic document MUST NOT contain a reference to another knowledge file by file name or path. This MUST be enforced at `write_topic` — a write that carries one is refused and reported — rather than requested in a prompt.
- **FR-028**: After a pass completes, every source it consumed MUST have `coffer_ingested_at` written into its frontmatter, and nothing else about the file may change. A pass that does not complete MUST leave the watermark unset, so the material is curated later rather than lost.
- **FR-029**: With no internal model connection configured, a pass MUST be a clean no-op reporting `no_model`: no topic written, no watermark set, no directory created.
- **FR-030**: Only **one pass per collection** may run at a time, whoever started it. A manual trigger arriving while a pass is in flight MUST be refused (`UPKEEP_ALREADY_RUNNING`, 409) rather than queued, and the sweep MUST skip a collection already being curated. Which collections are being curated right now MUST be readable. The record is per-daemon and does not outlive it.
- **FR-031**: A pass and a vault-sync converge round MUST NOT overlap — both write the vault — so they MUST take the same lock, and a pass MUST be skipped while a conflict or pending confirmation is outstanding (spec [vault-sync](../vault-sync/spec.md)).
- **FR-032**: Because a pass rewrites synced content unattended, it MUST run on one machine only: the `internal_engine_config` pair `auto_curate_enabled` and `curate_owner_machine_id` MUST both be read on every sweep, so the switch reads as *on, here* rather than merely *on*. Unlike the pass it replaces, `auto_curate_enabled` defaults **on**, because curation is now the only path from a source to something an agent can read.

### Tools and delivery

- **FR-033**: Coffer's MCP gateway MUST expose exactly **one** built-in knowledge tool: `coffer__write`. There MUST be no `list`, `grep`, `read`, `search` or `delete`. An agent reads knowledge with its own file tools at the paths the skill gives it.
- **FR-034**: Coffer MUST write a generated **knowledge skill** into each registered agent's own skill directory — the same `<config_dir>/skills/` spec [skill-manager](../skill-manager/spec.md) delivers into, but as a file this layer owns and regenerates rather than a registered skill Resource, because its content is derived from the catalogue and is rewritten whenever the catalogue moves, which is not something a person curating a bundle can keep up with. This layer MUST NOT push anything into a session of its own accord and MUST NOT write into any agent's own memory files: knowledge is pulled. Session-start delivery belongs to spec [memory](../memory/spec.md), which carries its own budget and its own consent.
- **FR-035**: The skill MUST be **written into each agent's own directory, not linked**: each agent's copy MUST be real bytes rather than a link into one master folder, and a delivery MUST replace a link an earlier design left behind rather than write through it. Its text is now the same for every agent (FR-010), so what this requires is independence of the *file*, not difference in the content: a copy that is a link into a shared master is a copy this layer cannot re-render, stale or reclaim for one agent without doing it to all of them. It MUST be re-rendered whenever the catalogue changes — after a curation pass, or a collection's creation, deletion, enabling or disabling — and delivery MUST never raise: a failure leaves the corpus readable at paths a person can still give an agent.
- **FR-036**: The skill's **frontmatter description** MUST name the subjects the enabled collections cover, drawn from their READMEs. It is the only part of this layer that is always in a model's context, so it MUST carry matchable specifics rather than a description of the layer.
- **FR-037**: The skill's **body** MUST carry the absolute path of the knowledge root, and, for each enabled collection, every topic document's collection-relative path, title and description. It MUST instruct the agent to read those files with its own tools and to reach for `coffer__write` when it learns something durable.
- **FR-038**: The MCP gateway's own instructions text MUST describe this layer as it now is — a directory read with the agent's own tools, with the catalogue in the skill — and MUST NOT name a retrieval tool.

### Surfaces

- **FR-039**: The REST API under `/api/v1/knowledge` and the `coffer knowledge` CLI group MUST cover: create a collection, list a lane at a path, read a file, write a source, upload a document, delete a source, and trigger curation. Collection deletion goes through the Resource framework (`DELETE /api/v1/resources/{uid}`). There MUST be no index, reindex, check-sources, update-source or embedding-configuration endpoint, no settings endpoint for the cwd-derived scope axis FR-009 forbids, and no per-agent reach endpoint for this kind (FR-010) — a collection's one switch is `enabled`, which the framework already serves. These surfaces serve the human and the UI; they are not an agent's retrieval path.
- **FR-040**: The web UI MUST present a collection as **two trees** — `sources/` and `topics/` — with the file chosen from either rendered read-only in the pane beside them, through the unified file preview with open-in-external-editor and reveal-in-file-manager. A source MUST additionally offer delete, naming the exact path before it runs, reporting a refusal in place, and leaving the preview on no file afterwards. A topic document MUST offer no delete and no editor, and MUST be labelled as written by curation. The page MUST offer upload into the collection in view and a manual curation trigger that reports a pass already in flight. It MUST NOT carry a retrieval box: the one input beside a tree narrows the names already on screen, client-side.
- **FR-041**: Read responses MUST carry the file's absolute path and its containing folder's absolute path.

### Migration

- **FR-042**: One migration MUST rewrite the on-disk corpus: every content file at a collection's root moves into that collection's `sources/`, every `.raw/` original moves into `sources/` as a visible file beside it, `topics/` is created empty, and `.raw/` and `.history/` are removed. `README.md` stays at the collection root. It MUST also retire the previous delivery: the shared `coffer-knowledge` skill Resource, its master folder and every link to it go, so no agent is left holding a stale shared copy beside its generated one. The migration MUST be one-way, with **no compatibility shim left behind**.
- **FR-043**: The migration MUST back the knowledge root up before it writes, and MUST report where. The corpus is the user's own writing and this migration empties the lane an agent reads until the first curation pass runs.
- **FR-044**: `auto_curate_enabled` MUST be seeded on, and `curate_owner_machine_id` MUST default to the machine the migration runs on, so a vault that has just been migrated curates itself rather than staying dark until the setting is found.

### Constraints

- **FR-045**: This layer MUST carry **no vector-store or embedding-model dependency**: `sqlite-vec`, `fastembed`, mem0, chroma and LlamaIndex MUST NOT appear in the dependency set, and no vector may be computed, fetched or stored anywhere. `markitdown` is this layer's converter as well as the channel's; the importlinter contract MUST admit exactly those two consumers and no others.
- **FR-046**: The knowledge layer MUST NOT add any table to `coffer.db`, and MUST NOT create a directory of its own outside the knowledge root. A collection is a row in the kind-agnostic `resources` table like every other Resource; everything else this layer holds is a file the human can open.

## Success Criteria

- **SC-001**: A fact written by one agent is readable by a different agent as a curated topic document, with no index step in between.
- **SC-002**: A source the human adds or edits outside Coffer is folded into the topics by the next sweep, with no import or reconciliation.
- **SC-003**: A disabled collection's name, catalogue and paths appear in no agent's delivered skill, and every enabled collection's appear in all of them.
- **SC-004**: The layer holds no knowledge-specific table in `coffer.db` and keeps no derived copy of a file's content anywhere outside `topics/`, which is itself rebuildable from `sources/`.
- **SC-005**: Deleting `topics/` entirely and re-running curation reproduces a corpus carrying the same facts.
- **SC-006**: The gateway advertises exactly one knowledge tool, and an agent reaches every topic document without calling it.
- **SC-007**: A document sent from a channel is a file in the intended collection's `sources/` afterwards, with its original beside it.
- **SC-008**: Every agent holds its own `SKILL.md` — real bytes in its own skill directory, not a link into a shared master — so one agent's copy is re-rendered, staled or reclaimed without touching another's.

## Assumptions

- The corpus stays in the hundreds of files. A catalogue of every topic document fits a skill body at that size — measured at ~5.2K tokens for 58 documents — so the agent never has to guess what exists. Tens of thousands of files would be a different design and the place embeddings would be reconsidered.
- Curation rewrites `topics/` with no review step. `sources/` is the safety net, which is why nothing but a person may write there and why a pass that fails leaves its watermark unset.
- The internal connection is the one place user content may leave the machine, exactly as spec [channels](../channels/spec.md) FR-019 already establishes for voice. Curation and an ingested document's generated description are the only things this layer sends there.
- A source is small enough to be handed to a model whole. A person writing a note, or a document a person uploads, is bounded by what a person produces; a pass that meets one too large for its context reports rather than truncates.
