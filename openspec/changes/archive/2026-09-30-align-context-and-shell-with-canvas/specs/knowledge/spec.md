## ADDED Requirements

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

## MODIFIED Requirements

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
