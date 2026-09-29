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

### Requirement: Cover knowledge management on REST and the CLI
The REST API under `/api/v1/knowledge` and the `coffer knowledge` CLI group MUST cover: create a collection, list one level of a collection at a path, read a document, save an edited document's body (`PUT /file`; `coffer knowledge save`, see "Save a document edited in the web UI"), submit material (`POST /material`; `coffer knowledge write`), upload a document, delete a document, and trigger curation. A person may equally edit a document in their own editor, reached from the page's open-in-editor action, and that edit is live on the next read (see "Keep direct file edits a complete way to change knowledge"). Collection deletion goes through the Resource framework (`DELETE /api/v1/resources/{uid}`). There MUST be no index, reindex, check-sources, update-source or embedding-configuration endpoint, no settings endpoint for the cwd-derived scope axis "Derive no boundary from the working directory" forbids, no per-agent reach endpoint for this kind and no enabled switch (see "Serve every collection to every agent"). These surfaces serve the human and the UI; they are not an agent's retrieval path.

#### Scenario: expose every knowledge operation on both surfaces
- **GIVEN** the daemon's route table and the `coffer knowledge` command group
- **WHEN** both are enumerated
- **THEN** each offers create, list a level, read, save an edited body, submit material, upload, delete a document and trigger curation
- **AND** none is an index, reindex, source, embedding, scope or reach endpoint

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

### Requirement: Deliver the guide as the shared-master link
The skill MUST reach each agent as the **ordinary shared-master link** of [skill-manager](../skill-manager/spec.md) "Deliver a skill as a directory link" — one master folder, one link per agent — and MUST NOT be written into an agent's directory as real bytes. **This too reverses what this requirement used to say.** The rule was that each agent's copy be independent bytes, because a link into a shared master was "a copy this layer cannot re-render, stale or reclaim". Neither half of that is true any more: the master is re-rendered in place at every boot and whenever the catalogue changes, which re-renders every agent's view of it at once; and reclaiming is the skill kind's own per-agent reconciliation against the delivery predicate ([skill-manager](../skill-manager/spec.md) "Reconcile deliveries per agent on every trigger"), which removes one agent's link without touching another's or the master. The text is the same for every agent (see "Serve every collection to every agent"), so per-agent bytes were buying independence nothing asked for while paying for it with a delivery path of this layer's own. Re-rendering MUST happen whenever the catalogue changes — after a curation pass or a promotion, or a collection's creation, rename or deletion, and on every sweep tick so a document a person added by hand is catalogued too — and MUST never raise: a failed render leaves the previous master exactly where it was, and the corpus stays readable at paths a person can still give an agent.

#### Scenario: every agent reaches the guide through the one master folder
- **GIVEN** two registered agents and the `coffer-guide` skill seeded
- **WHEN** each agent's `<config_dir>/skills/coffer-guide` is inspected
- **THEN** each is the ordinary Coffer-managed link into `~/.coffer/skills/coffer-guide/`, not a directory of real bytes
- **AND** a re-render that changes the catalogue changes what both agents read in one write, while narrowing the skill's scope to one agent reclaims only the other agent's link and leaves the master untouched

## REMOVED Requirements

### Requirement: Gate collections with enabled alone
**Reason**: Nobody disables a collection; the layer as a whole is already switched by the experimental-features toggle.
**Migration**: Replaced by "Serve every collection to every agent"; a migration enables every collection stored disabled.

### Requirement: Cover collection management on REST and the CLI
**Reason**: It forbade any route that writes a document; the web UI now saves edited documents.
**Migration**: Replaced by "Cover knowledge management on REST and the CLI", which adds the save operation on REST and the CLI.
