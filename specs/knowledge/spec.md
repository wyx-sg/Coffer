# Feature Specification: Knowledge Layer

**Status**: Accepted
**Folder name**: this spec lives at `specs/knowledge/`, the spec id every inbound link and `scripts/audit_acceptance.py` keys on. It keeps that name although the layer merged with what used to be a separate Knowledge Base: the name is an identifier other documents and the acceptance audit resolve, not a description. The layer's revision history lives in the roadmap's revision log.

**Input**: Coffer holds **knowledge about the user's working environment**: their repositories, services, projects, the people they work with, the decisions and traps worth surviving a session. It is a **directory of Markdown files**, and each collection is **one tree of documents** that the person and Coffer's internal model write together. New knowledge — an uploaded document parsed into Markdown, a fact an agent writes down — arrives as **material** in a hidden inbox, and Coffer's curation pass merges what is new in it into the documents. The documents are what an agent reads — with its own `Read`, at an absolute path, through no tool of Coffer's. See [Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md).

**Knowledge is not memory.** Knowledge is about the world — a platform's API contract, a service's ownership, a document someone published — and it arrives because a person, or an agent working with them, put it there. Memory is about the user and their projects, and it accrues on its own as agents work. They differ in every dimension that matters — who authors them, how they are partitioned, how they are delivered — so they are two layers: this one, filed by collection and **pulled** through a skill, and spec [memory](../memory/spec.md), partitioned by project and **pushed** at session start through a hook.

## The principle this layer answers to

**Knowledge is co-created.** A person and Coffer's model edit the same documents, and every decision below follows from that. Source files arrive in whatever format they were written in; on arrival they are parsed into Markdown, and what is new in them is **appended to the knowledge base** — merged into the documents that already cover the subject — rather than kept as a file of their own. From then on the documents are edited by whoever has something to add: a person in their editor, an agent with its own file tools, the curation pass carrying one change through to the rest. Metadata lives in the file rather than a database row because only the file is visible to all of them.

## The four invariants

1. **A collection is one tree of documents, and every writer shares it.** There is no lane that belongs to one writer. A person may edit, add or delete any document; curation may write or retire any document; neither owns a part of the tree the other may not touch. What protects a person's work is a rule the pass is held to — a person's edit is deliberate and is never reverted (FR-026) — not a directory.
2. **New knowledge arrives as material, and material is merged.** Every entrance Coffer serves submits into the collection's hidden `.inbox/`; a curation pass folds each item into the documents and deletes it. Material is not knowledge yet: nothing lists it, no catalogue names it, and nothing keeps it once it is merged. With no model to merge it, it becomes a document of its own on arrival (FR-029).
3. **A document MUST NOT reference another file by name.** Document paths are chosen by whoever files them and change as the corpus is reorganised; a name written into prose is a link that rots. Name the subject, not the file.
4. **Retrieval is the agent's own.** Coffer exposes no tool for reading, listing, grepping or searching knowledge. The catalogue and the path ride in Coffer's own delivered skill, `coffer-guide`; the agent reads the files with the tools it already has.

## What this layer is not

Everything below is a **standing constraint**, not a phase that has passed.

**No derived index of any kind.** No vectors, no sidecar, no FTS5, no chunking, no reindex. The documents are files and nothing stands between a query and them. This survives every redesign unchanged and is the one place the constitution's Persistence constraint binds this layer directly.

**No retrieval tool.** Coffer used to expose `list`, `grep`, `read` and `search`. It exposes none of them. An audit of 448 Claude Code sessions after the corpus was built found the delivered skill had never once been loaded and no knowledge tool had ever been called from that agent: the failure was never that literal matching missed, it was that nothing carried a hook the model could recognise. A tool an agent does not remember to call is not retrieval. What the agent already has — `Read`, `Grep` — needs no remembering, so the layer's job narrows to putting the right paths in front of it.

**No second retrieval surface on the web page.** A collection *is* a folder, so its page browses that one tree and nothing else.

**No structure that carries meaning.** The system assigns no meaning to any directory inside a collection. There is no `sources/` ÷ `topics/`, no `notes/` ÷ `docs/`, no `global` ÷ `project-<ULID>` axis, no cwd-derived scope, no auto-provisioning and no scope display labels. The nesting is whoever filed the document's — a person's or curation's, and either may move what the other filed. The one hidden directory, `.inbox/`, is not structure a reader sees; it is where material waits.

**No kept originals.** An uploaded document is the carrier of its knowledge, not the knowledge. It is parsed to Markdown, submitted as material and merged; neither the original bytes nor the extracted text survives as a file. There is no `source_mode`, no external-source table, no re-conversion on a schedule, no hidden `.raw/` and no visible original beside the text.

**Ingestion is an additional entrance, never a required one.** Writing or editing a Markdown document in the collection with any editor stays a complete way to add knowledge. Upload exists because the filesystem is only reachable while the user is at the machine, and their live entrance is a phone.

## User Scenarios & Testing

### User Story 1 — One knowledge store, every agent (Priority: P1)

The developer works with Claude Code in the morning and Codex in the afternoon. In the morning an agent records that a service's login state is owned by `account.session`. By the afternoon that fact is in a document, and the second agent reads it, because both read the same directory. No copy diverges, because there is only one.

**Independent Test**: write material through one MCP client; run a curation pass; confirm a document holding the fact, and read it back from a second client with a different agent identity.

### User Story 2 — Collections are the human's filing, and `enabled` is the switch (Priority: P1)

Some knowledge is a company's internal detail; some is about a side project. The developer creates a collection deliberately, files the material into it, and decides one thing about it: whether it is served at all. A collection they are not ready to hand to their agents is **disabled**, and no agent's delivered skill mentions it, its catalogue or any path inside it. Every enabled collection reaches every agent — the per-agent variant of this switch was withdrawn, because the skill it trimmed hands the agent the absolute knowledge root in the same breath (FR-010).

**Independent Test**: create two collections, disable one, and confirm each agent's delivered skill names the enabled one and names neither the disabled collection nor any path inside it.

### User Story 3 — Find the right file without an index and without a tool (Priority: P1)

An agent needs a fact it has no exact words for. The skill's description, already in its context, names the domains the corpus covers; the agent recognises one, loads the skill, and gets the whole catalogue — every document's path, title and description — plus the absolute root. It then reads the file with its own `Read`.

**Independent Test**: with a populated collection, confirm the delivered skill body carries every document's path/title/description and the absolute knowledge root, and that a path named in it resolves to a readable file.

### User Story 4 — The person edits the documents themselves (Priority: P2)

The developer opens a document from the Knowledge page in their editor and corrects a wrong line; drops a new Markdown document into the collection from Finder; deletes one that went stale. Each is live on the next read. Within the minute the sweep notices the edited document, and curation carries the correction into the other documents that said the same wrong thing — leaving the developer's own wording exactly as they wrote it.

**Independent Test**: edit a curated document out-of-band; confirm the next sweep runs a pass over it, that the person's wording survives the pass, and that the document is stamped as curated afterwards.

### User Story 5 — The agent knows what is in the corpus, not merely that it exists (Priority: P1)

A skill Coffer delivers names the domains the corpus covers in its description — the part that is always in the agent's context — and carries the full catalogue in its body, after Coffer's own manual. It is a registered skill like any other, so it arrives through exactly the machinery that already delivers the user's own skills, and every managed agent gets it without a hook and without anything being written into the agent's own memory.

**Independent Test**: with two collections and a managed agent bound, confirm the agent's `skills/coffer-guide` is the ordinary managed link into the master folder, that its description names the collections' subjects, and that its body lists each document.

### User Story 6 — Knowledge arrives through a conversation (Priority: P1)

The developer and an agent work something out together — why a build fails, who owns a service, what a flag actually does. The agent writes it down with `coffer__write`. It lands in the collection's inbox as material, and the next curation pass merges it into whichever document owns that subject, deduplicating against what is already there, and removes it from the inbox.

**Independent Test**: submit two pieces of material stating overlapping facts; run curation until the inbox is empty; confirm one document holds both facts and nothing is left in the inbox.

### User Story 7 — A document gets into the vault from wherever the user is (Priority: P1)

The developer is handed a PDF in a chat. They forward it to their Coffer channel and say which collection it belongs in. The PDF is parsed into Markdown and what it says is appended to that collection's knowledge — merged into the documents on the next pass — and neither the PDF nor its extracted text is kept as a file. At the desk they do the same by dropping the file on the Knowledge page.

**Independent Test**: upload a non-Markdown document through the REST surface and confirm one item waits in the inbox and no file of it appears in the tree, and that a following curation pass merges it into a document and empties the inbox.

### User Story 8 — A correction is a fact with a date on it (Priority: P2)

New material says a service counts daily actives with a plain Set; the document says HyperLogLog, because older material said so. Curation resolves it in favour of the newer statement and leaves the correction visible in the prose, so a reader learns both what is true and that it changed. Where the correction came from a person editing a document, the pass takes the person's edit as the truth and carries it outward rather than arguing with it.

**Independent Test**: curate material contradicting an existing document; confirm the new fact is what the document asserts and that the superseded one is still legible as a correction.

## Acceptance Scenarios

### Scenario: written material waits in the inbox, or becomes a document with no model

- **Given** a `shopee` collection created through `coffer knowledge create`,
  and an internal model connection configured
- **When** `coffer__write` is called against the daemon with the title
  `Session ownership`, a description and a body
- **Then** the answer's `status` is `pending` and it carries no path, the
  material waits in `shopee/.inbox/session-ownership.md` — named by the title's
  own slug, with no id in it anywhere — and one `knowledge_written` audit event
  is recorded
- **And** with no internal model configured, the same call answers `written`
  with the path `shopee/session-ownership.md`: the material became a document
  of its own on the spot, and the inbox is empty

### Scenario: frontmatter carries title, description and actor

- **Given** an empty `shopee` collection
- **When** a document is written into it with a title, a description and
  `actor` `user`
- **Then** the file's YAML frontmatter holds `title`, `description`, `actor`,
  `created_at` and `updated_at`, carries the title and the actor it was given,
  and the body follows the fence unchanged

### Scenario: a document edited out-of-band is curated by the next sweep

- **Given** a curated document in `shopee/`, whose file a person then edits
  in their own editor, by a file manager rather than by Coffer
- **When** the curation sweep runs, with no import or registration step in
  between
- **Then** a pass is run over that document as its item, the person's wording
  is still in it afterwards, and its frontmatter carries a
  `coffer_curated_at` no older than the edit — so the next sweep does not hand
  it back

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
  holding documents
- **When** the guide skill is re-rendered and seeded into its master folder
- **Then** the master `SKILL.md` names neither `shopee`, its catalogue, nor any
  path inside it
- **And** it names `personal` and lists its catalogue — `enabled` is the only
  thing that decides, and, because every agent reads the one master, it decides
  the same way for every agent

### Scenario: Coffer's own skill is an ordinary skill resource

- **Given** a daemon starting with a collection holding documents
- **When** the boot refresh runs
- **Then** there is one `coffer-guide` master folder under `~/.coffer/skills/`
  and one `skill:coffer-guide` resource row carrying the `builtin` source, and
  the skills listing shows it beside the user's imported skills
- **And** this layer has written nothing into any agent's own skill directory
  itself, and nothing into any agent's memory files

### Scenario: every agent reaches the guide through the one master folder

- **Given** two registered agents and the `coffer-guide` skill seeded
- **When** each agent's `<config_dir>/skills/coffer-guide` is inspected
- **Then** each is the ordinary Coffer-managed link into
  `~/.coffer/skills/coffer-guide/`, not a directory of real bytes
- **And** a re-render that changes the catalogue changes what both agents read
  in one write, while narrowing the skill's scope to one agent reclaims only
  the other agent's link and leaves the master untouched

### Scenario: the skill body carries the catalogue and the absolute root

- **Given** a collection holding three documents
- **When** the skill is rendered
- **Then** its body carries each document's collection-relative path, title and
  description, and the path of the knowledge root, and it instructs the agent
  to read those files with its own tools
- **And** the frontmatter `description` names the collection's subject, taken
  from the collection's own `README.md`, so a model matching on it has
  something to match

### Scenario: one skill carries both Coffer's manual and the catalogue

- **Given** a rendered `coffer-guide` `SKILL.md`
- **When** its frontmatter and its body are read
- **Then** the description names Coffer and its built-in tools as well as the
  enabled collections' subjects, and is within 1024 characters — a catalogue
  too large to fit drops whole collection subjects from the tail rather than
  ending mid-sentence
- **And** the body carries the manual first — the four built-in tools, the
  tiering contract, that Coffer never writes an agent's memory, and that no
  Coffer tool waits on an approval — and the catalogue after it, in one file

### Scenario: the rendered skill is byte-identical on two machines

- **Given** the same build and the same catalogue rendered twice, once with the
  knowledge root at each of two different home directories, and once again with
  the root explicitly relocated
- **When** the two default-placed renderings are compared byte for byte
- **Then** they are identical, and the knowledge root appears in its
  `~`-relative form rather than as either home's absolute path
- **And** the relocated root is written out in full, and the skill's stored
  config carries no timestamp of when it was generated

### Scenario: the handshake names Coffer's tools and points at the skill

- **Given** a real daemon driven over its `/mcp` endpoint by the MCP SDK
- **When** the client initializes, both with upstream tools hidden and with
  none hidden
- **Then** the `instructions` text is within its character cap, names
  `coffer__write`, `coffer__recall`, `coffer__diagnose` and
  `coffer__search_tools`, and points at the `coffer-guide` skill for the rest
- **And** it names no retrieval tool and carries no collection catalogue

### Scenario: an upload is converted and submitted as material, keeping neither file

- **Given** a collection with an internal model configured, and a document sent
  into it — `notes.md` through the ingest service, `team.csv` through
  `POST /api/v1/knowledge/upload`
- **When** the upload is accepted (201 from the route)
- **Then** the answer reports `pending` with no path, the converter that ran,
  the title and a description, and the collection holds exactly one new file:
  an inbox item carrying the extracted Markdown with frontmatter `actor: user`
- **And** neither the original bytes nor a copy of the extracted text exists
  anywhere in the collection's visible tree, and no hidden `.raw/` exists
  either — the upload was the carrier of its knowledge, not the knowledge

### Scenario: an upload of an unsupported type is refused with its reason

- **Given** a collection, and a file whose type no converter handles —
  `archive.bin` at the service, `payload.exe` at the route
- **When** it is uploaded
- **Then** the service raises `UnsupportedDocument` and the route answers 400
  `INGEST_REJECTED` whose details name `reason` `unsupported_type` and
  `doc_type` `exe`, and the collection is left with no new file at all —
  neither a document nor an inbox item

### Scenario: a document is never stored half-converted

- **Given** a document whose converter succeeds but yields no text, as an
  image-only PDF does
- **When** it is uploaded
- **Then** the upload is refused with the reason naming the document type, and
  nothing is written — no inbox item, no document, no original

### Scenario: a document forwarded to a channel lands in a collection

- **Given** a paired channel whose owner has just sent `note.txt` as an
  attachment, and one existing collection named `research`
- **When** the owner follows it with the plain text `/save research`
- **Then** the ingest service is called exactly once — that collection, that
  file name, those bytes, `actor` `user` and the channel's own default agent —
  and the channel replies with a confirmation naming both the file and the
  collection

### Scenario: curation merges material into the documents and empties the inbox

- **Given** a collection whose inbox holds two items and an internal
  connection configured
- **When** a curation pass runs over one of them and writes a document
- **Then** the document is in the collection's tree, stamped with
  `coffer_curated_at`, and the item the pass absorbed is gone from the inbox
  while the item it was not handed still waits
- **And** the pass's own write is not handed back by the next sweep as an edit

### Scenario: with no internal model, pending material becomes documents as it stands

- **Given** a collection whose inbox holds two items and no internal model
  connection at all
- **When** a curation pass is run over it
- **Then** it reports `no_model` and lists in `promoted` the two documents the
  items became, each at the collection root with its body as submitted and a
  `coffer_curated_at` stamp, and the inbox is empty — material never waits on
  a connection nobody configured

### Scenario: a pass is bounded to a handful of writes

- **Given** a collection holding twenty documents and one new item of
  material
- **When** a curation pass runs and its agent attempts eleven writes
- **Then** the pass stops at the eighth and reports the bound, and the writes
  that did land are complete files rather than truncated ones

### Scenario: a pass sees candidates and the catalogue, never the inbox

- **Given** a collection whose inbox holds the triggering item and another,
  and whose tree holds a matching document, an unrelated one and a `README.md`
- **When** the pass is assembled and its model tries to read the inbox item,
  the README and a file in another collection
- **Then** the model is given the triggering item, at most five candidate
  documents in full, and every document's title and description; each of the
  three reads is refused; `list_documents` lists the two documents and nothing
  else; and the other waiting item is nowhere in the brief

### Scenario: the pass is instructed that newer material wins and a person's edit stands

- **Given** the instructions a curation pass hands its model
- **When** they are read
- **Then** they state that where new material contradicts a document the newer
  statement wins, and that the superseded statement must stay legible with the
  date it changed
- **And** they state that a document a person edited is the truth — never to be
  reverted or reworded, only carried outward into the other documents — the
  rules live in the instructions because no code can adjudicate a
  contradiction, so the instructions are what this scenario pins

### Scenario: a curated document carries no file-name reference

- **Given** a pass whose model writes a document whose body names another
  document's file name
- **When** the write is applied
- **Then** it is refused and reported, because invariant 3 is enforced at the
  write rather than asked for in a prompt

### Scenario: an item is curated once, not on every sweep

- **Given** a document already carrying `coffer_curated_at` no earlier than its
  own modification time
- **When** the sweep looks for work
- **Then** the document is not owed a pass; and with the file touched
  afterwards, the next sweep does owe it one

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
- **And** a `coffer__write` call over that same session submits material into
  the collection

### Scenario: a path escaping the knowledge root is rejected

- **Given** the single path-construction module every surface resolves through
- **When** it is asked to resolve `../etc/passwd`, `shopee/../../outside`, or
  any path naming a hidden entry — `shopee/.inbox/material.md` included
- **Then** each one raises `UnsafeKnowledgePath` rather than returning a
  location outside the root

### Scenario: the viewer shows one tree of documents

- **Given** a collection page whose tree holds a document at the root and one
  inside a folder, with one item of material waiting in the inbox
- **When** the page renders and a document's row is clicked
- **Then** there is one tree — no lane headings and no tabs — listing both
  documents and not the inbox item, the pending material is shown as a count
- **And** the document offers open-in-editor, reveal and delete, and a delete
  names the exact path before it runs

### Scenario: migration queues both lanes for re-curation after a backup

- **Given** a two-lane vault — a collection with a topic document under
  `topics/`, Markdown sources under `sources/` including one nested, an
  uploaded PDF original, and a `README.md` at the collection root
- **When** the database is upgraded
- **Then** the whole knowledge root was first copied to `<root>.pre-0101.bak`,
  and every Markdown file of both lanes now waits in the collection's
  `.inbox/`, the topic document queued first and the sources after it in the
  order they were last modified
- **And** both lanes are gone, the PDF survives only in the backup, the
  `README.md` stays where it was, no document has been promoted by the
  migration itself, and a second upgrade changes nothing

### Scenario: migration removes the retired knowledge skill and spares a foreign folder

- **Given** two registered agents, one holding the old generated delivery at
  `<config_dir>/skills/coffer-knowledge` as a directory of real bytes and the
  other holding it as a symlink left by the delivery before it, and a third
  agent whose `skills/coffer-knowledge` is a folder a person put there, which
  carries neither of the two files the generated delivery always wrote
- **When** the database is upgraded
- **Then** the first two are gone from those agents' skill directories, so no
  agent is left holding a manual for a layer whose contract has moved
- **And** the third is untouched — it is somebody else's skill that happens to
  share the name, and the sweep only removes what it can positively recognise
  as Coffer's own: a symlink, or a directory holding both `SKILL.md` and
  `README.md`

## Requirements

### Storage

- **FR-001**: Knowledge MUST be stored as files under `~/.coffer/knowledge/<collection>/`, each collection **one tree of Markdown documents** that people and Coffer's curation pass write together. There MUST be no directory division inside a collection that says who may write where. The files are the only copy; the system MUST NOT keep a retrieval index of any kind — no vectors, no sidecar, no cache — so every answer is read off disk at call time.
- **FR-002**: A file's **path is its identity**. There MUST be no separate id field in frontmatter and no id-to-path mapping anywhere. File names MUST be human-readable slugs derived from the title; a collision appends a short suffix.
- **FR-003**: Every document and every inbox item MUST carry YAML frontmatter with `title`, `description`, `actor` (`agent` | `user`), `created_at` and `updated_at`. A document curation has had in front of it additionally carries `coffer_curated_at`, which Coffer writes and the sweep reads (FR-022, FR-028). Those six keys are what Coffer writes; any other key a person put in a document MUST be kept, in place and with its value unchanged, whenever Coffer rewrites or stamps the file — a document is the person's as much as Coffer's.
- **FR-004**: A collection MAY contain arbitrarily nested subdirectories, and the system MUST NOT assign them meaning or require them. The nesting is **chosen by whoever files a document** — a person, or curation — and either MAY create, move and remove directories.
- **FR-005**: Hidden entries (dot-prefixed) MUST be excluded from every listing, count of documents and catalogue. The system itself MUST write exactly one: a collection's `.inbox/`, where submitted material waits to be merged (FR-013). An inbox item MUST be deleted once a pass has merged it or it has been promoted (FR-028, FR-029), and MUST NOT be addressable through any surface. `.history/` and `.raw/` stay removed; nothing is kept of what a pass replaced or of the document an upload arrived in.
- **FR-006**: Every name that becomes a path segment MUST pass a traversal guard, and path construction MUST live in exactly one module. A path that names a document MUST lie inside a collection and MUST NOT be the collection itself or its `README.md`.
- **FR-007**: A collection's `README.md` MUST sit at the collection root and MUST NOT be curated, listed as a document, or counted.

### Collections

- **FR-008**: A **collection** is a top-level subdirectory of the knowledge root and is one `knowledge` Resource. It MUST be created deliberately — through the REST/CLI/UI surface — and MUST NOT be provisioned by a read, a write, or an agent's working directory. Creating one creates its directory and nothing inside it but an optional `README.md`.
- **FR-009**: The system MUST NOT derive any boundary from the agent's cwd. There MUST be no `global` scope, no `project-<ULID>` naming, no git-root resolution and no scope-to-project-root mapping table.
- **FR-010**: A collection MUST NOT carry the Resource framework's **per-agent reach**. Every **enabled** collection MUST be named, catalogued and served to **every** agent, and a **disabled** collection MUST appear in no agent's delivered skill — not its name, not its catalogue, not its description, not a path inside it. The per-agent form is withdrawn because it never chose anything and could not have: in the live vault every collection's scope was null, and its only effect would have been to omit a collection from one agent's rendered skill while that same skill hands the agent the absolute knowledge root and tells it to grep the whole thing. It was non-disclosure, and it disclosed anyway. `enabled` is now the only gate on this layer, and it is a real one. `coffer__write` MUST refuse a write naming a collection that does not exist or is disabled, and MUST answer with the collections that **are** available.
- **FR-011**: A collection's one-line description MUST be the first paragraph of its `README.md`, absent when there is none, and MUST be read off disk on every listing. It MUST NOT be stored in the database — not even in the `resources` row's own generic `description` column, which for this kind stays empty: a copy written once and read by nothing is wrong from the first time the person edits the file. It is also what the delivered skill's own description draws on (FR-036), so a collection that fails to describe itself is a collection an agent never recognises.
- **FR-012**: What this layer serves is **files on disk**, and the system MUST describe it as such wherever it is presented: a delivered path is the whole of the access story, because an agent handed the knowledge root reads anything under it with the shell tools it already has. `enabled` is therefore a **delivery** gate, and MUST NOT be presented as a filesystem boundary either — a disabled collection is one no skill names, not one no process can open.

### New knowledge arriving

- **FR-013**: Every entrance Coffer serves — `coffer__write`, the CLI's `write` and its route `POST /api/v1/knowledge/material`, an upload, and a channel's `/save` — MUST **submit material** into the named collection's `.inbox/` rather than write a document. What becomes of material is curation's to decide (FR-021): which document it belongs in, what in it is new, and what it corrects. The one exception is FR-029, where no model is configured to decide and the material becomes a document as it stands.
- **FR-014**: `coffer__write` MUST submit material to a named collection from `title`, `description` and body text. It MUST take no path, no folder and no lane, and MUST NOT replace anything: two submissions of the same title are two pieces of material. A submission MUST be a plain file write — no LLM, no conversion, no indexing step — and MUST record one `mcp_invocations` row and one audit event naming the calling agent, taken from the session's handshake identity (spec [mcp-gateway](../mcp-gateway/spec.md) FR-013) written in as an `agent` argument no tool advertises and no caller can set. Its answer MUST say what became of the material: `pending`, with no path — an inbox address vanishes once the material is merged, so reporting one would be reporting an address that is about to stop existing — or `written`, with the document's path, when it was promoted (FR-029). A submission naming a collection that does not exist or is disabled MUST be refused with the collections that **are** available: that names exactly what this agent's own delivered skill already lists, and it turns a dead end into a correction for a model that reached for the tool without opening the skill.
- **FR-015**: Writing, editing or deleting a document directly in the collection's tree — by a person in their own editor, or by an agent with its own file tools — MUST remain a complete way to change knowledge: no import, no registration, no conversion step, and the change is live on the very next read. The sweep MUST notice an edited or new document by its modification time (FR-022) and carry it into the rest of the collection. Ingestion below is an additional entrance, never a required one.
- **FR-016**: The system MUST accept a document upload into a named collection, convert it to Markdown, and **submit the Markdown as material** (FR-013), so what is new in the document is appended to the collection's knowledge rather than filed beside it. Supported inputs MUST be exactly what `markitdown` handles plus plain text and CSV; an unsupported type MUST be refused with the type named, never stored half-converted. Neither the **original** bytes nor the extracted Markdown MUST be kept as a file of its own: the upload is the carrier of its knowledge, and once the knowledge is merged the carrier has nothing left to say. An upload takes no folder — where its knowledge lands is curation's to decide.
- **FR-017**: The submitted Markdown MUST carry FR-003's frontmatter — `title` from the document (falling back to its file name) and `description` filled in, by the internal connection when one is configured and from the document's opening prose when not.
- **FR-018**: A document sent to a Coffer channel MUST be ingestible into a collection through the same path, so the phone and the Knowledge page are two ends of one entrance (spec [channels](../channels/spec.md)). The channel MUST confirm the collection with the owner before storing, and MUST NOT store anything from a non-owner.
- **FR-019**: Upload MUST be bounded: one file per call, a size ceiling, and a refusal that names the limit. A conversion failure MUST leave nothing behind — no inbox item, no document.
- **FR-020**: Deleting a document MUST be a person's action, offered on the REST, CLI and web surfaces, and it MUST be allowed for **any** document, whoever wrote it: the tree is the person's as much as curation's. No agent-facing tool may delete anything. Inside a pass, `retire_document` is curation's own way to remove a document whose content it has written elsewhere (FR-024), and it is bounded like a write (FR-025).

### Curation

- **FR-021**: Curation is how material becomes knowledge and how an edit to one document reaches the rest. It is a bounded agentic pass driven by the internal model connection, whose tool surface is exactly `list_documents`, `read_document`, `write_document` and `retire_document`, fenced to **one collection's documents**: no tool may reach the inbox, the collection's `README.md`, or another collection. A pass takes **one item** — one piece of material, or one edited document — and the context and writes of FR-023 and FR-025.
- **FR-022**: Passes MUST be run by a **sweep on an interval** and by a manual trigger. Each sweep MUST read the interval afresh rather than capture it at boot, and MUST find a collection's pending items in this order: first every inbox item, oldest first — until it is merged it is knowledge no agent can read — then every document whose modification time is newer than its own `coffer_curated_at` stamp (or which has none), meaning a person or an agent edited or added it out of band. A sweep MUST run at most a bounded number of passes per collection, so a freshly migrated vault drains visibly rather than in one long batch. The manual trigger takes the oldest pending item, or the one document it is given.
- **FR-023**: A pass MUST be assembled from a **bounded** context: the item in full, at most **five** candidate documents in full, and the collection's full catalogue of titles and descriptions. Candidates MUST be selected by literal matching of distinctive strings drawn from the item against the collection's documents — never the inbox; the catalogue is present so the model can conclude that none of the candidates is the right home and open a new document instead.
- **FR-024**: A pass MUST preserve every fact it is shown. Merging MUST integrate rather than regenerate, and `retire_document` MUST be permitted only for a document whose content the same pass has written elsewhere.
- **FR-025**: A pass MUST be bounded to at most **eight** writes — a retire counts as one — and to a recursion limit, and MUST report reaching either. A single item MUST NOT be able to trigger a corpus-wide rewrite.
- **FR-026**: Where new material contradicts a document, the **newer statement wins**, and the resulting document MUST keep the superseded statement legible as a correction with the date it changed — a contradiction is knowledge about the world changing, and when it changed is itself worth keeping. Where the item is a **document a person edited**, what they wrote there is the truth: the pass MUST NOT revert or reword it, and carries it outward instead — correcting other documents that say otherwise, and moving a section that belongs elsewhere — leaving the edited document alone unless it now duplicates another. Both rules are instructions to the model, because no code can adjudicate a contradiction.
- **FR-027**: A document MUST NOT contain a reference to another knowledge file by file name or path. This MUST be enforced at `write_document` — a write that carries one is refused and reported — rather than requested in a prompt.
- **FR-028**: An item MUST be settled only after its pass completes: merged material is deleted from the inbox, and an edited document is stamped with `coffer_curated_at` and nothing else about it changes. Every document curation itself writes MUST be stamped as it is written, so the sweep does not hand the pass its own output back as an edit. A stamp MUST set the file's modification time to the stamp, so the stamping itself does not count as an edit. A pass that does not complete MUST leave the item as it was, so it is curated later rather than lost.
- **FR-029**: With no internal model connection configured, material MUST NOT wait: a submission MUST be **promoted** on the spot into a document at the collection root, as it stands and stamped as curated, and a pass MUST promote every item already in the inbox the same way and report `no_model` with the documents it promoted. Nothing is merged — merging is the model's job — but nothing sits in a hidden directory waiting for a connection nobody configured, where no agent can read it. An edited document needs nothing without a model: it is readable as it stands.
- **FR-030**: Only **one pass per collection** may run at a time, whoever started it. A manual trigger arriving while a pass is in flight MUST be refused (`UPKEEP_ALREADY_RUNNING`, 409) rather than queued, and the sweep MUST skip a collection already being curated. Which collections are being curated right now MUST be readable. The record is per-daemon and does not outlive it.
- **FR-031**: A pass and a vault-sync converge round MUST NOT overlap — both write the vault — so they MUST take the same lock, and a pass MUST be skipped while a conflict or pending confirmation is outstanding (spec [vault-sync](../vault-sync/spec.md)).
- **FR-032**: Because a pass rewrites synced content unattended, it MUST run on one machine only: the `internal_engine_config` pair `auto_curate_enabled` and `curate_owner_machine_id` MUST both be read on every sweep, so the switch reads as *on, here* rather than merely *on*. Both halves of that reading MUST also be **reportable and changeable** by the user, on the same terms as a channel's machine binding — an owner naming a machine the registry no longer holds is a fault rather than silence, and can be taken over (spec [vault-sync](../vault-sync/spec.md) FR-098). `auto_curate_enabled` defaults **on**, because curation is how submitted material becomes part of the documents an agent reads.

### Tools and delivery

- **FR-033**: Coffer's MCP gateway MUST expose exactly **one** built-in knowledge tool: `coffer__write`. There MUST be no `list`, `grep`, `read`, `search` or `delete`. An agent reads knowledge with its own file tools at the paths the skill gives it.
- **FR-034**: The catalogue MUST be carried by Coffer's own skill, `coffer-guide`, which MUST be an ordinary registered `skill` Resource — one master folder under `~/.coffer/skills/`, one row, delivered by the predicate and the links every imported skill uses (spec [skill-manager](../skill-manager/spec.md) FR-028, FR-012, FR-008). This layer contributes the **text** and nothing else: it renders, and the skill kind writes, registers and delivers. **This reverses what this requirement used to say.** The generated skill was deliberately kept outside the resource framework — written per agent into `<config_dir>/skills/` by this layer, as a file the skill kind knew nothing about — on the grounds that a skill Resource is a bundle a person imports and curates, and no person can keep a bundle level with a catalogue that moves whenever curation runs. That reason has expired: a skill's master folder is now regenerated from the running build at every boot and whenever the catalogue changes (spec skill-manager FR-028), so "generated" and "registered as a Resource" stopped being alternatives. What the old rule bought was a folder nobody had to maintain; what it cost was a second delivery mechanism with its own writer and its own per-agent copies, invisible on the Skills surface, unreachable by `enabled` or scope, and outside every piece of machinery the skill kind already had — drift verification, repair, reclaim and the audit trail. The per-agent copies of the retired `coffer-knowledge` delivery MUST be removed rather than left in an agent's skill directory describing a layer whose contract has moved. This layer MUST NOT push anything into a session of its own accord and MUST NOT write into any agent's own memory files: knowledge is pulled. Session-start delivery belongs to spec [memory](../memory/spec.md), which carries its own budget and its own consent.
- **FR-035**: The skill MUST reach each agent as the **ordinary shared-master link** of spec skill-manager FR-008 — one master folder, one link per agent — and MUST NOT be written into an agent's directory as real bytes. **This too reverses what this requirement used to say.** The rule was that each agent's copy be independent bytes, because a link into a shared master was "a copy this layer cannot re-render, stale or reclaim". Neither half of that is true any more: the master is re-rendered in place at every boot and whenever the catalogue changes, which re-renders every agent's view of it at once; and reclaiming is the skill kind's own per-agent reconciliation against the delivery predicate (spec skill-manager FR-019), which removes one agent's link without touching another's or the master. The text is the same for every agent (FR-010), so per-agent bytes were buying independence nothing asked for while paying for it with a delivery path of this layer's own. Re-rendering MUST happen whenever the catalogue changes — after a curation pass or a promotion, or a collection's creation, deletion, enabling or disabling, and on every sweep tick so a document a person added by hand is catalogued too — and MUST never raise: a failed render leaves the previous master exactly where it was, and the corpus stays readable at paths a person can still give an agent.
- **FR-036**: The skill's **frontmatter description** MUST describe Coffer itself — naming its built-in tools so a model recognises them — **and** name the subjects the enabled collections cover, drawn from their READMEs. It is the only part of this layer that is always in a model's context, so it MUST carry matchable specifics rather than a description of the layer, and it MUST fit the tightest frontmatter ceiling any importer imposes (1024 characters), dropping whole collection subjects from the tail rather than cutting a sentence mid-way.
- **FR-037**: The skill's **body** MUST be one merged manual: Coffer's own — its four built-in tools and when to reach for each, the tiering contract that makes an unlisted upstream tool still callable, the fact that Coffer reads an agent's memory and never writes it, that no Coffer tool waits on a human approval, and what does not belong in knowledge — **followed by** the catalogue: the path of the knowledge root, and, for each enabled collection, every document's collection-relative path, title and description. It MUST instruct the agent to read those files with its own tools, to reach for `coffer__write` when it learns something durable, and that it may also correct or extend a document it has read by editing the file itself, which the next sweep carries into the rest of the collection (FR-015). One skill, not a set: a frontmatter description is resident in every session whether the skill is opened or not, while a body is paid for only when a model reaches for it, so a second skill would spend the resident budget again to describe something most sessions never open.
- **FR-038**: The MCP gateway's own `initialize` instructions MUST stay within their character cap and MUST carry only what a skill cannot: what Coffer is, the names of its four built-in tools (`coffer__write`, `coffer__recall`, `coffer__diagnose`, `coffer__search_tools`) so they are recognisable in a tool list, the tiering sentence when tools are actually hidden this session, and a pointer to the `coffer-guide` skill for everything else. It MUST NOT restate the manual, MUST NOT name a retrieval tool, and MUST NOT carry the catalogue — the catalogue is in the skill body, which costs a session nothing until a model opens it.
- **FR-047**: The rendered `SKILL.md` MUST be a **pure function of the running build and the catalogue it is given**: the same build over the same enabled collections MUST produce the same bytes, run after run and machine after machine. Nothing machine-specific may enter it — not an absolute home directory, not a timestamp, not a build path — and the skill's own config MUST likewise carry no timestamp of its generation. **The reason is no longer convergence, and that changes what the requirement is worth saying.** It used to read "byte-identical on every machine running the same build against the same catalogue", with the hedge doing the real work, because the artifact converged: a purely local difference would have had two vaults overwriting each other's copy forever. It no longer converges at all (spec [vault-sync](../vault-sync/spec.md) FR-093) — every machine renders its own from files that converge plus its own reach, and two machines are *expected* to differ whenever their enabled sets differ, which is exactly what the hedge was excusing. What determinism buys now is local and still worth paying for: an unchanged vault re-rendering to the same bytes is what lets the seed skip the write, so a boot or a curation tick that changed nothing registers nothing, audits nothing and re-delivers nothing (spec [skill-manager](../skill-manager/spec.md) FR-028) — and it is what makes the `version_hash` in the row mean "the content moved" rather than "time passed". The knowledge root MUST still be written in its `~`-relative form whenever it sits in its default place, so a path an agent reads is one a person can retype; an explicitly relocated root (`COFFER_KNOWLEDGE_ROOT`) MUST be written out in full, because an accurate path is worth more than a tidy one.

### Surfaces

- **FR-039**: The REST API under `/api/v1/knowledge` and the `coffer knowledge` CLI group MUST cover: create a collection, list one level of a collection at a path, read a document, submit material (`POST /material`; `coffer knowledge write`), upload a document, delete a document, and trigger curation. There MUST be no route that writes a document: a person edits one in their own editor, reached from the page's open-in-editor action, and the edit is live on the next read (FR-015). Collection deletion goes through the Resource framework (`DELETE /api/v1/resources/{uid}`). There MUST be no index, reindex, check-sources, update-source or embedding-configuration endpoint, no settings endpoint for the cwd-derived scope axis FR-009 forbids, and no per-agent reach endpoint for this kind (FR-010) — a collection's one switch is `enabled`, which the framework already serves. These surfaces serve the human and the UI; they are not an agent's retrieval path.
- **FR-040**: The web UI MUST present a collection as **one tree** of its documents — no lanes, no tabs — with the chosen document rendered read-only in the pane beside it, through the unified file preview with open-in-external-editor and reveal-in-file-manager. Every document MUST offer delete, naming the exact path before it runs, reporting a refusal in place, and leaving the preview on no file afterwards. The page MUST show how much material is waiting to be merged, offer upload into the collection in view, and offer a manual curation trigger that reports a pass already in flight. It MUST NOT list the inbox's items, and MUST NOT carry a retrieval box: the one input beside the tree narrows the names already on screen, client-side.
- **FR-041**: Read responses MUST carry the file's absolute path and its containing folder's absolute path.

### Migration

- **FR-042**: One migration (revision `0101`) MUST rewrite the two-lane corpus into one tree: every Markdown file of a collection's `topics/` and then of its `sources/` moves into that collection's `.inbox/` as material — the topic documents queued first, because they are already organised by subject and the first passes lay down that structure, and the sources after them in the order they were last modified — under a flat name that says which lane it came from; every non-Markdown file (an uploaded original) is dropped; and both lanes are removed. `README.md` stays at the collection root. The migration MUST NOT promote or merge anything itself: the ordinary sweep distils the whole corpus again, one pass per item. It MUST be idempotent — a collection with neither lane is walked past — and one-way, with **no compatibility shim left behind**. The earlier revisions it rewrites on top of also retired the previous delivery: the shared `coffer-knowledge` skill Resource, its master folder and every link to it (0085), and the per-agent copies that delivery then wrote (0089, FR-034).
- **FR-043**: The migration MUST back the whole knowledge root up before it moves a single file, to a sibling directory named `<root>.pre-0101.bak`, and MUST report where. A second run MUST reuse that backup rather than photograph a tree it has already rewritten. The corpus is the user's own writing, this migration empties the tree an agent reads until the sweep refills it, and the dropped originals survive nowhere else.
- **FR-044**: `auto_curate_enabled` MUST be on and `curate_owner_machine_id` MUST name a machine for a migrated vault, so it curates itself rather than staying dark until the setting is found. Revision 0085 seeded both — on, owned by the machine that migrated — and revision 0101 changes nothing in the database.

### Constraints

- **FR-045**: This layer MUST carry **no vector-store or embedding-model dependency**: `sqlite-vec`, `fastembed`, mem0, chroma and LlamaIndex MUST NOT appear in the dependency set, and no vector may be computed, fetched or stored anywhere. `markitdown` is this layer's converter as well as the channel's; the importlinter contract MUST admit exactly those two consumers and no others.
- **FR-046**: The knowledge layer MUST NOT add any table to `coffer.db`, and MUST NOT create a directory of its own outside the knowledge root. A collection is a row in the kind-agnostic `resources` table like every other Resource; everything else this layer holds is a file the human can open.

## Success Criteria

- **SC-001**: A fact written by one agent is readable by a different agent in a curated document, with no index step in between.
- **SC-002**: A document the human edits outside Coffer is carried into the rest of the collection by the next sweep, with no import or reconciliation, and their own wording survives the pass.
- **SC-003**: A disabled collection's name, catalogue and paths appear in no agent's delivered skill, and every enabled collection's appear in all of them.
- **SC-004**: The layer holds no knowledge-specific table in `coffer.db` and keeps no derived copy of a document's content anywhere; the only other thing under a collection is material waiting in `.inbox/`, which is gone once merged.
- **SC-005**: Once the inbox is drained, every fact submitted as material is present in a document, and nothing of the material itself remains.
- **SC-006**: The gateway advertises exactly one knowledge tool, and an agent reaches every document without calling it.
- **SC-007**: A document sent from a channel is knowledge in the intended collection afterwards — merged into its documents, or a document of its own with no model — and neither the original nor its extracted text is kept as a file.
- **SC-008**: Coffer's own skill is indistinguishable from an imported one everywhere the skill kind touches it — it is listed, scoped, enabled, delivered, verified for drift and repaired by the same code — and the only thing that sets it apart is that its master folder is Coffer's to rewrite and its deletion is refused.
- **SC-009**: Two machines running the same build over the same catalogue render the same bytes, so a converge round between them carries no change to this skill at all.

## Assumptions

- The corpus stays in the hundreds of files. A catalogue of every document fits a skill body at that size — measured at ~5.2K tokens for 58 documents — so the agent never has to guess what exists. Tens of thousands of files would be a different design and the place embeddings would be reconsidered.
- Curation rewrites documents with no review step, including documents a person wrote. What stands between a person's work and a bad pass is the rule that a person's edit is never reverted (FR-026), the eight-write bound, one pass per collection, the audit event every pass records, and — where vault sync is configured — the vault's git history, which is the way back to an earlier version of a document. Nothing in this layer keeps a copy of what a pass replaced.
- The internal connection is the one place user content may leave the machine, exactly as spec [channels](../channels/spec.md) FR-019 already establishes for voice. Curation and an ingested document's generated description are the only things this layer sends there.
- One item is small enough to be handed to a model whole. A person writing a note, a document a person uploads, or one document a person edited is bounded by what a person produces; a pass that meets one too large for its context reports rather than truncates.
