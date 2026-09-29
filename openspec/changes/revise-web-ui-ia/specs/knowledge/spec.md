## MODIFIED Requirements

### Requirement: Hide dot-prefixed entries except the inbox
Hidden entries (dot-prefixed) MUST be excluded from every count of documents and from the catalogue. The system itself MUST write exactly one: a collection's `.inbox/`, where submitted material waits to be merged (see "Submit every entrance's input as material"). An inbox item MUST be deleted once a pass has merged it or it has been promoted (see "Settle an item only after its pass completes", "Promote material directly when no model is configured"). The tree route MUST list a collection root's `.inbox/` as a directory and its items as files, and the read route MUST read an inbox item, so a person can see what is waiting; no other hidden entry is listed or readable, and no surface may write or delete an inbox item. `.history/` and `.raw/` stay removed: what a pass or a person replaced is kept in the vault's git history (see "Keep every document's history and undo a pass as a whole"), not in the collection, and nothing is kept of the document an upload arrived in.

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
`coffer__write` MUST submit material to a named collection from `title`, `description` and body text. It MUST take no path, no folder and no lane, and MUST NOT replace anything: two submissions of the same title are two pieces of material. A submission MUST be a plain file write — no LLM, no conversion, no indexing step — and MUST record one `mcp_invocations` row and one audit event naming the calling agent, taken from the session's handshake identity ([mcp-gateway](../mcp-gateway/spec.md) "Take the agent identity from the handshake") written in as an `agent` argument no tool advertises and no caller can set. A person's **Add a note** in the web UI (see "Present a collection as one tree in the web UI") submits through the same path with the actor `user`, so there is no route that creates a document directly. Its answer MUST say what became of the material: `pending`, with no path — an inbox address vanishes once the material is merged, so reporting one would be reporting an address that is about to stop existing — or `written`, with the document's path, when it was promoted (see "Promote material directly when no model is configured"). A submission naming a collection that does not exist MUST be refused with the collections that **are** available: that names exactly what this agent's own delivered skill already lists, and it turns a dead end into a correction for a model that reached for the tool without opening the skill.

#### Scenario: written material waits in the inbox, or becomes a document with no model
- **GIVEN** a `shopee` collection created through `coffer knowledge add`, and an internal model connection configured
- **WHEN** `coffer__write` is called against the daemon with the title `Session ownership`, a description and a body
- **THEN** the answer's `status` is `pending` and it carries no path, the material waits in `shopee/.inbox/session-ownership.md` — named by the title's own slug, with no id in it anywhere — and one `knowledge_written` audit event is recorded
- **AND** with no internal model configured, the same call answers `written` with the path `shopee/session-ownership.md`: the material became a document of its own on the spot, and the inbox is empty

### Requirement: Run curation on a sweep and on demand
Passes MUST be run by a **sweep on an interval** and by a manual trigger. The interval is the one global curation interval — the `curate` pass's interval under Settings › General's Coffer's model section, 60 seconds by default ([internal-engine](../internal-engine/spec.md) "Show and change Coffer's model in Settings › General") — and no collection has an interval of its own. Each sweep MUST read the interval afresh rather than capture it at boot, and MUST find a collection's pending items in this order: first every inbox item, oldest first — until it is merged it is knowledge no agent can read — then every document whose modification time is newer than its own `coffer_curated_at` stamp (or which has none), meaning a person or an agent edited or added it out of band. A sweep MUST run at most a bounded number of passes per collection, so a freshly migrated vault drains visibly rather than in one long batch. The manual trigger — **Curate now** in the web UI, `coffer knowledge curate <collection>` on the command line — MUST run passes until the collection has nothing pending, in the same order (inbox items oldest first, then documents edited out of band), still **one pass at a time** (see "Run one pass per collection at a time") and each pass still bounded (see "Bound a pass to eight writes"). While it runs it MUST report progress as *n of m*, where *m* is what was pending when it started, and it MUST stop at the first pass that fails, reporting that pass and leaving the rest pending for the next run or sweep. Given one document, it curates just that document. A trigger arriving while a pass over the collection is in flight is refused with 409, as any other.

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
- **THEN** progress reads 1 of 3, 2 of 3 and 3 of 3 as passes finish, and `coffer knowledge curate` prints the same

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

### Requirement: Present a collection as one tree in the web UI
The web UI MUST present a collection as **one tree** of its documents — no lanes, no tabs, no filter or retrieval box — with the chosen document in the pane beside it, the same two panes a skill's Files tab is. The pane MUST render the document and offer **Edit**, which turns it into an editor saved through "Save a document edited in the web UI" and reports a conflict in place; open-in-external-editor and reveal-in-file-manager; and delete, naming the exact path before it runs, reporting a refusal in place, and leaving the preview on no file afterwards. The pane MUST show a document's title and description as read-only metadata above the editor, which holds only the body; a save refused as stale MUST say the document changed on disk and that the text was not saved, and offer **Reload**, **Compare** and **Copy my text**, never a second save over it. The tree MUST show the collection's `.inbox/` as an **Inbox** node carrying the number of items waiting; choosing it opens the Inbox view, whose items open read-only, with no edit and no delete. In the web UI inbox entries are called **items** (the spec's *material*), and curation is called **Curate** / **Curation** (整理) everywhere — the web UI, CLI help and docs-site — never "merge". The collection's header MUST carry one status line — its document count, how many items are waiting, and when it was last curated. The page MUST offer upload into the collection in view and **Add a note** (a title and body submitted as an item, see "Submit material through coffer__write"). The only manual trigger MUST be a quiet **Curate now** in the Inbox view and in Recent changes, reporting its progress, a pass already in flight and a failed pass. While Coffer's model is not set, the page MUST show no Inbox node and no Curate now, and instead one line saying that items become documents as they arrive and linking to Settings › General. The tree and the pane MUST extend to the bottom of the window and scroll inside.

#### Scenario: the viewer shows one tree of documents
- **GIVEN** a collection page whose tree holds a document at the root and one inside a folder, with one item of material waiting in the inbox
- **WHEN** the page renders, a document's row is clicked, and then the inbox item's
- **THEN** there is one tree — no lane headings, no tabs, no filter input — listing both documents and an `.inbox` folder holding the item
- **AND** the document offers Edit, open-in-editor, reveal and delete, and the inbox item offers neither Edit nor delete

#### Scenario: edit a document in place
- **GIVEN** a document open in a collection's pane
- **WHEN** the user chooses Edit, changes the text and saves
- **THEN** the save is sent with the fingerprint the pane loaded, and the pane renders the saved body

#### Scenario: the inbox node counts waiting items and holds the only trigger
- **GIVEN** a collection with two items waiting and Coffer's model set
- **WHEN** the collection page renders and the user opens the Inbox node
- **THEN** the node reads 2, the header reads the document count, 2 waiting and when it was last curated, and Curate now is offered in the Inbox view and nowhere in the header or on documents

#### Scenario: no model shows no curation controls
- **GIVEN** Coffer's model not set
- **WHEN** a collection page renders
- **THEN** there is no Inbox node and no Curate now, and one line links to Settings › General

#### Scenario: a stale save offers reload and compare
- **GIVEN** a document open in the editor that curation changes on disk before the user saves
- **WHEN** the user saves
- **THEN** the pane says the document changed on disk and the text was not saved, and offers Reload, Compare and Copy my text, with no way to save over it

#### Scenario: add a note submits an item
- **GIVEN** a collection page
- **WHEN** the user chooses Add a note and submits a title and body
- **THEN** one item waits in the collection's inbox with actor `user`, and no document is created directly

#### Scenario: curation is called curate, never merge
- **GIVEN** the web UI in English and in 中文, and `coffer knowledge --help`
- **WHEN** every label, button and help line about curation is read
- **THEN** each says Curate or Curation (整理 in 中文) and none says merge, and inbox entries are called items

### Requirement: Render the guide skill deterministically
The rendered `SKILL.md` MUST be a **pure function of the running build and the catalogue it is given**: the same build over the same collections MUST produce the same bytes, run after run and machine after machine. Nothing machine-specific may enter it — not an absolute home directory, not a timestamp, not a build path — and the skill's own config MUST likewise carry no timestamp of its generation.

**The reason is no longer convergence, and that changes what the requirement is worth saying.** It used to read "byte-identical on every machine running the same build against the same catalogue", with the hedge doing the real work, because the artifact converged: a purely local difference would have had two vaults overwriting each other's copy forever. It no longer converges at all ([vault-sync](../vault-sync/spec.md) "Withhold derived output in both halves") — every machine renders its own from files that converge plus its own reach, and two machines are *expected* to differ whenever their enabled sets differ, which is exactly what the hedge was excusing. What determinism buys now is local and still worth paying for: an unchanged vault re-rendering to the same bytes is what lets the seed skip the write, so a boot or a curation tick that changed nothing registers nothing, audits nothing and re-delivers nothing ([skill-manager](../skill-manager/spec.md) "Regenerate Coffer's builtin skill from the build") — and it is what makes the `version_hash` in the row mean "the content moved" rather than "time passed".

The knowledge root MUST still be written in its `~`-relative form whenever it sits in its default place, so a path an agent reads is one a person can retype; an explicitly relocated root (`COFFER_KNOWLEDGE_ROOT`) MUST be written out in full, because an accurate path is worth more than a tidy one.

#### Scenario: the rendered skill is byte-identical on two machines
- **GIVEN** the same build and the same catalogue rendered twice, once with the knowledge root at each of two different home directories, and once again with the root explicitly relocated
- **WHEN** the two default-placed renderings are compared byte for byte
- **THEN** they are identical, and the knowledge root appears in its `~`-relative form rather than as either home's absolute path
- **AND** the relocated root is written out in full, and the skill's stored config carries no timestamp of when it was generated

## ADDED Requirements

### Requirement: Keep every document's history and undo a pass as a whole
The knowledge root is part of the vault, which is always a git repository, and every write to a
document MUST be a commit naming its writer
([Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer](../../../docs/decisions/every-vault-write-is-a-validated-commit-naming-its-writer.md)):
a person's save or delete names the user, a curation pass is **one commit** naming Coffer's
curation and the item it curated — and, for an item an agent wrote, that agent, taken from the
`knowledge_written` audit event of the submission — and a change that arrives through vault sync
names sync. A document's history MUST list its versions newest first with their writer and time,
show the diff of each, and restore any version as a new commit. A pass MUST be undoable **as a
whole**: undoing it reverts that pass's commit — every document it wrote or retired — as one new
commit; when a later commit changed one of the same documents, the undo MUST be refused naming that
document rather than overwrite the later change.

#### Scenario: a document's history lists its versions with their writers
- **GIVEN** a document the user created through Add a note, that a pass then merged a Claude Code item into, and that the user then edited
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
