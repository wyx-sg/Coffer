# Knowledge Layer

## Purpose

Coffer holds **knowledge about the user's working environment**: their repositories, services, projects, the people they work with, the decisions and traps worth surviving a session. It is a **directory of Markdown files**, and each collection is **one tree of documents** that the person and their agents write together. Coffer runs no model over it. New knowledge — an uploaded document parsed into Markdown, a Markdown file an agent writes — becomes a **document at once**: an upload is promoted as it stands, and an agent writes straight into a collection's documents by the writing rules in `coffer-guide`. The documents are what an agent reads — with its own `Read`, at an absolute path, through no tool of Coffer's. Every agent reads the same directory, so what one agent records in the morning a different agent reads in the afternoon, and no copy diverges because there is only one. See [Knowledge Is Plain Files](../../../docs/decisions/knowledge-is-plain-files.md). The spec id `knowledge` is kept although the layer merged with what used to be a separate Knowledge Base: it is the identifier inbound links and the acceptance audit resolve, not a description.

**Knowledge is not memory.** Knowledge is about the world — a platform's API contract, a service's ownership, a document someone published — and it arrives because a person, or an agent working with them, put it there. Memory is about the user and their projects, and it accrues on its own as agents work. They differ in who authors them, how they are partitioned and how they are delivered, so they are two layers: this one, filed by collection and **pulled** through a skill, and [memory](../memory/spec.md), partitioned by project and **pushed** at session start.

**Knowledge is written and tidied by the person and their agents.** Source files arrive in whatever format they were written in; on arrival they are parsed into Markdown and promoted to a document of their own. From then on the documents are edited by whoever has something to add: a person in their editor, an agent with its own file tools. Tidying — merging documents on one subject, splitting one that grew, correcting a stale statement and keeping it legible as a dated correction — is judgement, so it is the agent's: a **Tidy** button on a collection, and **Tidy all** on the Knowledge page, open a conversation on the default managed agent seeded with the backend's tidy prompt, and the agent follows the `coffer-guide` section "Tidying a collection". Nothing tidies unattended: Coffer starts no agent run of its own. Metadata lives in the file rather than a database row because only the file is visible to all of them. The layer answers to four invariants:

1. **A collection is one tree of documents, and every writer shares it.** There is no lane that belongs to one writer; no statement is protected because of who wrote it — the newer or better-evidenced one wins and the superseded one stays legible — and no directory carries that meaning.
2. **New knowledge is promoted to a document at once.** Every entrance turns its input into a document as it stands. A file an agent drops into the hidden `.inbox/` is a drop zone for writers outside Coffer: the next sweep adopts it and promotes it. Nothing waits longer than one sweep.
3. **A document MUST NOT reference another file by name.** Document paths change as the corpus is reorganised; a name written into prose is a link that rots. Name the subject, not the file.
4. **Retrieval is the agent's own.** Coffer exposes no tool for reading, listing, grepping or searching knowledge. The catalogue and the path ride in Coffer's own delivered skill, `coffer-guide`; the agent reads the files with the tools it already has.

These are **standing constraints**, not a phase that has passed: no derived index of any kind, no retrieval tool (an audit of 448 Claude Code sessions found the old tools were never called — a tool an agent does not remember to call is not retrieval), no second retrieval surface on the web page, no directory that carries meaning, and no kept originals. Ingestion is an additional entrance, never a required one: writing a Markdown document with any editor stays a complete way to add knowledge, and upload exists because the user's live entrance is often a phone.

The **knowledge sweep** keeps three mechanical duties: it re-renders the guide, adopts and promotes files dropped into `.inbox/`, and commits edits found on disk. It calls no model and has no switch or interval of its own.

Assumptions: the corpus stays in the hundreds of files, so a catalogue of every document fits a skill body (measured at ~5.2K tokens for 58 documents); tens of thousands of files would be a different design and the place embeddings would be reconsidered. Agents tidy with no review step; what stands between a document and a bad tidy is the collection's git history, where every change is recorded and can be undone through History and Restore. An ingested document's description is filled from its opening prose, so no user content leaves the machine for this layer.

While the `knowledge` feature is switched off (spec [experimental-features](../experimental-features/spec.md) "Close the knowledge feature's surfaces"), the knowledge routes are closed, the knowledge sections of `coffer-guide` are absent, and the knowledge sweep skips its rounds; collections stay on disk untouched. Requirements below describe the feature while it is on.

## Requirements

### Requirement: Store each collection as one tree of Markdown files
Knowledge MUST be stored as files under `~/.coffer/vault/knowledge/<collection>/` — the knowledge root is the vault's `knowledge/` folder ([vault-storage](../vault-storage/spec.md) "Store state in five classes by nature") — each collection **one tree of Markdown documents** that people and agents write together. There MUST be no directory division inside a collection that says who may write where. The files are the only copy; the system MUST NOT keep a retrieval index of any kind — no vectors, no sidecar, no FTS5, no chunking, no reindex, no cache — so every answer is read off disk at call time.

#### Scenario: keep no index beside the documents
- **GIVEN** a `shopee` collection holding one document written through Coffer
- **WHEN** the knowledge root is walked, and the document's file is then rewritten on disk by hand
- **THEN** the only files under the collection are the document itself and nothing Coffer derived from it — no index, sidecar or cache file
- **AND** the next read through the service returns the hand-written text, with no reindex step in between

### Requirement: Use the file path as a document's identity
A file's **path is its identity**. There MUST be no separate id field in frontmatter and no id-to-path mapping anywhere. File names MUST be human-readable slugs derived from the title; a collision appends a short suffix.

#### Scenario: name a file by its title and suffix a collision
- **GIVEN** an empty `shopee` collection
- **WHEN** two pieces of material titled `Session Ownership` are submitted
- **THEN** the two documents are `shopee/session-ownership.md` and `shopee/session-ownership-2.md`
- **AND** neither file's frontmatter carries an `id` key

### Requirement: Carry title, description and actor in frontmatter
Every document MUST carry YAML frontmatter with `title`, `description`, `actor` (`agent` | `user`), `created_at` and `updated_at`. Those five keys are what Coffer writes; any other key a person put in a document MUST be kept, in place and with its value unchanged, whenever Coffer rewrites the file — a document is the person's as much as Coffer's.

#### Scenario: frontmatter carries title, description and actor
- **GIVEN** an empty `shopee` collection
- **WHEN** a document is written into it with a title, a description and `actor` `user`
- **THEN** the file's YAML frontmatter holds `title`, `description`, `actor`, `created_at` and `updated_at`, carries the title and the actor it was given, and the body follows the fence unchanged

### Requirement: Allow nesting without giving it meaning
A collection MAY contain arbitrarily nested subdirectories, and the system MUST NOT assign them meaning or require them. There is no `sources/` ÷ `topics/` and no `notes/` ÷ `docs/` division. The nesting is **chosen by whoever files a document** — a person or an agent — and either MAY create, move and remove directories.

#### Scenario: list and catalogue a nested document at its own path
- **GIVEN** a `shopee` collection holding a document a person filed at `shopee/a/b/deep.md`
- **WHEN** the level `shopee/a/b` is listed and the collection's catalogue is read
- **THEN** the listing names `shopee/a/b/deep.md` as a document
- **AND** the catalogue carries it at that nested path, with no folder required or renamed

### Requirement: Hide every dot-prefixed entry
Hidden entries (dot-prefixed) MUST be excluded from every count of documents and from the catalogue, and no surface MUST list or read one: the tree route lists none, the read route refuses every hidden path, and a collection reports no count of what hides in it. A collection's `.inbox/` is an ordinary hidden entry whose files the sweep adopts and promotes (see "Adopt a file dropped into the inbox"). `.history/` and `.raw/` do not exist: what a person or an agent replaced is kept in the collection's git history (see "Commit every knowledge write naming its writer"), not in the collection, and nothing is kept of the document an upload arrived in.

#### Scenario: leave hidden entries out of every listing
- **GIVEN** a `shopee` collection holding one document, a file in `.inbox/`, and a file a person put under `.scratch/`
- **WHEN** the collection is listed, its document count read, its catalogue rendered and its tree requested
- **THEN** the count is one and the catalogue names the one document only
- **AND** the tree lists the document and nothing from `.inbox/` or `.scratch/`, and the read route refuses a path under either

### Requirement: Guard every path through one module
Every name that becomes a path segment MUST pass a traversal guard, and path construction MUST live in exactly one module. A path that names a document MUST lie inside a collection and MUST NOT be the collection itself or its `README.md`.

#### Scenario: a path escaping the knowledge root is rejected
- **GIVEN** the single path-construction module every surface resolves through
- **WHEN** it is asked to resolve `../etc/passwd`, `shopee/../../outside`, or any path naming a hidden entry — `shopee/.inbox/material.md` included
- **THEN** each one raises `UnsafeKnowledgePath` rather than returning a location outside the root

### Requirement: Keep the collection README out of the corpus
A collection's `README.md` MUST sit at the collection root and MUST NOT be listed as a document or counted.

#### Scenario: keep the README out of listings, counts and curation
- **GIVEN** a `shopee` collection whose root holds a `README.md` edited after it was created and one document
- **WHEN** the collection is listed, counted and swept
- **THEN** the listing names only the document, the count is one, and the README is never promoted or catalogued as a document

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

### Requirement: Fill frontmatter on converted material
The submitted Markdown MUST carry the frontmatter of "Carry title, description and actor in frontmatter" — `title` from the document (falling back to its file name) and `description` drawn from the document's opening prose.

#### Scenario: title an upload from its file name when it has no heading
- **GIVEN** a collection and a plain-text file `release-notes.txt` whose text has no heading and opens with a sentence of prose
- **WHEN** it is uploaded
- **THEN** the resulting file's frontmatter `title` is derived from the name `release-notes`
- **AND** its `description` is drawn from the text's opening prose rather than left empty

### Requirement: Bound uploads and leave nothing behind on failure
Upload MUST be bounded: one file per call, a size ceiling, and a refusal that names the limit. A conversion failure MUST leave nothing behind — no document and no file in the collection's `.inbox/`.

#### Scenario: a document is never stored half-converted
- **GIVEN** a document whose converter succeeds but yields no text, as an image-only PDF does
- **WHEN** it is uploaded
- **THEN** the upload is refused with the reason naming the document type, and nothing is written — no document, no original

### Requirement: Let only a person delete a document
Deleting a document through Coffer MUST be a person's action, and it MUST be allowed for **any** document, whoever wrote it: the tree is the person's as much as an agent's. The REST route and the web UI MUST offer it, and each deletion through them MUST record a `knowledge_deleted` audit event. A person may equally delete the file itself in the collection's directory under the knowledge root, and the deletion is live on the next read and the next catalogue (see "Treat a direct file edit as a complete change"). Coffer offers no tool that deletes anything.

#### Scenario: delete a document an agent wrote
- **GIVEN** two documents in `shopee/` whose frontmatter `actor` is `agent`
- **WHEN** a person deletes one through `DELETE` on the knowledge route, and removes the other's file from the `shopee` directory under the knowledge root
- **THEN** both files are gone from the tree, and neither is listed or catalogued afterwards
- **AND** a `knowledge_deleted` audit event is recorded for the one deleted through the route

### Requirement: Deliver the catalogue through the coffer-guide skill
The catalogue MUST be carried by Coffer's own skill, `coffer-guide`, which MUST be an ordinary registered `skill` Resource — one master folder, `~/.coffer/derived/skills/coffer-guide/`, one resource, delivered by the predicate and the links every imported skill uses ([skill-manager](../skill-manager/spec.md) "Regenerate Coffer's builtin skill from the build", [skill-manager](../skill-manager/spec.md) "Deliver a skill only where it is enabled and in scope", [skill-manager](../skill-manager/spec.md) "Deliver a skill as a directory link"). This layer contributes the **text** and nothing else: it renders, and the skill kind writes, registers and delivers.

This layer MUST NOT push anything into a session of its own accord and MUST NOT write into any agent's own memory files: knowledge is pulled. Writing into an agent's native memory belongs to [memory](../memory/spec.md), and nothing in Coffer puts memory into a session ([memory](../memory/spec.md) "Deliver no memory into a session"). Coffer's own skill is indistinguishable from an imported one everywhere the skill kind touches it — listed, scoped, enabled, delivered, verified for drift and repaired by the same code — and the only thing that sets it apart is that its master folder is Coffer's to rewrite and its deletion is refused.

#### Scenario: Coffer's own skill is an ordinary skill resource
- **GIVEN** a daemon starting with a collection holding documents
- **WHEN** the boot refresh runs
- **THEN** there is one `coffer-guide` master folder under `~/.coffer/derived/skills/` and one `skill:coffer-guide` resource carrying the `builtin` source, and the skills listing shows it beside the user's imported skills
- **AND** this layer has written nothing into any agent's own skill directory itself, and nothing into any agent's memory files

### Requirement: Deliver the guide as the shared-master link
The skill MUST reach each agent as the **ordinary shared-master link** of [skill-manager](../skill-manager/spec.md) "Deliver a skill as a directory link" — one master folder, one link per agent — and MUST NOT be written into an agent's directory as real bytes. The master is re-rendered in place, which re-renders every agent's view of it at once; reclaiming is the skill kind's own per-agent reconciliation against the delivery predicate ([skill-manager](../skill-manager/spec.md) "Reconcile deliveries from state on every pass"), which removes one agent's link without touching another's or the master. The text is the same for every agent (see "Serve every collection to every agent"). Re-rendering MUST happen whenever the catalogue changes — after a promotion, or a collection's creation, rename or deletion, and on every sweep so a document a person added by hand is catalogued too — and MUST never raise: a failed render leaves the previous master exactly where it was, and the corpus stays readable at paths a person can still give an agent.

#### Scenario: every agent reaches the guide through the one master folder
- **GIVEN** two registered agents and the `coffer-guide` skill seeded
- **WHEN** each agent's `<config_dir>/skills/coffer-guide` is inspected
- **THEN** each is the ordinary Coffer-managed link into `~/.coffer/derived/skills/coffer-guide/`, not a directory of real bytes
- **AND** a re-render that changes the catalogue changes what both agents read in one write, while narrowing the skill's scope to one agent reclaims only the other agent's link and leaves the master untouched

### Requirement: Describe Coffer and the collections' subjects in the skill description
The skill's **frontmatter description** MUST describe Coffer itself — naming its built-in tool so a model recognises it — **and** name the subjects the collections cover, drawn from their READMEs, and, while the knowledge feature is on, that the skill teaches how to write and tidy knowledge (see "Teach writing and tidying in the guide"). It is the only part of this layer that is always in a model's context, so it MUST carry matchable specifics rather than a description of the layer, and it MUST fit the tightest frontmatter ceiling any importer imposes (1024 characters), dropping whole collection subjects from the tail rather than cutting a sentence mid-way.

#### Scenario: one skill carries both Coffer's manual and the catalogue
- **GIVEN** a rendered `coffer-guide` `SKILL.md`
- **WHEN** its frontmatter and its body are read
- **THEN** the description names Coffer and its built-in tool as well as the collections' subjects, and is within 1024 characters — a catalogue too large to fit drops whole collection subjects from the tail rather than ending mid-sentence
- **AND** the body carries the manual first — the built-in tool, the tiering contract and that no Coffer tool waits on an approval — and the catalogue after it, in one file

### Requirement: Keep the handshake instructions to what a skill cannot carry
The MCP gateway's own `initialize` instructions MUST stay within their character cap and MUST carry only what a skill cannot: what Coffer is, the name of its one built-in tool (`coffer__search_tools`) so it is recognisable in a tool list, one line, while the knowledge feature is on, saying that Coffer's knowledge is Markdown read with the agent's own file tools, one line saying that Coffer's own logs are read with `coffer log`, the tiering sentence when tools are actually hidden this session, and a pointer to the `coffer-guide` skill for everything else. It MUST NOT restate the manual, MUST NOT name a memory directory, MUST NOT name a retrieval tool, and MUST NOT carry the catalogue — the catalogue is in the skill body, which costs a session nothing until a model opens it. A built-in tool whose experimental feature is switched off is not in the tool list, and the instructions MUST NOT name it either ([experimental-features](../experimental-features/spec.md) "Withdraw what a switched-off feature put in front of agents").

#### Scenario: name only the search tool in the handshake and point at the skill
- **GIVEN** a real daemon driven over its `/mcp` endpoint by the MCP SDK
- **WHEN** the client initializes, both with upstream tools hidden and with none hidden
- **THEN** the `instructions` text is within its character cap, names `coffer__search_tools`, names none of `coffer__write`, `coffer__recall` and `coffer__diagnose`, and points at the `coffer-guide` skill for the rest
- **AND** it names no retrieval tool and carries no collection catalogue

### Requirement: Render the guide skill deterministically
The rendered `SKILL.md` MUST be a **pure function of the running build and the catalogue it is given**: the same build over the same collections MUST produce the same bytes, run after run and machine after machine. Nothing machine-specific may enter it — not an absolute home directory, not a timestamp, not a build path — and the skill's own config MUST likewise carry no timestamp of its generation.

The artifact does not converge between machines ([vault-sync](../vault-sync/spec.md) "Withhold derived output in both halves"): every machine renders its own from files that converge plus its own reach. Determinism matters locally: an unchanged vault re-rendering to the same bytes is what lets the seed skip the write, so a boot or a sweep that changed nothing registers nothing, audits nothing and re-delivers nothing ([skill-manager](../skill-manager/spec.md) "Regenerate Coffer's builtin skill from the build"), and it is what makes the `version_hash` in the resource mean "the content moved" rather than "time passed".

The knowledge root MUST still be written in its `~`-relative form whenever it sits in its default place, so a path an agent reads is one a person can retype; a root that is not under the home directory MUST be written out in full, because an accurate path is worth more than a tidy one.

#### Scenario: the rendered skill is byte-identical on two machines
- **GIVEN** the same build and the same catalogue rendered twice, once with the knowledge root at each of two different home directories, and once again with the root outside the home directory
- **WHEN** the two default-placed renderings are compared byte for byte
- **THEN** they are identical, and the knowledge root appears in its `~`-relative form rather than as either home's absolute path
- **AND** the root outside the home directory is written out in full, and the skill's stored config carries no timestamp of when it was generated

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
The knowledge layer MUST NOT add any table to Coffer's databases, and MUST NOT create a directory or a record of its own outside the knowledge root. A collection is a resource file, `resources/knowledge/<name>.json` in the vault, like every other Resource; everything else this layer holds is a file the human can open.

#### Scenario: a collection is a resource file and a directory, nothing more
- **GIVEN** a database upgraded to head and a knowledge root under a temporary home
- **WHEN** a collection is created and material is submitted into it
- **THEN** no table in the history database is named for knowledge, and the collection is one resource of kind `knowledge`
- **AND** every file the layer wrote lies under the knowledge root

### Requirement: Serve every collection to every agent
Every collection MUST be named, catalogued and served to **every** agent, and a collection MUST NOT carry the Resource framework's per-agent reach or an enabled switch: the kind declares itself non-toggleable ([resource-framework](../resource-framework/spec.md) "Address every resource by an immutable uid through one kind-agnostic surface"). A collection leaves every agent's delivered skill only by being deleted. A file written under a top-level directory that is not a collection MUST be left alone and MUST NOT be catalogued (see "Adopt a file dropped into the inbox").

#### Scenario: every collection is in every agent's skill
- **GIVEN** two collections, `shopee` and `personal`, both holding documents, one of them stored disabled by an earlier version
- **WHEN** the database is migrated and the guide skill is re-rendered and seeded into its master folder
- **THEN** the master `SKILL.md` names both collections and lists both catalogues
- **AND** a request to disable either collection through the generic resource route is refused and changes nothing

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

### Requirement: Adopt a file dropped into the inbox
An agent, another machine or an older guide MAY leave a Markdown file at `<collection>/.inbox/<any-name>.md`, with optional frontmatter. The sweep MUST recognise a new inbox file that no Coffer surface wrote, **normalise** it, and promote it to a document (see "Promote submitted material at once"):

- `title` is kept, else the first `# ` heading, else the file name's stem;
- `description` is kept, else the first prose paragraph, else the title — the same fallback an upload uses (see "Fill frontmatter on converted material");
- `actor` is kept as written (it is self-reported), else `agent`;
- `created_at` and `updated_at` are kept, else the time the sweep saw the file;
- every other key a writer set is kept.

Coffer MUST record one `knowledge_written` audit event per file, carrying `actor_reported: true` when the actor came from the file. A Markdown file in a top-level directory that is not a collection MUST be left alone and MUST NOT be catalogued: only a person creates a collection (see "Create collections only deliberately"). A non-Markdown file in an inbox MUST be left in place, logged, and not promoted.

#### Scenario: a bare inbox file is normalised and audited
- **GIVEN** a `shopee` collection, and a file `shopee/.inbox/cache-ttl.md` holding a `# Cache TTL` heading, a paragraph and no frontmatter
- **WHEN** the sweep runs
- **THEN** the resulting document's frontmatter carries `title` `Cache TTL`, a `description` drawn from the paragraph, `actor` `agent`, and `created_at` and `updated_at` set to when the sweep saw it, with the body unchanged
- **AND** one `knowledge_written` audit event is recorded with `actor_reported` false, and the file is no longer in `.inbox/`

#### Scenario: keys a writer set are kept
- **GIVEN** an inbox file whose frontmatter sets `actor` `user`, a `title`, and a `source` key
- **WHEN** the sweep adopts it
- **THEN** the title, the actor and the `source` key are as written on the resulting document, and the audit event records `actor_reported: true`

#### Scenario: a file outside a collection or that is not Markdown is not material
- **GIVEN** a Markdown file at `notes/.inbox/idea.md`, where `notes` is not a collection, and a `shopee/.inbox/data.bin` file
- **WHEN** the sweep runs
- **THEN** the first is left alone and appears in no catalogue, no `notes` collection is created, and the second stays in the inbox, is logged, and is not promoted

### Requirement: Expose no knowledge tool
Coffer's MCP gateway MUST expose **no** tool that reads, lists, searches, writes or deletes knowledge. An agent reads knowledge with its own file tools at the paths the `coffer-guide` skill gives it and adds to it by writing files into the collection's documents (see "Teach writing and tidying in the guide").

#### Scenario: no knowledge tool appears in the client tool list
- **GIVEN** a real daemon with an upstream MCP server registered, driven over its `/mcp` endpoint by the MCP SDK so the SDK's own models validate every frame
- **WHEN** the client initializes and calls `tools/list`
- **THEN** `coffer__search_tools` is in the listing beside the upstream server's own tools, and `coffer__write`, `coffer__list`, `coffer__grep`, `coffer__read`, `coffer__search` and `coffer__delete` are **absent**

### Requirement: Teach writing and tidying in the guide
The `coffer-guide` skill MUST teach the agent that reads it to do the judgement Coffer does not do for it. Its knowledge sections MUST carry **Writing something down** — put a durable fact straight into the collection's documents with the agent's own file tools, by six rules: find the fact's home (fold it into the document that owns the subject, and create a file only when none does), lose nothing, organise by subject and never by provenance, let the newer statement win unless the older one is shown to be right while keeping the superseded one legible, never name another knowledge file, and give every document frontmatter with a `title`, a `description` saying what question the document answers, and `actor: agent` — and **Tidying a collection** — read one collection's README and documents, merge documents that answer the same question, split one that answers several, correct what is wrong or contradictory, and report what was merged, split, corrected and deleted. The skill's resident description MUST name writing and tidying knowledge, so an agent asked to organise knowledge (整理知识) recognises the skill. These sections MUST be present only while the `knowledge` feature is on.

#### Scenario: the rendered guide carries the writing and tidying sections
- **GIVEN** a vault with one collection and the `knowledge` feature on
- **WHEN** the guide skill is rendered
- **THEN** its body carries a "Writing something down" section and a "Tidying a collection" section
- **AND** its frontmatter description names writing and tidying knowledge

#### Scenario: the writing section states the six rules
- **GIVEN** the rendered guide body
- **WHEN** the "Writing something down" section is read
- **THEN** it tells the agent to fold a fact into the document that owns its subject, to lose nothing, to organise by subject and never by provenance, that the newer statement wins unless the older is shown to be right, never to name another knowledge file, and to give every document a title, a description and `actor: agent`

#### Scenario: the writing and tidying sections are absent while knowledge is off
- **GIVEN** the `knowledge` feature switched off
- **WHEN** the guide skill is rendered
- **THEN** neither "Writing something down" nor "Tidying a collection" appears in the body, and the description does not name tidying knowledge

### Requirement: Hand a tidy to the agent
A collection's read MUST carry `tidy_handoff`: a prompt the daemon writes, from the same hand-off module every other hand-off uses, that names the collection, gives its absolute path, and tells the agent to follow the `coffer-guide` section "Tidying a collection". `GET /api/v1/knowledge/tidy-handoff` MUST return the same kind of prompt for every collection at once: it asks the agent to tidy the collections one at a time by the `coffer-guide` section "Tidying a collection", and carries the knowledge root's absolute path and one fact line per collection with its name, absolute path and document count. The web UI MUST offer a **Tidy** button on a collection's page and a **Tidy all** button in the Knowledge page's header, which uses that route. Pressing either MUST start the hand-off agent in the person's preferred terminal with that prompt sent at once, as [web-ui](../web-ui/spec.md) "Hand a machine-dependent problem to an agent with one split button" says, and leave the page where it is. When no managed agent is available the button MUST offer **Copy prompt** only. Nothing MUST tidy unattended: Coffer starts no agent run of its own, and a collection is tidied only when a person presses Tidy or asks their own agent to.

#### Scenario: a collection read carries its tidy hand-off
- **GIVEN** a `shopee` collection holding documents
- **WHEN** the collection is read
- **THEN** its `tidy_handoff` prompt names `shopee`, carries the collection's absolute path under the knowledge root, and names the "Tidying a collection" section of `coffer-guide`

#### Scenario: the knowledge tidy-all hand-off names every collection
- **GIVEN** two collections, `shopee` with three documents and `personal` with one
- **WHEN** `GET /api/v1/knowledge/tidy-handoff` is read
- **THEN** the prompt names the "Tidying a collection" section of `coffer-guide` and asks for the collections to be tidied one at a time
- **AND** it carries the knowledge root's absolute path and one fact line each for `shopee` (its path, 3 documents) and `personal` (its path, 1 document)

#### Scenario: Tidy all sends the prompt like Tidy does
- **GIVEN** the Knowledge page header and a managed agent available
- **WHEN** the user presses Tidy all
- **THEN** the hand-off agent starts in the preferred terminal with the all-collections prompt sent once, and the page stays where it is
- **AND** with no managed agent available the button offers Copy prompt only

#### Scenario: Tidy sends the prompt to the default managed agent at once
- **GIVEN** a collection page and a managed agent available
- **WHEN** the user presses Tidy
- **THEN** the hand-off agent starts in the preferred terminal with the collection's tidy prompt sent once, and the page stays where it is

#### Scenario: Tidy offers only Copy prompt with no managed agent
- **GIVEN** a collection page and no managed agent available
- **WHEN** the user presses Tidy
- **THEN** the page offers Copy prompt carrying the collection's tidy prompt and starts no terminal

### Requirement: Sweep the knowledge root on three mechanical duties
The daemon MUST run a **knowledge sweep** on a recurring timer, and the sweep MUST do exactly three things and call no model: re-render and re-seed the `coffer-guide` skill so a document added by hand is catalogued; adopt every file sitting in a collection's `.inbox/` and promote it to a document (see "Adopt a file dropped into the inbox"); and commit every change found on disk under `knowledge/` as an edit on disk, so a person's editor or an agent's file tools is never counted as Coffer's (see "Commit every knowledge write naming its writer"). The sweep MUST NOT hold the vault against a sync round: whatever it promotes is written through the vault's ordinary writer. While the `knowledge` feature is switched off the sweep MUST skip its rounds ([experimental-features](../experimental-features/spec.md) "Close the knowledge feature's surfaces").

#### Scenario: a sweep catalogues a document added by hand
- **GIVEN** a collection and a Markdown document a person adds to it in their own editor
- **WHEN** the knowledge sweep runs
- **THEN** the document is committed as an edit on disk and the re-rendered guide's catalogue lists it

#### Scenario: a sweep promotes a file dropped into the inbox
- **GIVEN** a Markdown file dropped into `shopee/.inbox/`
- **WHEN** the knowledge sweep runs
- **THEN** the file is a document at the `shopee` root and `.inbox/` no longer holds it

#### Scenario: a sweep runs while a sync round waits
- **GIVEN** a sync round that waits for a person and a file in an inbox
- **WHEN** the knowledge sweep runs
- **THEN** it does not wait for the round, and the file is promoted through the vault's ordinary writer

#### Scenario: a switched-off knowledge feature skips the sweep
- **GIVEN** the `knowledge` feature switched off and a file in an inbox
- **WHEN** the sweep's timer fires
- **THEN** nothing is adopted, committed or re-rendered, and the collections stay on disk untouched

### Requirement: Promote submitted material at once
Material MUST NOT wait. A submission Coffer receives — an upload — MUST become a document on the spot, at the collection root, with the frontmatter of "Carry title, description and actor in frontmatter" filled from its opening prose, named from its title (see "Use the file path as a document's identity"), and committed naming whoever submitted it. A file adopted from `.inbox/` becomes a document the same way. Whenever material is submitted or a sweep promotes a file, Coffer MUST announce the collection on the daemon's event stream as a `knowledge` event carrying the collection's uid, because the documents change without any write to the collection's row ([resource-framework](../resource-framework/spec.md) "Announce every change on one daemon-wide event stream"). Every entrance Coffer serves submits through this one operation. Nothing is merged into another document by Coffer: where a fact belongs among the existing documents is the agent's tidying (see "Hand a tidy to the agent"), so a promoted document stands as it arrived.

#### Scenario: an upload becomes a document at the collection root
- **GIVEN** a `shopee` collection
- **WHEN** a Markdown file is uploaded to it
- **THEN** the collection holds one new document at its root whose body is the uploaded text, whose frontmatter carries a title, a description drawn from its opening prose and `actor` `user`, and whose commit names the user
- **AND** nothing is left in `shopee/.inbox/`

#### Scenario: an upload answers with the document it became
- **GIVEN** a `shopee` collection
- **WHEN** a document is uploaded once through `POST /api/v1/knowledge/upload`
- **THEN** the answer carries the new document's path and no `pending` field, and the document is in the collection's visible tree

#### Scenario: submitting material announces the collection on the event stream
- **GIVEN** a `shopee` collection and a client reading the event stream
- **WHEN** a document is uploaded to it
- **THEN** a `knowledge` event naming the collection's uid is announced

### Requirement: Treat a direct file edit as a complete change
Writing, editing or deleting a document directly in the collection's tree — by a person in their own editor, or by an agent with its own file tools — MUST remain a complete way to change knowledge: no import, no registration, no conversion step, and the change is live on the very next read. The change MUST be committed to the vault as an edit found on disk, by the sweep or by the next Coffer write, whichever comes first (see "Sweep the knowledge root on three mechanical duties"). Ingestion is an additional entrance, never a required one.

#### Scenario: an agent's new document is live at once and committed as a disk edit
- **GIVEN** a `shopee` collection and an agent that writes a Markdown document into it with its own file tools
- **WHEN** the document is read before any sweep, and the knowledge sweep then runs
- **THEN** the read returns the agent's text with no import step in between
- **AND** the sweep commits the document as an edit found on disk

### Requirement: Convert uploads into documents without keeping the original
The system MUST accept a document upload into a named collection, convert it to Markdown, and **submit the Markdown as material** (see "Promote submitted material at once"), so it becomes a document of its own at the collection root. Supported inputs MUST be exactly what the converters accept: what `markitdown` handles (PDF, `docx`, `pptx`, `xlsx`, `xls`, HTML, EPUB), CSV, and text read as it stands (Markdown, plain text, reStructuredText, and source and configuration files such as `py`, `ts`, `sql`, `yaml`, `json`, `log`); an unsupported type MUST be refused with the type named, never stored half-converted. The **original** bytes MUST NOT be kept: only the extracted Markdown becomes a document. There is no `source_mode`, no external-source table, no re-conversion on a schedule, no hidden `.raw/` and no visible original beside the text. An upload takes no folder.

#### Scenario: an upload is converted into a document, keeping no original
- **GIVEN** a collection and a document sent into it — `notes.md` through the ingest service, `team.csv` through `POST /api/v1/knowledge/upload`
- **WHEN** the upload is accepted (201 from the route)
- **THEN** the answer carries the document's path, the converter that ran, the title and a description, and the collection holds exactly one new file: a document carrying the extracted Markdown with frontmatter `actor: user`
- **AND** the original bytes exist nowhere in the collection's visible tree, and no hidden `.raw/` exists either

#### Scenario: an upload of an unsupported type is refused with its reason
- **GIVEN** a collection, and a file whose type no converter handles — `archive.bin` at the service, `payload.exe` at the route
- **WHEN** it is uploaded
- **THEN** the service raises `UnsupportedDocument` and the route answers 400 `INGEST_REJECTED` whose details name `reason` `unsupported_type` and `doc_type` `exe`, and the collection is left with no new file at all

### Requirement: Follow edits across collections in one feed
The system MUST serve one feed of the recent changes to knowledge across every collection, newest first, paged by an opaque cursor ([resource-framework](../resource-framework/spec.md) "Page growing lists by an opaque cursor") and filterable to one collection: every document a person or an agent wrote, restored or deleted, and every change from sync or from disk — each with its writer, its time, its collection and, for each document it touched, whether that document was added, changed or removed and how many lines were added and removed. A change an earlier version of Coffer made as a curation pass is listed with its writer. One change MUST be readable in full — every document it touched with its diff. The feed is `GET /api/v1/knowledge/changes`, the route a delete's Undo reads to find the delete it restores (see "Undo a knowledge delete from its toast"); the web UI shows no timeline of it.

#### Scenario: recent changes lists edits across collections
- **GIVEN** a person's upload in one collection and an agent's edit on disk in another
- **WHEN** the feed is read, and read again filtered to one collection
- **THEN** both changes are listed newest first with their collections, writers and per-document line counts
- **AND** the filtered read holds only that collection's changes, and one change read in full carries each document's diff

### Requirement: Delete a document at once, a collection after asking, and offer Undo
The web UI MUST delete a document **at once**: its ⋯ menu's **Delete document** opens no confirmation, because the delete is reversible. **Delete collection** MUST ask first, in a confirmation naming the collection and how many documents it holds, because once its toast closes a collection can no longer be brought back from the page; the confirmation asks for no typed name. The page MUST report either delete in a toast — *Deleted <name>* — carrying **Undo**, which restores what the delete removed (see "Undo a knowledge delete from its toast"), and MUST then show the collection page after a document's delete and the Knowledge page after a collection's. The delete is audited as a `knowledge_deleted` event, and an Undo refused because the path or name is taken again MUST say so rather than overwrite it.

#### Scenario: delete a document at once and undo it
- **GIVEN** a document open in the Knowledge page
- **WHEN** the user chooses ⋯ → Delete document
- **THEN** no dialog asks, the document is gone, the collection page shows, and a toast reads *Deleted <name>* with Undo
- **AND** choosing Undo puts the document back at its path with its text, as one new change by the user

#### Scenario: delete a collection after asking and undo it from the toast
- **GIVEN** a collection with a document
- **WHEN** the user chooses ⋯ → Delete collection and confirms
- **THEN** a confirmation named the collection and its document count before anything was deleted, the collection is gone, the Knowledge page shows, and the toast offers Undo
- **AND** choosing Undo brings the collection back under its name with its document

### Requirement: Undo a knowledge delete from its toast
Deleting a document or a whole collection MUST keep what it removed in the vault's history, so the delete's toast can undo it. Undo MUST find the delete in the changes feed (see "Follow edits across collections in one feed") and restore exactly what it removed, as it was just before it: a document into its collection; a collection as a new collection of the same name with its documents and its `README.md`. A collection restore MUST write every file first and register the collection's row last, so a failure part-way leaves no row and no partial directory: what was written is removed again and the same restore can be tried afresh. The restore MUST be one new change naming the user, carrying the version of the delete it restored, and recorded as a `knowledge_edited` audit event; the delete itself stays in the history. A restore MUST be refused with nothing written when it would overwrite — a document at the same path, `409 KNOWLEDGE_RESTORE_CONFLICT` naming it, or a collection of the same name, `409 KNOWLEDGE_COLLECTION_EXISTS` — and a change that is not a delete MUST be refused with `400 KNOWLEDGE_NOT_A_DELETE`. The route is `POST /api/v1/knowledge/changes/{version}/restore`, the web UI's own. After the toast is gone the deleted document has no page to open its History tab from; its versions stay in the vault's history, where git reads them.

#### Scenario: undo a collection delete
- **GIVEN** a collection holding a document and a `README.md`, which the user deletes
- **WHEN** the delete is found in the changes feed and restored
- **THEN** the collection is back under its name with its document and its README's description, as one new change by the user naming the delete it restored
- **AND** a second restore of the same delete is refused because a collection of that name exists, and writes nothing

#### Scenario: a collection undo that fails part-way leaves nothing behind
- **GIVEN** a deleted collection whose restore fails while one of its files is being written
- **WHEN** the user restores the delete
- **THEN** the restore fails, no collection of that name is registered, and no directory of that name is left on disk
- **AND** a second restore, once the cause is gone, succeeds

#### Scenario: undo a document delete
- **GIVEN** a document the user deletes
- **WHEN** the user restores the delete
- **THEN** the document is back at its path with the text it had, and the vault's history holds the restore after the delete

#### Scenario: an undo that would overwrite is refused
- **GIVEN** a deleted document whose path holds a new document again
- **WHEN** the user restores the delete
- **THEN** the restore is refused naming that document, and the new document is unchanged
- **AND** restoring a change that is not a delete is refused as not a delete

### Requirement: Show a collection as one tree of read-only documents in the web UI
The web UI MUST present a collection as **one tree** of its documents — no lanes, no tabs, no filter or retrieval box — with the chosen document in the pane beside it, the same two panes a skill's Files tab is. The tree MUST name every collection, folder and document by its name on disk: a collection has no title (see "Name a collection by its folder and edit its description in place"). Its **Collections** header strip MUST carry **New collection** (a name and what belongs in it; the collection reaches every agent through the coffer-guide skill). The tree MUST show no hidden entry, and no collection or folder carries a document count. Knowledge calls its files **documents** everywhere.

A document's pane MUST carry two tabs in its bar, **Document** (the default, `/knowledge/<uid>?file=<path>`) and **History** (`/knowledge/<uid>/history?file=<path>`), neither with a count. Document MUST show the document read-only, with a **Preview / Source** switch, **Open in editor** as a visible button, and a ⋯ menu holding **Reveal in Finder** and **Delete document**. History is the document's versions in the vault and their diffs, with **Restore this version…** ([web-ui](../web-ui/spec.md) "Show a vault file's history on a History tab"). Its properties — who wrote it and when it was created, read from its frontmatter — MUST be one line under its title; there is no side column. The pane MUST NOT edit the document: a person changes it in their own editor and an agent with its own file tools (see "Treat a direct file edit as a complete change"), and the next read shows the change.

A collection's page MUST show its folder name, its description edited in place (see "Name a collection by its folder and edit its description in place") and its properties: **Documents** and **Folder**, and it MUST carry **Tidy** (see "Hand a tidy to the agent"). A collection with no documents shows the same page with one line saying so and how to fill it — upload one, or drop Markdown files into the folder — and **Reveal in Finder**. The collection's ⋯ menu MUST hold **Reveal in Finder**, **Copy path** and **Delete collection** (see "Delete a document at once, a collection after asking, and offer Undo").

The page MUST offer **Upload** into a collection as its one primary action and no other form that adds a document: people write in their own editor, agents by writing files. With no collection open, the page shows its collections and **Tidy all**; there is no Recent changes view. The tree and the pane MUST extend to the bottom of the window and scroll inside.

The Knowledge page's title MUST carry the **Experimental** tag ([experimental-features](../experimental-features/spec.md)).

#### Scenario: the viewer shows one tree of documents
- **GIVEN** a collection page whose tree holds a document at the root and one inside a folder
- **WHEN** the page renders and a document's row is clicked
- **THEN** there is one tree — no lane headings, no tabs, no filter input — listing both documents and no hidden entry
- **AND** the document carries Document and History tabs, offers Open in editor, and Reveal in Finder and Delete document in its ⋯ menu

#### Scenario: the page's one primary action is Upload
- **GIVEN** the Knowledge page with a document open
- **WHEN** the user reads the header and the document's pane
- **THEN** Upload is the primary button
- **AND** no control on the page adds a document from a typed title and body, and the pane offers no Edit

#### Scenario: a document opens in the person's editor
- **GIVEN** a document open in a collection's pane
- **WHEN** the user chooses Open in editor, and then Reveal in Finder from its ⋯ menu
- **THEN** the daemon is asked to open the document's absolute path and then to reveal it
- **AND** the pane shows the document read-only, with Preview and Source, and its created line read from the frontmatter

#### Scenario: a collection page shows its properties
- **GIVEN** a collection holding two documents
- **WHEN** its page renders
- **THEN** it shows the folder name, the description, the Documents and Folder properties and a Tidy button
- **AND** its ⋯ menu offers Reveal in Finder, Copy path and Delete collection

### Requirement: Commit every knowledge write naming its writer
Every accepted write to a collection MUST be a git commit naming its writer ([Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer](../../../docs/decisions/every-vault-write-is-a-validated-commit-naming-its-writer.md)). The commits are the vault repository's, under `knowledge/`: the knowledge root keeps no repository of its own. A person's upload, description edit, delete or Undo names the user; material promoted on arrival names whoever submitted it — the user, or, for a file an agent dropped into the inbox, the actor the file reports; a change that arrives through vault sync names sync; and a change any other writer made in the tree — a person's own editor, an agent's file tools — MUST be committed as an edit on disk before Coffer's next commit, so it is never counted as Coffer's. A commit an earlier version of Coffer made as a curation pass stays in the history under its writer. A document's history is read, and an earlier version restored as a new commit, on its History tab ([vault-storage](../vault-storage/spec.md) "Show and restore any version of a vault file or folder"). The vault is a git repository on every machine that runs Coffer ([vault-storage](../vault-storage/spec.md) "Keep the vault a git repository whether or not it syncs"); a read of the changes feed git cannot answer MUST answer 503 `KNOWLEDGE_HISTORY_UNAVAILABLE` while every write keeps working. git is looked for on every read, so one removed while the daemon runs is answered the same way. When the cause is that git is not installed, the refusal's details MUST carry `reason: "git_missing"` and `handoff`, a prompt asking the person's agent to install git on this machine — naming its OS and architecture and what needed git — the way that fits the machine, confirming it with `git --version`; neither the prompt nor the error's message may name an install command.

#### Scenario: knowledge writes are commits naming their writers
- **GIVEN** a document that an upload created for the user, that an agent then edited on disk
- **WHEN** the user then uploads another document and the vault's commits under `knowledge/` are read
- **THEN** the first document's commits name the user and then an edit on disk, and the second upload's commit holds only the new document and names the user

#### Scenario: an edit on disk becomes a commit of its own
- **GIVEN** a document a person edits in their own editor, outside Coffer
- **WHEN** Coffer then makes its next knowledge write
- **THEN** the edited document is committed first as its own edit on disk, and Coffer's commit holds only what Coffer wrote

#### Scenario: no git hands installing it to an agent
- **GIVEN** a machine with no git
- **WHEN** a document is written and the changes feed is then read
- **THEN** the write works and the read is refused `KNOWLEDGE_HISTORY_UNAVAILABLE` with reason `git_missing` and a prompt to install git naming this machine and `git --version`, and neither the prompt nor the message names an install command

### Requirement: Manage knowledge in the web UI and on the command line
People MUST manage knowledge in the web UI, and agents with the `coffer knowledge` commands: creating collections, uploading documents, reading documents and opening them in their editor, reading a document's history and restoring an earlier version, tidying a collection through their agent, deleting and undoing a delete, and editing a collection's description. The REST routes under `/api/v1/knowledge` behind those pages serve the web UI and the `coffer knowledge` commands, which call the same routes ([resource-framework](../resource-framework/spec.md) "Offer every management operation on the command line"): a route the web UI does not call MUST NOT exist, and there MUST be no route that creates or saves a document at a path — a person's text reaches knowledge through their own editor (see "Treat a direct file edit as a complete change") or as material like every other entrance (see "Promote submitted material at once"). There MUST be no route under `/api/v1/knowledge` that lists a document's versions, diffs a version or restores one: a document's history is read and restored through the vault's routes ([vault-storage](../vault-storage/spec.md) "Show and restore any version of a vault file or folder") on its History tab. There MUST be no index, reindex, check-sources, update-source or embedding-configuration endpoint, no curate or undo-pass endpoint, no settings endpoint for the cwd-derived scope axis "Derive no boundary from the working directory" forbids, and no per-agent reach endpoint or enabled switch for this kind (see "Serve every collection to every agent"). Collection deletion goes through the Resource framework (`DELETE /api/v1/resources/{uid}`). The `coffer knowledge` commands MUST list, create, describe and delete collections, read a level of the tree and the changes feed, upload material, undo a delete and print the tidy hand-off; no command reads, writes or deletes a document's content, and there is no `coffer path` target for knowledge: a collection's documents are plain files, so agents and people read, edit and delete them directly under the knowledge root that the `coffer-guide` skill names (see "Treat a direct file edit as a complete change").

#### Scenario: knowledge is managed on the command line, its documents as files
- **GIVEN** the `coffer` command tree
- **WHEN** the `knowledge` group is enumerated, and `coffer path` is run with a `knowledge` target
- **THEN** the group offers collections, create, describe, delete, tree, changes, restore and upload, and no command reads, writes or deletes a document
- **AND** `coffer path` refuses `knowledge` as an unknown target

#### Scenario: the routes are the web UI's, with no material or create-at-path route
- **GIVEN** the daemon's route table under `/api/v1/knowledge`
- **WHEN** it is enumerated
- **THEN** it offers create a collection, list a level, read, upload, delete a document, the changes feed and restoring a delete, rewrite a description, and the tidy-all hand-off
- **AND** it carries no route that saves a document, no history, version or version-restore route, no `/material` route, no curate route, no undo route, no route that creates a document at a path, and no index, reindex, source, embedding, scope or reach endpoint

### Requirement: Merge the manual and the catalogue in the skill body
The skill's **body** MUST be one merged manual: Coffer's own — its one built-in tool, `coffer__search_tools`, and when to reach for it; the tiering contract that makes an unlisted upstream tool still callable; the knowledge root; that Coffer's own logs are read with `coffer log` and located with `coffer path logs`; that a skill's scripts keep their logs, operation journals and temp files under `~/.coffer/skill-data/<skill-name>/` (found with `coffer path skill-data`), never in the skill's own folder or elsewhere in `~/.coffer`, and that files there are deleted after the Skill working files retention window, so durable data does not belong there; that `coffer cli list` lists the command-line tools Coffer manages, what each is for and whether it is ready on this machine; that no Coffer tool waits on a human approval; and what does not belong in knowledge — **followed by** the catalogue: the path of the knowledge root, and, for each collection, every document's collection-relative path, title and description. It MUST instruct the agent to read those files with its own tools, and to write what it learns that is durable straight into the collection's documents, and to tidy a collection when asked (see "Teach writing and tidying in the guide"); a change to a document is carried by the sweep into the vault's history (see "Treat a direct file edit as a complete change"). The manual MUST name no memory directory: an agent reaches memory through its own native memory ([memory](../memory/spec.md) "Deliver no memory into a session"). One skill, not a set: a frontmatter description is resident in every session whether the skill is opened or not, while a body is paid for only when a model reaches for it, so a second skill would spend the resident budget again to describe something most sessions never open.

#### Scenario: the skill body carries the catalogue and the absolute root
- **GIVEN** a collection holding three documents
- **WHEN** the skill is rendered
- **THEN** its body carries each document's collection-relative path, title and description, and the path of the knowledge root, and it instructs the agent to read those files with its own tools
- **AND** the frontmatter `description` names the collection's subject, taken from the collection's own `README.md`, so a model matching on it has something to match

#### Scenario: name one tool, the knowledge root and the log reader in the manual
- **GIVEN** a vault with one collection
- **WHEN** the skill is rendered
- **THEN** its manual names exactly one built-in tool, `coffer__search_tools`, and names none of `coffer__write`, `coffer__recall` and `coffer__diagnose`
- **AND** it names the knowledge root and no memory directory, tells the agent to write durable knowledge into a collection's documents itself, and names `coffer log` and `coffer path logs` as the way to read Coffer's own logs, and `coffer cli list` as the way to learn which command-line tools Coffer manages

#### Scenario: the manual says where a skill's scripts keep their files
- **GIVEN** a vault with one collection
- **WHEN** the skill is rendered, with or without the knowledge and memory features on
- **THEN** its manual says a skill's scripts write their logs, operation journals and temp files under `~/.coffer/skill-data/<skill-name>/`, found with `coffer path skill-data`
- **AND** it says never to write them inside the skill's own folder, that files there are deleted after the Skill working files retention window, and that durable data does not belong there
