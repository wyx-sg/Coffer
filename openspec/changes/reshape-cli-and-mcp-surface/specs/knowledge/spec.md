## MODIFIED Requirements

### Requirement: Create collections only deliberately
A **collection** is a top-level subdirectory of the knowledge root and is one `knowledge` Resource. It MUST be created deliberately — through the REST/CLI/UI surface — and MUST NOT be provisioned by a read, a write, or an agent's working directory. Creating one creates its directory and nothing inside it but an optional `README.md`.

#### Scenario: an unknown collection is an error, never auto-created
- **GIVEN** a knowledge root with no `typo` collection in it
- **WHEN** `coffer knowledge show typo --json` runs, and then `coffer path knowledge typo`
- **THEN** both commands exit non-zero and no `typo` directory exists afterwards: a read never provisions a collection

### Requirement: Read a collection's description from its README
A collection's one-line description MUST be the first paragraph of its `README.md`, absent when there is none, and MUST be read off disk on every listing. It MUST NOT be stored in the database — not even in the `resources` row's own generic `description` column, which for this kind stays empty: a copy written once and read by nothing is wrong from the first time the person edits the file. It is also what the delivered skill's own description draws on (see "Describe Coffer and the collections' subjects in the skill description"), so a collection that fails to describe itself is a collection an agent never recognises.

#### Scenario: the catalogue lists collections with their README description
- **GIVEN** a collection created with the description "First description", whose `README.md` is then edited by hand to open with "Edited by hand."
- **WHEN** `coffer knowledge list --json` runs
- **THEN** the collection's `description` is the README's first paragraph as edited, not the string the creation call supplied — the description is read off disk on every listing, never out of a row

### Requirement: Submit material through coffer__write
`coffer__write` MUST submit material to a named collection from `title`, `description` and body text. It MUST take no path, no folder and no lane, and MUST NOT replace anything: two submissions of the same title are two pieces of material. A submission MUST be a plain file write — no LLM, no conversion, no indexing step — and MUST record one `mcp_invocations` row and one audit event naming the calling agent, taken from the session's handshake identity ([mcp-gateway](../mcp-gateway/spec.md) "Take the agent identity from the handshake") written in as an `agent` argument no tool advertises and no caller can set. Its answer MUST say what became of the material: `pending`, with no path — an inbox address vanishes once the material is merged, so reporting one would be reporting an address that is about to stop existing — or `written`, with the document's path, when it was promoted (see "Promote material directly when no model is configured"). A submission naming a collection that does not exist or is disabled MUST be refused with the collections that **are** available: that names exactly what this agent's own delivered skill already lists, and it turns a dead end into a correction for a model that reached for the tool without opening the skill.

#### Scenario: written material waits in the inbox, or becomes a document with no model
- **GIVEN** a `shopee` collection created through `coffer knowledge add`, and an internal model connection configured
- **WHEN** `coffer__write` is called against the daemon with the title `Session ownership`, a description and a body
- **THEN** the answer's `status` is `pending` and it carries no path, the material waits in `shopee/.inbox/session-ownership.md` — named by the title's own slug, with no id in it anywhere — and one `knowledge_written` audit event is recorded
- **AND** with no internal model configured, the same call answers `written` with the path `shopee/session-ownership.md`: the material became a document of its own on the spot, and the inbox is empty

### Requirement: Let only a person delete a document
Deleting a document MUST be a person's action, and it MUST be allowed for **any** document, whoever wrote it: the tree is the person's as much as curation's. The REST route and the web UI MUST offer it, and each deletion through them MUST record a `knowledge_deleted` audit event. On the command line a person deletes the file itself, in the collection directory that `coffer path knowledge <collection>` names, and the deletion is live on the next read and the next catalogue (see "Keep direct file edits a complete way to change knowledge"). No agent-facing tool may delete anything. Inside a pass, `retire_document` is curation's own way to remove a document whose content it has written elsewhere (see "Preserve every fact a pass is shown"), and it is bounded like a write (see "Bound a pass to eight writes").

#### Scenario: delete a document an agent wrote
- **GIVEN** two documents in `shopee/` whose frontmatter `actor` is `agent`
- **WHEN** a person deletes one through `DELETE` on the knowledge route, and removes the other's file from the directory `coffer path knowledge shopee` prints
- **THEN** both files are gone from the tree, and neither is listed or catalogued afterwards
- **AND** a `knowledge_deleted` audit event is recorded for the one deleted through the route

### Requirement: Describe Coffer and the collections' subjects in the skill description
The skill's **frontmatter description** MUST describe Coffer itself — naming its built-in tools so a model recognises them — **and** name the subjects the enabled collections cover, drawn from their READMEs. It is the only part of this layer that is always in a model's context, so it MUST carry matchable specifics rather than a description of the layer, and it MUST fit the tightest frontmatter ceiling any importer imposes (1024 characters), dropping whole collection subjects from the tail rather than cutting a sentence mid-way.

#### Scenario: one skill carries both Coffer's manual and the catalogue
- **GIVEN** a rendered `coffer-guide` `SKILL.md`
- **WHEN** its frontmatter and its body are read
- **THEN** the description names Coffer and its built-in tools as well as the enabled collections' subjects, and is within 1024 characters — a catalogue too large to fit drops whole collection subjects from the tail rather than ending mid-sentence
- **AND** the body carries the manual first — the two built-in tools, the tiering contract, that Coffer never writes an agent's memory, and that no Coffer tool waits on an approval — and the catalogue after it, in one file

### Requirement: Merge the manual and the catalogue in the skill body
The skill's **body** MUST be one merged manual: Coffer's own — its two built-in tools, `coffer__search_tools` and `coffer__write`, and when to reach for each; the tiering contract that makes an unlisted upstream tool still callable; the memory root, and that Coffer's distilled memory notes are Markdown under it which the agent finds by searching that directory with its own tools; that Coffer's own logs are read with `coffer log` and located with `coffer path logs`; the fact that Coffer reads an agent's memory and never writes it; that no Coffer tool waits on a human approval; and what does not belong in knowledge — **followed by** the catalogue: the path of the knowledge root, and, for each enabled collection, every document's collection-relative path, title and description. It MUST instruct the agent to read those files with its own tools, to reach for `coffer__write` when it learns something durable, and that it may also correct or extend a document it has read by editing the file itself, which the next sweep carries into the rest of the collection (see "Keep direct file edits a complete way to change knowledge"). One skill, not a set: a frontmatter description is resident in every session whether the skill is opened or not, while a body is paid for only when a model reaches for it, so a second skill would spend the resident budget again to describe something most sessions never open.

#### Scenario: the skill body carries the catalogue and the absolute root
- **GIVEN** a collection holding three documents
- **WHEN** the skill is rendered
- **THEN** its body carries each document's collection-relative path, title and description, and the path of the knowledge root, and it instructs the agent to read those files with its own tools
- **AND** the frontmatter `description` names the collection's subject, taken from the collection's own `README.md`, so a model matching on it has something to match

#### Scenario: the manual names two tools, the memory root and the log reader
- **GIVEN** the `knowledge` and `memory` features switched on
- **WHEN** the skill is rendered
- **THEN** its manual names exactly two built-in tools, `coffer__search_tools` and `coffer__write`, and names neither `coffer__recall` nor `coffer__diagnose`
- **AND** it names the memory root with the instruction to search it with the agent's own tools, and names `coffer log` and `coffer path logs` as the way to read Coffer's own logs

### Requirement: Keep the handshake instructions to what a skill cannot carry
The MCP gateway's own `initialize` instructions MUST stay within their character cap and MUST carry only what a skill cannot: what Coffer is, the names of its two built-in tools (`coffer__write`, `coffer__search_tools`) so they are recognisable in a tool list, one line saying that Coffer's memory notes are files under the memory root read with the agent's own tools and that Coffer's own logs are read with `coffer log`, the tiering sentence when tools are actually hidden this session, and a pointer to the `coffer-guide` skill for everything else. It MUST NOT restate the manual, MUST NOT name a retrieval tool, and MUST NOT carry the catalogue — the catalogue is in the skill body, which costs a session nothing until a model opens it. A built-in tool whose experimental feature is switched off is not in the tool list, and the instructions MUST NOT name it either, nor the memory root while the memory feature is off ([experimental-features](../experimental-features/spec.md) "Withdraw what a switched-off feature put in front of agents").

#### Scenario: the handshake names Coffer's tools and points at the skill
- **GIVEN** a real daemon driven over its `/mcp` endpoint by the MCP SDK
- **WHEN** the client initializes, both with upstream tools hidden and with none hidden
- **THEN** the `instructions` text is within its character cap, names `coffer__write` and `coffer__search_tools`, names neither `coffer__recall` nor `coffer__diagnose`, and points at the `coffer-guide` skill for the rest
- **AND** it names no retrieval tool and carries no collection catalogue

### Requirement: Cover collection management on REST and the CLI
The REST API under `/api/v1/knowledge` MUST cover: create a collection, list one level of a collection at a path, read a document, submit material (`POST /material`), upload a document, delete a document, and trigger curation. The `coffer knowledge` CLI group MUST offer `list`, `show`, `add`, `edit`, `rm`, `enable`, `disable`, `write` (submit material), `upload` and `curate`. A collection's documents are plain files, so on the command line `coffer path knowledge [<collection>]` prints the absolute path of the knowledge root or of one collection, and the documents are listed, read and deleted on disk; the `coffer knowledge` group carries no command that lists, prints or deletes a document. There MUST be no route that writes a document: a person edits one in their own editor, reached from the page's open-in-editor action, and the edit is live on the next read (see "Keep direct file edits a complete way to change knowledge"). Collection deletion goes through the Resource framework (`DELETE /api/v1/resources/{uid}`; `coffer knowledge rm`). There MUST be no index, reindex, check-sources, update-source or embedding-configuration endpoint, no settings endpoint for the cwd-derived scope axis "Derive no boundary from the working directory" forbids, and no per-agent reach endpoint or `scope` command for this kind (see "Gate collections with enabled alone") — a collection's one switch is `enabled`, which the framework already serves. These surfaces serve the human and the UI; they are not an agent's retrieval path.

#### Scenario: expose every collection operation and no document write
- **GIVEN** the daemon's route table and the `coffer knowledge` command group
- **WHEN** both are enumerated
- **THEN** the routes offer create, list a level, read, submit material, upload, delete a document and trigger curation, and the command group offers exactly `list`, `show`, `add`, `edit`, `rm`, `enable`, `disable`, `write`, `upload` and `curate`
- **AND** no route under `/api/v1/knowledge` accepts `PUT` or `PATCH` on a document, and none is an index, reindex, source, embedding, scope or reach endpoint

#### Scenario: locate a collection's documents from the command line
- **GIVEN** a `shopee` collection holding a document at `shopee/infra/cache.md`
- **WHEN** `coffer path knowledge shopee` runs, and then `coffer path knowledge` with no collection
- **THEN** the first prints the absolute path of the `shopee` directory, under which the document is read at `infra/cache.md`, and the second prints the absolute knowledge root
- **AND** `coffer knowledge` offers no `collections`, `create`, `ls`, `read` or `delete` command
