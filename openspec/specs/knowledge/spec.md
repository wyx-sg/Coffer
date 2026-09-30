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

Assumptions: the corpus stays in the hundreds of files, so a catalogue of every document fits a skill body (measured at ~5.2K tokens for 58 documents); tens of thousands of files would be a different design and the place embeddings would be reconsidered. Curation rewrites documents with no review step; what stands between a person's work and a bad pass is that a person's edit is never reverted, the eight-write bound, one pass per collection, the audit event every pass records, and the collection's git history, where every pass is one commit that can be undone as a whole. The internal connection is the one place user content may leave the machine, exactly as [channels](../channels/spec.md) "Transcribe inbound voice only when the user opted in" establishes for voice; curation and an ingested document's generated description are the only things this layer sends there. One item is small enough to hand a model whole; a pass that meets one too large for its context reports it and keeps the item as it stands rather than truncating it.

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
Hidden entries (dot-prefixed) MUST be excluded from every count of documents and from the catalogue. The system itself MUST write exactly one: a collection's `.inbox/`, where submitted material waits to be merged (see "Submit every entrance's input as material"). An inbox item MUST be deleted once a pass has merged it or it has been promoted (see "Settle an item only after its pass completes", "Promote material directly when no model is configured"). The tree route MUST list a collection root's `.inbox/` as a directory and its items as files, and the read route MUST read an inbox item, so a person can see what is waiting; no other hidden entry is listed or readable, and no surface may write or delete an inbox item. `.history/` and `.raw/` stay removed: what a pass or a person replaced is kept in the collection's git history (see "Keep every document's history and undo a pass as a whole"), not in the collection, and nothing is kept of the document an upload arrived in.

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
A **collection** is a top-level subdirectory of the knowledge root and is one `knowledge` Resource. It MUST be created deliberately — through the REST/CLI/UI surface — and MUST NOT be provisioned by a read, a write, or an agent's working directory. Creating one creates its directory and nothing inside it but an optional `README.md`.

#### Scenario: an unknown collection is an error, never auto-created
- **GIVEN** a knowledge root with no `typo` collection in it
- **WHEN** `coffer knowledge show typo --json` runs, and then `coffer path knowledge typo`
- **THEN** both commands exit non-zero and no `typo` directory exists afterwards: a read never provisions a collection

### Requirement: Derive no boundary from the working directory
The system MUST NOT derive any boundary from the agent's cwd. There MUST be no `global` scope, no `project-<ULID>` naming, no git-root resolution, no scope-to-project-root mapping table, no auto-provisioning and no scope display labels.

#### Scenario: refuse a write to a scope name instead of resolving it
- **GIVEN** a knowledge root holding only a `shopee` collection
- **WHEN** `coffer__write` names the collection `global`
- **THEN** the write is refused with `shopee` named as the available collection
- **AND** no `global` directory and no `project-` directory exists afterwards

### Requirement: Read a collection's description from its README
A collection's one-line description MUST be the first paragraph of its `README.md`, absent when there is none, and MUST be read off disk on every listing. It MUST NOT be stored in the database — not even in the `resources` row's own generic `description` column, which for this kind stays empty: a copy written once and read by nothing is wrong from the first time the person edits the file. It is also what the delivered skill's own description draws on (see "Describe Coffer and the collections' subjects in the skill description"), so a collection that fails to describe itself is a collection an agent never recognises.

#### Scenario: the catalogue lists collections with their README description
- **GIVEN** a collection created with the description "First description", whose `README.md` is then edited by hand to open with "Edited by hand."
- **WHEN** `coffer knowledge list --json` runs
- **THEN** the collection's `description` is the README's first paragraph as edited, not the string the creation call supplied — the description is read off disk on every listing, never out of a row

### Requirement: Present knowledge as files on disk
What this layer serves is **files on disk**, and the system MUST describe it as such wherever it is presented: a delivered path is the whole of the access story, because an agent handed the knowledge root reads anything under it with the shell tools it already has. Every collection is served to every agent (see "Serve every collection to every agent"), and nothing about a collection may be presented as a filesystem boundary: a collection has no switch that would hide it from a process that can open the directory.

#### Scenario: the guide hands over files to read with the agent's own tools
- **GIVEN** a collection holding one document
- **WHEN** the guide skill's catalogue is rendered
- **THEN** it tells the agent to read each document at `<root>/<collection>/<path>` with its own file tool and names the directory the collection's files live under
- **AND** it names no Coffer tool as the way to read a document

### Requirement: Submit every entrance's input as material
Every entrance Coffer serves — `coffer__write`, the CLI's `write` and its route `POST /api/v1/knowledge/material`, an upload, and a channel's `/kb` — MUST **submit material** into the named collection's `.inbox/` rather than write a document. What becomes of material is curation's to decide (see "Curate through a fenced four-tool pass"): which document it belongs in, what in it is new, and what it corrects. The one exception is "Promote material directly when no model is configured", where no model is configured to decide and the material becomes a document as it stands.

#### Scenario: the CLI and the material route leave material in the inbox
- **GIVEN** a `shopee` collection and an internal model connection configured
- **WHEN** material is submitted once with `coffer knowledge write` and once with `POST /api/v1/knowledge/material`
- **THEN** each answer reports `pending` with no path, and two items wait in `shopee/.inbox/`
- **AND** no document has been added to the collection's visible tree

### Requirement: Submit material through coffer__write
`coffer__write` MUST submit material to a named collection from `title`, `description` and body text. It MUST take no path, no folder and no lane, and MUST NOT replace anything: two submissions of the same title are two pieces of material. A submission MUST be a plain file write — no LLM, no conversion, no indexing step — and MUST record one `mcp_invocations` row and one audit event naming the calling agent, taken from the session's handshake identity ([mcp-gateway](../mcp-gateway/spec.md) "Take the agent identity from the handshake") written in as an `agent` argument no tool advertises and no caller can set. A person's **Add a document** in the web UI (see "Present a collection as one tree in the web UI") submits through the same path with the actor `user`, so there is no route that creates a document directly. Its answer MUST say what became of the material: `pending`, with no path — an inbox address vanishes once the material is merged, so reporting one would be reporting an address that is about to stop existing — or `written`, with the document's path, when it was promoted (see "Promote material directly when no model is configured"). A submission naming a collection that does not exist MUST be refused with the collections that **are** available: that names exactly what this agent's own delivered skill already lists, and it turns a dead end into a correction for a model that reached for the tool without opening the skill.

#### Scenario: written material waits in the inbox, or becomes a document with no model
- **GIVEN** a `shopee` collection created through `coffer knowledge add`, and an internal model connection configured
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
- **WHEN** the owner follows it with the plain text `/kb research`
- **THEN** the ingest service is called exactly once — that collection, that file name, those bytes, `actor` `user` and the channel's own default agent — and the channel replies with a confirmation naming both the file and the collection

### Requirement: Bound uploads and leave nothing behind on failure
Upload MUST be bounded: one file per call, a size ceiling, and a refusal that names the limit. A conversion failure MUST leave nothing behind — no inbox item, no document.

#### Scenario: a document is never stored half-converted
- **GIVEN** a document whose converter succeeds but yields no text, as an image-only PDF does
- **WHEN** it is uploaded
- **THEN** the upload is refused with the reason naming the document type, and nothing is written — no inbox item, no document, no original

### Requirement: Let only a person delete a document
Deleting a document MUST be a person's action, and it MUST be allowed for **any** document, whoever wrote it: the tree is the person's as much as curation's. The REST route and the web UI MUST offer it, and each deletion through them MUST record a `knowledge_deleted` audit event. On the command line a person deletes the file itself, in the collection directory that `coffer path knowledge <collection>` names, and the deletion is live on the next read and the next catalogue (see "Keep direct file edits a complete way to change knowledge"). No agent-facing tool may delete anything. Inside a pass, `retire_document` is curation's own way to remove a document whose content it has written elsewhere (see "Preserve every fact a pass is shown"), and it is bounded like a write (see "Bound a pass to eight writes").

#### Scenario: delete a document an agent wrote
- **GIVEN** two documents in `shopee/` whose frontmatter `actor` is `agent`
- **WHEN** a person deletes one through `DELETE` on the knowledge route, and removes the other's file from the directory `coffer path knowledge shopee` prints
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
Passes MUST be run by a **sweep on an interval** and by a manual trigger. The interval is the one global curation interval — the `curate` pass's interval under Settings › General's Coffer's model section, 60 minutes by default ([internal-engine](../internal-engine/spec.md) "Show and change Coffer's model in Settings › General") — and no collection has an interval of its own. Each sweep MUST read the interval afresh rather than capture it at boot, and MUST find a collection's pending items in this order: first every inbox item, oldest first — until it is merged it is knowledge no agent can read — then every document whose modification time is newer than its own `coffer_curated_at` stamp (or which has none), meaning a person or an agent edited or added it out of band. A sweep MUST run at most a bounded number of passes per collection, so a freshly migrated vault drains visibly rather than in one long batch. The manual trigger — **Curate now** in the web UI, `coffer knowledge curate <collection>` on the command line — MUST run passes until the collection has nothing pending, in the same order (inbox items oldest first, then documents edited out of band), still **one pass at a time** (see "Run one pass per collection at a time") and each pass still bounded (see "Bound a pass to eight writes"). While it runs it MUST report progress as *n of m*, where *m* is what was pending when it started — readable on the in-flight list ([resource-framework](../resource-framework/spec.md) "Report the passes in flight in one cross-kind read"), which carries the run's *n* and *m*, and announced on the daemon's event stream as each pass finishes — and it MUST stop at the first pass that fails, reporting that pass and leaving the rest pending for the next run or sweep. Given one document, it curates just that document. A trigger arriving while a pass over the collection is in flight is refused with 409, as any other.

#### Scenario: an item is curated once, not on every sweep
- **GIVEN** a document already carrying `coffer_curated_at` no earlier than its own modification time
- **WHEN** the sweep looks for work
- **THEN** the document is not owed a pass; and with the file touched afterwards, the next sweep does owe it one

#### Scenario: curate now drains a collection until nothing is pending
- **GIVEN** a collection with three inbox items and one document edited out of band, and an internal connection configured
- **WHEN** the user chooses Curate now
- **THEN** four passes run one after another — the three items oldest first, then the document — each within the eight-write bound
- **AND** afterwards the inbox is empty and nothing is owed a pass

#### Scenario: curate now reports progress
- **GIVEN** a collection with three pending items
- **WHEN** Curate now runs
- **THEN** progress reads 1 of 3, 2 of 3 and 3 of 3 as passes finish, on the in-flight list and on the event stream, and `coffer knowledge curate` prints the same

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
An item MUST be settled only after its pass completes: merged material is deleted from the inbox, and an edited document is stamped with `coffer_curated_at` and nothing else about it changes. Every document curation itself writes MUST be stamped as it is written, so the sweep does not hand the pass its own output back as an edit. A stamp MUST set the file's modification time to the stamp, so the stamping itself does not count as an edit. A pass that does not complete MUST leave the item as it was, so it is curated later rather than lost. Three ways an item leaves the queue without a completed pass keep it as it stands rather than settle a merge that never happened: no model configured ("Promote material directly when no model is configured"), an item too large for any pass ("Report every pass outcome as a status"), and an item cut off three times in a row ("Bound a pass to eight writes").

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
The skill MUST reach each agent as the **ordinary shared-master link** of [skill-manager](../skill-manager/spec.md) "Deliver a skill as a directory link" — one master folder, one link per agent — and MUST NOT be written into an agent's directory as real bytes. **This too reverses what this requirement used to say.** The rule was that each agent's copy be independent bytes, because a link into a shared master was "a copy this layer cannot re-render, stale or reclaim". Neither half of that is true any more: the master is re-rendered in place at every boot and whenever the catalogue changes, which re-renders every agent's view of it at once; and reclaiming is the skill kind's own per-agent reconciliation against the delivery predicate ([skill-manager](../skill-manager/spec.md) "Reconcile deliveries per agent on every trigger"), which removes one agent's link without touching another's or the master. The text is the same for every agent (see "Serve every collection to every agent"), so per-agent bytes were buying independence nothing asked for while paying for it with a delivery path of this layer's own. Re-rendering MUST happen whenever the catalogue changes — after a curation pass or a promotion, or a collection's creation, rename or deletion, and on every sweep tick so a document a person added by hand is catalogued too — and MUST never raise: a failed render leaves the previous master exactly where it was, and the corpus stays readable at paths a person can still give an agent.

#### Scenario: every agent reaches the guide through the one master folder
- **GIVEN** two registered agents and the `coffer-guide` skill seeded
- **WHEN** each agent's `<config_dir>/skills/coffer-guide` is inspected
- **THEN** each is the ordinary Coffer-managed link into `~/.coffer/skills/coffer-guide/`, not a directory of real bytes
- **AND** a re-render that changes the catalogue changes what both agents read in one write, while narrowing the skill's scope to one agent reclaims only the other agent's link and leaves the master untouched

### Requirement: Describe Coffer and the collections' subjects in the skill description
The skill's **frontmatter description** MUST describe Coffer itself — naming its built-in tools so a model recognises them — **and** name the subjects the collections cover, drawn from their READMEs. It is the only part of this layer that is always in a model's context, so it MUST carry matchable specifics rather than a description of the layer, and it MUST fit the tightest frontmatter ceiling any importer imposes (1024 characters), dropping whole collection subjects from the tail rather than cutting a sentence mid-way.

#### Scenario: one skill carries both Coffer's manual and the catalogue
- **GIVEN** a rendered `coffer-guide` `SKILL.md`
- **WHEN** its frontmatter and its body are read
- **THEN** the description names Coffer and its built-in tools as well as the collections' subjects, and is within 1024 characters — a catalogue too large to fit drops whole collection subjects from the tail rather than ending mid-sentence
- **AND** the body carries the manual first — the two built-in tools, the tiering contract, that Coffer never writes an agent's memory, and that no Coffer tool waits on an approval — and the catalogue after it, in one file

### Requirement: Merge the manual and the catalogue in the skill body
The skill's **body** MUST be one merged manual: Coffer's own — its two built-in tools, `coffer__search_tools` and `coffer__write`, and when to reach for each; the tiering contract that makes an unlisted upstream tool still callable; the memory root, and that Coffer's distilled memory notes are Markdown under it which the agent finds by searching that directory with its own tools; that Coffer's own logs are read with `coffer log` and located with `coffer path logs`; the fact that Coffer reads an agent's memory and never writes it; that no Coffer tool waits on a human approval; and what does not belong in knowledge — **followed by** the catalogue: the path of the knowledge root, and, for each collection, every document's collection-relative path, title and description. It MUST instruct the agent to read those files with its own tools, to reach for `coffer__write` when it learns something durable, and that it may also correct or extend a document it has read by editing the file itself, which the next sweep carries into the rest of the collection (see "Keep direct file edits a complete way to change knowledge"). One skill, not a set: a frontmatter description is resident in every session whether the skill is opened or not, while a body is paid for only when a model reaches for it, so a second skill would spend the resident budget again to describe something most sessions never open.

#### Scenario: the skill body carries the catalogue and the absolute root
- **GIVEN** a collection holding three documents
- **WHEN** the skill is rendered
- **THEN** its body carries each document's collection-relative path, title and description, and the path of the knowledge root, and it instructs the agent to read those files with its own tools
- **AND** the frontmatter `description` names the collection's subject, taken from the collection's own `README.md`, so a model matching on it has something to match

#### Scenario: the manual names two tools, the memory root and the log reader
- **GIVEN** a vault with one collection
- **WHEN** the skill is rendered
- **THEN** its manual names exactly two built-in tools, `coffer__search_tools` and `coffer__write`, and names neither `coffer__recall` nor `coffer__diagnose`
- **AND** it names the memory root with the instruction to search it with the agent's own tools, and names `coffer log` and `coffer path logs` as the way to read Coffer's own logs

### Requirement: Keep the handshake instructions to what a skill cannot carry
The MCP gateway's own `initialize` instructions MUST stay within their character cap and MUST carry only what a skill cannot: what Coffer is, the names of its two built-in tools (`coffer__write`, `coffer__search_tools`) so they are recognisable in a tool list, one line saying that Coffer's memory notes are files under the memory root read with the agent's own tools and that Coffer's own logs are read with `coffer log`, the tiering sentence when tools are actually hidden this session, and a pointer to the `coffer-guide` skill for everything else. It MUST NOT restate the manual, MUST NOT name a retrieval tool, and MUST NOT carry the catalogue — the catalogue is in the skill body, which costs a session nothing until a model opens it. A built-in tool whose experimental feature is switched off is not in the tool list, and the instructions MUST NOT name it either ([experimental-features](../experimental-features/spec.md) "Withdraw what a switched-off feature put in front of agents").

#### Scenario: the handshake names Coffer's tools and points at the skill
- **GIVEN** a real daemon driven over its `/mcp` endpoint by the MCP SDK
- **WHEN** the client initializes, both with upstream tools hidden and with none hidden
- **THEN** the `instructions` text is within its character cap, names `coffer__write` and `coffer__search_tools`, names neither `coffer__recall` nor `coffer__diagnose`, and points at the `coffer-guide` skill for the rest
- **AND** it names no retrieval tool and carries no collection catalogue

### Requirement: Render the guide skill deterministically
The rendered `SKILL.md` MUST be a **pure function of the running build and the catalogue it is given**: the same build over the same collections MUST produce the same bytes, run after run and machine after machine. Nothing machine-specific may enter it — not an absolute home directory, not a timestamp, not a build path — and the skill's own config MUST likewise carry no timestamp of its generation.

**The reason is no longer convergence, and that changes what the requirement is worth saying.** It used to read "byte-identical on every machine running the same build against the same catalogue", with the hedge doing the real work, because the artifact converged: a purely local difference would have had two vaults overwriting each other's copy forever. It no longer converges at all ([vault-sync](../vault-sync/spec.md) "Withhold derived output in both halves") — every machine renders its own from files that converge plus its own reach, and two machines are *expected* to differ whenever their enabled sets differ, which is exactly what the hedge was excusing. What determinism buys now is local and still worth paying for: an unchanged vault re-rendering to the same bytes is what lets the seed skip the write, so a boot or a curation tick that changed nothing registers nothing, audits nothing and re-delivers nothing ([skill-manager](../skill-manager/spec.md) "Regenerate Coffer's builtin skill from the build") — and it is what makes the `version_hash` in the row mean "the content moved" rather than "time passed".

The knowledge root MUST still be written in its `~`-relative form whenever it sits in its default place, so a path an agent reads is one a person can retype; an explicitly relocated root (`COFFER_KNOWLEDGE_ROOT`) MUST be written out in full, because an accurate path is worth more than a tidy one.

#### Scenario: the rendered skill is byte-identical on two machines
- **GIVEN** the same build and the same catalogue rendered twice, once with the knowledge root at each of two different home directories, and once again with the root explicitly relocated
- **WHEN** the two default-placed renderings are compared byte for byte
- **THEN** they are identical, and the knowledge root appears in its `~`-relative form rather than as either home's absolute path
- **AND** the relocated root is written out in full, and the skill's stored config carries no timestamp of when it was generated

### Requirement: Present a collection as one tree in the web UI
The web UI MUST present a collection as **one tree** of its documents — no lanes, no tabs, no filter or retrieval box — with the chosen document in the pane beside it, the same two panes a skill's Files tab is. The pane MUST render the document and offer **Edit**, which turns it into an editor saved through "Save a document edited in the web UI" and reports a conflict in place; open-in-external-editor and reveal-in-file-manager; and delete, naming the exact path before it runs, reporting a refusal in place, and leaving the preview on no file afterwards. The tree MUST show the collection's `.inbox/` as a folder whose items open read-only, with no edit and no delete. The page MUST offer upload into the collection in view and a manual curation trigger that reports a pass already in flight. The tree and the pane MUST extend to the bottom of the window and scroll inside.

#### Scenario: the viewer shows one tree of documents
- **GIVEN** a collection page whose tree holds a document at the root and one inside a folder, with one item of material waiting in the inbox
- **WHEN** the page renders, a document's row is clicked, and then the inbox item's
- **THEN** there is one tree — no lane headings, no tabs, no filter input — listing both documents and an `.inbox` folder holding the item
- **AND** the document offers Edit, open-in-editor, reveal and delete, and the inbox item offers neither Edit nor delete

#### Scenario: edit a document in place
- **GIVEN** a document open in a collection's pane
- **WHEN** the user chooses Edit, changes the text and saves
- **THEN** the save is sent with the fingerprint the pane loaded, and the pane renders the saved body

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

### Requirement: Report every pass outcome as a status
Every curation outcome MUST be reported as a `status`, and the route that runs a pass MUST answer **200** for each of them, because none is a fault of the request: `ok` when a pass ran and settled its item; `no_model` when no internal connection is configured (see "Promote material directly when no model is configured"); `up_to_date` when nothing is pending, in which case no pass runs and nothing is touched; `too_large` when the item is past the size one pass can hold, with `limit` naming the ceiling; `truncated` when the recursion limit cut the pass off (see "Bound a pass to eight writes"); and `failed` when the pass did not complete. The manual trigger MUST answer with the outcome of each pass it ran, in order, ending at the first `failed`, and `up_to_date` when nothing was pending. The route MUST answer **404** for an unknown collection and **409** while a pass over the same collection is running (see "Run one pass per collection at a time"). A `too_large` item MUST never be shown to the model and MUST never be left pending — left where it was it would be offered to every sweep and refused by every pass: material is promoted to a document as it stands, exactly as the no-model path promotes it, and reported in `promoted`; an edited document, which has nothing to promote, is stamped curated and reported in `stamped`. Neither changes a word of the item.

#### Scenario: oversized material is promoted as it stands
- **GIVEN** a collection whose inbox holds one item of material longer than the item-size ceiling, and an internal connection configured
- **WHEN** a curation pass runs
- **THEN** it reports `too_large` with `limit` and lists in `promoted` the document the item became, whose body is the material as submitted and which carries a `coffer_curated_at` stamp
- **AND** the model was shown nothing, the inbox is empty and nothing is pending

#### Scenario: an oversized edited document is stamped, not re-offered
- **GIVEN** a document a person edited past the item-size ceiling, owed a pass, and an internal connection configured
- **WHEN** a curation pass runs
- **THEN** it reports `too_large` with `limit` and names the document in `stamped`, and the document's body is exactly what the person wrote under a new `coffer_curated_at` stamp
- **AND** the model was shown nothing and the sweep no longer finds the document pending

#### Scenario: a collection with nothing pending reports up to date
- **GIVEN** a collection holding only documents curation has already seen, and an internal connection configured
- **WHEN** a curation pass is run over it
- **THEN** it reports `up_to_date` with the collection's name and nothing else
- **AND** the model was shown nothing and every document is unchanged, stamp included

### Requirement: Serve every collection to every agent
Every collection MUST be named, catalogued and served to **every** agent, and a collection MUST NOT carry the Resource framework's per-agent reach or an enabled switch: the kind declares itself non-toggleable ([resource-framework](../resource-framework/spec.md) "Address every resource by an immutable uid through one kind-agnostic surface"). A collection leaves every agent's delivered skill only by being deleted. `coffer__write` MUST refuse a write naming a collection that does not exist, and MUST answer with the collections that do.

#### Scenario: every collection is in every agent's skill
- **GIVEN** two collections, `shopee` and `personal`, both holding documents, one of them stored disabled by an earlier version
- **WHEN** the database is migrated and the guide skill is re-rendered and seeded into its master folder
- **THEN** the master `SKILL.md` names both collections and lists both catalogues
- **AND** a request to disable either collection through the generic resource route is refused and changes nothing

### Requirement: Save a document edited in the web UI
`PUT /api/v1/knowledge/file` MUST replace a document's **body** with the text it is given and keep the document's frontmatter, and MUST take the fingerprint of the file the editor loaded: a file that changed on disk since is refused with `KNOWLEDGE_FILE_CONFLICT` (409) and left untouched. The refusal MUST carry what an editor needs to recover without a second save over the file — `saved: false`, and the document as it is on disk now, its body and its fingerprint — so the page can offer Reload, Compare and Copy my text. The read route MUST carry that fingerprint. The saved file's modification time moves, so the sweep treats it as a person's edit (see "Keep direct file edits a complete way to change knowledge", "Let newer statements win and a person's edit stand"), and an accepted save is a commit naming the user (see "Keep every document's history and undo a pass as a whole"). An inbox item and a path outside a document MUST be refused.

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

### Requirement: Cover knowledge management on REST and the CLI
The REST API under `/api/v1/knowledge` MUST cover: create a collection, list one level of a collection at a path, read a document, save an edited document's body (`PUT /file`, see "Save a document edited in the web UI"), submit material (`POST /material`), upload a document, delete a document, trigger curation, read a document's history, one version's diff and one version's body, restore a version, read the recent changes and one change in full, undo a pass, restore what a delete removed (see "Restore a deleted collection or document from Recent changes") and rewrite a collection's description (see "Name a collection by its folder and edit its description in place") (see "Keep every document's history and undo a pass as a whole", "Follow knowledge changes across collections"). The `coffer knowledge` CLI group MUST offer `list`, `show`, `add`, `edit`, `rm`, `write` (submit material), `upload`, `curate`, `history`, `restore`, `changes` and `undo`. A collection's documents are plain files, so on the command line `coffer path knowledge [<collection>]` prints the absolute path of the knowledge root or of one collection, and the documents are listed, read, edited and deleted on disk; the `coffer knowledge` group carries no command that lists, prints, saves or deletes a document. The web UI's editor saves through `PUT /file`, because a browser page cannot write the disk. A person may equally edit a document in their own editor, reached from the page's open-in-editor action or from that path, and that edit is live on the next read (see "Keep direct file edits a complete way to change knowledge"). Collection deletion goes through the Resource framework (`DELETE /api/v1/resources/{uid}`; `coffer knowledge rm`). There MUST be no route that creates a document at a path — a person's Add a document submits material like every other entrance (see "Submit material through coffer__write") — and no index, reindex, check-sources, update-source or embedding-configuration endpoint, no settings endpoint for the cwd-derived scope axis "Derive no boundary from the working directory" forbids, and no per-agent reach endpoint, `scope` command, enabled switch or `enable`/`disable` command for this kind (see "Serve every collection to every agent"). These surfaces serve the human and the UI; they are not an agent's retrieval path.

#### Scenario: expose every knowledge operation on both surfaces
- **GIVEN** the daemon's route table and the `coffer knowledge` command group
- **WHEN** both are enumerated
- **THEN** the routes offer create, list a level, read, save an edited body, submit material, upload, delete a document, trigger curation, a document's history and a version's diff, restore, the recent changes and one change, and undo, and the command group offers exactly `list`, `show`, `add`, `edit`, `rm`, `write`, `upload`, `curate`, `history`, `restore`, `changes` and `undo`
- **AND** none is an index, reindex, source, embedding, scope or reach endpoint or a route that creates a document at a path, and the group has no `enable`, `disable` or `scope` command

#### Scenario: locate a collection's documents from the command line
- **GIVEN** a `shopee` collection holding a document at `shopee/infra/cache.md`
- **WHEN** `coffer path knowledge shopee` runs, and then `coffer path knowledge` with no collection
- **THEN** the first prints the absolute path of the `shopee` directory, under which the document is read at `infra/cache.md`, and the second prints the absolute knowledge root
- **AND** `coffer knowledge` offers no `collections`, `create`, `ls`, `read`, `save` or `delete` command

### Requirement: Keep every document's history and undo a pass as a whole
Every accepted write to a collection MUST be a git commit naming its writer ([Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer](../../../docs/decisions/every-vault-write-is-a-validated-commit-naming-its-writer.md)). Until the vault is itself one git repository, the commits MUST be kept in a repository of the knowledge root's own — a hidden entry like every dot-prefixed one (see "Hide dot-prefixed entries except the inbox"), which vault sync never mirrors — shaped to fold into the vault's history once the vault is one. A person's save, restore, undo or delete names the user; material promoted on arrival names whoever submitted it — the user, or the agent named by the session's identity; a curation pass is **one commit** naming Coffer's curation and the item it curated — and, for an item an agent wrote, that agent, taken from the `knowledge_written` audit event of the submission; a change that arrives through vault sync names sync; and a change any other writer made in the tree — a person's own editor, an agent's file tools — MUST be committed as an edit on disk before Coffer's next commit, so it is never counted as Coffer's. A document's history MUST list its versions newest first with their writer and time, show the diff of each, and restore any version as a new commit. A pass MUST be undoable **as a whole**: undoing it puts every document it wrote or retired back exactly as it was before the pass, as one new commit naming the user, and does not put the item it consumed back in the inbox; when a later commit changed one of the same documents, the undo MUST be refused naming that document rather than overwrite the later change. Only a curation pass is undone this way — any single version is restored instead. A machine with no git keeps every write working and records no history, and the history reads answer 503 `KNOWLEDGE_HISTORY_UNAVAILABLE`.

#### Scenario: a document's history lists its versions with their writers
- **GIVEN** a document the user created through Add a document, that a pass then merged a Claude Code item into, and that the user then edited
- **WHEN** its history is read
- **THEN** it lists three versions newest first, written by the user, by Coffer's curation naming Claude Code's item, and by the user, each with its diff
- **AND** restoring the first version writes a new commit and leaves the history intact

#### Scenario: undo a pass as a whole
- **GIVEN** a pass that changed two documents and retired a third
- **WHEN** the user undoes it
- **THEN** one new commit puts all three documents back as they were before the pass

#### Scenario: an undo that would overwrite a later change is refused
- **GIVEN** a pass that changed a document the user has edited since
- **WHEN** the user undoes the pass
- **THEN** the undo is refused naming that document, and nothing is written

#### Scenario: an edit on disk becomes a version of its own
- **GIVEN** a document a person edits in their own editor, outside Coffer
- **WHEN** the user then saves another document from the web UI
- **THEN** the edited document's history shows the edit as its own version, written on disk, and the save's commit holds only the saved document

### Requirement: Follow knowledge changes across collections
The system MUST serve one feed of the recent changes to knowledge across every collection, newest first, paged by an opaque cursor ([resource-framework](../resource-framework/spec.md) "Page growing lists by an opaque cursor") and filterable to one collection: every curation pass, every document a person or an agent wrote, restored or deleted, every undo, and every change from sync or from disk — each with its writer, its time, its collection and, for each document it touched, whether that document was added, changed or removed and how many lines were added and removed. Material still waiting is not a change: the feed MUST carry it separately, as the items waiting in each collection's inbox with their title, who submitted them and when. One change MUST be readable in full — every document it touched with its diff — so a pass can be inspected before it is undone. The feed is `GET /api/v1/knowledge/changes` and one change `GET /api/v1/knowledge/changes/{version}`; on the command line both are `coffer knowledge changes`.

#### Scenario: recent changes lists passes and edits across collections with the waiting items
- **GIVEN** a pass in one collection, a person's edit in another, and two items waiting
- **WHEN** the feed is read, and read again filtered to one collection
- **THEN** both changes are listed newest first with their collections, writers and per-document line counts, and the two waiting items are listed with who submitted them
- **AND** the filtered read holds only that collection's changes and waiting items, and one change read in full carries each document's diff

### Requirement: Restore a deleted collection or document from Recent changes
Deleting a document or a whole collection MUST keep what it removed in the knowledge history, and Recent changes MUST list the delete — a document's under its collection, a collection's with every file it removed — with **Restore**. Restoring MUST put back exactly what the delete removed, as it was just before it: a document into its collection; a collection as a new collection of the same name with its documents, its `README.md` and the items that were waiting in its inbox. The restore MUST be one new change naming the user, carrying the version of the delete it restored, and recorded as a `knowledge_edited` audit event; the delete itself stays in the history. A restore MUST be refused with nothing written when it would overwrite — a document at the same path, `409 KNOWLEDGE_RESTORE_CONFLICT` naming it, or a collection of the same name, `409 KNOWLEDGE_COLLECTION_EXISTS` — and a change that is not a delete MUST be refused with `400 KNOWLEDGE_NOT_A_DELETE`. The route is `POST /api/v1/knowledge/changes/{version}/restore`; on the command line it is `coffer knowledge restore --deleted <version>`. Recent changes MUST say a refused restore on the delete's row, and show **Restored** instead of Restore once a later change restored it.

#### Scenario: restore a deleted collection from Recent changes
- **GIVEN** a collection holding a document, a `README.md` and one item waiting in its inbox, which the user deletes
- **WHEN** Recent changes is read and the user restores the delete it lists
- **THEN** the collection is back under its name with its document, its README's description and its waiting item, as one new change by the user naming the delete it restored
- **AND** a second restore of the same delete is refused because a collection of that name exists, and writes nothing

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
A collection MUST carry no title: every surface — the web UI's tree, its pickers and its collection view, the CLI's listings, the command palette — MUST show a collection by its folder name, and the collection routes MUST carry no `title` field. A title sent for a collection through the kind-agnostic update MUST be refused as a validation error, with nothing changed, and migration `0133` MUST clear every collection's stored title. What a collection is about MUST be its description, the opening paragraph of its `README.md` (see "Read a collection's description from its README"), and the web UI's collection view MUST offer **Edit description**, which rewrites exactly that paragraph and leaves the rest of the README as it was, as one change naming the user, audited as an edit of the collection, and re-renders the guide skill. The route is `PUT /api/v1/knowledge/collections/{uid}/description`; on the command line it is `coffer knowledge edit <name> --description <text>`. An empty description MUST be refused. Creating a collection in the web UI MUST ask for its name and for what belongs in it, both required.

#### Scenario: a collection carries no title
- **GIVEN** a collection
- **WHEN** it is listed, and a title is then sent for it through the kind-agnostic update
- **THEN** the listing carries its name and no title, and the update is refused as a validation error with the title still empty

#### Scenario: edit a collection's description in place
- **GIVEN** a collection whose README opens with a heading, a paragraph and a section a person wrote under it
- **WHEN** the user edits its description
- **THEN** only the opening paragraph is rewritten, the collection lists the new description, and the edit is one change by the user, audited as an edit of the README
- **AND** an empty description is refused
