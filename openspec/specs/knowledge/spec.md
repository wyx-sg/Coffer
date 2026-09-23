# Knowledge Layer

## Purpose

Coffer holds **knowledge about the user's working environment**: their repositories, services, projects, the people they work with, the decisions and traps worth surviving a session. It is a **directory of Markdown files**, and each collection is **one tree of documents** that the person and Coffer's internal model write together. New knowledge — an uploaded document parsed into Markdown, a fact an agent writes down — arrives as **material** in a hidden inbox, and Coffer's curation pass merges what is new in it into the documents. The documents are what an agent reads — with its own `Read`, at an absolute path, through no tool of Coffer's. Every agent reads the same directory, so what one agent records in the morning a different agent reads in the afternoon, and no copy diverges because there is only one. See [Knowledge Is Plain Files](../../../docs/decisions/knowledge-is-plain-files.md). The spec id `knowledge` is kept although the layer merged with what used to be a separate Knowledge Base: it is the identifier inbound links and the acceptance audit resolve, not a description.

**Knowledge is not memory.** Knowledge is about the world — a platform's API contract, a service's ownership, a document someone published — and it arrives because a person, or an agent working with them, put it there. Memory is about the user and their projects, and it accrues on its own as agents work. They differ in who authors them, how they are partitioned and how they are delivered, so they are two layers: this one, filed by collection and **pulled** through a skill, and [memory](../memory/spec.md), partitioned by project and **pushed** at session start.

**Knowledge is co-created.** A person and Coffer's model edit the same documents. Source files arrive in whatever format they were written in; on arrival they are parsed into Markdown and what is new in them is **appended to the knowledge base** — merged into the documents that already cover the subject — rather than kept as a file of their own. From then on the documents are edited by whoever has something to add: a person in their editor, an agent with its own file tools, the curation pass carrying one change through to the rest. A correction is a fact with a date on it: curation keeps the superseded statement legible so a reader learns both what is true and that it changed. Metadata lives in the file rather than a database row because only the file is visible to all of them. The layer answers to four invariants:

1. **A collection is one tree of documents, and every writer shares it.** There is no lane that belongs to one writer; what protects a person's work is the rule that their edit is never reverted, not a directory.
2. **New knowledge arrives as material, and material is merged.** Every entrance submits into the collection's hidden `.inbox/`; a curation pass folds each item into the documents and deletes it. With no model to merge it, it becomes a document of its own on arrival.
3. **A document MUST NOT reference another file by name.** Document paths change as the corpus is reorganised; a name written into prose is a link that rots. Name the subject, not the file.
4. **Retrieval is the agent's own.** Coffer exposes no tool for reading, listing, grepping or searching knowledge. The catalogue and the path ride in Coffer's own delivered skill, `coffer-guide`; the agent reads the files with the tools it already has.

These are **standing constraints**, not a phase that has passed: no derived index of any kind, no retrieval tool (an audit of 448 Claude Code sessions found the old tools were never called — a tool an agent does not remember to call is not retrieval), no second retrieval surface on the web page, no directory that carries meaning, and no kept originals. Ingestion is an additional entrance, never a required one: writing a Markdown document with any editor stays a complete way to add knowledge, and upload exists because the user's live entrance is often a phone.

Assumptions: the corpus stays in the hundreds of files, so a catalogue of every document fits a skill body (measured at ~5.2K tokens for 58 documents); tens of thousands of files would be a different design and the place embeddings would be reconsidered. Curation rewrites documents with no review step; what stands between a person's work and a bad pass is that a person's edit is never reverted, the eight-write bound, one pass per collection, the audit event every pass records, and — where vault sync is configured — the vault's git history. The internal connection is the one place user content may leave the machine, exactly as [channels](../channels/spec.md) "Transcribe inbound voice only when the user opted in" establishes for voice; curation and an ingested document's generated description are the only things this layer sends there. One item is small enough to hand a model whole; a pass that meets one too large for its context reports rather than truncates.

## Requirements

### Requirement: Store each collection as one tree of Markdown files
Knowledge MUST be stored as files under `~/.coffer/knowledge/<collection>/`, each collection **one tree of Markdown documents** that people and Coffer's curation pass write together. There MUST be no directory division inside a collection that says who may write where. The files are the only copy; the system MUST NOT keep a retrieval index of any kind — no vectors, no sidecar, no FTS5, no chunking, no reindex, no cache — so every answer is read off disk at call time.

#### Scenario: keep no index beside the documents
- **GIVEN** a `shopee` collection holding one document written through Coffer
- **WHEN** the knowledge root is walked, and the document's file is then rewritten on disk by hand
- **THEN** the only files under the collection are the document itself and nothing Coffer derived from it — no index, sidecar or cache file
- **AND** the next read through the service returns the hand-written text, with no reindex step in between

### Requirement: Use the file path as a document's identity
A file's **path is its identity**. There MUST be no separate id field in frontmatter and no id-to-path mapping anywhere. File names MUST be human-readable slugs derived from the title; a collision appends a short suffix.

#### Scenario: name a file by its title and suffix a collision
- **GIVEN** an empty `shopee` collection and no internal model configured
- **WHEN** two pieces of material titled `Session Ownership` are submitted
- **THEN** the two documents are `shopee/session-ownership.md` and `shopee/session-ownership-2.md`
- **AND** neither file's frontmatter carries an `id` key

### Requirement: Carry title, description and actor in frontmatter
Every document and every inbox item MUST carry YAML frontmatter with `title`, `description`, `actor` (`agent` | `user`), `created_at` and `updated_at`. A document curation has had in front of it additionally carries `coffer_curated_at`, which Coffer writes and the sweep reads (see "Run curation on a sweep and on demand", "Settle an item only after its pass completes"). Those six keys are what Coffer writes; any other key a person put in a document MUST be kept, in place and with its value unchanged, whenever Coffer rewrites or stamps the file — a document is the person's as much as Coffer's.

#### Scenario: frontmatter carries title, description and actor
- **GIVEN** an empty `shopee` collection
- **WHEN** a document is written into it with a title, a description and `actor` `user`
- **THEN** the file's YAML frontmatter holds `title`, `description`, `actor`, `created_at` and `updated_at`, carries the title and the actor it was given, and the body follows the fence unchanged

### Requirement: Allow nesting without giving it meaning
A collection MAY contain arbitrarily nested subdirectories, and the system MUST NOT assign them meaning or require them. There is no `sources/` ÷ `topics/` and no `notes/` ÷ `docs/` division. The nesting is **chosen by whoever files a document** — a person, or curation — and either MAY create, move and remove directories.

#### Scenario: list and catalogue a nested document at its own path
- **GIVEN** a `shopee` collection holding a document a person filed at `shopee/a/b/deep.md`
- **WHEN** the level `shopee/a/b` is listed and the collection's catalogue is read
- **THEN** the listing names `shopee/a/b/deep.md` as a document
- **AND** the catalogue carries it at that nested path, with no folder required or renamed

### Requirement: Hide dot-prefixed entries except the inbox
Hidden entries (dot-prefixed) MUST be excluded from every listing, count of documents and catalogue. The system itself MUST write exactly one: a collection's `.inbox/`, where submitted material waits to be merged (see "Submit every entrance's input as material"). An inbox item MUST be deleted once a pass has merged it or it has been promoted (see "Settle an item only after its pass completes", "Promote material directly when no model is configured"), and MUST NOT be addressable through any surface. `.history/` and `.raw/` stay removed; nothing is kept of what a pass replaced or of the document an upload arrived in.

#### Scenario: leave hidden entries out of every listing
- **GIVEN** a `shopee` collection holding one document, one item waiting in `.inbox/`, and a file a person put under `.scratch/`
- **WHEN** the collection is listed, its document count read and its catalogue rendered
- **THEN** each names the one document only, and the count is one
- **AND** reading the inbox item through the read route is refused

### Requirement: Guard every path through one module
Every name that becomes a path segment MUST pass a traversal guard, and path construction MUST live in exactly one module. A path that names a document MUST lie inside a collection and MUST NOT be the collection itself or its `README.md`.

#### Scenario: a path escaping the knowledge root is rejected
- **GIVEN** the single path-construction module every surface resolves through
- **WHEN** it is asked to resolve `../etc/passwd`, `shopee/../../outside`, or any path naming a hidden entry — `shopee/.inbox/material.md` included
- **THEN** each one raises `UnsafeKnowledgePath` rather than returning a location outside the root

### Requirement: Keep the collection README out of the corpus
A collection's `README.md` MUST sit at the collection root and MUST NOT be curated, listed as a document, or counted.

#### Scenario: keep the README out of listings, counts and curation
- **GIVEN** a `shopee` collection whose root holds a `README.md` edited after it was created and one document
- **WHEN** the collection is listed, counted and swept for pending items
- **THEN** the listing names only the document, the count is one, and the README is not owed a pass

### Requirement: Create collections only deliberately
A **collection** is a top-level subdirectory of the knowledge root and is one `knowledge` Resource. It MUST be created deliberately — through the REST/CLI/UI surface — and MUST NOT be provisioned by a read, a write, or an agent's working directory. Creating one creates its directory and nothing inside it but an optional `README.md`.

#### Scenario: an unknown collection is an error, never auto-created
- **GIVEN** a knowledge root with no `typo` collection in it
- **WHEN** `coffer knowledge ls typo --json` runs
- **THEN** the command exits non-zero and no `typo` directory exists afterwards: a read never provisions a collection

### Requirement: Derive no boundary from the working directory
The system MUST NOT derive any boundary from the agent's cwd. There MUST be no `global` scope, no `project-<ULID>` naming, no git-root resolution, no scope-to-project-root mapping table, no auto-provisioning and no scope display labels.

#### Scenario: refuse a write to a scope name instead of resolving it
- **GIVEN** a knowledge root holding only a `shopee` collection
- **WHEN** `coffer__write` names the collection `global`
- **THEN** the write is refused with `shopee` named as the available collection
- **AND** no `global` directory and no `project-` directory exists afterwards

### Requirement: Gate collections with enabled alone
A collection MUST NOT carry the Resource framework's **per-agent reach**. Every **enabled** collection MUST be named, catalogued and served to **every** agent, and a **disabled** collection MUST appear in no agent's delivered skill — not its name, not its catalogue, not its description, not a path inside it. The per-agent form is withdrawn because it never chose anything and could not have: in the live vault every collection's scope was null, and its only effect would have been to omit a collection from one agent's rendered skill while that same skill hands the agent the absolute knowledge root and tells it to grep the whole thing. It was non-disclosure, and it disclosed anyway. `enabled` is now the only gate on this layer, and it is a real one. `coffer__write` MUST refuse a write naming a collection that does not exist or is disabled, and MUST answer with the collections that **are** available.

#### Scenario: a disabled collection is absent from every agent's skill
- **GIVEN** a disabled `shopee` collection and an enabled `personal` one, both holding documents
- **WHEN** the guide skill is re-rendered and seeded into its master folder
- **THEN** the master `SKILL.md` names neither `shopee`, its catalogue, nor any path inside it
- **AND** it names `personal` and lists its catalogue — `enabled` is the only thing that decides, and, because every agent reads the one master, it decides the same way for every agent

### Requirement: Read a collection's description from its README
A collection's one-line description MUST be the first paragraph of its `README.md`, absent when there is none, and MUST be read off disk on every listing. It MUST NOT be stored in the database — not even in the `resources` row's own generic `description` column, which for this kind stays empty: a copy written once and read by nothing is wrong from the first time the person edits the file. It is also what the delivered skill's own description draws on (see "Describe Coffer and the collections' subjects in the skill description"), so a collection that fails to describe itself is a collection an agent never recognises.

#### Scenario: the catalogue lists collections with their README description
- **GIVEN** a collection created with the description "First description", whose `README.md` is then edited by hand to open with "Edited by hand."
- **WHEN** `coffer knowledge collections --json` runs
- **THEN** the collection's `description` is the README's first paragraph as edited, not the string the creation call supplied — the description is read off disk on every listing, never out of a row

### Requirement: Present knowledge as files on disk
What this layer serves is **files on disk**, and the system MUST describe it as such wherever it is presented: a delivered path is the whole of the access story, because an agent handed the knowledge root reads anything under it with the shell tools it already has. `enabled` is therefore a **delivery** gate, and MUST NOT be presented as a filesystem boundary either — a disabled collection is one no skill names, not one no process can open.

#### Scenario: the guide hands over files to read with the agent's own tools
- **GIVEN** an enabled collection holding one document
- **WHEN** the guide skill's catalogue is rendered
- **THEN** it tells the agent to read each document at `<root>/<collection>/<path>` with its own file tool and names the directory the collection's files live under
- **AND** it names no Coffer tool as the way to read a document

### Requirement: Submit every entrance's input as material
Every entrance Coffer serves — `coffer__write`, the CLI's `write` and its route `POST /api/v1/knowledge/material`, an upload, and a channel's `/save` — MUST **submit material** into the named collection's `.inbox/` rather than write a document. What becomes of material is curation's to decide (see "Curate through a fenced four-tool pass"): which document it belongs in, what in it is new, and what it corrects. The one exception is "Promote material directly when no model is configured", where no model is configured to decide and the material becomes a document as it stands.

#### Scenario: the CLI and the material route leave material in the inbox
- **GIVEN** a `shopee` collection and an internal model connection configured
- **WHEN** material is submitted once with `coffer knowledge write` and once with `POST /api/v1/knowledge/material`
- **THEN** each answer reports `pending` with no path, and two items wait in `shopee/.inbox/`
- **AND** no document has been added to the collection's visible tree

### Requirement: Submit material through coffer__write
`coffer__write` MUST submit material to a named collection from `title`, `description` and body text. It MUST take no path, no folder and no lane, and MUST NOT replace anything: two submissions of the same title are two pieces of material. A submission MUST be a plain file write — no LLM, no conversion, no indexing step — and MUST record one `mcp_invocations` row and one audit event naming the calling agent, taken from the session's handshake identity ([mcp-gateway](../mcp-gateway/spec.md) "Take the agent identity from the handshake") written in as an `agent` argument no tool advertises and no caller can set. Its answer MUST say what became of the material: `pending`, with no path — an inbox address vanishes once the material is merged, so reporting one would be reporting an address that is about to stop existing — or `written`, with the document's path, when it was promoted (see "Promote material directly when no model is configured"). A submission naming a collection that does not exist or is disabled MUST be refused with the collections that **are** available: that names exactly what this agent's own delivered skill already lists, and it turns a dead end into a correction for a model that reached for the tool without opening the skill.

#### Scenario: written material waits in the inbox, or becomes a document with no model
- **GIVEN** a `shopee` collection created through `coffer knowledge create`, and an internal model connection configured
- **WHEN** `coffer__write` is called against the daemon with the title `Session ownership`, a description and a body
- **THEN** the answer's `status` is `pending` and it carries no path, the material waits in `shopee/.inbox/session-ownership.md` — named by the title's own slug, with no id in it anywhere — and one `knowledge_written` audit event is recorded
- **AND** with no internal model configured, the same call answers `written` with the path `shopee/session-ownership.md`: the material became a document of its own on the spot, and the inbox is empty

### Requirement: Keep direct file edits a complete way to change knowledge
Writing, editing or deleting a document directly in the collection's tree — by a person in their own editor, or by an agent with its own file tools — MUST remain a complete way to change knowledge: no import, no registration, no conversion step, and the change is live on the very next read. The sweep MUST notice an edited or new document by its modification time (see "Run curation on a sweep and on demand") and carry it into the rest of the collection. Ingestion is an additional entrance, never a required one.

#### Scenario: a document edited out-of-band is curated by the next sweep
- **GIVEN** a curated document in `shopee/`, whose file a person then edits in their own editor, by a file manager rather than by Coffer
- **WHEN** the curation sweep runs, with no import or registration step in between
- **THEN** a pass is run over that document as its item, the person's wording is still in it afterwards, and its frontmatter carries a `coffer_curated_at` no older than the edit — so the next sweep does not hand it back

### Requirement: Convert uploads into material without keeping them
The system MUST accept a document upload into a named collection, convert it to Markdown, and **submit the Markdown as material** (see "Submit every entrance's input as material"), so what is new in the document is appended to the collection's knowledge rather than filed beside it. Supported inputs MUST be exactly what `markitdown` handles plus plain text and CSV; an unsupported type MUST be refused with the type named, never stored half-converted. Neither the **original** bytes nor the extracted Markdown MUST be kept as a file of its own: the upload is the carrier of its knowledge, and once the knowledge is merged the carrier has nothing left to say. There is no `source_mode`, no external-source table, no re-conversion on a schedule, no hidden `.raw/` and no visible original beside the text. An upload takes no folder — where its knowledge lands is curation's to decide.

#### Scenario: an upload is converted and submitted as material, keeping neither file
- **GIVEN** a collection with an internal model configured, and a document sent into it — `notes.md` through the ingest service, `team.csv` through `POST /api/v1/knowledge/upload`
- **WHEN** the upload is accepted (201 from the route)
- **THEN** the answer reports `pending` with no path, the converter that ran, the title and a description, and the collection holds exactly one new file: an inbox item carrying the extracted Markdown with frontmatter `actor: user`
- **AND** neither the original bytes nor a copy of the extracted text exists anywhere in the collection's visible tree, and no hidden `.raw/` exists either — the upload was the carrier of its knowledge, not the knowledge

#### Scenario: an upload of an unsupported type is refused with its reason
- **GIVEN** a collection, and a file whose type no converter handles — `archive.bin` at the service, `payload.exe` at the route
- **WHEN** it is uploaded
- **THEN** the service raises `UnsupportedDocument` and the route answers 400 `INGEST_REJECTED` whose details name `reason` `unsupported_type` and `doc_type` `exe`, and the collection is left with no new file at all — neither a document nor an inbox item

### Requirement: Fill frontmatter on converted material
The submitted Markdown MUST carry the frontmatter of "Carry title, description and actor in frontmatter" — `title` from the document (falling back to its file name) and `description` filled in, by the internal connection when one is configured and from the document's opening prose when not.

#### Scenario: title an upload from its file name when it has no heading
- **GIVEN** a collection with no internal model configured, and a plain-text file `release-notes.txt` whose text has no heading and opens with a sentence of prose
- **WHEN** it is uploaded
- **THEN** the resulting file's frontmatter `title` is derived from the name `release-notes`
- **AND** its `description` is drawn from the text's opening prose rather than left empty

### Requirement: Ingest documents sent to a channel
A document sent to a Coffer channel MUST be ingestible into a collection through the same path, so the phone and the Knowledge page are two ends of one entrance ([channels](../channels/spec.md)). The channel MUST confirm the collection with the owner before storing, and MUST NOT store anything from a non-owner.

#### Scenario: a document forwarded to a channel lands in a collection
- **GIVEN** a paired channel whose owner has just sent `note.txt` as an attachment, and one existing collection named `research`
- **WHEN** the owner follows it with the plain text `/save research`
- **THEN** the ingest service is called exactly once — that collection, that file name, those bytes, `actor` `user` and the channel's own default agent — and the channel replies with a confirmation naming both the file and the collection

### Requirement: Bound uploads and leave nothing behind on failure
Upload MUST be bounded: one file per call, a size ceiling, and a refusal that names the limit. A conversion failure MUST leave nothing behind — no inbox item, no document.

#### Scenario: a document is never stored half-converted
- **GIVEN** a document whose converter succeeds but yields no text, as an image-only PDF does
- **WHEN** it is uploaded
- **THEN** the upload is refused with the reason naming the document type, and nothing is written — no inbox item, no document, no original

### Requirement: Let only a person delete a document
Deleting a document MUST be a person's action, offered on the REST, CLI and web surfaces, and it MUST be allowed for **any** document, whoever wrote it: the tree is the person's as much as curation's. No agent-facing tool may delete anything. Inside a pass, `retire_document` is curation's own way to remove a document whose content it has written elsewhere (see "Preserve every fact a pass is shown"), and it is bounded like a write (see "Bound a pass to eight writes").

#### Scenario: delete a document an agent wrote
- **GIVEN** a document in `shopee/` whose frontmatter `actor` is `agent`
- **WHEN** a person deletes it through `DELETE` on the knowledge route and another through `coffer knowledge delete`
- **THEN** both files are gone from the tree and a `knowledge_deleted` audit event is recorded for each

### Requirement: Curate through a fenced four-tool pass
Curation is how material becomes knowledge and how an edit to one document reaches the rest. It is a bounded agentic pass driven by the internal model connection, whose tool surface MUST be exactly `list_documents`, `read_document`, `write_document` and `retire_document`, fenced to **one collection's documents**: no tool may reach the inbox, the collection's `README.md`, or another collection. A pass takes **one item** — one piece of material, or one edited document — and the context and writes of "Assemble a pass from a bounded context" and "Bound a pass to eight writes".

#### Scenario: hand a pass exactly four tools over one collection
- **GIVEN** the curation tools built for the `shopee` collection, with a document in `shopee` and another in `personal`
- **WHEN** their names are listed and `write_document` is asked to write into `personal/`
- **THEN** the names are exactly `list_documents`, `read_document`, `write_document` and `retire_document`
- **AND** the write into `personal/` is refused and nothing is written there

### Requirement: Run curation on a sweep and on demand
Passes MUST be run by a **sweep on an interval** and by a manual trigger. Each sweep MUST read the interval afresh rather than capture it at boot, and MUST find a collection's pending items in this order: first every inbox item, oldest first — until it is merged it is knowledge no agent can read — then every document whose modification time is newer than its own `coffer_curated_at` stamp (or which has none), meaning a person or an agent edited or added it out of band. A sweep MUST run at most a bounded number of passes per collection, so a freshly migrated vault drains visibly rather than in one long batch. The manual trigger takes the oldest pending item, or the one document it is given.

#### Scenario: an item is curated once, not on every sweep
- **GIVEN** a document already carrying `coffer_curated_at` no earlier than its own modification time
- **WHEN** the sweep looks for work
- **THEN** the document is not owed a pass; and with the file touched afterwards, the next sweep does owe it one

### Requirement: Assemble a pass from a bounded context
A pass MUST be assembled from a **bounded** context: the item in full, at most **five** candidate documents in full, and the collection's full catalogue of titles and descriptions. Candidates MUST be selected by literal matching of distinctive strings drawn from the item against the collection's documents — never the inbox; the catalogue is present so the model can conclude that none of the candidates is the right home and open a new document instead.

#### Scenario: a pass sees candidates and the catalogue, never the inbox
- **GIVEN** a collection whose inbox holds the triggering item and another, and whose tree holds a matching document, an unrelated one and a `README.md`
- **WHEN** the pass is assembled and its model tries to read the inbox item, the README and a file in another collection
- **THEN** the model is given the triggering item, at most five candidate documents in full, and every document's title and description; each of the three reads is refused; `list_documents` lists the two documents and nothing else; and the other waiting item is nowhere in the brief

### Requirement: Preserve every fact a pass is shown
A pass MUST preserve every fact it is shown. Merging MUST integrate rather than regenerate, and `retire_document` MUST be permitted only for a document whose content the same pass has written elsewhere.

#### Scenario: refuse a retire before the pass has written anything
- **GIVEN** the curation tools for a `shopee` collection holding two documents, and a pass that has written nothing yet
- **WHEN** the pass calls `retire_document` on one of them
- **THEN** the retire is refused and the document is still on disk

### Requirement: Bound a pass to eight writes
A pass MUST be bounded to at most **eight** writes — a retire counts as one — and to a recursion limit, and MUST report reaching either. A single item MUST NOT be able to trigger a corpus-wide rewrite.

#### Scenario: a pass is bounded to a handful of writes
- **GIVEN** a collection holding twenty documents and one new item of material
- **WHEN** a curation pass runs and its agent attempts eleven writes
- **THEN** the pass stops at the eighth and reports the bound, and the writes that did land are complete files rather than truncated ones

### Requirement: Let newer statements win and a person's edit stand
Where new material contradicts a document, the **newer statement wins**, and the resulting document MUST keep the superseded statement legible as a correction with the date it changed — a contradiction is knowledge about the world changing, and when it changed is itself worth keeping. Where the item is a **document a person edited**, what they wrote there is the truth: the pass MUST NOT revert or reword it, and carries it outward instead — correcting other documents that say otherwise, and moving a section that belongs elsewhere — leaving the edited document alone unless it now duplicates another. Both rules are instructions to the model, because no code can adjudicate a contradiction.

#### Scenario: the pass is instructed that newer material wins and a person's edit stands
- **GIVEN** the instructions a curation pass hands its model
- **WHEN** they are read
- **THEN** they state that where new material contradicts a document the newer statement wins, and that the superseded statement must stay legible with the date it changed
- **AND** they state that a document a person edited is the truth — never to be reverted or reworded, only carried outward into the other documents — the rules live in the instructions because no code can adjudicate a contradiction, so the instructions are what this scenario pins

### Requirement: Refuse file-name references in documents
A document MUST NOT contain a reference to another knowledge file by file name or path. This MUST be enforced at `write_document` — a write that carries one is refused and reported — rather than requested in a prompt.

#### Scenario: a curated document carries no file-name reference
- **GIVEN** a pass whose model writes a document whose body names another document's file name
- **WHEN** the write is applied
- **THEN** it is refused and reported, because invariant 3 is enforced at the write rather than asked for in a prompt

### Requirement: Settle an item only after its pass completes
An item MUST be settled only after its pass completes: merged material is deleted from the inbox, and an edited document is stamped with `coffer_curated_at` and nothing else about it changes. Every document curation itself writes MUST be stamped as it is written, so the sweep does not hand the pass its own output back as an edit. A stamp MUST set the file's modification time to the stamp, so the stamping itself does not count as an edit. A pass that does not complete MUST leave the item as it was, so it is curated later rather than lost.

#### Scenario: curation merges material into the documents and empties the inbox
- **GIVEN** a collection whose inbox holds two items and an internal connection configured
- **WHEN** a curation pass runs over one of them and writes a document
- **THEN** the document is in the collection's tree, stamped with `coffer_curated_at`, and the item the pass absorbed is gone from the inbox while the item it was not handed still waits
- **AND** the pass's own write is not handed back by the next sweep as an edit

### Requirement: Promote material directly when no model is configured
With no internal model connection configured, material MUST NOT wait: a submission MUST be **promoted** on the spot into a document at the collection root, as it stands and stamped as curated, and a pass MUST promote every item already in the inbox the same way and report `no_model` with the documents it promoted. Nothing is merged — merging is the model's job — but nothing sits in a hidden directory waiting for a connection nobody configured, where no agent can read it. An edited document needs nothing without a model: it is readable as it stands.

#### Scenario: with no internal model, pending material becomes documents as it stands
- **GIVEN** a collection whose inbox holds two items and no internal model connection at all
- **WHEN** a curation pass is run over it
- **THEN** it reports `no_model` and lists in `promoted` the two documents the items became, each at the collection root with its body as submitted and a `coffer_curated_at` stamp, and the inbox is empty — material never waits on a connection nobody configured

### Requirement: Run one pass per collection at a time
Only **one pass per collection** may run at a time, whoever started it. A manual trigger arriving while a pass is in flight MUST be refused (`UPKEEP_ALREADY_RUNNING`, 409) rather than queued, and the sweep MUST skip a collection already being curated. Which collections are being curated right now MUST be readable. The record is per-daemon and does not outlive it.

#### Scenario: a second curation pass over the same collection is refused while the first is running
- **GIVEN** two collections, and a pass already in flight over `shopee` held in the daemon's in-flight registry
- **WHEN** a pass is requested for `shopee` over the route that starts one
- **THEN** it is refused 409 `UPKEEP_ALREADY_RUNNING` rather than queued, while the same request for the other collection answers 200
- **AND** once the in-flight record is released the previously refused request answers 200

### Requirement: Never overlap curation with a sync round
A pass and a vault-sync converge round MUST NOT overlap — both write the vault — so they MUST take the same lock, and a pass MUST be skipped while a conflict or pending confirmation is outstanding ([vault-sync](../vault-sync/spec.md)).

#### Scenario: wait for the vault lock before sweeping
- **GIVEN** a curation worker sharing the vault-write lock, with an item pending, while a converge round holds that lock
- **WHEN** the worker's tick starts
- **THEN** no pass runs until the round releases the lock
- **AND** once it is released the pending item is curated

### Requirement: Curate on one owner machine only
Because a pass rewrites synced content unattended, it MUST run on one machine only: the `internal_engine_config` pair `auto_curate_enabled` and `curate_owner_machine_id` MUST both be read on every sweep, so the switch reads as *on, here* rather than merely *on*. Both halves of that reading MUST also be **reportable and changeable** by the user, on the same terms as a channel's machine binding — an owner naming a machine the registry no longer holds is a fault rather than silence, and can be taken over ([vault-sync](../vault-sync/spec.md) "Report and change the rewriter's owner"). `auto_curate_enabled` defaults **on**, because curation is how submitted material becomes part of the documents an agent reads.

#### Scenario: curate only where the owner machine is this one
- **GIVEN** an internal engine config with `auto_curate_enabled` left at its default
- **WHEN** the config is asked whether curation runs on this machine, first with `curate_owner_machine_id` naming another machine and then naming this one
- **THEN** the default is on, the first answer is no and the second is yes
- **AND** with no owner set at all the answer is yes, because a single-machine vault has no other machine to run on

### Requirement: Expose exactly one knowledge tool
Coffer's MCP gateway MUST expose exactly **one** built-in knowledge tool: `coffer__write`. There MUST be no `list`, `grep`, `read`, `search` or `delete`. An agent reads knowledge with its own file tools at the paths the skill gives it.

#### Scenario: exactly one built-in knowledge tool appears in the client tool list
- **GIVEN** a real daemon with an upstream MCP server registered, driven over its `/mcp` endpoint by the MCP SDK so the SDK's own models validate every frame
- **WHEN** the client initializes and calls `tools/list`
- **THEN** `coffer__write` is in the listing beside the upstream server's own tools, and `coffer__list`, `coffer__grep`, `coffer__read`, `coffer__search` and `coffer__delete` are **absent**
- **AND** a `coffer__write` call over that same session submits material into the collection

### Requirement: Deliver the catalogue through the coffer-guide skill
The catalogue MUST be carried by Coffer's own skill, `coffer-guide`, which MUST be an ordinary registered `skill` Resource — one master folder under `~/.coffer/skills/`, one row, delivered by the predicate and the links every imported skill uses ([skill-manager](../skill-manager/spec.md) "Regenerate Coffer's builtin skill from the build", [skill-manager](../skill-manager/spec.md) "Deliver a skill only where it is enabled and in scope", [skill-manager](../skill-manager/spec.md) "Deliver a skill as a directory link"). This layer contributes the **text** and nothing else: it renders, and the skill kind writes, registers and delivers.

**This reverses what this requirement used to say.** The generated skill was deliberately kept outside the resource framework — written per agent into `<config_dir>/skills/` by this layer, as a file the skill kind knew nothing about — on the grounds that a skill Resource is a bundle a person imports and curates, and no person can keep a bundle level with a catalogue that moves whenever curation runs. That reason has expired: a skill's master folder is now regenerated from the running build at every boot and whenever the catalogue changes ([skill-manager](../skill-manager/spec.md) "Regenerate Coffer's builtin skill from the build"), so "generated" and "registered as a Resource" stopped being alternatives. What the old rule bought was a folder nobody had to maintain; what it cost was a second delivery mechanism with its own writer and its own per-agent copies, invisible on the Skills surface, unreachable by `enabled` or scope, and outside every piece of machinery the skill kind already had — drift verification, repair, reclaim and the audit trail.

The per-agent copies of the retired `coffer-knowledge` delivery MUST be removed rather than left in an agent's skill directory describing a layer whose contract has moved. This layer MUST NOT push anything into a session of its own accord and MUST NOT write into any agent's own memory files: knowledge is pulled. Session-start delivery belongs to [memory](../memory/spec.md), which carries its own budget and its own consent. Coffer's own skill is indistinguishable from an imported one everywhere the skill kind touches it — listed, scoped, enabled, delivered, verified for drift and repaired by the same code — and the only thing that sets it apart is that its master folder is Coffer's to rewrite and its deletion is refused.

#### Scenario: Coffer's own skill is an ordinary skill resource
- **GIVEN** a daemon starting with a collection holding documents
- **WHEN** the boot refresh runs
- **THEN** there is one `coffer-guide` master folder under `~/.coffer/skills/` and one `skill:coffer-guide` resource row carrying the `builtin` source, and the skills listing shows it beside the user's imported skills
- **AND** this layer has written nothing into any agent's own skill directory itself, and nothing into any agent's memory files

#### Scenario: migration removes the retired knowledge skill and spares a foreign folder
- **GIVEN** two registered agents, one holding the old generated delivery at `<config_dir>/skills/coffer-knowledge` as a directory of real bytes and the other holding it as a symlink left by the delivery before it, and a third agent whose `skills/coffer-knowledge` is a folder a person put there, which carries neither of the two files the generated delivery always wrote
- **WHEN** the database is upgraded
- **THEN** the first two are gone from those agents' skill directories, so no agent is left holding a manual for a layer whose contract has moved
- **AND** the third is untouched — it is somebody else's skill that happens to share the name, and the sweep only removes what it can positively recognise as Coffer's own: a symlink, or a directory holding both `SKILL.md` and `README.md`

### Requirement: Deliver the guide as the shared-master link
The skill MUST reach each agent as the **ordinary shared-master link** of [skill-manager](../skill-manager/spec.md) "Deliver a skill as a directory link" — one master folder, one link per agent — and MUST NOT be written into an agent's directory as real bytes. **This too reverses what this requirement used to say.** The rule was that each agent's copy be independent bytes, because a link into a shared master was "a copy this layer cannot re-render, stale or reclaim". Neither half of that is true any more: the master is re-rendered in place at every boot and whenever the catalogue changes, which re-renders every agent's view of it at once; and reclaiming is the skill kind's own per-agent reconciliation against the delivery predicate ([skill-manager](../skill-manager/spec.md) "Reconcile deliveries per agent on every trigger"), which removes one agent's link without touching another's or the master. The text is the same for every agent (see "Gate collections with enabled alone"), so per-agent bytes were buying independence nothing asked for while paying for it with a delivery path of this layer's own. Re-rendering MUST happen whenever the catalogue changes — after a curation pass or a promotion, or a collection's creation, deletion, enabling or disabling, and on every sweep tick so a document a person added by hand is catalogued too — and MUST never raise: a failed render leaves the previous master exactly where it was, and the corpus stays readable at paths a person can still give an agent.

#### Scenario: every agent reaches the guide through the one master folder
- **GIVEN** two registered agents and the `coffer-guide` skill seeded
- **WHEN** each agent's `<config_dir>/skills/coffer-guide` is inspected
- **THEN** each is the ordinary Coffer-managed link into `~/.coffer/skills/coffer-guide/`, not a directory of real bytes
- **AND** a re-render that changes the catalogue changes what both agents read in one write, while narrowing the skill's scope to one agent reclaims only the other agent's link and leaves the master untouched

### Requirement: Describe Coffer and the collections' subjects in the skill description
The skill's **frontmatter description** MUST describe Coffer itself — naming its built-in tools so a model recognises them — **and** name the subjects the enabled collections cover, drawn from their READMEs. It is the only part of this layer that is always in a model's context, so it MUST carry matchable specifics rather than a description of the layer, and it MUST fit the tightest frontmatter ceiling any importer imposes (1024 characters), dropping whole collection subjects from the tail rather than cutting a sentence mid-way.

#### Scenario: one skill carries both Coffer's manual and the catalogue
- **GIVEN** a rendered `coffer-guide` `SKILL.md`
- **WHEN** its frontmatter and its body are read
- **THEN** the description names Coffer and its built-in tools as well as the enabled collections' subjects, and is within 1024 characters — a catalogue too large to fit drops whole collection subjects from the tail rather than ending mid-sentence
- **AND** the body carries the manual first — the four built-in tools, the tiering contract, that Coffer never writes an agent's memory, and that no Coffer tool waits on an approval — and the catalogue after it, in one file

### Requirement: Merge the manual and the catalogue in the skill body
The skill's **body** MUST be one merged manual: Coffer's own — its four built-in tools and when to reach for each, the tiering contract that makes an unlisted upstream tool still callable, the fact that Coffer reads an agent's memory and never writes it, that no Coffer tool waits on a human approval, and what does not belong in knowledge — **followed by** the catalogue: the path of the knowledge root, and, for each enabled collection, every document's collection-relative path, title and description. It MUST instruct the agent to read those files with its own tools, to reach for `coffer__write` when it learns something durable, and that it may also correct or extend a document it has read by editing the file itself, which the next sweep carries into the rest of the collection (see "Keep direct file edits a complete way to change knowledge"). One skill, not a set: a frontmatter description is resident in every session whether the skill is opened or not, while a body is paid for only when a model reaches for it, so a second skill would spend the resident budget again to describe something most sessions never open.

#### Scenario: the skill body carries the catalogue and the absolute root
- **GIVEN** a collection holding three documents
- **WHEN** the skill is rendered
- **THEN** its body carries each document's collection-relative path, title and description, and the path of the knowledge root, and it instructs the agent to read those files with its own tools
- **AND** the frontmatter `description` names the collection's subject, taken from the collection's own `README.md`, so a model matching on it has something to match

### Requirement: Keep the handshake instructions to what a skill cannot carry
The MCP gateway's own `initialize` instructions MUST stay within their character cap and MUST carry only what a skill cannot: what Coffer is, the names of its four built-in tools (`coffer__write`, `coffer__recall`, `coffer__diagnose`, `coffer__search_tools`) so they are recognisable in a tool list, the tiering sentence when tools are actually hidden this session, and a pointer to the `coffer-guide` skill for everything else. It MUST NOT restate the manual, MUST NOT name a retrieval tool, and MUST NOT carry the catalogue — the catalogue is in the skill body, which costs a session nothing until a model opens it.

#### Scenario: the handshake names Coffer's tools and points at the skill
- **GIVEN** a real daemon driven over its `/mcp` endpoint by the MCP SDK
- **WHEN** the client initializes, both with upstream tools hidden and with none hidden
- **THEN** the `instructions` text is within its character cap, names `coffer__write`, `coffer__recall`, `coffer__diagnose` and `coffer__search_tools`, and points at the `coffer-guide` skill for the rest
- **AND** it names no retrieval tool and carries no collection catalogue

### Requirement: Render the guide skill deterministically
The rendered `SKILL.md` MUST be a **pure function of the running build and the catalogue it is given**: the same build over the same enabled collections MUST produce the same bytes, run after run and machine after machine. Nothing machine-specific may enter it — not an absolute home directory, not a timestamp, not a build path — and the skill's own config MUST likewise carry no timestamp of its generation.

**The reason is no longer convergence, and that changes what the requirement is worth saying.** It used to read "byte-identical on every machine running the same build against the same catalogue", with the hedge doing the real work, because the artifact converged: a purely local difference would have had two vaults overwriting each other's copy forever. It no longer converges at all ([vault-sync](../vault-sync/spec.md) "Withhold derived output in both halves") — every machine renders its own from files that converge plus its own reach, and two machines are *expected* to differ whenever their enabled sets differ, which is exactly what the hedge was excusing. What determinism buys now is local and still worth paying for: an unchanged vault re-rendering to the same bytes is what lets the seed skip the write, so a boot or a curation tick that changed nothing registers nothing, audits nothing and re-delivers nothing ([skill-manager](../skill-manager/spec.md) "Regenerate Coffer's builtin skill from the build") — and it is what makes the `version_hash` in the row mean "the content moved" rather than "time passed".

The knowledge root MUST still be written in its `~`-relative form whenever it sits in its default place, so a path an agent reads is one a person can retype; an explicitly relocated root (`COFFER_KNOWLEDGE_ROOT`) MUST be written out in full, because an accurate path is worth more than a tidy one.

#### Scenario: the rendered skill is byte-identical on two machines
- **GIVEN** the same build and the same catalogue rendered twice, once with the knowledge root at each of two different home directories, and once again with the root explicitly relocated
- **WHEN** the two default-placed renderings are compared byte for byte
- **THEN** they are identical, and the knowledge root appears in its `~`-relative form rather than as either home's absolute path
- **AND** the relocated root is written out in full, and the skill's stored config carries no timestamp of when it was generated

### Requirement: Cover collection management on REST and the CLI
The REST API under `/api/v1/knowledge` and the `coffer knowledge` CLI group MUST cover: create a collection, list one level of a collection at a path, read a document, submit material (`POST /material`; `coffer knowledge write`), upload a document, delete a document, and trigger curation. There MUST be no route that writes a document: a person edits one in their own editor, reached from the page's open-in-editor action, and the edit is live on the next read (see "Keep direct file edits a complete way to change knowledge"). Collection deletion goes through the Resource framework (`DELETE /api/v1/resources/{uid}`). There MUST be no index, reindex, check-sources, update-source or embedding-configuration endpoint, no settings endpoint for the cwd-derived scope axis "Derive no boundary from the working directory" forbids, and no per-agent reach endpoint for this kind (see "Gate collections with enabled alone") — a collection's one switch is `enabled`, which the framework already serves. These surfaces serve the human and the UI; they are not an agent's retrieval path.

#### Scenario: expose every collection operation and no document write
- **GIVEN** the daemon's route table and the `coffer knowledge` command group
- **WHEN** both are enumerated
- **THEN** each offers create, list a level, read, submit material, upload, delete a document and trigger curation
- **AND** no route under `/api/v1/knowledge` accepts `PUT` or `PATCH` on a document, and none is an index, reindex, source, embedding, scope or reach endpoint

### Requirement: Present a collection as one tree in the web UI
The web UI MUST present a collection as **one tree** of its documents — no lanes, no tabs — with the chosen document rendered read-only in the pane beside it, through the unified file preview with open-in-external-editor and reveal-in-file-manager. Every document MUST offer delete, naming the exact path before it runs, reporting a refusal in place, and leaving the preview on no file afterwards. The page MUST show how much material is waiting to be merged, offer upload into the collection in view, and offer a manual curation trigger that reports a pass already in flight. It MUST NOT list the inbox's items, and MUST NOT carry a retrieval box: the one input beside the tree narrows the names already on screen, client-side.

#### Scenario: the viewer shows one tree of documents
- **GIVEN** a collection page whose tree holds a document at the root and one inside a folder, with one item of material waiting in the inbox
- **WHEN** the page renders and a document's row is clicked
- **THEN** there is one tree — no lane headings and no tabs — listing both documents and not the inbox item, the pending material is shown as a count
- **AND** the document offers open-in-editor, reveal and delete, and a delete names the exact path before it runs

### Requirement: Return absolute paths on reads
Read responses MUST carry the file's absolute path and its containing folder's absolute path.

#### Scenario: a read answers with the file's and its folder's absolute paths
- **GIVEN** a document at `shopee/infra/cache.md`
- **WHEN** it is read over `/api/v1/knowledge`
- **THEN** the answer carries the file's absolute path under the knowledge root and the absolute path of `shopee/infra/`

### Requirement: Migrate the two-lane corpus into the inbox
One migration (revision `0101`) MUST rewrite the two-lane corpus into one tree: every Markdown file of a collection's `topics/` and then of its `sources/` moves into that collection's `.inbox/` as material — the topic documents queued first, because they are already organised by subject and the first passes lay down that structure, and the sources after them in the order they were last modified — under a flat name that says which lane it came from; every non-Markdown file (an uploaded original) is dropped; and both lanes are removed. `README.md` stays at the collection root. The migration MUST NOT promote or merge anything itself: the ordinary sweep distils the whole corpus again, one pass per item. It MUST be idempotent — a collection with neither lane is walked past — and one-way, with **no compatibility shim left behind**. The earlier revisions it rewrites on top of also retired the previous delivery: the shared `coffer-knowledge` skill Resource, its master folder and every link to it (0085), and the per-agent copies that delivery then wrote (0089, see "Deliver the catalogue through the coffer-guide skill").

#### Scenario: migration queues both lanes for re-curation after a backup
- **GIVEN** a two-lane vault — a collection with a topic document under `topics/`, Markdown sources under `sources/` including one nested, an uploaded PDF original, and a `README.md` at the collection root
- **WHEN** the database is upgraded
- **THEN** the whole knowledge root was first copied to `<root>.pre-0101.bak`, and every Markdown file of both lanes now waits in the collection's `.inbox/`, the topic document queued first and the sources after it in the order they were last modified
- **AND** both lanes are gone, the PDF survives only in the backup, the `README.md` stays where it was, no document has been promoted by the migration itself, and a second upgrade changes nothing

### Requirement: Back up the knowledge root before migrating
The migration MUST back the whole knowledge root up before it moves a single file, to a sibling directory named `<root>.pre-0101.bak`, and MUST report where. A second run MUST reuse that backup rather than photograph a tree it has already rewritten. The corpus is the user's own writing, this migration empties the tree an agent reads until the sweep refills it, and the dropped originals survive nowhere else.

#### Scenario: reuse the backup on a second run
- **GIVEN** a two-lane knowledge root whose backup `<root>.pre-0101.bak` already exists from an earlier run that did not finish
- **WHEN** the migration runs again
- **THEN** it reports that backup's location
- **AND** the backup is left exactly as it was rather than photographed again over the tree being rewritten

### Requirement: Keep auto-curation on for migrated vaults
`auto_curate_enabled` MUST be on and `curate_owner_machine_id` MUST name a machine for a migrated vault, so it curates itself rather than staying dark until the setting is found. Revision 0085 seeded both — on, owned by the machine that migrated — and revision 0101 changes nothing in the database.

#### Scenario: a migrated vault curates on the machine that migrated it
- **GIVEN** a database upgraded through revision 0101 on a machine with a registered identity
- **WHEN** the internal engine config is read
- **THEN** `auto_curate_enabled` is on and `curate_owner_machine_id` names that machine

### Requirement: Carry no vector or embedding dependency
This layer MUST carry **no vector-store or embedding-model dependency**: `sqlite-vec`, `fastembed`, mem0, chroma and LlamaIndex MUST NOT appear in the dependency set, and no vector may be computed, fetched or stored anywhere. `markitdown` is this layer's converter as well as the channel's; the importlinter contract MUST admit exactly those two consumers and no others.

#### Scenario: the dependency set holds no vector store
- **GIVEN** the backend's declared dependencies and its import-linter contracts
- **WHEN** they are read
- **THEN** none of `sqlite-vec`, `fastembed`, `mem0`, `chroma` or `llama-index` is declared
- **AND** the contract fencing `markitdown` admits only the knowledge converter and the channel as its importers

### Requirement: Add no table and no directory outside the knowledge root
The knowledge layer MUST NOT add any table to `coffer.db`, and MUST NOT create a directory of its own outside the knowledge root. A collection is a row in the kind-agnostic `resources` table like every other Resource; everything else this layer holds is a file the human can open.

#### Scenario: a collection is a resources row and a directory, nothing more
- **GIVEN** a database upgraded to head and a knowledge root under a temporary home
- **WHEN** a collection is created and material is submitted into it
- **THEN** no table in `coffer.db` is named for knowledge, the collection is one `resources` row of kind `knowledge`
- **AND** every file the layer wrote lies under the knowledge root
