## MODIFIED Requirements

### Requirement: Cover knowledge management on REST and the CLI
The REST API under `/api/v1/knowledge` MUST cover: create a collection, list one level of a collection at a path, read a document, save an edited document's body (`PUT /file`, see "Save a document edited in the web UI"), submit material (`POST /material`), upload a document, delete a document, and trigger curation. The `coffer knowledge` CLI group MUST offer `list`, `show`, `add`, `edit`, `rm`, `write` (submit material), `upload` and `curate`. A collection's documents are plain files, so on the command line `coffer path knowledge [<collection>]` prints the absolute path of the knowledge root or of one collection, and the documents are listed, read, edited and deleted on disk; the `coffer knowledge` group carries no command that lists, prints, saves or deletes a document. The web UI's editor saves through `PUT /file`, because a browser page cannot write the disk. A person may equally edit a document in their own editor, reached from the page's open-in-editor action or from that path, and that edit is live on the next read (see "Keep direct file edits a complete way to change knowledge"). Collection deletion goes through the Resource framework (`DELETE /api/v1/resources/{uid}`; `coffer knowledge rm`). There MUST be no index, reindex, check-sources, update-source or embedding-configuration endpoint, no settings endpoint for the cwd-derived scope axis "Derive no boundary from the working directory" forbids, and no per-agent reach endpoint, `scope` command, enabled switch or `enable`/`disable` command for this kind (see "Serve every collection to every agent"). These surfaces serve the human and the UI; they are not an agent's retrieval path.

#### Scenario: expose every knowledge operation on both surfaces
- **GIVEN** the daemon's route table and the `coffer knowledge` command group
- **WHEN** both are enumerated
- **THEN** the routes offer create, list a level, read, save an edited body, submit material, upload, delete a document and trigger curation, and the command group offers exactly `list`, `show`, `add`, `edit`, `rm`, `write`, `upload` and `curate`
- **AND** none is an index, reindex, source, embedding, scope or reach endpoint, and the group has no `enable`, `disable` or `scope` command

#### Scenario: locate a collection's documents from the command line
- **GIVEN** a `shopee` collection holding a document at `shopee/infra/cache.md`
- **WHEN** `coffer path knowledge shopee` runs, and then `coffer path knowledge` with no collection
- **THEN** the first prints the absolute path of the `shopee` directory, under which the document is read at `infra/cache.md`, and the second prints the absolute knowledge root
- **AND** `coffer knowledge` offers no `collections`, `create`, `ls`, `read`, `save` or `delete` command
