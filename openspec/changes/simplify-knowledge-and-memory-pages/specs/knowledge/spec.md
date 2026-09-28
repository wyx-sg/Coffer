## ADDED Requirements

### Requirement: Serve every collection to every agent
Every collection MUST be named, catalogued and served to **every** agent, and a collection MUST NOT carry the Resource framework's per-agent reach or an enabled switch: the kind declares itself non-toggleable ([resource-framework](../resource-framework/spec.md) "Address every resource by an immutable uid through one kind-agnostic surface"). A collection leaves every agent's delivered skill only by being deleted. `coffer__write` MUST refuse a write naming a collection that does not exist, and MUST answer with the collections that do.

#### Scenario: every collection is in every agent's skill
- **GIVEN** two collections, `shopee` and `personal`, both holding documents, one of them stored disabled by an earlier version
- **WHEN** the database is migrated and the guide skill is re-rendered and seeded into its master folder
- **THEN** the master `SKILL.md` names both collections and lists both catalogues
- **AND** a request to disable either collection through the generic resource route is refused and changes nothing

### Requirement: Save a document edited in the web UI
`PUT /api/v1/knowledge/file` MUST replace a document's **body** with the text it is given and keep the document's frontmatter, and MUST take the fingerprint of the file the editor loaded: a file that changed on disk since is refused with `KNOWLEDGE_FILE_CONFLICT` (409) and left untouched. The read route MUST carry that fingerprint. The saved file's modification time moves, so the sweep treats it as a person's edit (see "Keep direct file edits a complete way to change knowledge", "Let newer statements win and a person's edit stand"). An inbox item and a path outside a document MUST be refused.

#### Scenario: save an edited body and refuse a stale one
- **GIVEN** a document `shopee/infra/cache.md` read with its fingerprint
- **WHEN** a new body is saved with that fingerprint, and then another body is saved with the same, now stale, fingerprint
- **THEN** the first save rewrites the body, keeps the frontmatter's title and description, and answers with the new fingerprint
- **AND** the second is refused with 409 `KNOWLEDGE_FILE_CONFLICT` and the file still holds the first save's body

## MODIFIED Requirements

### Requirement: Hide dot-prefixed entries except the inbox
Hidden entries (dot-prefixed) MUST be excluded from every count of documents and from the catalogue. The system itself MUST write exactly one: a collection's `.inbox/`, where submitted material waits to be merged (see "Submit every entrance's input as material"). An inbox item MUST be deleted once a pass has merged it or it has been promoted (see "Settle an item only after its pass completes", "Promote material directly when no model is configured"). The tree route MUST list a collection root's `.inbox/` as a directory and its items as files, and the read route MUST read an inbox item, so a person can see what is waiting; no other hidden entry is listed or readable, and no surface may write or delete an inbox item. `.history/` and `.raw/` stay removed; nothing is kept of what a pass replaced or of the document an upload arrived in.

#### Scenario: leave hidden entries out of every listing
- **GIVEN** a `shopee` collection holding one document, one item waiting in `.inbox/`, and a file a person put under `.scratch/`
- **WHEN** the collection is listed, its document count read, its catalogue rendered and its tree requested
- **THEN** the count is one and the catalogue names the one document only
- **AND** the tree lists the document and an `.inbox` directory holding the waiting item, which the read route returns, and nothing from `.scratch/`

### Requirement: Present a collection as one tree in the web UI
The web UI MUST present a collection as **one tree** of its documents — no lanes, no tabs, no filter or retrieval box — with the chosen document in the pane beside it, the same two panes a skill's Files tab is. The pane MUST render the document and offer **Edit**, which turns it into an editor saved through "Save a document edited in the web UI" and reports a conflict in place; open-in-external-editor and reveal-in-file-manager; and delete, naming the exact path before it runs, reporting a refusal in place, and leaving the preview on no file afterwards. The tree MUST show the collection's `.inbox/` as a folder whose items open read-only, with no edit and no delete. The page MUST offer upload into the collection in view and a manual curation trigger that reports a pass already in flight. The tree and the pane MUST extend to the bottom of the window and scroll inside.

#### Scenario: the viewer shows one tree of documents
- **GIVEN** a collection page whose tree holds a document at the root and one inside a folder, with one item of material waiting in the inbox
- **WHEN** the page renders, a document's row is clicked, and then the inbox item's
- **THEN** there is one tree — no lane headings, no tabs, no filter input — listing both documents and an `.inbox` folder holding the item
- **AND** the document offers Edit, open-in-editor, reveal and delete, and the inbox item offers neither Edit nor delete

#### Scenario: edit a document in place
- **GIVEN** a document open in a collection's pane
- **WHEN** the user chooses Edit, changes the text and saves
- **THEN** the save is sent with the fingerprint the pane loaded, and the pane renders the saved body

## REMOVED Requirements

### Requirement: Gate collections with enabled alone
**Reason**: Nobody disables a collection; the layer as a whole is already switched by the experimental-features toggle.
**Migration**: Replaced by "Serve every collection to every agent"; a migration enables every collection stored disabled.
