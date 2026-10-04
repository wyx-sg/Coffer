# Knowledge Layer

## Purpose

Coffer holds **knowledge about the user's working environment**: their repositories, services, projects, the people they work with, the decisions and traps worth surviving a session. It is a **directory of Markdown files**, and each collection is **one tree of documents** that the person and Coffer's internal model write together. New knowledge — an uploaded document parsed into Markdown, a Markdown file an agent drops into the inbox — arrives as **material** in a hidden inbox, and Coffer's curation pass merges what is new in it into the documents. The documents are what an agent reads — with its own `Read`, at an absolute path, through no tool of Coffer's. Every agent reads the same directory, so what one agent records in the morning a different agent reads in the afternoon, and no copy diverges because there is only one. See [Knowledge Is Plain Files](../../../docs/decisions/knowledge-is-plain-files.md). The spec id `knowledge` is kept although the layer merged with what used to be a separate Knowledge Base: it is the identifier inbound links and the acceptance audit resolve, not a description.

**Knowledge is not memory.** Knowledge is about the world — a platform's API contract, a service's ownership, a document someone published — and it arrives because a person, or an agent working with them, put it there. Memory is about the user and their projects, and it accrues on its own as agents work. They differ in who authors them, how they are partitioned and how they are delivered, so they are two layers: this one, filed by collection and **pulled** through a skill, and [memory](../memory/spec.md), partitioned by project and **pushed** at session start.

**Knowledge is co-created.** A person and Coffer's model edit the same documents. Source files arrive in whatever format they were written in; on arrival they are parsed into Markdown and what is new in them is **appended to the knowledge base** — merged into the documents that already cover the subject — rather than kept as a file of their own. From then on the documents are edited by whoever has something to add: a person in their editor, an agent with its own file tools, the curation pass carrying one change through to the rest. A correction is a fact with a date on it: curation keeps the superseded statement legible so a reader learns both what is true and that it changed. Metadata lives in the file rather than a database row because only the file is visible to all of them. The layer answers to four invariants:

1. **A collection is one tree of documents, and every writer shares it.** There is no lane that belongs to one writer; no statement is protected because of who wrote it — the newer or better-evidenced one wins and the superseded one stays legible — and no directory carries that meaning.
2. **New knowledge arrives as material, and material is merged.** Every entrance submits into the collection's hidden `.inbox/`; a curation pass folds each item into the documents and deletes it. With no model to merge it, it becomes a document of its own on arrival.
3. **A document MUST NOT reference another file by name.** Document paths change as the corpus is reorganised; a name written into prose is a link that rots. Name the subject, not the file.
4. **Retrieval is the agent's own.** Coffer exposes no tool for reading, listing, grepping or searching knowledge. The catalogue and the path ride in Coffer's own delivered skill, `coffer-guide`; the agent reads the files with the tools it already has.

These are **standing constraints**, not a phase that has passed: no derived index of any kind, no retrieval tool (an audit of 448 Claude Code sessions found the old tools were never called — a tool an agent does not remember to call is not retrieval), no second retrieval surface on the web page, no directory that carries meaning, and no kept originals. Ingestion is an additional entrance, never a required one: writing a Markdown document with any editor stays a complete way to add knowledge, and upload exists because the user's live entrance is often a phone.

Assumptions: the corpus stays in the hundreds of files, so a catalogue of every document fits a skill body (measured at ~5.2K tokens for 58 documents); tens of thousands of files would be a different design and the place embeddings would be reconsidered. Curation rewrites documents with no review step; what stands between a document and a bad pass is that a pass never overwrites a file changed after it read it, the eight-write bound, one pass per collection, the audit event every pass records, and the collection's git history, where every pass is one commit that can be undone as a whole. The internal connection is the one place user content may leave the machine, exactly as [channels](../channels/spec.md) "Transcribe inbound voice only when the user opted in" establishes for voice; curation and an ingested document's generated description are the only things this layer sends there. One item is small enough to hand a model whole; a pass that meets one too large for its context reports it and keeps the item as it stands rather than truncating it.

While the `knowledge` feature is switched off (spec [experimental-features](../experimental-features/spec.md) "Close the knowledge feature's surfaces"), the knowledge routes are closed, the knowledge sections of `coffer-guide` are absent, and curation passes skip their rounds; collections stay on disk untouched. Requirements below describe the feature while it is on.

## Requirements

### Requirement: Store each collection as one tree of Markdown files
Knowledge MUST be stored as files under `~/.coffer/vault/knowledge/<collection>/` — the knowledge root is the vault's `knowledge/` folder ([vault-storage](../vault-storage/spec.md) "Store state in five classes by nature") — each collection **one tree of Markdown documents** that people and Coffer's curation pass write together. There MUST be no directory division inside a collection that says who may write where. The files are the only copy; the system MUST NOT keep a retrieval index of any kind — no vectors, no sidecar, no FTS5, no chunking, no reindex, no cache — so every answer is read off disk at call time.

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
Every document and every inbox item MUST carry YAML frontmatter with `title`, `description`, `actor` (`agent` | `user`), `created_at` and `updated_at`. Curation writes no stamp into a document: what it last settled is a record of this machine's (see "Run curation on a sweep and on demand", "Settle an item only after its pass completes"). Those five keys are what Coffer writes; any other key a person put in a document MUST be kept, in place and with its value unchanged, whenever Coffer rewrites the file — a document is the person's as much as Coffer's.

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
Hidden entries (dot-prefixed) MUST be excluded from every count of documents and from the catalogue. The system itself MUST write exactly one: a collection's `.inbox/`, where submitted material waits to be merged (see "Submit every entrance's input as material"). An inbox item MUST be deleted once a pass has merged it or it has been promoted (see "Settle an item only after its pass completes", "Promote material directly when no model is configured"). The tree route MUST list a collection root's `.inbox/` as a directory and its items as files, and the read route MUST read an inbox item, so a person can see what is waiting; no other hidden entry is listed or readable, and no Coffer surface may edit or delete an inbox item — an agent adds one by writing a file there (see "Submit material by writing a file into the inbox"). `.history/` and `.raw/` stay removed: what a pass or a person replaced is kept in the collection's git history (see "Keep every document's history and undo a pass as a whole"), not in the collection, and nothing is kept of the document an upload arrived in.

#### Scenario: leave hidden entries out of every listing
- **GIVEN** a `shopee` collection holding one document, one item waiting in `.inbox/`, and a file a person put under `.scratch/`
- **WHEN** the collection is listed, its document count read, its catalogue rendered and its tree requested
- **THEN** the count is one and the catalogue names the one document only
- **AND** the tree lists the document and an `.inbox` directory holding the waiting item, which the read route returns, and nothing from `.scratch/`

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
A **collection** is a top-level subdirectory of the knowledge root and is one `knowledge` Resource. It MUST be created deliberately — through the web UI's New collection — and MUST NOT be provisioned by a read, a write, a file an agent wrote, or an agent's working directory. Creating one creates its directory and nothing inside it but an optional `README.md`.

#### Scenario: an unknown collection is an error, never auto-created
- **GIVEN** a knowledge root with no `typo` collection in it
- **WHEN** the web UI's read route is asked for the collection `typo`
- **THEN** it answers 404 and no `typo` directory exists afterwards: a read never provisions a collection

### Requirement: Derive no boundary from the working directory
The system MUST NOT derive any boundary from the agent's cwd. There MUST be no `global` scope, no `project-<ULID>` naming, no git-root resolution, no scope-to-project-root mapping table, no auto-provisioning and no scope display labels.

#### Scenario: leave a file under a scope name uncatalogued instead of resolving it
- **GIVEN** a knowledge root holding only a `shopee` collection
- **WHEN** an agent writes a Markdown file to `global/.inbox/note.md`
- **THEN** the file is left where it is, `global` is not a collection and is not catalogued, and `shopee` is still the only collection
- **AND** no `global` collection and no `project-` collection exists afterwards

### Requirement: Read a collection's description from its README
A collection's one-line description MUST be the first paragraph of its `README.md`, absent when there is none, and MUST be read off disk on every listing. It MUST NOT be stored in the database — not even in the `resources` row's own generic `description` column, which for this kind stays empty: a copy written once and read by nothing is wrong from the first time the person edits the file. It is also what the delivered skill's own description draws on (see "Describe Coffer and the collections' subjects in the skill description"), so a collection that fails to describe itself is a collection an agent never recognises. Each listing MUST also carry when the collection's newest document was written (`updated_at`, absent for a collection holding none), read off the files' times, which is what the Overview's Knowledge tile words as "edited today 13:30".

#### Scenario: a collection lists when its newest document was written
- **GIVEN** a collection holding two documents written at different times, and an empty one
- **WHEN** the collections are listed
- **THEN** the first carries the later document's write time as `updated_at` and the empty one carries none

#### Scenario: the catalogue lists collections with their README description
- **GIVEN** a collection created with the description "First description", whose `README.md` is then edited by hand to open with "Edited by hand."
- **WHEN** the collections are listed
- **THEN** the collection's `description` is the README's first paragraph as edited, not the string the creation call supplied — the description is read off disk on every listing, never out of a row

### Requirement: Present knowledge as files on disk
What this layer serves is **files on disk**, and the system MUST describe it as such wherever it is presented: a delivered path is the whole of the access story, because an agent handed the knowledge root reads anything under it with the shell tools it already has. Every collection is served to every agent (see "Serve every collection to every agent"), and nothing about a collection may be presented as a filesystem boundary: a collection has no switch that would hide it from a process that can open the directory.

#### Scenario: the guide hands over files to read with the agent's own tools
- **GIVEN** a collection holding one document
- **WHEN** the guide skill's catalogue is rendered
- **THEN** it tells the agent to read each document at `<root>/<collection>/<path>` with its own file tool and names the directory the collection's files live under
- **AND** it names no Coffer tool as the way to read a document

### Requirement: Submit every entrance's input as material
Every entrance Coffer serves — a file an agent writes into a collection's `.inbox/` (see "Submit material by writing a file into the inbox"), an upload, and a channel's `/kb` — MUST **submit material** into the named collection's `.inbox/` rather than write a document. What becomes of material is curation's to decide (see "Curate through a fenced four-tool pass"): which document it belongs in, what in it is new, and what it corrects. The one exception is "Promote material directly when no model is configured", where no model is configured to decide and the material becomes a document as it stands. Whenever material is submitted or a curation pass settles — from any entrance or from the sweep — Coffer MUST announce the collection on the daemon's event stream as a `knowledge` event carrying the collection's uid, because the inbox count and the documents change without any write to the collection's row ([resource-framework](../resource-framework/spec.md) "Announce every change on one daemon-wide event stream").

#### Scenario: an upload and an agent's file both leave material in the inbox
- **GIVEN** a `shopee` collection and an internal model connection configured
- **WHEN** a document is uploaded once through `POST /api/v1/knowledge/upload`, and an agent writes a Markdown file into `shopee/.inbox/` once
- **THEN** the upload's answer reports `pending` with no path, and after the sweep has seen the file two items wait in `shopee/.inbox/`
- **AND** no document has been added to the collection's visible tree

#### Scenario: submitting material announces the collection on the event stream
- **GIVEN** a `shopee` collection and a client reading the event stream
- **WHEN** a document is uploaded to it
- **THEN** a `knowledge` event naming the collection's uid is announced

### Requirement: Keep direct file edits a complete way to change knowledge
Writing, editing or deleting a document directly in the collection's tree — by a person in their own editor, or by an agent with its own file tools — MUST remain a complete way to change knowledge: no import, no registration, no conversion step, and the change is live on the very next read. The change MUST be committed to the vault as an edit found on disk, and the sweep MUST notice an edited or new document by its content, never by its modification time (see "Run curation on a sweep and on demand") and carry it into the rest of the collection as a newer statement (see "Let the newer or better-evidenced statement win"). Ingestion is an additional entrance, never a required one.

#### Scenario: a document edited out-of-band is curated by the next sweep
- **GIVEN** a curated document in `shopee/`, whose file is then edited on disk, by a person in their own editor or by an agent's file tools, rather than by Coffer
- **WHEN** the curation sweep runs, with no import or registration step in between
- **THEN** a pass is run over that document as its item, which carries the edit outward to the documents that disagree with it, and the document is recorded as settled with the content the pass left — so the next sweep does not hand it back

### Requirement: Convert uploads into material without keeping them
The system MUST accept a document upload into a named collection, convert it to Markdown, and **submit the Markdown as material** (see "Submit every entrance's input as material"), so what is new in the document is appended to the collection's knowledge rather than filed beside it. Supported inputs MUST be exactly what the converters accept: what `markitdown` handles (PDF, `docx`, `pptx`, `xlsx`, `xls`, HTML, EPUB), CSV, and text read as it stands (Markdown, plain text, reStructuredText, and source and configuration files such as `py`, `ts`, `sql`, `yaml`, `json`, `log`); an unsupported type MUST be refused with the type named, never stored half-converted. Neither the **original** bytes nor the extracted Markdown MUST be kept as a file of its own: the upload is the carrier of its knowledge, and once the knowledge is merged the carrier has nothing left to say. There is no `source_mode`, no external-source table, no re-conversion on a schedule, no hidden `.raw/` and no visible original beside the text. An upload takes no folder — where its knowledge lands is curation's to decide.

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

### Requirement: Bound uploads and leave nothing behind on failure
Upload MUST be bounded: one file per call, a size ceiling, and a refusal that names the limit. A conversion failure MUST leave nothing behind — no inbox item, no document.

#### Scenario: a document is never stored half-converted
- **GIVEN** a document whose converter succeeds but yields no text, as an image-only PDF does
- **WHEN** it is uploaded
- **THEN** the upload is refused with the reason naming the document type, and nothing is written — no inbox item, no document, no original

### Requirement: Let only a person delete a document
Deleting a document through Coffer MUST be a person's action, and it MUST be allowed for **any** document, whoever wrote it: the tree is the person's as much as curation's. The REST route and the web UI MUST offer it, and each deletion through them MUST record a `knowledge_deleted` audit event. A person may equally delete the file itself in the collection's directory under the knowledge root, and the deletion is live on the next read and the next catalogue (see "Keep direct file edits a complete way to change knowledge"). Coffer offers no tool that deletes anything. Inside a pass, `retire_document` is curation's own way to remove a document whose content it has written elsewhere (see "Preserve every fact a pass is shown"), and it is bounded like a write (see "Bound a pass to eight writes").

#### Scenario: delete a document an agent wrote
- **GIVEN** two documents in `shopee/` whose frontmatter `actor` is `agent`
- **WHEN** a person deletes one through `DELETE` on the knowledge route, and removes the other's file from the `shopee` directory under the knowledge root
- **THEN** both files are gone from the tree, and neither is listed or catalogued afterwards
- **AND** a `knowledge_deleted` audit event is recorded for the one deleted through the route

### Requirement: Curate through a fenced four-tool pass
Curation is how material becomes knowledge and how an edit to one document reaches the rest. It is a bounded agentic pass driven by the internal model connection, whose tool surface MUST be exactly `list_documents`, `read_document`, `write_document` and `retire_document`, fenced to **one collection's documents**: no tool may reach the inbox, the collection's `README.md`, or another collection. A pass takes **one item** — one piece of material, or one edited document — and the context and writes of "Assemble a pass from a bounded context" and "Bound a pass to eight writes".

#### Scenario: hand a pass exactly four tools over one collection
- **GIVEN** the curation tools built for the `shopee` collection, with a document in `shopee` and another in `personal`
- **WHEN** their names are listed and `write_document` is asked to write into `personal/`
- **THEN** the names are exactly `list_documents`, `read_document`, `write_document` and `retire_document`
- **AND** the write into `personal/` is refused and nothing is written there

### Requirement: Run curation on a sweep and on demand
Passes MUST be run by a **sweep on an interval** and by a manual trigger. The interval is the one global curation interval — the `curate` pass's interval under Settings › General's Coffer's model section, 60 minutes by default ([internal-engine](../internal-engine/spec.md) "Show and change Coffer's model in Settings › General") — and no collection has an interval of its own. Each sweep MUST read the interval afresh rather than capture it at boot, and MUST find a collection's pending items in this order: first every inbox item, oldest submitted first (by the `created_at` in its own frontmatter, never by file time) — until it is merged it is knowledge no agent can read — then every document whose content is not what curation last settled (or which curation never settled) and whose newest commit a person or an agent made rather than curation or sync, meaning a person or an agent edited or added it out of band. A modification time never decides: a checkout, a restore from backup or a clock change that moves only times makes nothing pending. A sweep MUST run at most a bounded number of passes per collection, so a collection with a long inbox drains visibly rather than in one long batch. The manual trigger — **Curate now** in the web UI — MUST run passes until the collection has nothing pending, in the same order (inbox items oldest first, then documents edited out of band), still **one pass at a time** (see "Run one pass per collection at a time") and each pass still bounded (see "Bound a pass to eight writes"). While it runs it MUST report progress as *n of m*, where *m* is what was pending when it started — readable on the in-flight list ([resource-framework](../resource-framework/spec.md) "Report the passes in flight in one cross-kind read"), which carries the run's *n* and *m*, and announced on the daemon's event stream as each pass finishes — and it MUST stop at the first pass that fails, reporting that pass and leaving the rest pending for the next run or sweep. Given one document, it curates just that document. A trigger arriving while a pass over the collection is in flight is refused with 409, as any other. The manual trigger MUST also be refused with 409 while a sync round waits for a person (a stop on conflicts, a hold, or a join's differing files), because a rewrite is never piled onto the files a person is deciding between; it is NOT bound to the owner machine, since pressing the button is choosing to rewrite on this machine.

#### Scenario: an item is curated once, not on every sweep
- **GIVEN** a document curation has settled
- **WHEN** the sweep looks for work
- **THEN** the document is not owed a pass; and once its content changes on disk, by a person's editor or an agent's file tools, the change is committed as an edit on disk and the next sweep does owe it one

#### Scenario: curate now drains a collection until nothing is pending
- **GIVEN** a collection with three inbox items and one document edited out of band, and an internal connection configured
- **WHEN** the user chooses Curate now
- **THEN** four passes run one after another — the three items oldest first, then the document — each within the eight-write bound
- **AND** afterwards the inbox is empty and nothing is owed a pass

#### Scenario: curate now reports progress
- **GIVEN** a collection with three pending items
- **WHEN** Curate now runs
- **THEN** progress reads 1 of 3, 2 of 3 and 3 of 3 as passes finish, on the in-flight list and on the event stream

#### Scenario: curate now stops at the first failed pass
- **GIVEN** a collection with three pending items whose second pass fails
- **WHEN** Curate now runs
- **THEN** the first item is settled, the run stops reporting the failed pass, and the second and third items are still pending

#### Scenario: curate now on one document curates only it
- **GIVEN** a collection with two pending items and a document the user names
- **WHEN** the manual trigger is given that document
- **THEN** one pass runs over that document and the two items stay pending

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
A pass MUST be bounded to at most **eight** writes — a retire counts as one — and to a recursion limit, and MUST report reaching either. A single item MUST NOT be able to trigger a corpus-wide rewrite. An item the recursion limit cuts off **three times in a row** MUST NOT be offered again: that third pass settles it — material promoted as it stands, an edited document stamped — and reports `gave_up`, so an item too large for the limit costs a bounded number of passes rather than one every sweep.

#### Scenario: a pass is bounded to a handful of writes
- **GIVEN** a collection holding twenty documents and one new item of material
- **WHEN** a curation pass runs and its agent attempts eleven writes
- **THEN** the pass stops at the eighth and reports the bound, and the writes that did land are complete files rather than truncated ones

#### Scenario: a pass cut off by the recursion limit reports it and leaves its item owed
- **GIVEN** a collection whose inbox holds one item of material and an internal connection configured
- **WHEN** a curation pass over it reaches the recursion limit before the loop completes
- **THEN** the pass reports status `truncated` with the same counters as `ok` (`written`, `retired`, `refused`, `model`, `item`), the documents it wrote stay in the tree, and the item is still in the inbox for a later sweep to finish
- **AND** the sweep goes on to the collection's next pending item rather than stopping, and the next sweep offers the item only after the collection's other pending items
- **AND** when a pass over the same item is cut off for the third time in a row, it reports `truncated` with `gave_up` true and the item promoted to a document as it stands (named in `promoted`), and the item is not offered again

### Requirement: Let the newer or better-evidenced statement win
Where two statements disagree — new material and a document, or a document and an edit made to another — the **newer statement wins unless the older one is shown to be right**: by a source, a date, a command's output or the code. The resulting document MUST keep the superseded statement legible as a correction with the date it changed — a contradiction is knowledge about the world changing, and when it changed is itself worth keeping. **No writer is exempt.** A person, an agent and a curation pass are all judged by when a statement was made and the evidence behind it, never by who wrote it. Where the item is a **document edited out of band** — by a person in the web UI or in an editor, or by an agent's file tools — it is still owed a pass, which carries the edit outward **as a newer statement**: correcting other documents that say otherwise and moving a section that belongs elsewhere. The edited document is not untouchable: a later item may correct it like anything else, by the same rule. Both rules are instructions to the model, because no code can adjudicate a contradiction. What code can do it does, because these two guards protect data rather than a writer: a pass MUST NOT overwrite a document whose bytes changed after the pass read it (or was shown it in its brief) — the write is refused and counted among the pass's `refused`, so an edit made while a pass runs is never silently reverted — and a rewrite of a document MUST keep every frontmatter key it did not set, including falsy values such as `draft: false`.

#### Scenario: instruct the pass that the newer or better-evidenced statement wins and no writer is exempt
- **GIVEN** the instructions a curation pass hands its model
- **WHEN** they are read
- **THEN** they state that where two statements disagree the newer one wins unless the older one is shown to be right by a source, a date, a command's output or the code, and that the superseded statement must stay legible with the date it changed
- **AND** they state that no writer — person, agent or pass — is exempt, and that a document edited out of band is carried outward into the other documents as a newer statement rather than protected; the rules live in the instructions because no code can adjudicate a contradiction, so the instructions are what this scenario pins

### Requirement: Refuse file-name references in documents
A document MUST NOT contain a reference to another knowledge file by file name or path. This MUST be enforced at `write_document` — a write that carries one is refused and reported — rather than requested in a prompt.

#### Scenario: a curated document carries no file-name reference
- **GIVEN** a pass whose model writes a document whose body names another document's file name
- **WHEN** the write is applied
- **THEN** it is refused and reported, because invariant 3 is enforced at the write rather than asked for in a prompt

### Requirement: Settle an item only after its pass completes
An item MUST be settled only after its pass completes: merged material is deleted from the inbox, and an edited document is recorded as settled — the content it has when the pass completes, kept in this machine's curation record `~/.coffer/local/curation.json` — while nothing about the document itself changes. Every document curation itself writes MUST be recorded as settled as it is written, and is a commit naming curation, so the sweep does not hand the pass its own output back as an edit. Settling writes nothing into the document, so it can never count as an edit itself. The record is machine-local and never travels: a change another machine's curation made arrives as a sync commit, which is not an edit to carry, and losing the record costs one more pass over each document. A pass that does not complete MUST leave the item as it was, so it is curated later rather than lost. Three ways an item leaves the queue without a completed pass keep it as it stands rather than settle a merge that never happened: no model configured ("Promote material directly when no model is configured"), an item too large for any pass ("Report every pass outcome as a status"), and an item cut off three times in a row ("Bound a pass to eight writes").

#### Scenario: curation merges material into the documents and empties the inbox
- **GIVEN** a collection whose inbox holds two items and an internal connection configured
- **WHEN** a curation pass runs over one of them and writes a document
- **THEN** the document is in the collection's tree, recorded as settled, and the item the pass absorbed is gone from the inbox while the item it was not handed still waits
- **AND** the pass's own write is not handed back by the next sweep as an edit

### Requirement: Promote material directly when no model is configured
With no internal model connection configured, material MUST NOT wait: a submission Coffer receives — an upload — MUST be **promoted** on the spot into a document at the collection root, as it stands and recorded as settled, and a pass MUST promote every item already in the inbox the same way — a file an agent wrote there included — and report `no_model` with the documents it promoted. Nothing is merged — merging is the model's job — but nothing sits in a hidden directory waiting for a connection nobody configured, where no agent can read it. An edited document needs nothing without a model: it is readable as it stands.

#### Scenario: with no internal model, pending material becomes documents as it stands
- **GIVEN** a collection whose inbox holds two items and no internal model connection at all
- **WHEN** a curation pass is run over it
- **THEN** it reports `no_model` and lists in `promoted` the two documents the items became, each at the collection root with its body as submitted and recorded as settled, and the inbox is empty — material never waits on a connection nobody configured

### Requirement: Run one pass per collection at a time
Only **one pass per collection** may run at a time, whoever started it. A manual trigger arriving while a pass is in flight MUST be refused (`UPKEEP_ALREADY_RUNNING`, 409) rather than queued, and the sweep MUST skip a collection already being curated. Which collections are being curated right now MUST be readable. The record is per-daemon and does not outlive it.

#### Scenario: a second curation pass over the same collection is refused while the first is running
- **GIVEN** two collections, and a pass already in flight over `shopee` held in the daemon's in-flight registry
- **WHEN** a pass is requested for `shopee` over the route that starts one
- **THEN** it is refused 409 `UPKEEP_ALREADY_RUNNING` rather than queued, while the same request for the other collection answers 200
- **AND** once the in-flight record is released the previously refused request answers 200

### Requirement: Never overlap curation with a sync round
A pass and a vault-sync round MUST NOT overlap — both write the vault — so they MUST take the same lock, and a pass MUST be skipped while a conflict or pending confirmation is outstanding ([vault-sync](../vault-sync/spec.md) "Never overlap a curation pass and a round").

#### Scenario: wait for the vault lock before sweeping
- **GIVEN** a curation worker sharing the vault-write lock, with an item pending, while a sync round holds that lock
- **WHEN** the worker's tick starts
- **THEN** no pass runs until the round releases the lock
- **AND** once it is released the pending item is curated

### Requirement: Curate on one owner machine only
Because a pass rewrites synced content unattended, it MUST run on one machine only: the `internal_engine_config` pair `auto_curate_enabled` and `curate_owner_machine_id` MUST both be read on every sweep, so the switch reads as *on, here* rather than merely *on*. Both halves of that reading MUST also be **reportable and changeable** by the user, on the same terms as a channel's machine binding — an owner naming a machine the registry no longer holds is a fault rather than silence, and can be taken over ([vault-sync](../vault-sync/spec.md) "Report and change the rewriter's owner"). `auto_curate_enabled` defaults **on**, because curation is how submitted material becomes part of the documents an agent reads.

#### Scenario: a pass does not overwrite an edit made while it ran
- **GIVEN** a document a pass has read, which a person then saves with different text
- **WHEN** the pass writes that document
- **THEN** the write is refused with an error naming the change, the pass's `refused` count includes it, and the person's text is still the document's body

#### Scenario: Curate now is refused while a sync round waits for a person
- **GIVEN** a sync round that waits for a person, and a collection with pending material
- **WHEN** Curate now is requested for the collection
- **THEN** the route answers 409 `KNOWLEDGE_CURATION_HELD` and no pass runs

#### Scenario: curate only where the owner machine is this one
- **GIVEN** an internal engine config with `auto_curate_enabled` left at its default
- **WHEN** the config is asked whether curation runs on this machine, first with `curate_owner_machine_id` naming another machine and then naming this one
- **THEN** the default is on, the first answer is no and the second is yes
- **AND** with no owner set at all the answer is yes, because a single-machine vault has no other machine to run on

### Requirement: Deliver the catalogue through the coffer-guide skill
The catalogue MUST be carried by Coffer's own skill, `coffer-guide`, which MUST be an ordinary registered `skill` Resource — one master folder, `~/.coffer/derived/skills/coffer-guide/`, one resource, delivered by the predicate and the links every imported skill uses ([skill-manager](../skill-manager/spec.md) "Regenerate Coffer's builtin skill from the build", [skill-manager](../skill-manager/spec.md) "Deliver a skill only where it is enabled and in scope", [skill-manager](../skill-manager/spec.md) "Deliver a skill as a directory link"). This layer contributes the **text** and nothing else: it renders, and the skill kind writes, registers and delivers.

**This reverses what this requirement used to say.** The generated skill was deliberately kept outside the resource framework — written per agent into `<config_dir>/skills/` by this layer, as a file the skill kind knew nothing about — on the grounds that a skill Resource is a bundle a person imports and curates, and no person can keep a bundle level with a catalogue that moves whenever curation runs. That reason has expired: a skill's master folder is now regenerated from the running build at every boot and whenever the catalogue changes ([skill-manager](../skill-manager/spec.md) "Regenerate Coffer's builtin skill from the build"), so "generated" and "registered as a Resource" stopped being alternatives. What the old rule bought was a folder nobody had to maintain; what it cost was a second delivery mechanism with its own writer and its own per-agent copies, invisible on the Skills surface, unreachable by `enabled` or scope, and outside every piece of machinery the skill kind already had — drift verification, repair, reclaim and the audit trail.

This layer MUST NOT push anything into a session of its own accord and MUST NOT write into any agent's own memory files: knowledge is pulled. Session-start delivery belongs to [memory](../memory/spec.md), which carries its own budget and its own consent. Coffer's own skill is indistinguishable from an imported one everywhere the skill kind touches it — listed, scoped, enabled, delivered, verified for drift and repaired by the same code — and the only thing that sets it apart is that its master folder is Coffer's to rewrite and its deletion is refused.

#### Scenario: Coffer's own skill is an ordinary skill resource
- **GIVEN** a daemon starting with a collection holding documents
- **WHEN** the boot refresh runs
- **THEN** there is one `coffer-guide` master folder under `~/.coffer/derived/skills/` and one `skill:coffer-guide` resource carrying the `builtin` source, and the skills listing shows it beside the user's imported skills
- **AND** this layer has written nothing into any agent's own skill directory itself, and nothing into any agent's memory files

### Requirement: Deliver the guide as the shared-master link
The skill MUST reach each agent as the **ordinary shared-master link** of [skill-manager](../skill-manager/spec.md) "Deliver a skill as a directory link" — one master folder, one link per agent — and MUST NOT be written into an agent's directory as real bytes. **This too reverses what this requirement used to say.** The rule was that each agent's copy be independent bytes, because a link into a shared master was "a copy this layer cannot re-render, stale or reclaim". Neither half of that is true any more: the master is re-rendered in place at every boot and whenever the catalogue changes, which re-renders every agent's view of it at once; and reclaiming is the skill kind's own per-agent reconciliation against the delivery predicate ([skill-manager](../skill-manager/spec.md) "Reconcile deliveries from state on every pass"), which removes one agent's link without touching another's or the master. The text is the same for every agent (see "Serve every collection to every agent"), so per-agent bytes were buying independence nothing asked for while paying for it with a delivery path of this layer's own. Re-rendering MUST happen whenever the catalogue changes — after a curation pass or a promotion, or a collection's creation, rename or deletion, and on every sweep tick so a document a person added by hand is catalogued too — and MUST never raise: a failed render leaves the previous master exactly where it was, and the corpus stays readable at paths a person can still give an agent.

#### Scenario: every agent reaches the guide through the one master folder
- **GIVEN** two registered agents and the `coffer-guide` skill seeded
- **WHEN** each agent's `<config_dir>/skills/coffer-guide` is inspected
- **THEN** each is the ordinary Coffer-managed link into `~/.coffer/derived/skills/coffer-guide/`, not a directory of real bytes
- **AND** a re-render that changes the catalogue changes what both agents read in one write, while narrowing the skill's scope to one agent reclaims only the other agent's link and leaves the master untouched

### Requirement: Describe Coffer and the collections' subjects in the skill description
The skill's **frontmatter description** MUST describe Coffer itself — naming its built-in tool so a model recognises it — **and** name the subjects the collections cover, drawn from their READMEs. It is the only part of this layer that is always in a model's context, so it MUST carry matchable specifics rather than a description of the layer, and it MUST fit the tightest frontmatter ceiling any importer imposes (1024 characters), dropping whole collection subjects from the tail rather than cutting a sentence mid-way.

#### Scenario: one skill carries both Coffer's manual and the catalogue
- **GIVEN** a rendered `coffer-guide` `SKILL.md`
- **WHEN** its frontmatter and its body are read
- **THEN** the description names Coffer and its built-in tool as well as the collections' subjects, and is within 1024 characters — a catalogue too large to fit drops whole collection subjects from the tail rather than ending mid-sentence
- **AND** the body carries the manual first — the built-in tool, the tiering contract, that Coffer never writes an agent's memory, and that no Coffer tool waits on an approval — and the catalogue after it, in one file

### Requirement: Merge the manual and the catalogue in the skill body
The skill's **body** MUST be one merged manual: Coffer's own — its one built-in tool, `coffer__search_tools`, and when to reach for it; the tiering contract that makes an unlisted upstream tool still callable; the knowledge root and the memory root, and that Coffer's distilled memory notes are Markdown under the latter which the agent finds by searching that directory with its own tools; that Coffer's own logs are read with `coffer log` and located with `coffer path logs`; the fact that Coffer reads an agent's memory and never writes it; that no Coffer tool waits on a human approval; and what does not belong in knowledge — **followed by** the catalogue: the path of the knowledge root, and, for each collection, every document's collection-relative path, title and description. It MUST instruct the agent to read those files with its own tools, to write a Markdown file into a collection's `.inbox/` when it learns something durable (see "Submit material by writing a file into the inbox"), and that it may also correct or extend a document it has read by editing the file itself, which the next sweep carries into the rest of the collection (see "Keep direct file edits a complete way to change knowledge"). One skill, not a set: a frontmatter description is resident in every session whether the skill is opened or not, while a body is paid for only when a model reaches for it, so a second skill would spend the resident budget again to describe something most sessions never open.

#### Scenario: the skill body carries the catalogue and the absolute root
- **GIVEN** a collection holding three documents
- **WHEN** the skill is rendered
- **THEN** its body carries each document's collection-relative path, title and description, and the path of the knowledge root, and it instructs the agent to read those files with its own tools
- **AND** the frontmatter `description` names the collection's subject, taken from the collection's own `README.md`, so a model matching on it has something to match

#### Scenario: name one tool, both roots and the log reader in the manual
- **GIVEN** a vault with one collection
- **WHEN** the skill is rendered
- **THEN** its manual names exactly one built-in tool, `coffer__search_tools`, and names none of `coffer__write`, `coffer__recall` and `coffer__diagnose`
- **AND** it names the knowledge root and the memory root with the instruction to search them with the agent's own tools, tells the agent to add knowledge by writing a file into a collection's `.inbox/`, and names `coffer log` and `coffer path logs` as the way to read Coffer's own logs

### Requirement: Keep the handshake instructions to what a skill cannot carry
The MCP gateway's own `initialize` instructions MUST stay within their character cap and MUST carry only what a skill cannot: what Coffer is, the name of its one built-in tool (`coffer__search_tools`) so it is recognisable in a tool list, one line saying that Coffer's knowledge and memory notes are files under their roots read with the agent's own tools and that Coffer's own logs are read with `coffer log`, the tiering sentence when tools are actually hidden this session, and a pointer to the `coffer-guide` skill for everything else. It MUST NOT restate the manual, MUST NOT name a retrieval tool, and MUST NOT carry the catalogue — the catalogue is in the skill body, which costs a session nothing until a model opens it. A built-in tool whose experimental feature is switched off is not in the tool list, and the instructions MUST NOT name it either ([experimental-features](../experimental-features/spec.md) "Withdraw what a switched-off feature put in front of agents").

#### Scenario: name only the search tool in the handshake and point at the skill
- **GIVEN** a real daemon driven over its `/mcp` endpoint by the MCP SDK
- **WHEN** the client initializes, both with upstream tools hidden and with none hidden
- **THEN** the `instructions` text is within its character cap, names `coffer__search_tools`, names none of `coffer__write`, `coffer__recall` and `coffer__diagnose`, and points at the `coffer-guide` skill for the rest
- **AND** it names no retrieval tool and carries no collection catalogue

### Requirement: Render the guide skill deterministically
The rendered `SKILL.md` MUST be a **pure function of the running build and the catalogue it is given**: the same build over the same collections MUST produce the same bytes, run after run and machine after machine. Nothing machine-specific may enter it — not an absolute home directory, not a timestamp, not a build path — and the skill's own config MUST likewise carry no timestamp of its generation.

**The reason is no longer convergence, and that changes what the requirement is worth saying.** It used to read "byte-identical on every machine running the same build against the same catalogue", with the hedge doing the real work, because the artifact converged: a purely local difference would have had two vaults overwriting each other's copy forever. It no longer converges at all ([vault-sync](../vault-sync/spec.md) "Withhold derived output in both halves") — every machine renders its own from files that converge plus its own reach, and two machines are *expected* to differ whenever their enabled sets differ, which is exactly what the hedge was excusing. What determinism buys now is local and still worth paying for: an unchanged vault re-rendering to the same bytes is what lets the seed skip the write, so a boot or a curation tick that changed nothing registers nothing, audits nothing and re-delivers nothing ([skill-manager](../skill-manager/spec.md) "Regenerate Coffer's builtin skill from the build") — and it is what makes the `version_hash` in the resource mean "the content moved" rather than "time passed".

The knowledge root MUST still be written in its `~`-relative form whenever it sits in its default place, so a path an agent reads is one a person can retype; a root that is not under the home directory MUST be written out in full, because an accurate path is worth more than a tidy one.

#### Scenario: the rendered skill is byte-identical on two machines
- **GIVEN** the same build and the same catalogue rendered twice, once with the knowledge root at each of two different home directories, and once again with the root outside the home directory
- **WHEN** the two default-placed renderings are compared byte for byte
- **THEN** they are identical, and the knowledge root appears in its `~`-relative form rather than as either home's absolute path
- **AND** the root outside the home directory is written out in full, and the skill's stored config carries no timestamp of when it was generated

### Requirement: Present a collection as one tree in the web UI
The web UI MUST present a collection as **one tree** of its documents — no lanes, no tabs, no filter or retrieval box — with the chosen document in the pane beside it, the same two panes a skill's Files tab is. The tree MUST name every collection, folder and document by its name on disk: a collection has no title (see "Name a collection by its folder and edit its description in place"). Its **Collections** header strip MUST carry **New collection** (a name and what belongs in it; the collection reaches every agent through the coffer-guide skill). The tree MUST show the collection's `.inbox/` as an **Inbox** node carrying the number of items waiting, and that count MUST be the only number the tree shows: no collection or folder carries a document count, and the sidebar carries no badge for waiting items. Choosing the Inbox node opens the Inbox view and expands the node to list the items, which open read-only, with no edit and no delete. In the web UI inbox entries are called **items** (the spec's *material*), and curation is called **Curate** / **Curation** (整理) everywhere — the web UI and docs-site — never "merge". Knowledge calls its files **documents** everywhere (memory keeps *notes*).

A document's pane MUST carry **Document** and **History** tabs (see [web-ui](../web-ui/spec.md) "Show a knowledge document's history on its History tab"), a **Preview / Source** switch, **Edit**, and a ⋯ menu holding **Open in editor**, **Reveal in Finder** and **Delete document**. Its properties — who wrote it, with a **See the pass** link when curation did, and when it was created — MUST be one line under its title; there is no side column. The **editor** MUST hold only the body: the frontmatter is shown read-only above it as kept by curation. The editor is the one place with an explicit save: it offers **Discard** and **Save**, and leaving it with unsaved changes — by choosing another page or closing the window — MUST ask first whether to leave without saving; the tree marks the open document with an unsaved dot meanwhile. It saves through "Save a document edited in the web UI". A save refused as stale MUST say the document changed on disk and that the text was not saved, and offer **Compare**, **Copy my text** and **Reload**, never a second save over it: **Compare** opens a conflict view with two choices, **Keep my edit** and **Take the version on disk**, each showing its diff, and the version left out stays in History; **Reload** asks first, because it discards the text being edited.

A collection's page MUST show its folder name, its description edited in place (see "Name a collection by its folder and edit its description in place") and its properties: **Documents**, **Inbox** (*N waiting* with **Open Inbox**, or *Nothing*), **Last curated** (a time, or *Never*) and **Folder**. A collection with no documents shows the same page with one line saying so and how to fill it — upload one, or drop Markdown files into the folder — and **Reveal in Finder**. The collection's ⋯ menu MUST hold **Reveal in Finder**, **Copy path** and **Delete collection** (see "Delete a document or a collection at once and offer Undo").

The page MUST offer **Upload** into a collection's Inbox as its one primary action — secondary while a document is being edited — and no other form that adds a document: people write through **Edit**, agents by writing files. The manual trigger MUST be a quiet **Curate now** in the Inbox view, in Recent changes and in the header's Automatic control, never on a document, reporting its progress (*Curating · 1 of 2*, no dialog), a pass already in flight and a failed pass; a manual run MUST end with one summary toast (naming Activity when it failed), and what became of each item that could not be curated — too large, cut off three times, over the step limit — MUST be written on that change's row in Recent changes, not as a toast apiece. While Coffer's model is not set, the page MUST show no Inbox node, no Automatic control and no Curate now, and in the control's place one **Curation needs Coffer’s engine** button leading to Settings › General; its properties are **Documents** and **Folder** only, items become documents as they arrive until then, and the Upload dialog says the file is added to the collection as a document rather than to its Inbox. The tree and the pane MUST extend to the bottom of the window and scroll inside.

The Knowledge page's title MUST carry the **Experimental** tag ([experimental-features](../experimental-features/spec.md)).

#### Scenario: the viewer shows one tree of documents
- **GIVEN** a collection page whose tree holds a document at the root and one inside a folder, with one item of material waiting in the inbox
- **WHEN** the page renders, a document's row is clicked, and then the inbox item's
- **THEN** there is one tree — no lane headings, no tabs, no filter input — listing both documents and an Inbox node holding the item, and the only number in the tree is the Inbox node's 1
- **AND** the document offers Edit, and Open in editor, Reveal in Finder and Delete document in its ⋯ menu, and the inbox item offers neither Edit nor delete

#### Scenario: the page's one primary action is Upload
- **GIVEN** the Knowledge page with a document open
- **WHEN** the user reads the header, then chooses Edit
- **THEN** Upload is the primary button, and while the document is being edited it is secondary
- **AND** no control on the page adds a document from a typed title and body

#### Scenario: edit a document in place
- **GIVEN** a document open in a collection's pane
- **WHEN** the user chooses Edit, changes the text and chooses Save
- **THEN** the save is sent with the fingerprint the pane loaded, and the pane renders the saved body
- **AND** choosing Discard, or leaving the page, with unsaved changes asks before the text is dropped

#### Scenario: the inbox node counts waiting items and holds the only trigger
- **GIVEN** a collection with one item waiting and Coffer's model set
- **WHEN** the collection page renders and the user follows Open Inbox
- **THEN** the Inbox node reads 1, the page's Inbox property reads *1 waiting* beside the Automatic control, the collection view offers no Curate now, and the Inbox view it opens does

#### Scenario: a collection page shows its properties
- **GIVEN** a collection never curated, holding two documents
- **WHEN** its page renders
- **THEN** it shows the folder name, the description, and Documents, Inbox (Nothing), Last curated (Never) and Folder
- **AND** its ⋯ menu offers Reveal in Finder, Copy path and Delete collection

#### Scenario: no model shows no curation controls
- **GIVEN** Coffer's model not set
- **WHEN** a collection page renders
- **THEN** there is no Inbox node, no Automatic control and no Curate now, and one button, Curation needs Coffer’s engine, leads to Settings › General
- **AND** the page's properties are Documents and Folder

#### Scenario: a stale save offers compare, copy and reload
- **GIVEN** a document open in the editor that curation changes on disk before the user saves
- **WHEN** the user saves
- **THEN** the pane says the document changed on disk and the text was not saved, and offers Compare, Copy my text and Reload, with no way to save over it
- **AND** Compare offers Keep my edit and Take the version on disk with their diffs, and Reload asks before dropping the text

#### Scenario: a manual curation run ends with one toast
- **GIVEN** a collection with three items waiting, one of them too large to curate
- **WHEN** the user chooses Curate now and the run finishes
- **THEN** one summary toast reports the run, and the too-large item is explained on its change's row in Recent changes

#### Scenario: curation is called curate, never merge
- **GIVEN** the web UI in English and in 中文
- **WHEN** every label, button and help line about curation is read
- **THEN** each says Curate or Curation (整理 in 中文) and none says merge, and inbox entries are called items

### Requirement: Return absolute paths on reads
Read responses MUST carry the file's absolute path and its containing folder's absolute path.

#### Scenario: a read answers with the file's and its folder's absolute paths
- **GIVEN** a document at `shopee/infra/cache.md`
- **WHEN** it is read over `/api/v1/knowledge`
- **THEN** the answer carries the file's absolute path under the knowledge root and the absolute path of `shopee/infra/`

### Requirement: Carry no vector or embedding dependency
This layer MUST carry **no vector-store or embedding-model dependency**: `sqlite-vec`, `fastembed`, mem0, chroma and LlamaIndex MUST NOT appear in the dependency set, and no vector may be computed, fetched or stored anywhere. `markitdown` is this layer's converter as well as the channel's; the importlinter contract MUST admit exactly those two consumers and no others.

#### Scenario: the dependency set holds no vector store
- **GIVEN** the backend's declared dependencies and its import-linter contracts
- **WHEN** they are read
- **THEN** none of `sqlite-vec`, `fastembed`, `mem0`, `chroma` or `llama-index` is declared
- **AND** the contract fencing `markitdown` admits only the knowledge converter and the channel as its importers

### Requirement: Add no table and no directory outside the knowledge root
The knowledge layer MUST NOT add any table to Coffer's databases, and MUST NOT create a directory of its own outside the knowledge root. A collection is a resource file, `resources/knowledge/<name>.json` in the vault, like every other Resource; everything else this layer holds is a file the human can open, but for the one record of this machine's that says what curation last settled (see "Settle an item only after its pass completes").

#### Scenario: a collection is a resource file and a directory, nothing more
- **GIVEN** a database upgraded to head and a knowledge root under a temporary home
- **WHEN** a collection is created and material is submitted into it
- **THEN** no table in the history database is named for knowledge, and the collection is one resource of kind `knowledge`
- **AND** every file the layer wrote lies under the knowledge root, but for this machine's curation record

### Requirement: Report every pass outcome as a status
Every curation outcome MUST be reported as a `status`, and the route that runs a pass MUST answer **200** for each of them, because none is a fault of the request: `ok` when a pass ran and settled its item; `no_model` when no internal connection is configured (see "Promote material directly when no model is configured"); `up_to_date` when nothing is pending, in which case no pass runs and nothing is touched; `too_large` when the item is past the size one pass can hold, with `limit` naming the ceiling; `truncated` when the recursion limit cut the pass off (see "Bound a pass to eight writes"); and `failed` when the pass did not complete. The manual trigger MUST answer with the outcome of each pass it ran, in order, ending at the first `failed`, and `up_to_date` when nothing was pending. The route MUST answer **404** for an unknown collection and **409** while a pass over the same collection is running (see "Run one pass per collection at a time"). A `too_large` item MUST never be shown to the model and MUST never be left pending — left where it was it would be offered to every sweep and refused by every pass: material is promoted to a document as it stands, exactly as the no-model path promotes it, and reported in `promoted`; an edited document, which has nothing to promote, is recorded as settled and reported in `stamped`. Neither changes a word of the item.

#### Scenario: oversized material is promoted as it stands
- **GIVEN** a collection whose inbox holds one item of material longer than the item-size ceiling, and an internal connection configured
- **WHEN** a curation pass runs
- **THEN** it reports `too_large` with `limit` and lists in `promoted` the document the item became, whose body is the material as submitted and which is recorded as settled
- **AND** the model was shown nothing, the inbox is empty and nothing is pending

#### Scenario: an oversized edited document is stamped, not re-offered
- **GIVEN** a document a person edited past the item-size ceiling, owed a pass, and an internal connection configured
- **WHEN** a curation pass runs
- **THEN** it reports `too_large` with `limit` and names the document in `stamped`, and the document's body is exactly what the person wrote, recorded as settled
- **AND** the model was shown nothing and the sweep no longer finds the document pending

#### Scenario: a collection with nothing pending reports up to date
- **GIVEN** a collection holding only documents curation has already seen, and an internal connection configured
- **WHEN** a curation pass is run over it
- **THEN** it reports `up_to_date` with the collection's name and nothing else
- **AND** the model was shown nothing and every document is unchanged

### Requirement: Serve every collection to every agent
Every collection MUST be named, catalogued and served to **every** agent, and a collection MUST NOT carry the Resource framework's per-agent reach or an enabled switch: the kind declares itself non-toggleable ([resource-framework](../resource-framework/spec.md) "Address every resource by an immutable uid through one kind-agnostic surface"). A collection leaves every agent's delivered skill only by being deleted. A file written under a top-level directory that is not a collection MUST be left alone and MUST NOT be catalogued (see "Submit material by writing a file into the inbox").

#### Scenario: every collection is in every agent's skill
- **GIVEN** two collections, `shopee` and `personal`, both holding documents, one of them stored disabled by an earlier version
- **WHEN** the database is migrated and the guide skill is re-rendered and seeded into its master folder
- **THEN** the master `SKILL.md` names both collections and lists both catalogues
- **AND** a request to disable either collection through the generic resource route is refused and changes nothing

### Requirement: Save a document edited in the web UI
`PUT /api/v1/knowledge/file` MUST replace a document's **body** with the text it is given and keep the document's frontmatter, and MUST take the fingerprint of the file the editor loaded: a file that changed on disk since is refused with `KNOWLEDGE_FILE_CONFLICT` (409) and left untouched. The refusal MUST carry what an editor needs to recover without a second save over the file — `saved: false`, and the document as it is on disk now, its body and its fingerprint — so the page can offer Reload, Compare and Copy my text. The read route MUST carry that fingerprint. The save changes the document's content in a commit naming the user, so the sweep treats it as an out-of-band edit to carry outward as a newer statement (see "Keep direct file edits a complete way to change knowledge", "Let the newer or better-evidenced statement win"), and an accepted save is a commit naming the user (see "Keep every document's history and undo a pass as a whole"). An inbox item and a path outside a document MUST be refused.

#### Scenario: save an edited body and refuse a stale one
- **GIVEN** a document `shopee/infra/cache.md` read with its fingerprint
- **WHEN** a new body is saved with that fingerprint, and then another body is saved with the same, now stale, fingerprint
- **THEN** the first save rewrites the body, keeps the frontmatter's title and description, and answers with the new fingerprint
- **AND** the second is refused with 409 `KNOWLEDGE_FILE_CONFLICT` and the file still holds the first save's body

#### Scenario: a stale save answers with what is on disk now
- **GIVEN** a document open in the editor that curation rewrites on disk before the user saves
- **WHEN** the user's save arrives with the fingerprint the editor loaded
- **THEN** it is refused 409 `KNOWLEDGE_FILE_CONFLICT` with `saved` false and the body and fingerprint the document has on disk now
- **AND** the file holds curation's text, and saving the user's text again needs the new fingerprint

### Requirement: Keep every document's history and undo a pass as a whole
Every accepted write to a collection MUST be a git commit naming its writer ([Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer](../../../docs/decisions/every-vault-write-is-a-validated-commit-naming-its-writer.md)). The commits are the vault repository's, under `knowledge/` ([vault-storage](../vault-storage/spec.md) "Show, compare and restore any version of a vault file"): the knowledge root keeps no repository of its own. A person's save, restore, undo or delete names the user; material promoted on arrival names whoever submitted it — the user, or, for a file an agent wrote into the inbox, the actor the file reports; a curation pass is **one commit** naming Coffer's curation and the item it curated — and, for an item an agent wrote, that agent, taken from the `knowledge_written` audit event of the submission; a change that arrives through vault sync names sync; and a change any other writer made in the tree — a person's own editor, an agent's file tools — MUST be committed as an edit on disk before Coffer's next commit, so it is never counted as Coffer's. A document's history MUST list its versions newest first with their writer and time, show the diff of each, and restore any version as a new commit. A pass MUST be undoable **as a whole**: undoing it puts every document it wrote or retired back exactly as it was before the pass, as one new commit naming the user; the item the pass consumed is not put back in the inbox when the pass merged it (its text stays in the history), but MUST be put back when the pass merged nothing — a `no_model` pass, a `too_large` item or an item the pass gave up on turned the item into a document as it stood, so removing that document without returning the item would lose the knowledge; when a later commit changed one of the same documents, the undo MUST be refused naming that document rather than overwrite the later change, and the refusal (409 `KNOWLEDGE_UNDO_CONFLICT`) MUST carry in its details, beside the document and the later version, `handoff`: a prompt the daemon writes asking the person's agent to undo the pass by hand — naming the pass and its summary, the knowledge folder, every document it touched and what it did to each, each document edited since with the version that last changed it, and where to read the pass's diff and the later ones in the vault repository (under `knowledge/`) — reversing what the pass changed while keeping the later edits, editing only the files (Coffer records them as an edit on disk), committing nothing itself, and showing each result first. Only a curation pass is undone this way — any single version is restored instead. The vault is a git repository on every machine that runs Coffer ([vault-storage](../vault-storage/spec.md) "Keep the vault a git repository whether or not it syncs"); a history read git cannot answer MUST answer 503 `KNOWLEDGE_HISTORY_UNAVAILABLE` while every write keeps working. git is looked for on every read, so one removed while the daemon runs is answered the same way. When the cause is that git is not installed, the refusal's details MUST carry `reason: "git_missing"` and `handoff`, a prompt asking the person's agent to install git on this machine — naming its OS and architecture and what needed git — the way that fits the machine, confirming it with `git --version`; neither the prompt nor the error's message may name an install command.

#### Scenario: a document's history lists its versions with their writers
- **GIVEN** a document that a pass created from a Codex item, that the user then edited, and that a pass then merged a Claude Code item into
- **WHEN** its history is read
- **THEN** it lists three versions newest first, written by Coffer's curation naming Claude Code's item, by the user, and by Coffer's curation naming Codex's item, each with its diff
- **AND** restoring the oldest version writes a new commit and leaves the history intact

#### Scenario: undo a pass as a whole
- **GIVEN** a pass that changed two documents and retired a third
- **WHEN** the user undoes it
- **THEN** one new commit puts all three documents back as they were before the pass

#### Scenario: undoing a pass that promoted an item puts the item back
- **GIVEN** a `no_model` pass that promoted an inbox item into a document at the collection root
- **WHEN** the user undoes that pass
- **THEN** the promoted document is gone and the item is back in the collection's inbox with the text it had, so nothing is lost
- **AND** undoing a pass that merged its item into other documents leaves that item out of the inbox

#### Scenario: an undo that would overwrite a later change is refused
- **GIVEN** a pass that changed a document the user has edited since
- **WHEN** the user undoes the pass
- **THEN** the undo is refused naming that document, and nothing is written

#### Scenario: an edit on disk becomes a version of its own
- **GIVEN** a document a person edits in their own editor, outside Coffer
- **WHEN** the user then saves another document from the web UI
- **THEN** the edited document's history shows the edit as its own version, written on disk, and the save's commit holds only the saved document

#### Scenario: a refused undo carries a prompt for undoing the pass by hand
- **GIVEN** a pass that changed a document the user has edited since
- **WHEN** the user undoes the pass
- **THEN** the refusal names the document and the version that edited it, and carries a prompt naming the pass, that document with that version, where to read the pass's diff in the vault repository, keeping the later edits and committing nothing
- **AND** nothing is written

#### Scenario: no git hands installing it to an agent
- **GIVEN** a machine with no git
- **WHEN** a document is written and its history is then read
- **THEN** the write works and the read is refused `KNOWLEDGE_HISTORY_UNAVAILABLE` with reason `git_missing` and a prompt to install git naming this machine and `git --version`, and neither the prompt nor the message names an install command

### Requirement: Follow knowledge changes across collections
The system MUST serve one feed of the recent changes to knowledge across every collection, newest first, paged by an opaque cursor ([resource-framework](../resource-framework/spec.md) "Page growing lists by an opaque cursor") and filterable to one collection: every curation pass, every document a person or an agent wrote, restored or deleted, every undo, and every change from sync or from disk — each with its writer, its time, its collection and, for each document it touched, whether that document was added, changed or removed and how many lines were added and removed. Material still waiting is not a change: the feed MUST carry it separately, as the items waiting in each collection's inbox with their title, who submitted them and when. One change MUST be readable in full — every document it touched with its diff — so a pass can be inspected before it is undone. The feed is `GET /api/v1/knowledge/changes` and one change `GET /api/v1/knowledge/changes/{version}`, both routes of the web UI's Recent changes.

#### Scenario: recent changes lists passes and edits across collections with the waiting items
- **GIVEN** a pass in one collection, a person's edit in another, and two items waiting
- **WHEN** the feed is read, and read again filtered to one collection
- **THEN** both changes are listed newest first with their collections, writers and per-document line counts, and the two waiting items are listed with who submitted them
- **AND** the filtered read holds only that collection's changes and waiting items, and one change read in full carries each document's diff

### Requirement: Delete a document or a collection at once and offer Undo
The web UI MUST delete a document or a collection **at once**: its ⋯ menu's **Delete document** and **Delete collection** open no confirmation and ask for no typed name, because a delete is reversible (see "Restore a deleted collection or document from Recent changes"). The page MUST report the delete in a toast — *Deleted <name>* — carrying **Undo**, which restores what the delete removed from the vault history exactly as **Restore** in Recent changes does, and MUST then show the collection page after a document's delete and Recent changes after a collection's. The delete is audited as a `knowledge_deleted` event, and an Undo refused because the path or name is taken again MUST say so rather than overwrite it. Deleting a **memory partition** is not covered: it is irreversible and keeps its confirmation ([memory](../memory/spec.md) "Present a partition as its memories").

#### Scenario: delete a document at once and undo it
- **GIVEN** a document open in the Knowledge page
- **WHEN** the user chooses ⋯ → Delete document
- **THEN** no dialog asks, the document is gone, the collection page shows, and a toast reads *Deleted <name>* with Undo
- **AND** choosing Undo puts the document back at its path with its text, as one new change by the user

#### Scenario: delete a collection at once and find it in Recent changes
- **GIVEN** a collection with a document and an item waiting
- **WHEN** the user chooses ⋯ → Delete collection
- **THEN** no dialog asks and no name is typed, the collection is gone, Recent changes shows, and the toast offers Undo
- **AND** the delete is listed there with Restore even after the toast has closed

### Requirement: Restore a deleted collection or document from Recent changes
Deleting a document or a whole collection MUST keep what it removed in the knowledge history, and Recent changes MUST list the delete — a document's under its collection, a collection's with every file it removed — with **Restore**. Restoring MUST put back exactly what the delete removed, as it was just before it: a document into its collection; a collection as a new collection of the same name with its documents, its `README.md` and the items that were waiting in its inbox. A collection restore MUST write every file first and register the collection's row last, so a failure part-way leaves no row and no partial directory: what was written is removed again and the same restore can be tried afresh. The restore MUST be one new change naming the user, carrying the version of the delete it restored, and recorded as a `knowledge_edited` audit event; the delete itself stays in the history. A restore MUST be refused with nothing written when it would overwrite — a document at the same path, `409 KNOWLEDGE_RESTORE_CONFLICT` naming it, or a collection of the same name, `409 KNOWLEDGE_COLLECTION_EXISTS` — and a change that is not a delete MUST be refused with `400 KNOWLEDGE_NOT_A_DELETE`. The route is `POST /api/v1/knowledge/changes/{version}/restore`, the web UI's own. Recent changes MUST say a refused restore on the delete's row, and show **Restored** instead of Restore once a later change restored it.

#### Scenario: restore a deleted collection from Recent changes
- **GIVEN** a collection holding a document, a `README.md` and one item waiting in its inbox, which the user deletes
- **WHEN** Recent changes is read and the user restores the delete it lists
- **THEN** the collection is back under its name with its document, its README's description and its waiting item, as one new change by the user naming the delete it restored
- **AND** a second restore of the same delete is refused because a collection of that name exists, and writes nothing

#### Scenario: a collection restore that fails part-way leaves nothing behind
- **GIVEN** a deleted collection whose restore fails while one of its files is being written
- **WHEN** the user restores the delete
- **THEN** the restore fails, no collection of that name is registered, and no directory of that name is left on disk
- **AND** a second restore, once the cause is gone, succeeds

#### Scenario: restore a deleted document
- **GIVEN** a document the user deletes
- **WHEN** the user restores the delete from Recent changes
- **THEN** the document is back at its path with the text it had, and its history lists the restore, the delete and the versions before them

#### Scenario: a restore that would overwrite is refused
- **GIVEN** a deleted document whose path holds a new document again
- **WHEN** the user restores the delete
- **THEN** the restore is refused naming that document, and the new document is unchanged
- **AND** restoring a change that is not a delete is refused as not a delete

### Requirement: Name a collection by its folder and edit its description in place
A collection MUST carry no title: every surface — the web UI's tree, its pickers and its collection view, and the command palette — MUST show a collection by its folder name, and the collection routes MUST carry no `title` field. A title sent for a collection through the kind-agnostic update MUST be refused as a validation error, with nothing changed. What a collection is about MUST be its description, the opening paragraph of its `README.md` (see "Read a collection's description from its README"), and the web UI's collection view MUST show it as text that is edited **in place**: choosing it opens it for editing, leaving the field or pressing ⌘Enter saves it, Esc cancels, and a saved edit reports a toast with **Undo**. A save rewrites exactly that paragraph and leaves the rest of the README as it was, as one change naming the user, audited as an edit of the collection, and re-renders the guide skill; Undo puts the previous paragraph back as a change of its own. The route is `PUT /api/v1/knowledge/collections/{uid}/description`, the web UI's own. An empty description MUST be refused. Creating a collection in the web UI MUST ask for its name and for what belongs in it, both required. The collection's ⋯ menu in the web UI MUST offer **Rename…**, a dialog with the name field that sends the kind-agnostic update (`PATCH /api/v1/resources/{uid}` with the new `name`); the collection's directory MUST move with the name, and the page MUST stay on the same collection, whose address carries its uid. A refused name — taken by another collection or a folder already there, or not a valid folder name — MUST be shown under the field with the dialog still open and nothing changed.

#### Scenario: a collection carries no title
- **GIVEN** a collection
- **WHEN** it is listed, and a title is then sent for it through the kind-agnostic update
- **THEN** the listing carries its name and no title, and the update is refused as a validation error with the title still empty

#### Scenario: edit a collection's description in place
- **GIVEN** a collection whose README opens with a heading, a paragraph and a section a person wrote under it
- **WHEN** the user edits its description
- **THEN** only the opening paragraph is rewritten, the collection lists the new description, and the edit is one change by the user, audited as an edit of the README
- **AND** an empty description is refused, and the web UI saves on leaving the field, cancels on Esc, and offers Undo in its toast

#### Scenario: rename a collection from its menu
- **GIVEN** a collection open in the web UI
- **WHEN** the user picks Rename… from its ⋯ menu and enters a new name
- **THEN** the kind-agnostic update is sent with that name, the dialog closes, a toast names the new name, the collection list is read again and the page stays on the same collection
- **AND** a name the server refuses is shown under the field and the dialog stays open

### Requirement: Submit material by writing a file into the inbox
An agent MUST be able to add knowledge by writing a Markdown file at `<collection>/.inbox/<any-name>.md`, with optional frontmatter, using its own file tools. The sweep MUST recognise a new inbox file that no Coffer surface wrote and **normalise** it before committing it as an edit on disk (see "Keep every document's history and undo a pass as a whole"):

- `title` is kept, else the first `# ` heading, else the file name's stem;
- `description` is kept, else the first prose paragraph, else the title — the same fallback an upload uses (see "Fill frontmatter on converted material");
- `actor` is kept as written (it is self-reported), else `agent`;
- `created_at` and `updated_at` are kept, else the time the sweep saw the file;
- every other key a writer set is kept.

Coffer MUST record one `knowledge_written` audit event per item, carrying `actor_reported: true` when the actor came from the file. A Markdown file in a top-level directory that is not a collection MUST be left alone and MUST NOT be catalogued: only a person creates a collection (see "Create collections only deliberately"). A non-Markdown file in an inbox MUST be left in place, logged, and not curated. The item is then material like any other (see "Submit every entrance's input as material").

#### Scenario: a bare inbox file is normalised and audited
- **GIVEN** a `shopee` collection, and an agent that writes `shopee/.inbox/cache-ttl.md` holding a `# Cache TTL` heading, a paragraph and no frontmatter
- **WHEN** the sweep runs
- **THEN** the file's frontmatter carries `title` `Cache TTL`, a `description` drawn from the paragraph, `actor` `agent`, and `created_at` and `updated_at` set to when the sweep saw it, with the body unchanged
- **AND** one `knowledge_written` audit event is recorded with `actor_reported` false, and the item is owed a curation pass

#### Scenario: keys a writer set are kept
- **GIVEN** an inbox file whose frontmatter sets `actor` `user`, a `title`, and a `source` key
- **WHEN** the sweep normalises it
- **THEN** the title, the actor and the `source` key are as written, and the audit event records `actor_reported: true`

#### Scenario: a file outside a collection or that is not Markdown is not material
- **GIVEN** a Markdown file at `notes/.inbox/idea.md`, where `notes` is not a collection, and a `shopee/.inbox/data.bin` file
- **WHEN** the sweep runs
- **THEN** the first is left alone and appears in no catalogue, no `notes` collection is created, and the second stays in the inbox, is logged, and is not curated

### Requirement: Expose no knowledge tool
Coffer's MCP gateway MUST expose **no** tool that reads, lists, searches, writes or deletes knowledge. An agent reads knowledge with its own file tools at the paths the `coffer-guide` skill gives it and adds to it by writing files (see "Submit material by writing a file into the inbox").

#### Scenario: no knowledge tool appears in the client tool list
- **GIVEN** a real daemon with an upstream MCP server registered, driven over its `/mcp` endpoint by the MCP SDK so the SDK's own models validate every frame
- **WHEN** the client initializes and calls `tools/list`
- **THEN** `coffer__search_tools` is in the listing beside the upstream server's own tools, and `coffer__write`, `coffer__list`, `coffer__grep`, `coffer__read`, `coffer__search` and `coffer__delete` are **absent**

### Requirement: Manage knowledge in the web UI
People MUST manage knowledge in the web UI: creating collections, uploading documents, curating now, reading a document's history and restoring a version, undoing a pass, reading the recent changes and restoring a delete, and editing a collection's description. The REST routes under `/api/v1/knowledge` behind those pages are the web UI's own private interface, not a public API: a route the web UI does not call MUST NOT exist, and there MUST be no route that creates a document at a path — a person's text reaches knowledge through the editor (see "Save a document edited in the web UI") or as material like every other entrance (see "Submit every entrance's input as material"). There MUST be no index, reindex, check-sources, update-source or embedding-configuration endpoint, no settings endpoint for the cwd-derived scope axis "Derive no boundary from the working directory" forbids, and no per-agent reach endpoint or enabled switch for this kind (see "Serve every collection to every agent"). Collection deletion goes through the Resource framework (`DELETE /api/v1/resources/{uid}`). There MUST be no command group for knowledge and no `coffer path` target for it: a collection's documents are plain files, so agents and people read, edit and delete them directly under the knowledge root that the `coffer-guide` skill names (see "Keep direct file edits a complete way to change knowledge").

#### Scenario: no knowledge command group or path target exists
- **GIVEN** the `coffer` command tree
- **WHEN** it is enumerated, and `coffer path` is run with a `knowledge` target
- **THEN** there is no `knowledge` command group, and `coffer path` refuses `knowledge` as an unknown target

#### Scenario: the routes are the web UI's, with no material or create-at-path route
- **GIVEN** the daemon's route table under `/api/v1/knowledge`
- **WHEN** it is enumerated
- **THEN** it offers create a collection, list a level, read, save an edited body, upload, delete a document, trigger curation, a document's history and a version's diff, restore, the recent changes and one change, undo, and rewrite a description
- **AND** it carries no `/material` route, no route that creates a document at a path, and no index, reindex, source, embedding, scope or reach endpoint
