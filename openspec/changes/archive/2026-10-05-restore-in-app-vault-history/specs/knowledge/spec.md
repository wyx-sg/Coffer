## MODIFIED Requirements

### Requirement: Manage knowledge in the web UI
People MUST manage knowledge in the web UI: creating collections, uploading documents, reading documents and opening them in their editor, reading a document's history and restoring an earlier version, tidying a collection through their agent, deleting and undoing a delete, and editing a collection's description. The REST routes under `/api/v1/knowledge` behind those pages are the web UI's own private interface, not a public API: a route the web UI does not call MUST NOT exist, and there MUST be no route that creates or saves a document at a path — a person's text reaches knowledge through their own editor (see "Treat a direct file edit as a complete change") or as material like every other entrance (see "Promote submitted material at once"). There MUST be no route under `/api/v1/knowledge` that lists a document's versions, diffs a version or restores one: a document's history is read and restored through the vault's routes ([vault-storage](../vault-storage/spec.md) "Show and restore any version of a vault file or folder") on its History tab. There MUST be no index, reindex, check-sources, update-source or embedding-configuration endpoint, no curate or undo-pass endpoint, no settings endpoint for the cwd-derived scope axis "Derive no boundary from the working directory" forbids, and no per-agent reach endpoint or enabled switch for this kind (see "Serve every collection to every agent"). Collection deletion goes through the Resource framework (`DELETE /api/v1/resources/{uid}`). There MUST be no command group for knowledge and no `coffer path` target for it: a collection's documents are plain files, so agents and people read, edit and delete them directly under the knowledge root that the `coffer-guide` skill names (see "Treat a direct file edit as a complete change").

#### Scenario: no knowledge command group or path target exists
- **GIVEN** the `coffer` command tree
- **WHEN** it is enumerated, and `coffer path` is run with a `knowledge` target
- **THEN** there is no `knowledge` command group, and `coffer path` refuses `knowledge` as an unknown target

#### Scenario: the routes are the web UI's, with no material or create-at-path route
- **GIVEN** the daemon's route table under `/api/v1/knowledge`
- **WHEN** it is enumerated
- **THEN** it offers create a collection, list a level, read, upload, delete a document, the changes feed and restoring a delete, rewrite a description, and the tidy-all hand-off
- **AND** it carries no route that saves a document, no history, version or version-restore route, no `/material` route, no curate route, no undo route, no route that creates a document at a path, and no index, reindex, source, embedding, scope or reach endpoint

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
The web UI MUST present a collection as **one tree** of its documents — no lanes, no tabs, no filter or retrieval box — with the chosen document in the pane beside it, the same two panes a skill's Files tab is. The tree MUST name every collection, folder and document by its name on disk: a collection has no title (see "Name a collection by its folder and edit its description in place"). Its **Collections** header strip MUST carry **New collection** (a name and what belongs in it; the collection reaches every agent through the coffer-guide skill). The tree MUST show no hidden entry, and no collection or folder carries a document count. Knowledge calls its files **documents** everywhere (memory keeps *notes*).

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
