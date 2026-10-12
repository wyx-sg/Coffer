# Knowledge Layer

## Purpose

Coffer holds **knowledge about the user's working environment**: their repositories, services, projects, the people they work with, the decisions and traps worth surviving a session. It is a **directory of Markdown files**, and each collection is a **wiki**: its `README.md` is the schema, `sources/` keeps the material that arrived — an upload converted to Markdown, or a file dropped into the inbox — and `pages/` holds the pages the person and their agents write from it. Coffer runs no model over it. The pages are what an agent reads first — with its own `Read`, at an absolute path, through no tool of Coffer's — and `sources/` is what it greps for an exact fact. Every agent reads the same directory, so what one agent records in the morning a different agent reads in the afternoon. See [Knowledge Is Plain Files](../../../docs/decisions/knowledge-is-plain-files.md) and [Knowledge Is a Wiki of Pages Compiled From Kept Sources](../../../docs/decisions/knowledge-is-a-wiki-of-pages-compiled-from-kept-sources.md). The spec id `knowledge` is kept although the layer merged with what used to be a separate Knowledge Base: it is the identifier inbound links and the acceptance audit resolve, not a description.

**Knowledge is not memory.** Knowledge is about the world — a platform's API contract, a service's ownership, a document someone published — and it arrives because a person, or an agent working with them, put it there. Memory is about the user and their projects, and it accrues on its own as agents work. They differ in who authors them, how they are partitioned and how they are delivered, so they are two layers: this one, filed by collection and **pulled** through a skill, and [memory](../memory/spec.md), filed by project and written into each agent's own memory.

**Knowledge is compiled and tidied by the person and their agents.** A source waits until a page cites it; integrating it — folding what it says into the pages that own its subjects — is judgement, and so are merging, splitting and correcting pages, so all of it is the agent's: a **Tidy** button on a collection, and **Tidy all** on the Knowledge page, start the person's agent with the backend's tidy prompt, which carries what Coffer found and asks the agent to fix it, to leave what it is unsure of alone and to report it. What is mechanical Coffer computes itself on every read: dead links, orphan pages, pages without sources, waiting sources. A tidy lands in the collection's history as one change carrying the agent's report, which the person can undo as a whole. Nothing tidies unattended: Coffer starts no agent run of its own. Metadata lives in the file rather than a database row because only the file is visible to all of them. The layer answers to four invariants:

1. **Sources are kept, pages are edited, and every writer shares the pages.** A source is never edited; no page belongs to one writer, and no statement is protected because of who wrote it — the newer or better-evidenced one wins and the superseded one stays legible.
2. **New knowledge is kept as a source at once.** Every entrance turns its input into a source as it arrives. A file an agent drops into the hidden `.inbox/` is adopted by the next sweep. Which sources still wait is derived from the pages that cite them, never recorded.
3. **Pages link by slug, never by path.** Paths change as a collection is reorganised; a `[[slug]]` survives a move, and Coffer reports every link that names nothing.
4. **Retrieval is the agent's own.** Coffer exposes no tool for reading, listing, grepping or searching knowledge. The catalogue and the path ride in Coffer's own delivered skill, `coffer-guide`; the agent reads the files with the tools it already has.

These are **standing constraints**, not a phase that has passed: no derived index of any kind, no retrieval tool (an audit of 448 Claude Code sessions found the old tools were never called — a tool an agent does not remember to call is not retrieval), no second retrieval surface on the web page, and no stored state about the corpus. Ingestion is an additional entrance, never a required one: writing a Markdown page with any editor stays a complete way to add knowledge, and upload exists because the user's live entrance is often a phone.

**A linked folder is the other sort of collection.** A person can link a folder they keep with their own tools anywhere on this machine — an Obsidian vault, say — and Coffer then only **shares** it with agents: `coffer-guide` lists it with its own path, its own rules file and its notes, and the Knowledge page reads it. Nothing is copied into Coffer and Coffer writes nothing into it: no upload, delete, tidy, check, history or sweep. Its record is machine-local, so it never syncs; on another Mac the person links that Mac's copy. Where a requirement below speaks of a collection's directory under the knowledge root, its README as schema, its pages, sources or inbox, its check, its tidy or its history, it means a collection Coffer keeps; what holds for a linked folder is in "Link a folder the person keeps themselves" and "Leave a linked folder to its own tools". See [A Linked Knowledge Folder Is Shared in Place, Read-Only to Coffer, and Recorded Machine-Local](../../../docs/decisions/linked-knowledge-folders-are-read-only-and-machine-local.md).

The **knowledge sweep** keeps its mechanical duties: it adopts files dropped into `.inbox/` as sources, files Markdown left outside `pages/` and `sources/` into `pages/`, commits edits found on disk, and re-renders the guide. It calls no model and has no switch or interval of its own.

Assumptions: the corpus stays in the hundreds of files, so a catalogue of every document fits a skill body (measured at ~5.2K tokens for 58 documents); tens of thousands of files would be a different design and the place embeddings would be reconsidered. Agents tidy with no review step; what stands between a document and a bad tidy is the collection's git history, where every change is recorded, a tidy is one change that **Undo this tidy…** puts back, and any file can be restored through History. An ingested document's description is filled from its opening prose, so no user content leaves the machine for this layer.

While the `knowledge` feature is switched off (spec [experimental-features](../experimental-features/spec.md) "Close the knowledge feature's surfaces"), the knowledge routes are closed, the knowledge sections of `coffer-guide` are absent, and the knowledge sweep skips its rounds; collections stay on disk untouched. Requirements below describe the feature while it is on.

## Requirements

### Requirement: Store each collection as one tree of Markdown files
Knowledge Coffer keeps MUST be stored as files under `~/.coffer/vault/knowledge/<collection>/` — the knowledge root is the vault's `knowledge/` folder ([vault-storage](../vault-storage/spec.md) "Store state in five classes by nature") — each collection **one tree of Markdown files** that people and agents write together, divided by what a file is (a source or a page, see "Keep sources and pages apart in each collection") and never by who may write it. The files are the only copy; the system MUST NOT keep a retrieval index of any kind — no vectors, no sidecar, no FTS5, no chunking, no reindex, no cache — so every answer, the mechanical check included, is read off disk at call time. A linked folder is the one collection stored elsewhere: its files stay in the folder the person keeps, and Coffer reads them there, with no index either (see "Link a folder the person keeps themselves").

#### Scenario: keep no index beside the documents
- **GIVEN** a `shopee` collection holding one page written through the agent's file tools
- **WHEN** the knowledge root is walked, and the page's file is then rewritten on disk by hand
- **THEN** the only files under the collection are the page itself and nothing Coffer derived from it — no index, sidecar or cache file
- **AND** the next read through the service returns the hand-written text, with no reindex step in between

### Requirement: Use the file path as a document's identity
A file's **path is its identity**, and a page's or a source's **slug** — its file name without `.md` — is the name links use (see "Link pages by slug and check every link"). There MUST be no separate id field in frontmatter and no id-to-path mapping anywhere. File names MUST be human-readable slugs derived from the title; a collision appends a short suffix. Two pages sharing a slug is a finding, not something Coffer resolves (see "Check a collection mechanically on every read").

#### Scenario: name a file by its title and suffix a collision
- **GIVEN** an empty `shopee` collection
- **WHEN** two pieces of material titled `Session Ownership` are submitted
- **THEN** the two sources are `shopee/sources/session-ownership.md` and `shopee/sources/session-ownership-2.md`
- **AND** neither file's frontmatter carries an `id` key

### Requirement: Carry title, description and actor in frontmatter
Every source MUST carry YAML frontmatter with `title`, `description`, `actor` (`agent` | `user`), `created_at` and `updated_at`; those are the keys Coffer writes. A page carries `title`, `type`, `description`, `sources`, `aliases`, `actor`, `created_at` and `updated_at`, and may carry `verified: YYYY-MM-DD`, when it was last checked against its sources or the code, all written by whoever writes the page as the guide teaches; Coffer writes no page. A page's read MUST return its `verified` value as written, empty when it has none. Any other key a person put in a file MUST be kept, in place and with its value unchanged, whenever Coffer rewrites the file — a file is the person's as much as Coffer's.

#### Scenario: frontmatter carries title, description and actor
- **GIVEN** an empty `shopee` collection
- **WHEN** material is submitted into it with a title, a description and `actor` `user`
- **THEN** the source's YAML frontmatter holds `title`, `description`, `actor`, `created_at` and `updated_at`, carries the title and the actor it was given, and the body follows the fence unchanged

### Requirement: Allow nesting without giving it meaning
Inside `pages/` and `sources/` a collection MAY contain arbitrarily nested subdirectories, and the system MUST NOT assign them meaning or require them: `pages/` and `sources/` are the only directories that mean anything. The nesting is **chosen by whoever files a page** — a person or an agent — and either MAY create, move and remove directories under `pages/`.

#### Scenario: list and catalogue a nested document at its own path
- **GIVEN** a `shopee` collection holding a page a person filed at `shopee/pages/a/b/deep.md`
- **WHEN** the level `shopee/pages/a/b` is listed and the collection's catalogue is read
- **THEN** the listing names `shopee/pages/a/b/deep.md` as a page
- **AND** the catalogue carries it at that nested path, with no folder required or renamed

### Requirement: Hide every dot-prefixed entry
Hidden entries (dot-prefixed) MUST be excluded from every count and from the catalogue and the check, and no surface MUST list or read one: the tree route lists none, the read route refuses every hidden path, and a collection reports no count of what hides in it. A collection's `.inbox/` is an ordinary hidden entry whose files the sweep adopts as sources (see "Adopt a file dropped into the inbox"). `.history/` and `.raw/` do not exist: what a person or an agent replaced is kept in the collection's git history (see "Commit every knowledge write naming its writer"), and an upload is kept only as its Markdown source in `sources/` (see "Keep every upload as a Markdown source").

#### Scenario: leave hidden entries out of every listing
- **GIVEN** a `shopee` collection holding one page, a file in `.inbox/`, and a file a person put under `.scratch/`
- **WHEN** the collection is listed, its page count read, its catalogue rendered and its tree requested
- **THEN** the page count is one and the catalogue names the one page only
- **AND** the tree lists the page and nothing from `.inbox/` or `.scratch/`, and the read route refuses a path under either

### Requirement: Guard every path through one module
Every name that becomes a path segment MUST pass a traversal guard, and path construction MUST live in exactly one module. A path that names a document MUST lie inside a collection and MUST NOT be the collection itself or its `README.md`.

#### Scenario: a path escaping the knowledge root is rejected
- **GIVEN** the single path-construction module every surface resolves through
- **WHEN** it is asked to resolve `../etc/passwd`, `shopee/../../outside`, or any path naming a hidden entry — `shopee/.inbox/material.md` included
- **THEN** each one raises `UnsafeKnowledgePath` rather than returning a location outside the root

### Requirement: Keep the collection README out of the corpus
A collection's `README.md` MUST sit at the collection root and MUST NOT be listed as a page or a source or counted. It is the collection's schema: its first paragraph is the collection's description, and what it says about the collection's page types and conventions MUST take precedence over the guide's defaults, as the guide tells agents (see "Teach writing and tidying in the guide").

#### Scenario: keep the README out of listings, counts and curation
- **GIVEN** a `shopee` collection whose root holds a `README.md` edited after it was created and one page
- **WHEN** the collection is listed, counted and swept
- **THEN** the listing names only the page, the page count is one, and the README is never moved, adopted or catalogued as a page

### Requirement: Create collections only deliberately
A **collection** is one `knowledge` Resource, of one of two sorts: a collection Coffer keeps, which is a top-level subdirectory of the knowledge root, or a linked folder, which is a folder the person keeps elsewhere on this machine (see "Link a folder the person keeps themselves"). Either MUST be created deliberately — through the web UI's **New collection…** or **Link an external folder…**, or the `coffer knowledge create` and `coffer knowledge link` commands over the same routes — and MUST NOT be provisioned by a read, a write, a file an agent wrote, or an agent's working directory. Creating a collection Coffer keeps creates its directory and nothing inside it but an optional `README.md`; linking a folder creates nothing in the folder.

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
What this layer serves is **files on disk**, and the system MUST describe it as such wherever it is presented: a delivered path is the whole of the access story, because an agent handed the knowledge root reads anything under it with the shell tools it already has. Every collection is served to every agent (see "Serve every collection to every agent"), and nothing about a collection may be presented as a filesystem boundary: a collection has no switch that would hide it from a process that can open the directory. A linked folder is presented the same way, as files at its own absolute path, which its section of the catalogue names (see "Merge the manual and the catalogue in the skill body").

#### Scenario: the guide hands over files to read with the agent's own tools
- **GIVEN** a collection holding one document
- **WHEN** the guide skill's catalogue is rendered
- **THEN** it tells the agent to read each document at `<root>/<collection>/<path>` with its own file tool and names the directory the collection's files live under
- **AND** it names no Coffer tool as the way to read a document

### Requirement: Fill frontmatter on converted material
A source made from an upload MUST carry the frontmatter of "Carry title, description and actor in frontmatter" — `title` from the document (falling back to its file name) and `description` drawn from the document's opening prose.

#### Scenario: title an upload from its file name when it has no heading
- **GIVEN** a collection and a plain-text file `release-notes.txt` whose text has no heading and opens with a sentence of prose
- **WHEN** it is uploaded
- **THEN** the resulting source's frontmatter `title` is derived from the name `release-notes`
- **AND** its `description` is drawn from the text's opening prose rather than left empty

### Requirement: Bound uploads and leave nothing behind on failure
Upload MUST be bounded: one file per call, a size ceiling, and a refusal that names the limit. A conversion failure MUST leave nothing behind — no source and no file in the collection's `.inbox/`.

#### Scenario: a document is never stored half-converted
- **GIVEN** a document whose converter succeeds but yields no text, as an image-only PDF does
- **WHEN** it is uploaded
- **THEN** the upload is refused with the reason naming the document type, and nothing is written — no source

### Requirement: Let only a person delete a document
Deleting a document through Coffer MUST be a person's action, and it MUST be allowed for **any** document in a collection Coffer keeps, whoever wrote it: the tree is the person's as much as an agent's. A linked folder's files are not Coffer's to delete, and the route refuses them (see "Leave a linked folder to its own tools"). The REST route and the web UI MUST offer it, and each deletion through them MUST record a `knowledge_deleted` audit event. A person may equally delete the file itself in the collection's directory under the knowledge root, and the deletion is live on the next read and the next catalogue (see "Treat a direct file edit as a complete change"). Coffer offers no tool that deletes anything.

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
The knowledge layer MUST NOT add any table to Coffer's databases, and MUST NOT create a directory or a record of its own outside the knowledge root. A collection Coffer keeps is a resource file, `resources/knowledge/<name>.json` in the vault, like every other Resource. A linked folder is the same resource file filed in the machine-local class, under `~/.coffer/local/resources/knowledge/`, because the folder's path is true of this machine only ([vault-storage](../vault-storage/spec.md) "Store state in five classes by nature"); Coffer MUST create nothing inside a linked folder. Everything else this layer holds is a file the human can open.

#### Scenario: a collection is a resource file and a directory, nothing more
- **GIVEN** a database upgraded to head and a knowledge root under a temporary home
- **WHEN** a collection is created and material is submitted into it
- **THEN** no table in the history database is named for knowledge, and the collection is one resource of kind `knowledge`
- **AND** every file the layer wrote lies under the knowledge root

### Requirement: Serve every collection to every agent
Every collection MUST be named, catalogued and served to **every** agent, a linked folder too, under its own path and with its own rules file (see "Link a folder the person keeps themselves"), and a collection MUST NOT carry the Resource framework's per-agent reach or an enabled switch: the kind declares itself non-toggleable ([resource-framework](../resource-framework/spec.md) "Address every resource by an immutable uid through one kind-agnostic surface"). A collection leaves every agent's delivered skill only by being deleted; for a linked folder that is **Disconnect…**, which leaves its files where they are. A file written under a top-level directory that is not a collection MUST be left alone and MUST NOT be catalogued (see "Adopt a file dropped into the inbox").

#### Scenario: every collection is in every agent's skill
- **GIVEN** two collections, `shopee` and `personal`, both holding documents, one of them stored disabled by an earlier version
- **WHEN** the database is migrated and the guide skill is re-rendered and seeded into its master folder
- **THEN** the master `SKILL.md` names both collections and lists both catalogues
- **AND** a request to disable either collection through the generic resource route is refused and changes nothing

### Requirement: Name a collection by its folder and edit its description in place
A collection MUST carry no title: every surface — the web UI's tree, its pickers and its collection view, and the command palette — MUST show a collection by its folder name (a linked folder by the name it was linked under, the folder's own by default), and the collection routes MUST carry no `title` field. A title sent for a collection through the kind-agnostic update MUST be refused as a validation error, with nothing changed. What a collection is about MUST be its description, the opening paragraph of its `README.md` (see "Read a collection's description from its README"), and the web UI's collection view MUST show it as text that is edited **in place**: choosing it opens it for editing, leaving the field or pressing ⌘Enter saves it, Esc cancels, and a saved edit reports a toast with **Undo**. A save rewrites exactly that paragraph and leaves the rest of the README as it was, as one change naming the user, audited as an edit of the collection, and re-renders the guide skill; Undo puts the previous paragraph back as a change of its own. The route is `PUT /api/v1/knowledge/collections/{uid}/description`, the web UI's own. An empty description MUST be refused. A linked folder's description is read from its own `README.md` the same way, and is not edited through Coffer (see "Leave a linked folder to its own tools"). Creating a collection in the web UI MUST ask for its name and for what belongs in it, both required. The collection's ⋯ menu in the web UI MUST offer **Rename…**, a dialog with the name field that sends the kind-agnostic update (`PATCH /api/v1/resources/{uid}` with the new `name`); the directory of a collection Coffer keeps MUST move with the name, while a linked folder's rename changes only its label and the folder on disk keeps its name; the page MUST stay on the same collection, whose address carries its uid. A refused name — taken by another collection or a folder already there, or not a valid folder name — MUST be shown under the field with the dialog still open and nothing changed.

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
An agent, another machine or an older guide MAY leave a Markdown file at `<collection>/.inbox/<any-name>.md`, with optional frontmatter. The sweep MUST recognise a new inbox file that no Coffer surface wrote, **normalise** it, and keep it as a source (see "Promote submitted material at once"):

- `title` is kept, else the first `# ` heading, else the file name's stem;
- `description` is kept, else the first prose paragraph, else the title — the same fallback an upload uses (see "Fill frontmatter on converted material");
- `actor` is kept as written (it is self-reported), else `agent`;
- `created_at` and `updated_at` are kept, else the time the sweep saw the file;
- every other key a writer set is kept.

Coffer MUST record one `knowledge_written` audit event per file, carrying `actor_reported: true` when the actor came from the file. A Markdown file in a top-level directory that is not a collection MUST be left alone and MUST NOT be catalogued: only a person creates a collection (see "Create collections only deliberately"). A non-Markdown file in an inbox MUST be left in place, logged, and not adopted.

#### Scenario: a bare inbox file is normalised and audited
- **GIVEN** a `shopee` collection, and a file `shopee/.inbox/cache-ttl.md` holding a `# Cache TTL` heading, a paragraph and no frontmatter
- **WHEN** the sweep runs
- **THEN** the resulting source's frontmatter carries `title` `Cache TTL`, a `description` drawn from the paragraph, `actor` `agent`, and `created_at` and `updated_at` set to when the sweep saw it, with the body unchanged
- **AND** one `knowledge_written` audit event is recorded with `actor_reported` false, and the file is no longer in `.inbox/`

#### Scenario: keys a writer set are kept
- **GIVEN** an inbox file whose frontmatter sets `actor` `user`, a `title`, and a `source` key
- **WHEN** the sweep adopts it
- **THEN** the title, the actor and the `source` key are as written on the resulting source, and the audit event records `actor_reported: true`

#### Scenario: a file outside a collection or that is not Markdown is not material
- **GIVEN** a Markdown file at `notes/.inbox/idea.md`, where `notes` is not a collection, and a `shopee/.inbox/data.bin` file
- **WHEN** the sweep runs
- **THEN** the first is left alone and appears in no catalogue, no `notes` collection is created, and the second stays in the inbox, is logged, and is not adopted

### Requirement: Expose no knowledge tool
Coffer's MCP gateway MUST expose **no** tool that reads, lists, searches, writes or deletes knowledge. An agent reads knowledge with its own file tools at the paths the `coffer-guide` skill gives it and adds to it by writing files into the collection's documents (see "Teach writing and tidying in the guide").

#### Scenario: no knowledge tool appears in the client tool list
- **GIVEN** a real daemon with an upstream MCP server registered, driven over its `/mcp` endpoint by the MCP SDK so the SDK's own models validate every frame
- **WHEN** the client initializes and calls `tools/list`
- **THEN** `coffer__search_tools` is in the listing beside the upstream server's own tools, and `coffer__write`, `coffer__list`, `coffer__grep`, `coffer__read`, `coffer__search` and `coffer__delete` are **absent**

### Requirement: Teach writing and tidying in the guide
The `coffer-guide` skill MUST teach the agent that reads it to do the judgement Coffer does not do for it. Its knowledge sections MUST describe the layout — the README as the schema whose page types and conventions win over the guide's defaults, kept `sources/` and edited `pages/` — and carry **Writing a page** — put a durable fact straight into the collection's pages with the agent's own file tools, by these rules: find the fact's home (fold it into the page that owns the subject, and create a page under `pages/` only when none does), lose nothing, organise by subject and never by provenance, let the newer statement win unless the older one is shown to be right while keeping the superseded one legible, link other pages by `[[slug]]` and never by path, keep links whole when renaming a page (update the links to it, or keep its old slug in `aliases`), never edit a source except to mark it `ingest: skipped`, and give every page frontmatter with a `title`, a `type` (by default one of `concept`, `entity`, `how-to`, `decision` and `overview`), a `description` saying what question the page answers, the `sources` it draws on, any `aliases`, when it was last checked against its sources or the code as `verified: YYYY-MM-DD`, and `actor: agent`; where a page's facts came from belongs in `sources` and `verified`, never in a paragraph of the body listing what was read; **Integrating sources** — read each waiting source in full, fold what it says into the pages that own its subjects, create pages for subjects with none, add the source's slug to each such page's `sources`, and mark a source with nothing worth keeping `ingest: skipped`; and **Tidying a collection** — one collection at a time: run `coffer knowledge tidy-start <collection>` before changing anything, integrate its waiting sources, fix the mechanical findings the prompt lists or `coffer knowledge check <collection>` prints, read the README and the pages, merge pages that answer the same question, split one that answers several, correct what is wrong, stale or contradictory, give a subject mentioned across pages but owned by none a page of its own, leave alone what it is not sure about — two pages that disagree with nothing to tell which is right, a deletion of much text, a change to the README's page types — and list it in its report, then run `coffer knowledge tidy-finish <collection> --set summary="<report>"` with a report of the sources integrated or skipped, what was merged, split, corrected and deleted, and what is left for the developer to decide; asked only for a check or a review, it reports what it would do and changes nothing. There MUST be no separate checking section. The skill's resident description MUST name writing, tidying and checking knowledge, so an agent asked to organise knowledge (整理知识) recognises the skill. These sections MUST be present only while the `knowledge` feature is on.

#### Scenario: the rendered guide carries the writing and tidying sections
- **GIVEN** a vault with one collection and the `knowledge` feature on
- **WHEN** the guide skill is rendered
- **THEN** its body carries "Writing a page", "Integrating sources" and "Tidying a collection" sections and no "Checking a collection" section
- **AND** its frontmatter description names writing, tidying and checking knowledge

#### Scenario: the writing section states the six rules
- **GIVEN** the rendered guide body
- **WHEN** the "Writing a page" section is read
- **THEN** it tells the agent to fold a fact into the page that owns its subject, to lose nothing, to organise by subject and never by provenance, that the newer statement wins unless the older is shown to be right, to link pages by `[[slug]]` and never by path and keep links whole on a rename, never to edit a source, and to give every page a title, a type, a description, its sources, any aliases, a `verified` date and `actor: agent`

#### Scenario: the writing and tidying sections are absent while knowledge is off
- **GIVEN** the `knowledge` feature switched off
- **WHEN** the guide skill is rendered
- **THEN** none of "Writing a page", "Integrating sources" and "Tidying a collection" appears in the body, and the description does not name tidying knowledge

### Requirement: Hand a tidy to the agent
Tidy MUST be the one hand-off of a collection's maintenance: there is no separate report-only check. A collection's read MUST carry `tidy_handoff`: a prompt the daemon writes, from the same hand-off module every other hand-off uses, that names the collection, gives its absolute path, its page count, its waiting-source count and its mechanical findings (see "Check a collection mechanically on every read") — at most 40 lines, then how many were left out — and tells the agent, by the `coffer-guide` sections "Integrating sources" and "Tidying a collection", to run `coffer knowledge tidy-start <collection>` before changing anything, to integrate the waiting sources, then fix the mechanical findings, then merge, split and correct the pages, to leave alone anything it is not sure about and list it in its report, and to finish with `coffer knowledge tidy-finish <collection>` carrying that report (see "Record a tidy as one change"). `GET /api/v1/knowledge/tidy-handoff` MUST return the same kind of prompt for every collection at once: it asks the agent to work through the collections one at a time by those two sections and the same steps, tells it to read each collection's findings with `coffer knowledge check <collection>`, and carries the knowledge root's absolute path and one fact line per collection with its name, absolute path, page count, waiting-source count and finding count. The web UI MUST offer a **Tidy** button on a collection's page and a **Tidy all** button in the Knowledge page's header, which uses that route. Pressing either MUST start the hand-off agent in the person's preferred terminal with that prompt sent at once, as [web-ui](../web-ui/spec.md) "Hand a machine-dependent problem to an agent with one split button" says, and leave the page where it is. When no managed agent is available the button MUST offer **Copy prompt** only. Nothing MUST tidy unattended: Coffer starts no agent run of its own, and a collection is tidied only when a person presses Tidy or asks their own agent to.

#### Scenario: a collection read carries its tidy hand-off
- **GIVEN** a `shopee` collection holding pages and a waiting source
- **WHEN** the collection is read
- **THEN** its `tidy_handoff` prompt names `shopee`, carries the collection's absolute path under the knowledge root and its one waiting source, and names the "Integrating sources" and "Tidying a collection" sections of `coffer-guide`

#### Scenario: the tidy hand-off carries the findings and the tidy commands
- **GIVEN** a `shopee` collection with a page holding a dead link
- **WHEN** the collection is read
- **THEN** its `tidy_handoff` prompt carries the collection's absolute path and the dead link with its page and target, and names `coffer knowledge tidy-start <collection>` and `coffer knowledge tidy-finish <collection>`
- **AND** the read carries no `check_handoff`

#### Scenario: the knowledge tidy-all hand-off names every collection
- **GIVEN** two collections, `shopee` with three pages and `personal` with one
- **WHEN** `GET /api/v1/knowledge/tidy-handoff` is read
- **THEN** the prompt names the "Integrating sources" and "Tidying a collection" sections of `coffer-guide` and asks for the collections to be worked through one at a time
- **AND** it carries the knowledge root's absolute path and one fact line each for `shopee` (its path, 3 pages) and `personal` (its path, 1 page), each with its waiting-source and finding counts

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

### Requirement: Sweep the knowledge root on its mechanical duties
The daemon MUST run a **knowledge sweep** on a recurring timer, and the sweep MUST do exactly these things and call no model: adopt every file sitting in a collection's `.inbox/` as a source (see "Adopt a file dropped into the inbox"); file every Markdown document left in a collection outside `pages/`, `sources/` and hidden entries, other than the root `README.md`, and untouched for a minute, into `pages/` at the same relative path, suffixed on a collision, as one commit by the daemon that rewrites no content; commit every change found on disk under `knowledge/` as an edit on disk, so a person's editor or an agent's file tools is never counted as Coffer's (see "Commit every knowledge write naming its writer"), except in a collection an agent is tidying, whose edits wait for the tidy to close (see "Record a tidy as one change"); close every tidy whose collection has sat unchanged for 30 minutes; and re-render and re-seed the `coffer-guide` skill so a page added by hand is catalogued. The sweep MUST NOT hold the vault against a sync round: whatever it writes goes through the vault's ordinary writer. While the `knowledge` feature is switched off the sweep MUST skip its rounds ([experimental-features](../experimental-features/spec.md) "Close the knowledge feature's surfaces").

#### Scenario: a sweep catalogues a document added by hand
- **GIVEN** a collection and a Markdown page a person adds under its `pages/` in their own editor
- **WHEN** the knowledge sweep runs
- **THEN** the page is committed as an edit on disk and the re-rendered guide's catalogue lists it

#### Scenario: a sweep promotes a file dropped into the inbox
- **GIVEN** a Markdown file dropped into `shopee/.inbox/`
- **WHEN** the knowledge sweep runs
- **THEN** the file is a source under `shopee/sources/` and `.inbox/` no longer holds it

#### Scenario: a sweep files a loose document into pages
- **GIVEN** a collection holding `infra/cache.md` and `notes.md` outside `pages/` and `sources/`, both untouched for over a minute, and a `README.md` at its root
- **WHEN** the knowledge sweep runs
- **THEN** they are `pages/infra/cache.md` and `pages/notes.md` with their text unchanged, moved in one commit by the daemon, and the README has not moved

#### Scenario: a sweep runs while a sync round waits
- **GIVEN** a sync round that waits for a person and a file in an inbox
- **WHEN** the knowledge sweep runs
- **THEN** it does not wait for the round, and the file is adopted through the vault's ordinary writer

#### Scenario: a switched-off knowledge feature skips the sweep
- **GIVEN** the `knowledge` feature switched off and a file in an inbox
- **WHEN** the sweep's timer fires
- **THEN** nothing is adopted, moved, committed or re-rendered, and the collections stay on disk untouched

### Requirement: Promote submitted material at once
Material MUST NOT wait to be stored. A submission Coffer receives — an upload — MUST become a source on the spot, under `sources/`, with the frontmatter of "Carry title, description and actor in frontmatter" filled from its opening prose, named from its title (see "Use the file path as a document's identity"), and committed naming whoever submitted it. A file adopted from `.inbox/` becomes a source the same way. Whenever material is submitted or a sweep adopts or files a file, Coffer MUST announce the collection on the daemon's event stream as a `knowledge` event carrying the collection's uid, because the files change without any write to the collection's row ([resource-framework](../resource-framework/spec.md) "Announce every change on one daemon-wide event stream"). Every entrance Coffer serves submits through this one operation. Coffer merges nothing into a page: compiling a source into pages is the agent's work when the person presses Tidy (see "Hand a tidy to the agent"), and until then the source waits.

#### Scenario: an upload becomes a document at the collection root
- **GIVEN** a `shopee` collection
- **WHEN** a Markdown file is uploaded to it
- **THEN** the collection holds one new source under `shopee/sources/` whose body is the uploaded text, whose frontmatter carries a title, a description drawn from its opening prose and `actor` `user`, and whose commit names the user
- **AND** nothing is left in `shopee/.inbox/`, and the source is waiting

#### Scenario: an upload answers with the document it became
- **GIVEN** a `shopee` collection
- **WHEN** a document is uploaded once through `POST /api/v1/knowledge/upload`
- **THEN** the answer carries the new source's path and no `pending` field, and the source is in the collection's visible tree

#### Scenario: submitting material announces the collection on the event stream
- **GIVEN** a `shopee` collection and a client reading the event stream
- **WHEN** a document is uploaded to it
- **THEN** a `knowledge` event naming the collection's uid is announced

### Requirement: Treat a direct file edit as a complete change
Writing, editing or deleting a page directly in the collection's tree — by a person in their own editor, or by an agent with its own file tools — MUST remain a complete way to change knowledge: no import, no registration, no conversion step, and the change is live on the very next read. The change MUST be committed to the vault as an edit found on disk, by the sweep or by the next Coffer write, whichever comes first (see "Sweep the knowledge root on its mechanical duties"), unless an agent has a tidy of that collection open: then it is committed with the rest of the tidy when the tidy closes (see "Record a tidy as one change"). Ingestion is an additional entrance, never a required one.

#### Scenario: an agent's new document is live at once and committed as a disk edit
- **GIVEN** a `shopee` collection and an agent that writes a Markdown page into its `pages/` with its own file tools
- **WHEN** the page is read before any sweep, and the knowledge sweep then runs
- **THEN** the read returns the agent's text with no import step in between
- **AND** the sweep commits the page as an edit found on disk

### Requirement: Follow edits across collections in one feed
The system MUST serve one feed of the recent changes to knowledge across every collection, newest first, paged by an opaque cursor ([resource-framework](../resource-framework/spec.md) "Page growing lists by an opaque cursor") and filterable to one collection: every page or source a person or an agent wrote, restored, filed or deleted, every tidy, and every change from sync or from disk — each with its writer, its operation, its summary, its time, its collection and, for each file it touched, whether that file was added, changed or removed and how many lines were added and removed. A tidy is listed as one change whose operation is `tidy`, whose summary is the agent's report and whose `status` is `reported`, or `expired` when Coffer closed it (see "Record a tidy as one change"); an Undo carries the version it undid in `undoes`. A change an earlier version of Coffer made as a curation pass is listed with its writer. One change MUST be readable in full — every file it touched with its diff. The feed is `GET /api/v1/knowledge/changes`, the route a delete's Undo reads to find the delete it restores (see "Undo a knowledge delete from its toast") and the one a collection page's **Change log** reads (see "Show a collection as one tree of read-only documents in the web UI").

#### Scenario: recent changes lists edits across collections
- **GIVEN** a person's upload in one collection and an agent's edit on disk in another
- **WHEN** the feed is read, and read again filtered to one collection
- **THEN** both changes are listed newest first with their collections, writers and per-file line counts
- **AND** the filtered read holds only that collection's changes, and one change read in full carries each file's diff

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
Deleting a file or a whole collection MUST keep what it removed in the vault's history, so the delete's toast can undo it. Undo MUST find the delete in the changes feed (see "Follow edits across collections in one feed") and restore exactly what it removed, as it was just before it: a file into its collection; a collection as a new collection of the same name with its pages, its sources and its `README.md`. A collection restore MUST write every file first and register the collection's row last, so a failure part-way leaves no row and no partial directory: what was written is removed again and the same restore can be tried afresh. The restore MUST be one new change naming the user, carrying the version of the delete it restored, and recorded as a `knowledge_edited` audit event; the delete itself stays in the history. A restore MUST be refused with nothing written when it would overwrite — a file at the same path, `409 KNOWLEDGE_RESTORE_CONFLICT` naming it, or a collection of the same name, `409 KNOWLEDGE_COLLECTION_EXISTS` — and a change that is not a delete MUST be refused with `400 KNOWLEDGE_NOT_A_DELETE`. The route is `POST /api/v1/knowledge/changes/{version}/restore`, the web UI's own. After the toast is gone the deleted file has no pane to open its history from; its versions stay in the vault's history, where git reads them.

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

### Requirement: Commit every knowledge write naming its writer
Every accepted write to a collection MUST be a git commit naming its writer ([Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer](../../../docs/decisions/every-vault-write-is-a-validated-commit-naming-its-writer.md)). The commits are the vault repository's, under `knowledge/`: the knowledge root keeps no repository of its own. A person's upload, description edit, delete, Undo of a delete or Undo of a tidy names the user; material kept on arrival names whoever submitted it — the user, or, for a file an agent dropped into the inbox, the actor the file reports; a tidy names the agent (see "Record a tidy as one change"); a loose document the sweep files into `pages/` names the daemon; a change that arrives through vault sync names sync; and a change any other writer made in the tree — a person's own editor, an agent's file tools outside a tidy — MUST be committed as an edit on disk before Coffer's next commit, so it is never counted as Coffer's. A commit an earlier version of Coffer made as a curation pass stays in the history under its writer. A file's history is read, and an earlier version restored as a new commit, in its history drawer ([vault-storage](../vault-storage/spec.md) "Show and restore any version of a vault file or folder"). The vault is a git repository on every machine that runs Coffer ([vault-storage](../vault-storage/spec.md) "Keep the vault a git repository whether or not it syncs"); a read of the changes feed git cannot answer MUST answer 503 `KNOWLEDGE_HISTORY_UNAVAILABLE` while every write keeps working. git is looked for on every read, so one removed while the daemon runs is answered the same way. When the cause is that git is not installed, the refusal's details MUST carry `reason: "git_missing"` and `handoff`, a prompt asking the person's agent to install git on this machine — naming its OS and architecture and what needed git — the way that fits the machine, confirming it with `git --version`; neither the prompt nor the error's message may name an install command.

#### Scenario: knowledge writes are commits naming their writers
- **GIVEN** a source that an upload created for the user, that an agent then edited on disk
- **WHEN** the user then uploads another document and the vault's commits under `knowledge/` are read
- **THEN** the first source's commits name the user and then an edit on disk, and the second upload's commit holds only the new source and names the user

#### Scenario: an edit on disk becomes a commit of its own
- **GIVEN** a page a person edits in their own editor, outside Coffer
- **WHEN** Coffer then makes its next knowledge write
- **THEN** the edited page is committed first as its own edit on disk, and Coffer's commit holds only what Coffer wrote

#### Scenario: no git hands installing it to an agent
- **GIVEN** a machine with no git
- **WHEN** a document is written and the changes feed is then read
- **THEN** the write works and the read is refused `KNOWLEDGE_HISTORY_UNAVAILABLE` with reason `git_missing` and a prompt to install git naming this machine and `git --version`, and neither the prompt nor the message names an install command

### Requirement: Manage knowledge in the web UI and on the command line
People MUST manage knowledge in the web UI, and agents with the `coffer knowledge` commands: creating collections, linking a folder the person keeps themselves (see "Link a folder the person keeps themselves"), uploading sources, reading pages and sources and opening them in their editor, reading a file's history and restoring an earlier version, checking a collection, listing its contents, tidying a collection through their agent and undoing a tidy, deleting and undoing a delete, and editing a collection's description. The REST routes under `/api/v1/knowledge` behind those pages serve the web UI and the `coffer knowledge` commands, which call the same routes ([resource-framework](../resource-framework/spec.md) "Offer every management operation on the command line"): a route the web UI does not call MUST NOT exist, except the two a tidying agent calls to open and close its tidy, and there MUST be no route that creates or saves a page at a path — a person's text reaches knowledge through their own editor (see "Treat a direct file edit as a complete change") or as material like every other entrance (see "Promote submitted material at once"). There MUST be no route under `/api/v1/knowledge` that lists a file's versions, diffs a version or restores one: a file's history is read and restored through the vault's routes ([vault-storage](../vault-storage/spec.md) "Show and restore any version of a vault file or folder") in its history drawer. There MUST be no index, reindex, check-sources, update-source or embedding-configuration endpoint, no curate or undo-pass endpoint, no route that fixes a finding, no settings endpoint for the cwd-derived scope axis "Derive no boundary from the working directory" forbids, and no per-agent reach endpoint or enabled switch for this kind (see "Serve every collection to every agent"). Collection deletion goes through the Resource framework (`DELETE /api/v1/resources/{uid}`). The `coffer knowledge` commands MUST list, create, link, describe and delete collections, read a level of the tree, a collection's check, its contents and the changes feed, upload material, undo a delete, open and finish a tidy (`tidy-start`, `tidy-finish`), undo a tidy (`undo`) and print the tidy hand-off; no command reads, writes or deletes a file's content, and there is no `coffer path` target for knowledge: a collection's files are plain files, so agents and people read, edit and delete them directly under the knowledge root that the `coffer-guide` skill names (see "Treat a direct file edit as a complete change").

#### Scenario: knowledge is managed on the command line, its documents as files
- **GIVEN** the `coffer` command tree
- **WHEN** the `knowledge` group is enumerated, and `coffer path` is run with a `knowledge` target
- **THEN** the group offers collections, create, describe, delete, tree, check, files, changes, restore, undo, tidy-start, tidy-finish and upload, and no command reads, writes or deletes a file
- **AND** `coffer path` refuses `knowledge` as an unknown target

#### Scenario: the routes are the web UI's, with no material or create-at-path route
- **GIVEN** the daemon's route table under `/api/v1/knowledge`
- **WHEN** it is enumerated
- **THEN** it offers create a collection, link a folder, list a level, read, upload, delete a file, check a collection, list a collection's files, the changes feed, restoring a delete, undoing a change, starting and finishing a tidy, rewrite a description, and the tidy-all hand-off
- **AND** it carries no route that saves a file, no history, version or version-restore route, no `/material` route, no curate route, no route that fixes a finding, no route that creates a file at a path, and no index, reindex, source, embedding, scope or reach endpoint

### Requirement: Keep sources and pages apart in each collection
Every collection MUST hold its knowledge in two places: `sources/`, the material that arrived — each upload and each file dropped into the inbox — kept as it came; and `pages/`, the wiki pages people and agents write from it. A Markdown file under `pages/` is a **page**, a Markdown file under `sources/` is a **source**, and any other file is a plain file that is listed but neither catalogued nor checked. The collection's `README.md` is its schema: what belongs in the collection, its page types and its conventions. Agents MUST be told never to edit a source (see "Teach writing and tidying in the guide").

#### Scenario: a collection keeps sources and pages apart
- **GIVEN** a `shopee` collection into which a file is uploaded and in which an agent writes a page
- **WHEN** the collection's tree and its catalogue are read
- **THEN** the upload is a source under `shopee/sources/` and the agent's page is under `shopee/pages/`
- **AND** the catalogue lists the page among the pages and the source among the sources, each read with the kind it has

### Requirement: Keep every upload as a Markdown source
An upload MUST be converted to Markdown and kept as a **source**: `sources/<slug>.md` carrying the extracted Markdown with frontmatter. Only the Markdown is kept: the uploaded file itself MUST NOT be stored, so the collection stays one tree of Markdown that every agent can read and the sync repository carries no binaries. Supported inputs MUST be exactly what the converters accept: what `markitdown` handles (PDF, `docx`, `pptx`, `xlsx`, `xls`, HTML, EPUB), CSV, and text read as it stands (Markdown, plain text, reStructuredText, and source and configuration files such as `py`, `ts`, `sql`, `yaml`, `json`, `log`); an unsupported type MUST be refused with the type named, and nothing is written. An upload takes no folder. A name collision suffixes the source's name.

#### Scenario: an upload is kept as a Markdown source
- **GIVEN** a collection and a `team.csv` file
- **WHEN** it is uploaded through `POST /api/v1/knowledge/upload`
- **THEN** the answer is 201 and carries the source's path, the converter that ran, the title and a description
- **AND** the collection holds `sources/team.md` with the extracted Markdown and frontmatter `actor: user`, and no other new file — the uploaded `team.csv` is not stored

#### Scenario: an upload of an unsupported type is refused with its reason
- **GIVEN** a collection, and a file whose type no converter handles — `archive.bin` at the service, `payload.exe` at the route
- **WHEN** it is uploaded
- **THEN** the service raises `UnsupportedDocument` and the route answers 400 `INGEST_REJECTED` whose details name `reason` `unsupported_type` and `doc_type` `exe`, and the collection is left with no new file at all

### Requirement: Link pages by slug and check every link
A page's **slug** is its file name without `.md`; its `aliases` frontmatter list gives it more names. A link in a page's body MUST be written `[[target]]` or `[[target|text]]`, outside code, and MUST name a slug or an alias, never a path. Coffer MUST resolve every link when a page is read, against every page's slug and aliases and every source's slug, case-insensitively: a link that names nothing is **dead**, and one that names more than one file is **ambiguous**. A page's read MUST carry each link with the path it resolves to, or none, so the web UI can follow it; a page's `sources` entries MUST be resolved against source slugs the same way.

#### Scenario: a page's links resolve by slug and alias
- **GIVEN** pages `session-ownership` with alias `sessions` and `cache-ttl`, and a page whose body links `[[session-ownership]]`, `[[sessions|the session service]]`, `[[cache-ttl]]` and `[[gone]]`
- **WHEN** that page is read
- **THEN** the first two links resolve to `pages/session-ownership.md`, the third to `pages/cache-ttl.md`, and `gone` resolves to nothing
- **AND** a `[[gone]]` inside a fenced code block is not counted as a link

### Requirement: Derive which sources wait from the pages that cite them
A page MUST name the sources it draws on in its `sources` frontmatter list, by slug. A source **waits** while no page cites it and its frontmatter does not set `ingest: skipped`; Coffer MUST keep no other record of which sources were integrated. A source's read MUST carry the pages that cite it and whether it waits, and a tree listing MUST mark each waiting source.

#### Scenario: a source waits until a page cites it or it is skipped
- **GIVEN** three sources, `a`, `b` and `c`, a page whose `sources` lists `a`, and `c` marked `ingest: skipped`
- **WHEN** the collection is checked and `a` and `b` are read
- **THEN** only `b` is waiting, `a` names the page that cites it, and the collection reports one waiting source

### Requirement: Check a collection mechanically on every read
Coffer MUST compute a collection's **findings** from its files on every read, keep none of them, and fix none of them: `dead_link` and `ambiguous_link` for each such link, with the page and the target; `duplicate_slug` for a slug or alias two pages share; `orphan_page` for a page no other page links to, when the collection holds two or more pages, except a page whose `type` is `overview`; `incomplete_page` for a page missing `title`, `type` or `description`; `unsourced_page` for a page with no `sources`; `missing_source` for a `sources` entry that names no source; and `waiting_source` for each waiting source (see "Derive which sources wait from the pages that cite them"). The route is `GET /api/v1/knowledge/collections/{uid}/check`, and the collection listing MUST carry its page, source, waiting-source and finding counts.

#### Scenario: a collection's check lists its mechanical findings
- **GIVEN** a collection holding a page with a dead link and no `type`, a second page nothing links to, a page citing a source that does not exist, and a waiting source
- **WHEN** `GET /api/v1/knowledge/collections/{uid}/check` is read
- **THEN** it lists a `dead_link`, an `incomplete_page`, an `orphan_page`, a `missing_source` and a `waiting_source` naming those files
- **AND** no file in the collection changed, and the collection listing carries the same finding count

### Requirement: Merge the manual and the catalogue in the skill body
The skill's **body** MUST be one merged manual: Coffer's own — its one built-in tool, `coffer__search_tools`, and when to reach for it; the tiering contract that makes an unlisted upstream tool still callable; the knowledge root; that Coffer's own logs are read with `coffer log` and located with `coffer path logs`; that a skill's scripts keep their logs, operation journals and temp files under `~/.coffer/skill-data/<skill-name>/` (found with `coffer path skill-data`), never in the skill's own folder or elsewhere in `~/.coffer`, and that files there are deleted after the Skill working files retention window, so durable data does not belong there; that `coffer cli list` lists the command-line tools Coffer manages, what each is for and whether it is ready on this machine; that no Coffer tool waits on a human approval; and what does not belong in knowledge — **followed by** the catalogue: the path of the knowledge root, and, for each collection, its README's path, its pages grouped by `type` with each page's collection-relative path, title and description, and its waiting sources with their paths and titles. A linked folder's section MUST instead say that it is a folder the developer keeps with their own tools which Coffer only shares, give its path with the home folder written as `~`, tell the agent to follow the folder's own rules file (`AGENTS.md`, `CLAUDE.md` or `README.md`, the first present at its root) before writing anything in it, or with none to write only the way its notes are already written, say that Coffer's `pages/`, `sources/`, inbox and tidy do not apply there, and list its Markdown notes with their folder-relative paths and titles; the catalogue MUST say that a linked folder is read at its own path, not under the knowledge root. When the catalogue would exceed its budget it MUST first drop the descriptions, and then list only each collection's counts and the directories to search (a linked folder's note count), saying that it was shortened. It MUST instruct the agent to read those files with its own tools, to grep `sources/` for an exact fact a page does not carry, to write what it learns that is durable straight into the collection's pages, and to integrate, tidy and check a collection when asked (see "Teach writing and tidying in the guide"); a change to a page is carried by the sweep into the vault's history (see "Treat a direct file edit as a complete change"). The manual MUST name no memory directory: an agent reaches memory through its own native memory ([memory](../memory/spec.md) "Deliver no memory into a session"). One skill, not a set: a frontmatter description is resident in every session whether the skill is opened or not, while a body is paid for only when a model reaches for it, so a second skill would spend the resident budget again to describe something most sessions never open.

#### Scenario: the skill body carries the catalogue and the absolute root
- **GIVEN** a collection holding three pages of two types and one waiting source
- **WHEN** the skill is rendered
- **THEN** its body carries each page's collection-relative path, title and description under its type, the waiting source's path and title, and the path of the knowledge root, and it instructs the agent to read those files with its own tools
- **AND** the frontmatter `description` names the collection's subject, taken from the collection's own `README.md`, so a model matching on it has something to match

#### Scenario: a catalogue past its budget shortens itself
- **GIVEN** collections whose full catalogue exceeds the budget
- **WHEN** the skill is rendered
- **THEN** the catalogue lists pages without their descriptions, or, past the budget again, each collection's counts and its `pages/` and `sources/` directories, and says the catalogue was shortened and to search those directories

#### Scenario: name one tool, the knowledge root and the log reader in the manual
- **GIVEN** a vault with one collection
- **WHEN** the skill is rendered
- **THEN** its manual names exactly one built-in tool, `coffer__search_tools`, and names none of `coffer__write`, `coffer__recall` and `coffer__diagnose`
- **AND** it names the knowledge root and no memory directory, tells the agent to write durable knowledge into a collection's pages itself, and names `coffer log` and `coffer path logs` as the way to read Coffer's own logs, and `coffer cli list` as the way to learn which command-line tools Coffer manages

#### Scenario: the manual says where a skill's scripts keep their files
- **GIVEN** a vault with one collection
- **WHEN** the skill is rendered, with or without the knowledge and memory features on
- **THEN** its manual says a skill's scripts write their logs, operation journals and temp files under `~/.coffer/skill-data/<skill-name>/`, found with `coffer path skill-data`
- **AND** it says never to write them inside the skill's own folder, that files there are deleted after the Skill working files retention window, and that durable data does not belong there

### Requirement: Show a collection as one tree of read-only documents in the web UI
The web UI MUST present a collection as **one tree** of its files — no lanes, no filter or retrieval box — with the chosen file in the pane beside it, the same two panes a skill's Files tab is. At a collection's root the tree MUST show its two folders first, labelled **Pages** and **Sources**, then any other entry; each page MUST carry its type's icon and a source the source icon (see "Show a collection's contents by page type"), and a waiting source MUST carry a **Waiting** mark. The tree MUST name every collection, folder and file by its name on disk otherwise: a collection has no title (see "Name a collection by its folder and edit its description in place"). Its **Collections** header strip MUST carry **New collection** (a name and what belongs in it; the collection reaches every agent through the coffer-guide skill). A linked folder MUST carry the linked-folder icon in the tree. The tree MUST show no hidden entry, and no collection or folder carries a count. The tree MUST come back as the person left it: which collections and folders they opened or closed is kept in the browser, so leaving the page, reloading it or opening it again restores them, and what is on screen is open on the way to it unless they closed it. Knowledge calls its files **pages** and **sources** everywhere.

A file's pane MUST carry no tabs. Its bar MUST name where the file is, then **History** (opening the file's history over the whole Knowledge area, `?history=1` in the address, with the file's versions in the vault, their diffs and **Restore this version…**, [web-ui](../web-ui/spec.md) "Show a vault file's history on a History tab"), a **Preview / Source** switch, **Open in editor** as a visible button, and a ⋯ menu holding **Reveal in Finder**, **Open in Obsidian** when it is installed (see "Open a collection in Obsidian when it is installed") and **Delete**. While the history is open the tree and the file MUST make way for it, so the versions and the diff have the area to themselves; its ✕ or Esc brings the file back. Under a page's title one line MUST give its type, who wrote it and when it was created, **verified <date>** when the page carries `verified`, and its sources, each opening that source and a missing one marked; a page's `[[links]]` MUST render as links that open the file they resolve to, a dead one marked in the danger tone. Inline code MUST read lighter than a code block, and a long path MUST wrap at its `/`. Under a source's title one line MUST say which pages cite it, or that it is waiting. There is no side column. The pane MUST NOT edit the file: a person changes it in their own editor and an agent with its own file tools (see "Treat a direct file edit as a complete change"), and the next read shows the change.

The page of a collection Coffer keeps MUST show, under a pane bar carrying **Tidy** (see "Hand a tidy to the agent") and a ⋯ menu, its folder name as its heading, its description edited in place (see "Name a collection by its folder and edit its description in place"), and **one summary line** — how many pages, how many sources with how many wait, the folder's path with a copy button, and when it was last updated — then a muted line saying the collection is managed by Coffer: synced to the person's other Macs, its history kept, tidied by their agent. While an agent has a tidy of the collection open (`tidy_running`), the page MUST say that an agent is tidying it and that its edits will appear as one change when it finishes (see "Record a tidy as one change"). Below come three sections. **To do** MUST list the collection's findings (see "Check a collection mechanically on every read") grouped by kind, the most severe kind first, each naming the page by its title, with its path on hover, and opening it; the minor kinds — pages without sources and pages nothing links to — MUST be folded into one collapsed row; with nothing found it is one line saying so. **Contents** lists the collection's pages by type and its sources (see "Show a collection's contents by page type"). **Change log** MUST list the collection's changes newest first — what each did, its writer and time, and the files it touched by title, each opening that file at its history — with a tidy shown as one entry (see "Record a tidy as one change"), and **Show more** while more are left. A collection with no pages and no sources shows the same page with one line saying so and how to fill it — upload a source, or drop Markdown files into the folder — and **Reveal in Finder**. The collection's ⋯ menu MUST hold **Reveal in Finder**, **Open in Obsidian** when it is installed, **Copy path**, **Rename…** and **Delete collection…** (see "Delete a document at once, a collection after asking, and offer Undo"). There is no other hand-off button on the page. A linked folder's page and its files differ from all of this as "Leave a linked folder to its own tools" says.

The page MUST offer no form that adds a file from a typed title and body: people write in their own editor, agents by writing files, and material arrives through the header's **Add** menu (see "Add documents and collections from one Add menu"). With no collection open, the page shows its collections. The tree and the pane MUST extend to the bottom of the window and scroll inside.

The Knowledge page's title MUST carry the **Experimental** tag ([experimental-features](../experimental-features/spec.md)).

#### Scenario: the viewer shows one tree of documents
- **GIVEN** a collection page whose tree holds a page, a page inside a folder and a waiting source
- **WHEN** the page renders and a page's row is clicked
- **THEN** there is one tree — no lane headings, no filter input — showing Pages and Sources first, both pages and the source with its Waiting mark, and no hidden entry
- **AND** the page's pane carries no tabs, offers History, Preview and Source and Open in editor, and Reveal in Finder and Delete in its ⋯ menu

#### Scenario: a document's history takes the whole knowledge area
- **GIVEN** a page open in its collection's pane
- **WHEN** the user presses History
- **THEN** the page's versions open over the whole Knowledge area, the address carries `history=1`, and neither the page nor the tree is shown beside them
- **AND** closing the history brings the page and the tree back and drops `history=1` from the address

#### Scenario: the tree comes back as the person left it
- **GIVEN** a person who opened two collections and one collection's Sources folder
- **WHEN** they leave the Knowledge page and come back
- **THEN** the same collections and the Sources folder are open, and the Pages folder they never opened is closed
- **AND** a collection they then close is still closed when they come back again

#### Scenario: a page shows its sources and resolves its links
- **GIVEN** a page citing an existing source and a missing one, whose body links one page that exists and one that does not
- **WHEN** it is opened in Preview
- **THEN** the line under its title names both sources, the existing one opening it and the missing one marked
- **AND** the existing link opens the page it names, and the dead link is marked in the danger tone

#### Scenario: a document opens in the person's editor
- **GIVEN** a page open in a collection's pane
- **WHEN** the user chooses Open in editor, and then Reveal in Finder from its ⋯ menu
- **THEN** the daemon is asked to open the page's absolute path and then to reveal it
- **AND** the pane shows the page read-only, with Preview and Source, and its line read from the frontmatter

#### Scenario: the collection page shows a summary line, its to-do list, its contents and its change log
- **GIVEN** a collection holding two pages of different types, a page with a dead link and a page with no sources, and a waiting source
- **WHEN** its page renders
- **THEN** it shows the folder name, the description, one summary line reading its page count, its source count with 1 waiting, its folder path with a copy button and when it was updated, and the line saying it is managed by Coffer
- **AND** To do lists the dead link before the waiting source, each naming its page by title, with the page without sources folded into one collapsed row; Contents shows a card per page type and a Sources card; and the Change log lists the collection's changes
- **AND** the pane bar offers Tidy and no Check with agent, and its ⋯ menu offers Reveal in Finder, Copy path, Rename… and Delete collection…

#### Scenario: a collection's change log opens a file at its history
- **GIVEN** a collection whose change log lists an agent's edit of a page
- **WHEN** the user chooses the page in that row
- **THEN** the page opens at its history

### Requirement: Show a collection's contents by page type
`GET /api/v1/knowledge/collections/{uid}/files` (command `coffer knowledge files`) MUST return every page and source of one collection, read off disk on every call, each with its path, title, description, writer, time, kind (`page`, `source` or `file`), a page's `type` and whether a source waits. A collection's page in the web UI MUST show them under **Contents** as one card per page type — `overview`, `concept`, `entity`, `how-to` and `decision` in that order, then the types the collection's README defines by name, then pages with no type — each card with the type's icon, how many pages it holds and the first few page titles, each opening its page, then how many more; and a **Sources** card listing the sources the same way, a waiting one marked. The tree MUST mark each page with the same icon as its type's card, a page whose type has no icon of its own a generic page icon and an untyped page an untyped icon; a source carries the source icon, and a waiting source keeps its **Waiting** mark.

#### Scenario: a collection lists its pages and sources with their types
- **GIVEN** a `shopee` collection holding a page of type `concept` and a waiting source
- **WHEN** `GET /api/v1/knowledge/collections/{uid}/files` is read
- **THEN** it lists the page with kind `page` and type `concept`, and the source with kind `source`, marked waiting

#### Scenario: the tree marks each page with its type's icon
- **GIVEN** a collection holding an `overview` page, a page of a type the README defines, a page with no type and a waiting source
- **WHEN** the collection is opened in the tree
- **THEN** the overview page carries the overview icon, the custom-typed page the generic page icon, the untyped page the untyped icon, and the source the source icon with its Waiting mark

### Requirement: Record a tidy as one change
A tidy MUST land in a collection's history as **one** change. The agent the Tidy prompt starts opens a tidy with `POST /api/v1/knowledge/collections/{uid}/tidy/start` (`coffer knowledge tidy-start <collection>`) before it changes anything, and closes it with `POST /api/v1/knowledge/collections/{uid}/tidy/finish` (`coffer knowledge tidy-finish <collection>`) whose body carries its report as `summary`. Opening a tidy MUST first commit whatever already changed in the collection as the edit on disk it is, and starting an open tidy again keeps it. While a tidy is open the collection's edits MUST stay uncommitted in the working tree: the vault's scanner, the knowledge sweep and a sync round leave them alone, and a sync round whose incoming changes touch one of those files waits, as it does for any uncommitted edit ([vault-storage](../vault-storage/spec.md) "Keep the last valid version when a hand edit is invalid"). Finishing MUST commit every one of them as one commit by the `agent` writer whose operation is `tidy`, whose summary is the report and whose status is `reported`, and answer that change; a tidy that changed nothing commits nothing and answers `change: null`. Finishing with no tidy open MUST still commit the collection's uncommitted edits as a tidy. The sweep MUST close a tidy whose collection has sat unchanged for 30 minutes, committing what it changed with no report and status `expired`, so no collection stays paused. Which tidies are open lives in the daemon's memory only: a restart forgets an open tidy, and its edits are then committed as ordinary edits on disk. A collection's read MUST carry `tidy_running`. Starting and finishing a tidy are each audited as a `knowledge_edited` event.

A collection page's **Change log** MUST show a tidy as one entry: the agent, the time, its report — or that it was closed without a report — the files it touched by title, collapsed when there are many, and **Undo this tidy…** (see "Undo a tidy"). Edits on disk outside a tidy that follow each other within 10 minutes MUST show as one entry listing their files.

#### Scenario: a tidy's edits land as one change with its report
- **GIVEN** a `shopee` collection holding a committed page
- **WHEN** an agent starts a tidy, edits that page and writes a new one, the vault settles, and the agent finishes the tidy with a report
- **THEN** while the tidy was open the collection read `tidy_running` and neither edit was committed
- **AND** finishing answers one change by the `agent` writer, operation `tidy`, status `reported`, the report as its summary, holding both pages, which is the newest entry of the collection's feed, and the collection no longer reads `tidy_running`

#### Scenario: a tidy shows in the change log as one entry with its report and Undo
- **GIVEN** a collection whose feed holds a tidy that touched three pages, an expired tidy, and two edits on disk five minutes apart
- **WHEN** its page renders
- **THEN** the Change log shows the tidy as one entry naming the agent, its time, its report, its three pages by title and Undo this tidy…
- **AND** the expired tidy reads closed without a report, and the two edits on disk are one entry listing both files

### Requirement: Undo a tidy
`POST /api/v1/knowledge/changes/{version}/undo` (`coffer knowledge undo <version>`) MUST put every file the change touched back as it was just before it: a file the change edited or removed gets its earlier bytes back, and a file it added is removed. The undo MUST be one new commit by the user, operation `restore`, carrying in `undoes` the version it undid, and recorded as a `knowledge_edited` audit event naming the files and any later edits it discarded. When a file has been edited since the change, the undo MUST be refused with `409 KNOWLEDGE_UNDO_CONFLICT` whose details list those files in `documents`, and write nothing, unless the body sets `force: true`. A version that changed no knowledge file, or whose files are already as they were before it, MUST be refused with `400 KNOWLEDGE_NOT_A_CHANGE`. The web UI offers it as **Undo this tidy…** on a tidy's Change log entry: a confirmation names the tidy and how many files go back; when files were edited since, it lists them by title and offers **Undo anyway**, which sends `force`.

#### Scenario: undo a tidy
- **GIVEN** a tidy that edited a page and added another
- **WHEN** the tidy is undone
- **THEN** the edited page holds its text from before the tidy and the added page is gone, as one new change by the user with operation `restore` whose `undoes` names the tidy

#### Scenario: undoing a tidy asks before discarding later edits
- **GIVEN** a tidy that edited a page, which a person edited again afterwards
- **WHEN** the tidy is undone
- **THEN** the undo is refused `KNOWLEDGE_UNDO_CONFLICT` naming the page, and the person's edit is still on disk
- **AND** undoing it again with `force` puts the page back as it was before the tidy

#### Scenario: undoing a tidy whose files changed since asks first
- **GIVEN** a tidy in a collection's Change log, one of whose pages was edited after it
- **WHEN** the user chooses Undo this tidy… and confirms
- **THEN** the dialog names the edited page by title and offers Undo anyway, and nothing is undone until the user chooses it
- **AND** choosing Undo anyway sends the undo with `force`, and the Change log shows the undo

### Requirement: Add documents and collections from one Add menu
The Knowledge page's header MUST carry **Tidy all** and one primary **Add** menu button, and no separate Upload button. Each of its items MUST carry a one-line description saying what it keeps in Coffer: **Upload documents…** — converted to Markdown and kept as sources in the collection the person picks, synced with it — **New collection…** — kept in Coffer, synced to the person's other Macs, with history, tidied by their agent — and **Link an external folder…** — the files stay where they are and are only shared with agents; nothing is copied into Coffer, synced or tidied (see "Link a folder the person keeps themselves"). The upload dialog MUST offer only the collections Coffer keeps, never a linked folder. Upload MUST accept several files at once, picked or dropped, and list each with its own state — waiting, converting, done, or failed with its reason. A file it will refuse — a ZIP archive, or one over 20 MB — MUST be shown as refused, with its reason, before anything is sent. The files MUST be sent one after another, one per call to `POST /api/v1/knowledge/upload` (see "Bound uploads and leave nothing behind on failure"), each succeeding or failing on its own; a failed one MUST stay in the dialog to be retried; and one toast at the end MUST sum up how many were kept and how many failed.

#### Scenario: the Add menu says what each entry keeps in Coffer
- **GIVEN** the Knowledge page with a page open
- **WHEN** the user opens the header's Add menu
- **THEN** it offers Upload documents…, New collection… and Link an external folder…, each with its one-line description, and the header carries no separate Upload button
- **AND** no control on the page adds a file from a typed title and body, and the pane offers no Edit

#### Scenario: upload several files at once, each with its own outcome
- **GIVEN** the upload dialog and a collection picked
- **WHEN** the user drops a Markdown file, a PDF the server refuses, a ZIP archive and a file over 20 MB, and uploads
- **THEN** the ZIP archive and the large file are shown refused with their reasons before anything is sent, and are not sent
- **AND** the other two are sent one after another, the Markdown file ends done and the PDF failed with its reason and stays to be retried, and one toast sums up one kept and one failed

### Requirement: Open a collection in Obsidian when it is installed
A collection's folder MUST open as an Obsidian vault with nothing converted: its pages are plain Markdown, a `[[slug]]` link resolves by file name as Obsidian resolves it, and `aliases` frontmatter is the key Obsidian reads. Coffer MUST keep Obsidian's own files out of the collection: `.obsidian/` and every other hidden entry is neither committed, catalogued nor synced (see "Hide every dot-prefixed entry"). Obsidian MUST be among the editors the daemon detects. The web UI MUST offer **Open in Obsidian** in a collection's ⋯ menu and in a file's ⋯ menu only when the daemon detects Obsidian on this machine, opening the collection's folder, or the file, with it.

#### Scenario: Open in Obsidian shows only when Obsidian is installed
- **GIVEN** a collection open in the Knowledge page with a page chosen
- **WHEN** the daemon's detected editors include Obsidian, and then when they do not
- **THEN** with Obsidian detected the collection's and the page's ⋯ menus offer Open in Obsidian, which asks the daemon to open the collection's folder or the page's path with Obsidian
- **AND** without it neither menu names Obsidian

### Requirement: Link a folder the person keeps themselves
A person MUST be able to link a folder they keep with their own tools anywhere on this machine — an Obsidian vault, say — as a collection, through the Knowledge page's **Add → Link an external folder…** and `coffer knowledge link`, both over `POST /api/v1/knowledge/collections/link` with the folder's absolute path and an optional name. Linking MUST copy nothing into Coffer: the folder stays where it is, the only copy, and the system only shares it with agents. The name MUST default to the folder's own name and is a label, not a directory. A name another collection holds MUST be refused, and a folder already linked MUST be refused under the name it was linked as, both with `409 KNOWLEDGE_COLLECTION_EXISTS`. A folder that does not exist, a path that is not absolute, and Coffer's own home or any folder holding it — the home folder and the disk root included — MUST be refused with `400 KNOWLEDGE_FOLDER_REFUSED`. The link MUST be recorded as one `knowledge` resource whose config is `{"folder": "<absolute path>"}`, filed in the machine-local class under `~/.coffer/local/resources/knowledge/` and never in the vault, so it is never committed or synced ([vault-sync](../vault-sync/spec.md) "Keep machine-local state out of the repository"); on another machine the person links that machine's copy of the folder.

A linked folder MUST be listed with the other collections, carrying `linked`, its Markdown `note_count`, its `rules_file` (the first of `AGENTS.md`, `CLAUDE.md` and `README.md` present at its root, empty when none), its description read from the first paragraph of its own `README.md`, its absolute path and when its newest note was written; a folder that has gone missing MUST list with no notes rather than fail the listing. Every walk of a linked folder MUST skip hidden entries and `node_modules`, and stop at 5000 Markdown files; a file over 2 MB MUST be listed but its content not read into the page. A person who wants to share only part of a large folder links a subfolder. A linked folder MUST appear in the `coffer-guide` catalogue as "Merge the manual and the catalogue in the skill body" says, and the guide MUST be re-rendered when one is linked or disconnected, and by the next sweep after one is renamed.

The link dialog MUST say that the files stay where they are and nothing is copied into Coffer, that Coffer does not sync the folder, tidy it, keep its history or upload into it, and that agents follow its own `AGENTS.md`, `CLAUDE.md` or `README.md`. Its name field MUST follow the folder's name until the person types one, and a linked folder MUST open on the Knowledge page once it is linked. The reasoning is [A Linked Knowledge Folder Is Shared in Place, Read-Only to Coffer, and Recorded Machine-Local](../../../docs/decisions/linked-knowledge-folders-are-read-only-and-machine-local.md).

#### Scenario: a linked folder is listed and shared without being copied
- **GIVEN** a folder outside Coffer's home holding Markdown notes, an `AGENTS.md`, a `README.md` and a hidden `.obsidian/` folder
- **WHEN** it is linked through `POST /api/v1/knowledge/collections/link` with no name
- **THEN** it is listed under the folder's name, marked `linked`, with its four Markdown notes, `AGENTS.md` as its rules file, its README's first paragraph as its description and its absolute path
- **AND** nothing is written under the vault's knowledge root or into the folder, and its resource file lies under `local/resources/knowledge/` naming the folder, with none under the vault's `resources/knowledge/`

#### Scenario: the guide lists a linked folder with its own path and rules
- **GIVEN** a collection Coffer keeps and a linked folder `Work` under the home folder, with an `AGENTS.md` and one note
- **WHEN** the guide skill is rendered
- **THEN** the catalogue carries a section for `Work` marked as a linked folder that gives its path with the home folder written as `~`, tells the agent to follow its own `AGENTS.md`, and lists the note by its folder-relative path and title
- **AND** the rendered text holds no absolute home path, and the skill's description names the folder's subject from its README

#### Scenario: the link dialog says the files stay where they are
- **GIVEN** the Knowledge page
- **WHEN** the user picks Link an external folder… from the Add menu and enters a folder's path
- **THEN** the dialog's note says the files stay where they are, nothing is copied into Coffer, and Coffer doesn't sync it, tidy it, keep its history or upload into it
- **AND** the name follows the folder's name, Link folder sends the folder and the name, and the page opens the linked folder

### Requirement: Leave a linked folder to its own tools
A linked folder MUST be read by Coffer and never written. Coffer MUST NOT upload into it, delete a file from it, edit its description, check it, tidy it, undo or restore anything in it, or keep or show its history, and every route that would do one of these for a linked folder MUST answer `409 KNOWLEDGE_COLLECTION_LINKED` and change nothing. The sweep MUST leave it alone: no inbox adoption, no filing of loose Markdown into `pages/`, no commit of its edits. None of Coffer's wiki rules apply to it — no `pages/` and `sources/`, no page types, no waiting sources, no findings — and the tidy-all hand-off and the changes feed leave it out. Its tree and its files MUST be readable through the same tree and file routes as any collection, by `<name>/<path inside the folder>`, each read carrying the file's and its folder's absolute paths and the note's title (its frontmatter `title`, else its first `# ` heading, else its file name); a hidden entry, or a path that would leave the folder through `..` or a symlink, MUST be refused. Renaming a linked folder MUST change only its label, and deleting its resource — **Disconnect…** in the web UI — MUST stop sharing it and leave every file in the folder where it is. An agent MAY write in a linked folder only by that folder's own rules file, never by the guide's rules for a collection Coffer keeps (see "Teach writing and tidying in the guide").

In the web UI a linked folder's page MUST show its name with an **External** tag and, in place of a collection's summary line, To do, Contents and Change log, its facts under "About this folder": **Location** (its path, with **Reveal in Finder**), **Notes** (its Markdown note count), **Rules file** (or None) and **Managed by** — its own tools; Coffer only shares it with agents and copies, syncs, tidies and records nothing there. The page MUST carry no **Tidy**, and its ⋯ menu MUST hold **Reveal in Finder**, **Open in Obsidian** when it is installed, **Copy path**, **Rename…** and **Disconnect…**, which asks first and says the folder's files stay where they are, and no **Delete collection…**. A linked folder's file MUST open read-only with no **History** and no **Delete**. The upload dialog MUST NOT offer a linked folder.

#### Scenario: a linked folder is read but never written
- **GIVEN** a linked folder `Work` holding notes and a hidden `.obsidian/` folder
- **WHEN** its tree, a note and its files are read, and then a file delete, a check, a tidy start, a description edit and an upload into it are asked for
- **THEN** the reads answer with its visible folders and notes, the note's title and its absolute path, and no hidden entry
- **AND** each of the five answers 409 `KNOWLEDGE_COLLECTION_LINKED`, reading a hidden file is refused, and every file in the folder is byte for byte as it was

#### Scenario: disconnecting a linked folder leaves its files alone
- **GIVEN** a linked folder
- **WHEN** it is renamed through the kind-agnostic update and then deleted
- **THEN** both succeed, no collection is listed afterwards, and every file in the folder is as it was

#### Scenario: a linked folder's page shows who manages it
- **GIVEN** a linked folder `Work` with 12 Markdown notes and an `AGENTS.md`
- **WHEN** its page is opened
- **THEN** its heading carries the External tag, and its facts give its path, 12 Markdown notes, `AGENTS.md`, and that its own tools manage it and Coffer only shares it with agents
- **AND** the page has no Tidy, To do or Contents, reads no check and no change log for it, and its ⋯ menu offers Disconnect… and not Delete collection…

#### Scenario: a linked folder's note has no history or delete
- **GIVEN** a note of a linked folder open on the Knowledge page
- **WHEN** its pane bar and its ⋯ menu are read
- **THEN** there is no History button, and the menu offers no Delete…

#### Scenario: an upload never lands in a linked folder
- **GIVEN** a linked folder open on the Knowledge page
- **WHEN** the user opens Upload documents… from the Add menu and opens its collection picker
- **THEN** the linked folder is not among the collections offered
