## ADDED Requirements

### Requirement: Delete a document at once, a collection after asking, and offer Undo
The web UI MUST delete a document **at once**: its ⋯ menu's **Delete document** opens no confirmation, because the delete is reversible. **Delete collection** MUST ask first, in a confirmation naming the collection and how many documents it holds, because once its toast closes a collection can no longer be brought back from the page; the confirmation asks for no typed name. The page MUST report either delete in a toast — *Deleted <name>* — carrying **Undo**, which restores what the delete removed (see "Undo a knowledge delete from its toast"), and MUST then show the collection page after a document's delete and the Knowledge page after a collection's. The delete is audited as a `knowledge_deleted` event, and an Undo refused because the path or name is taken again MUST say so rather than overwrite it. Deleting a **memory partition** is not covered: it is irreversible and keeps its own confirmation ([memory](../memory/spec.md) "Show a partition's memories read-only").

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
Deleting a document or a whole collection MUST keep what it removed in the vault's history, so the delete's toast can undo it. Undo MUST find the delete in the changes feed (see "Follow edits across collections in one feed") and restore exactly what it removed, as it was just before it: a document into its collection; a collection as a new collection of the same name with its documents and its `README.md`. A collection restore MUST write every file first and register the collection's row last, so a failure part-way leaves no row and no partial directory: what was written is removed again and the same restore can be tried afresh. The restore MUST be one new change naming the user, carrying the version of the delete it restored, and recorded as a `knowledge_edited` audit event; the delete itself stays in the history. A restore MUST be refused with nothing written when it would overwrite — a document at the same path, `409 KNOWLEDGE_RESTORE_CONFLICT` naming it, or a collection of the same name, `409 KNOWLEDGE_COLLECTION_EXISTS` — and a change that is not a delete MUST be refused with `400 KNOWLEDGE_NOT_A_DELETE`. The route is `POST /api/v1/knowledge/changes/{version}/restore`, the web UI's own. After the toast is gone a document is brought back the way any earlier version of a vault file is ([vault-storage](../vault-storage/spec.md) "Hand restoring an earlier version of a vault file to an agent").

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
The web UI MUST present a collection as **one tree** of its documents — no lanes, no tabs, no filter or retrieval box — with the chosen document in the pane beside it, the same two panes a skill's Files tab is. The tree MUST name every collection, folder and document by its name on disk: a collection has no title (see "Name a collection by its folder and edit its description in place"). Its **Collections** header strip MUST carry **New collection** (a name and what belongs in it; the collection reaches every agent through the coffer-guide skill). The tree MUST show no hidden entry, and no collection or folder carries a document count. Knowledge calls its files **documents** everywhere (memory keeps *notes*).

A document's pane MUST show the document read-only, with a **Preview / Source** switch, **Open in editor** as a visible button, and a ⋯ menu holding **Reveal in Finder**, **History…** ([web-ui](../web-ui/spec.md) "Show where a file's history is and hand its restore to an agent") and **Delete document**. Its properties — who wrote it and when it was created, read from its frontmatter — MUST be one line under its title; there is no side column. The pane MUST NOT edit the document: a person changes it in their own editor and an agent with its own file tools (see "Treat a direct file edit as a complete change"), and the next read shows the change.

A collection's page MUST show its folder name, its description edited in place (see "Name a collection by its folder and edit its description in place") and its properties: **Documents** and **Folder**, and it MUST carry **Tidy** (see "Hand a tidy to the agent"). A collection with no documents shows the same page with one line saying so and how to fill it — upload one, or drop Markdown files into the folder — and **Reveal in Finder**. The collection's ⋯ menu MUST hold **Reveal in Finder**, **Copy path** and **Delete collection** (see "Delete a document at once, a collection after asking, and offer Undo").

The page MUST offer **Upload** into a collection as its one primary action and no other form that adds a document: people write in their own editor, agents by writing files. With no collection open, the page shows its collections and **Tidy all**; there is no Recent changes view. The tree and the pane MUST extend to the bottom of the window and scroll inside.

The Knowledge page's title MUST carry the **Experimental** tag ([experimental-features](../experimental-features/spec.md)).

#### Scenario: the viewer shows one tree of documents
- **GIVEN** a collection page whose tree holds a document at the root and one inside a folder
- **WHEN** the page renders and a document's row is clicked
- **THEN** there is one tree — no lane headings, no tabs, no filter input — listing both documents and no hidden entry
- **AND** the document offers Open in editor, and Reveal in Finder, History… and Delete document in its ⋯ menu

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
Every accepted write to a collection MUST be a git commit naming its writer ([Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer](../../../docs/decisions/every-vault-write-is-a-validated-commit-naming-its-writer.md)). The commits are the vault repository's, under `knowledge/`: the knowledge root keeps no repository of its own. A person's upload, description edit, delete or Undo names the user; material promoted on arrival names whoever submitted it — the user, or, for a file an agent dropped into the inbox, the actor the file reports; a change that arrives through vault sync names sync; and a change any other writer made in the tree — a person's own editor, an agent's file tools — MUST be committed as an edit on disk before Coffer's next commit, so it is never counted as Coffer's. A commit an earlier version of Coffer made as a curation pass stays in the history under its writer. The history is read with git or through an agent ([vault-storage](../vault-storage/spec.md) "Hand restoring an earlier version of a vault file to an agent"); the web UI shows no version list. The vault is a git repository on every machine that runs Coffer ([vault-storage](../vault-storage/spec.md) "Keep the vault a git repository whether or not it syncs"); a read of the changes feed git cannot answer MUST answer 503 `KNOWLEDGE_HISTORY_UNAVAILABLE` while every write keeps working. git is looked for on every read, so one removed while the daemon runs is answered the same way. When the cause is that git is not installed, the refusal's details MUST carry `reason: "git_missing"` and `handoff`, a prompt asking the person's agent to install git on this machine — naming its OS and architecture and what needed git — the way that fits the machine, confirming it with `git --version`; neither the prompt nor the error's message may name an install command.

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

## MODIFIED Requirements

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

### Requirement: Hide every dot-prefixed entry
Hidden entries (dot-prefixed) MUST be excluded from every count of documents and from the catalogue, and no surface MUST list or read one: the tree route lists none, the read route refuses every hidden path, and a collection reports no count of what hides in it. A collection's `.inbox/` is an ordinary hidden entry whose files the sweep adopts and promotes (see "Adopt a file dropped into the inbox"). `.history/` and `.raw/` do not exist: what a person or an agent replaced is kept in the collection's git history (see "Commit every knowledge write naming its writer"), not in the collection, and nothing is kept of the document an upload arrived in.

#### Scenario: leave hidden entries out of every listing
- **GIVEN** a `shopee` collection holding one document, a file in `.inbox/`, and a file a person put under `.scratch/`
- **WHEN** the collection is listed, its document count read, its catalogue rendered and its tree requested
- **THEN** the count is one and the catalogue names the one document only
- **AND** the tree lists the document and nothing from `.inbox/` or `.scratch/`, and the read route refuses a path under either

### Requirement: Manage knowledge in the web UI
People MUST manage knowledge in the web UI: creating collections, uploading documents, reading documents and opening them in their editor, tidying a collection through their agent, deleting and undoing a delete, and editing a collection's description. The REST routes under `/api/v1/knowledge` behind those pages are the web UI's own private interface, not a public API: a route the web UI does not call MUST NOT exist, and there MUST be no route that creates or saves a document at a path — a person's text reaches knowledge through their own editor (see "Treat a direct file edit as a complete change") or as material like every other entrance (see "Promote submitted material at once"). There MUST be no route that lists a document's versions, diffs a version or restores one: a document's history is git's ([vault-storage](../vault-storage/spec.md) "Hand restoring an earlier version of a vault file to an agent"). There MUST be no index, reindex, check-sources, update-source or embedding-configuration endpoint, no curate or undo-pass endpoint, no settings endpoint for the cwd-derived scope axis "Derive no boundary from the working directory" forbids, and no per-agent reach endpoint or enabled switch for this kind (see "Serve every collection to every agent"). Collection deletion goes through the Resource framework (`DELETE /api/v1/resources/{uid}`). There MUST be no command group for knowledge and no `coffer path` target for it: a collection's documents are plain files, so agents and people read, edit and delete them directly under the knowledge root that the `coffer-guide` skill names (see "Treat a direct file edit as a complete change").

#### Scenario: no knowledge command group or path target exists
- **GIVEN** the `coffer` command tree
- **WHEN** it is enumerated, and `coffer path` is run with a `knowledge` target
- **THEN** there is no `knowledge` command group, and `coffer path` refuses `knowledge` as an unknown target

#### Scenario: the routes are the web UI's, with no material or create-at-path route
- **GIVEN** the daemon's route table under `/api/v1/knowledge`
- **WHEN** it is enumerated
- **THEN** it offers create a collection, list a level, read, upload, delete a document, the changes feed and restoring a delete, rewrite a description, and the tidy-all hand-off
- **AND** it carries no route that saves a document, no history, version or version-restore route, no `/material` route, no curate route, no undo route, no route that creates a document at a path, and no index, reindex, source, embedding, scope or reach endpoint

### Requirement: Follow edits across collections in one feed
The system MUST serve one feed of the recent changes to knowledge across every collection, newest first, paged by an opaque cursor ([resource-framework](../resource-framework/spec.md) "Page growing lists by an opaque cursor") and filterable to one collection: every document a person or an agent wrote, restored or deleted, and every change from sync or from disk — each with its writer, its time, its collection and, for each document it touched, whether that document was added, changed or removed and how many lines were added and removed. A change an earlier version of Coffer made as a curation pass is listed with its writer. One change MUST be readable in full — every document it touched with its diff. The feed is `GET /api/v1/knowledge/changes`, the route a delete's Undo reads to find the delete it restores (see "Undo a knowledge delete from its toast"); the web UI shows no timeline of it.

#### Scenario: recent changes lists edits across collections
- **GIVEN** a person's upload in one collection and an agent's edit on disk in another
- **WHEN** the feed is read, and read again filtered to one collection
- **THEN** both changes are listed newest first with their collections, writers and per-document line counts
- **AND** the filtered read holds only that collection's changes, and one change read in full carries each document's diff

## REMOVED Requirements

### Requirement: Save a document edited in the web UI
**Reason**: Coffer is not a second editor (principles, What Coffer is not › Not a second agent). A person edits a document in their own editor and an agent with its own file tools; both are already complete ways to change knowledge ("Treat a direct file edit as a complete change").
**Migration**: Open the document in the editor from its pane (Open in editor). `PUT /api/v1/knowledge/file`, the read's `fingerprint` and `KNOWLEDGE_FILE_CONFLICT` are removed.

### Requirement: Delete a document or a collection at once and offer Undo
**Reason**: With Recent changes gone, a deleted collection can only be undone while its toast is open, so its delete now asks first. A document still goes at once.
**Migration**: See "Delete a document at once, a collection after asking, and offer Undo".

### Requirement: Restore a deleted collection or document from Recent changes
**Reason**: The Recent changes view is removed (version browsing is git's and an agent's, not Coffer's). Restoring a delete stays behind the delete's Undo.
**Migration**: See "Undo a knowledge delete from its toast". After the toast is gone, a deleted document is restored like any earlier version, through the History hand-off or git.

### Requirement: Show a collection as one tree of documents in the web UI
**Reason**: The document pane no longer edits: Edit, the editor, the stale-save banner, Compare, Copy my text and Reload, and the History tab are removed.
**Migration**: See "Show a collection as one tree of read-only documents in the web UI".

### Requirement: Keep every document's history
**Reason**: Every knowledge write is still a commit naming its writer, but the web UI no longer lists a document's versions, shows their diffs or restores one; that is git's or an agent's.
**Migration**: See "Commit every knowledge write naming its writer". `GET /api/v1/knowledge/history`, `/history/diff`, `/history/version`, `POST /history/restore` and `KNOWLEDGE_VERSION_NOT_FOUND` are removed; the History… dialog copies the `git log` command and hands a restore to the agent.
