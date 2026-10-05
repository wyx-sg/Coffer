## REMOVED Requirements

### Requirement: Manage knowledge in the web UI
**Reason**: The owner decided (2026-10-05) that every management operation a person can do in the web UI or the desktop app has a `coffer` command, so an agent can do it too; the rule that a web UI operation owes no command is withdrawn.
**Migration**: Nothing to migrate: the routes are unchanged and the new `coffer knowledge` commands call them.

## ADDED Requirements

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

