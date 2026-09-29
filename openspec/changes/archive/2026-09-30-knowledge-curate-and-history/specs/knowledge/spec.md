## MODIFIED Requirements

### Requirement: Hide dot-prefixed entries except the inbox
Hidden entries (dot-prefixed) MUST be excluded from every count of documents and from the catalogue. The system itself MUST write exactly one: a collection's `.inbox/`, where submitted material waits to be merged (see "Submit every entrance's input as material"). An inbox item MUST be deleted once a pass has merged it or it has been promoted (see "Settle an item only after its pass completes", "Promote material directly when no model is configured"). The tree route MUST list a collection root's `.inbox/` as a directory and its items as files, and the read route MUST read an inbox item, so a person can see what is waiting; no other hidden entry is listed or readable, and no surface may write or delete an inbox item. `.history/` and `.raw/` stay removed: what a pass or a person replaced is kept in the collection's git history (see "Keep every document's history and undo a pass as a whole"), not in the collection, and nothing is kept of the document an upload arrived in.

#### Scenario: leave hidden entries out of every listing
- **GIVEN** a `shopee` collection holding one document, one item waiting in `.inbox/`, and a file a person put under `.scratch/`
- **WHEN** the collection is listed, its document count read, its catalogue rendered and its tree requested
- **THEN** the count is one and the catalogue names the one document only
- **AND** the tree lists the document and an `.inbox` directory holding the waiting item, which the read route returns, and nothing from `.scratch/`

### Requirement: Present knowledge as files on disk
What this layer serves is **files on disk**, and the system MUST describe it as such wherever it is presented: a delivered path is the whole of the access story, because an agent handed the knowledge root reads anything under it with the shell tools it already has. Every collection is served to every agent (see "Serve every collection to every agent"), and nothing about a collection may be presented as a filesystem boundary: a collection has no switch that would hide it from a process that can open the directory.

#### Scenario: the guide hands over files to read with the agent's own tools
- **GIVEN** a collection holding one document
- **WHEN** the guide skill's catalogue is rendered
- **THEN** it tells the agent to read each document at `<root>/<collection>/<path>` with its own file tool and names the directory the collection's files live under
- **AND** it names no Coffer tool as the way to read a document

### Requirement: Submit material through coffer__write
`coffer__write` MUST submit material to a named collection from `title`, `description` and body text. It MUST take no path, no folder and no lane, and MUST NOT replace anything: two submissions of the same title are two pieces of material. A submission MUST be a plain file write — no LLM, no conversion, no indexing step — and MUST record one `mcp_invocations` row and one audit event naming the calling agent, taken from the session's handshake identity ([mcp-gateway](../mcp-gateway/spec.md) "Take the agent identity from the handshake") written in as an `agent` argument no tool advertises and no caller can set. A person's **Add a document** in the web UI (see "Present a collection as one tree in the web UI") submits through the same path with the actor `user`, so there is no route that creates a document directly. Its answer MUST say what became of the material: `pending`, with no path — an inbox address vanishes once the material is merged, so reporting one would be reporting an address that is about to stop existing — or `written`, with the document's path, when it was promoted (see "Promote material directly when no model is configured"). A submission naming a collection that does not exist MUST be refused with the collections that **are** available: that names exactly what this agent's own delivered skill already lists, and it turns a dead end into a correction for a model that reached for the tool without opening the skill.

#### Scenario: written material waits in the inbox, or becomes a document with no model
- **GIVEN** a `shopee` collection created through `coffer knowledge add`, and an internal model connection configured
- **WHEN** `coffer__write` is called against the daemon with the title `Session ownership`, a description and a body
- **THEN** the answer's `status` is `pending` and it carries no path, the material waits in `shopee/.inbox/session-ownership.md` — named by the title's own slug, with no id in it anywhere — and one `knowledge_written` audit event is recorded
- **AND** with no internal model configured, the same call answers `written` with the path `shopee/session-ownership.md`: the material became a document of its own on the spot, and the inbox is empty

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
- **GIVEN** the `knowledge` and `memory` features switched on
- **WHEN** the skill is rendered
- **THEN** its manual names exactly two built-in tools, `coffer__search_tools` and `coffer__write`, and names neither `coffer__recall` nor `coffer__diagnose`
- **AND** it names the memory root with the instruction to search it with the agent's own tools, and names `coffer log` and `coffer path logs` as the way to read Coffer's own logs

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

### Requirement: Render the guide skill deterministically
The rendered `SKILL.md` MUST be a **pure function of the running build and the catalogue it is given**: the same build over the same collections MUST produce the same bytes, run after run and machine after machine. Nothing machine-specific may enter it — not an absolute home directory, not a timestamp, not a build path — and the skill's own config MUST likewise carry no timestamp of its generation.

**The reason is no longer convergence, and that changes what the requirement is worth saying.** It used to read "byte-identical on every machine running the same build against the same catalogue", with the hedge doing the real work, because the artifact converged: a purely local difference would have had two vaults overwriting each other's copy forever. It no longer converges at all ([vault-sync](../vault-sync/spec.md) "Withhold derived output in both halves") — every machine renders its own from files that converge plus its own reach, and two machines are *expected* to differ whenever their enabled sets differ, which is exactly what the hedge was excusing. What determinism buys now is local and still worth paying for: an unchanged vault re-rendering to the same bytes is what lets the seed skip the write, so a boot or a curation tick that changed nothing registers nothing, audits nothing and re-delivers nothing ([skill-manager](../skill-manager/spec.md) "Regenerate Coffer's builtin skill from the build") — and it is what makes the `version_hash` in the row mean "the content moved" rather than "time passed".

The knowledge root MUST still be written in its `~`-relative form whenever it sits in its default place, so a path an agent reads is one a person can retype; an explicitly relocated root (`COFFER_KNOWLEDGE_ROOT`) MUST be written out in full, because an accurate path is worth more than a tidy one.

#### Scenario: the rendered skill is byte-identical on two machines
- **GIVEN** the same build and the same catalogue rendered twice, once with the knowledge root at each of two different home directories, and once again with the root explicitly relocated
- **WHEN** the two default-placed renderings are compared byte for byte
- **THEN** they are identical, and the knowledge root appears in its `~`-relative form rather than as either home's absolute path
- **AND** the relocated root is written out in full, and the skill's stored config carries no timestamp of when it was generated

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
The REST API under `/api/v1/knowledge` MUST cover: create a collection, list one level of a collection at a path, read a document, save an edited document's body (`PUT /file`, see "Save a document edited in the web UI"), submit material (`POST /material`), upload a document, delete a document, trigger curation, read a document's history and one version's diff, restore a version, read the recent changes and one change in full, and undo a pass (see "Keep every document's history and undo a pass as a whole", "Follow knowledge changes across collections"). The `coffer knowledge` CLI group MUST offer `list`, `show`, `add`, `edit`, `rm`, `write` (submit material), `upload`, `curate`, `history`, `restore`, `changes` and `undo`. A collection's documents are plain files, so on the command line `coffer path knowledge [<collection>]` prints the absolute path of the knowledge root or of one collection, and the documents are listed, read, edited and deleted on disk; the `coffer knowledge` group carries no command that lists, prints, saves or deletes a document. The web UI's editor saves through `PUT /file`, because a browser page cannot write the disk. A person may equally edit a document in their own editor, reached from the page's open-in-editor action or from that path, and that edit is live on the next read (see "Keep direct file edits a complete way to change knowledge"). Collection deletion goes through the Resource framework (`DELETE /api/v1/resources/{uid}`; `coffer knowledge rm`). There MUST be no route that creates a document at a path — a person's Add a document submits material like every other entrance (see "Submit material through coffer__write") — and no index, reindex, check-sources, update-source or embedding-configuration endpoint, no settings endpoint for the cwd-derived scope axis "Derive no boundary from the working directory" forbids, and no per-agent reach endpoint, `scope` command, enabled switch or `enable`/`disable` command for this kind (see "Serve every collection to every agent"). These surfaces serve the human and the UI; they are not an agent's retrieval path.

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

## ADDED Requirements

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
