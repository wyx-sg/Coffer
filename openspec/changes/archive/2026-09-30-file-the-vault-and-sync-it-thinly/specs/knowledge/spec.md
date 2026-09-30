## MODIFIED Requirements

### Requirement: Store each collection as one tree of Markdown files
Knowledge MUST be stored as files under `~/.coffer/vault/knowledge/<collection>/` — the knowledge root is the vault's `knowledge/` folder ([vault-storage](../vault-storage/spec.md) "Store state in five classes by nature") — each collection **one tree of Markdown documents** that people and Coffer's curation pass write together. There MUST be no directory division inside a collection that says who may write where. The files are the only copy; the system MUST NOT keep a retrieval index of any kind — no vectors, no sidecar, no FTS5, no chunking, no reindex, no cache — so every answer is read off disk at call time.

#### Scenario: keep no index beside the documents
- **GIVEN** a `shopee` collection holding one document written through Coffer
- **WHEN** the knowledge root is walked, and the document's file is then rewritten on disk by hand
- **THEN** the only files under the collection are the document itself and nothing Coffer derived from it — no index, sidecar or cache file
- **AND** the next read through the service returns the hand-written text, with no reindex step in between

### Requirement: Carry title, description and actor in frontmatter
Every document and every inbox item MUST carry YAML frontmatter with `title`, `description`, `actor` (`agent` | `user`), `created_at` and `updated_at`. Curation writes no stamp into a document: what it last settled is a record of this machine's (see "Run curation on a sweep and on demand", "Settle an item only after its pass completes"). Those five keys are what Coffer writes; any other key a person put in a document MUST be kept, in place and with its value unchanged, whenever Coffer rewrites the file — a document is the person's as much as Coffer's.

#### Scenario: frontmatter carries title, description and actor
- **GIVEN** an empty `shopee` collection
- **WHEN** a document is written into it with a title, a description and `actor` `user`
- **THEN** the file's YAML frontmatter holds `title`, `description`, `actor`, `created_at` and `updated_at`, carries the title and the actor it was given, and the body follows the fence unchanged

### Requirement: Keep direct file edits a complete way to change knowledge
Writing, editing or deleting a document directly in the collection's tree — by a person in their own editor, or by an agent with its own file tools — MUST remain a complete way to change knowledge: no import, no registration, no conversion step, and the change is live on the very next read. The change MUST be committed to the vault as an edit found on disk, and the sweep MUST notice an edited or new document by its content, never by its modification time (see "Run curation on a sweep and on demand") and carry it into the rest of the collection. Ingestion is an additional entrance, never a required one.

#### Scenario: a document edited out-of-band is curated by the next sweep
- **GIVEN** a curated document in `shopee/`, whose file a person then edits in their own editor, by a file manager rather than by Coffer
- **WHEN** the curation sweep runs, with no import or registration step in between
- **THEN** a pass is run over that document as its item, the person's wording is still in it afterwards, and it is recorded as settled with the content the pass left — so the next sweep does not hand it back

### Requirement: Run curation on a sweep and on demand
Passes MUST be run by a **sweep on an interval** and by a manual trigger. The interval is the one global curation interval — the `curate` pass's interval under Settings › General's Coffer's model section, 60 minutes by default ([internal-engine](../internal-engine/spec.md) "Show and change Coffer's model in Settings › General") — and no collection has an interval of its own. Each sweep MUST read the interval afresh rather than capture it at boot, and MUST find a collection's pending items in this order: first every inbox item, oldest first — until it is merged it is knowledge no agent can read — then every document whose content is not what curation last settled (or which curation never settled) and whose newest commit a person or an agent made rather than curation or sync, meaning a person or an agent edited or added it out of band. A modification time never decides: a checkout, a restore from backup or a clock change that moves only times makes nothing pending. A sweep MUST run at most a bounded number of passes per collection, so a freshly migrated vault drains visibly rather than in one long batch. The manual trigger — **Curate now** in the web UI, `coffer knowledge curate <collection>` on the command line — MUST run passes until the collection has nothing pending, in the same order (inbox items oldest first, then documents edited out of band), still **one pass at a time** (see "Run one pass per collection at a time") and each pass still bounded (see "Bound a pass to eight writes"). While it runs it MUST report progress as *n of m*, where *m* is what was pending when it started — readable on the in-flight list ([resource-framework](../resource-framework/spec.md) "Report the passes in flight in one cross-kind read"), which carries the run's *n* and *m*, and announced on the daemon's event stream as each pass finishes — and it MUST stop at the first pass that fails, reporting that pass and leaving the rest pending for the next run or sweep. Given one document, it curates just that document. A trigger arriving while a pass over the collection is in flight is refused with 409, as any other.

#### Scenario: an item is curated once, not on every sweep
- **GIVEN** a document curation has settled
- **WHEN** the sweep looks for work
- **THEN** the document is not owed a pass; and once a person changes its content in their own editor, the change is committed as an edit on disk and the next sweep does owe it one

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

### Requirement: Settle an item only after its pass completes
An item MUST be settled only after its pass completes: merged material is deleted from the inbox, and an edited document is recorded as settled — the content it has when the pass completes, kept in this machine's curation record `~/.coffer/local/curation.json` — while nothing about the document itself changes. Every document curation itself writes MUST be recorded as settled as it is written, and is a commit naming curation, so the sweep does not hand the pass its own output back as an edit. Settling writes nothing into the document, so it can never count as an edit itself. The record is machine-local and never travels: a change another machine's curation made arrives as a sync commit, which is not an edit to carry, and losing the record costs one more pass over each document. A pass that does not complete MUST leave the item as it was, so it is curated later rather than lost. Three ways an item leaves the queue without a completed pass keep it as it stands rather than settle a merge that never happened: no model configured ("Promote material directly when no model is configured"), an item too large for any pass ("Report every pass outcome as a status"), and an item cut off three times in a row ("Bound a pass to eight writes").

#### Scenario: curation merges material into the documents and empties the inbox
- **GIVEN** a collection whose inbox holds two items and an internal connection configured
- **WHEN** a curation pass runs over one of them and writes a document
- **THEN** the document is in the collection's tree, recorded as settled, and the item the pass absorbed is gone from the inbox while the item it was not handed still waits
- **AND** the pass's own write is not handed back by the next sweep as an edit

### Requirement: Promote material directly when no model is configured
With no internal model connection configured, material MUST NOT wait: a submission MUST be **promoted** on the spot into a document at the collection root, as it stands and recorded as settled, and a pass MUST promote every item already in the inbox the same way and report `no_model` with the documents it promoted. Nothing is merged — merging is the model's job — but nothing sits in a hidden directory waiting for a connection nobody configured, where no agent can read it. An edited document needs nothing without a model: it is readable as it stands.

#### Scenario: with no internal model, pending material becomes documents as it stands
- **GIVEN** a collection whose inbox holds two items and no internal model connection at all
- **WHEN** a curation pass is run over it
- **THEN** it reports `no_model` and lists in `promoted` the two documents the items became, each at the collection root with its body as submitted and recorded as settled, and the inbox is empty — material never waits on a connection nobody configured

### Requirement: Never overlap curation with a sync round
A pass and a vault-sync round MUST NOT overlap — both write the vault — so they MUST take the same lock, and a pass MUST be skipped while a conflict or pending confirmation is outstanding ([vault-sync](../vault-sync/spec.md) "Never overlap a curation pass and a round").

#### Scenario: wait for the vault lock before sweeping
- **GIVEN** a curation worker sharing the vault-write lock, with an item pending, while a sync round holds that lock
- **WHEN** the worker's tick starts
- **THEN** no pass runs until the round releases the lock
- **AND** once it is released the pending item is curated

### Requirement: Deliver the catalogue through the coffer-guide skill
The catalogue MUST be carried by Coffer's own skill, `coffer-guide`, which MUST be an ordinary registered `skill` Resource — one master folder, `~/.coffer/derived/skills/coffer-guide/`, one resource, delivered by the predicate and the links every imported skill uses ([skill-manager](../skill-manager/spec.md) "Regenerate Coffer's builtin skill from the build", [skill-manager](../skill-manager/spec.md) "Deliver a skill only where it is enabled and in scope", [skill-manager](../skill-manager/spec.md) "Deliver a skill as a directory link"). This layer contributes the **text** and nothing else: it renders, and the skill kind writes, registers and delivers.

**This reverses what this requirement used to say.** The generated skill was deliberately kept outside the resource framework — written per agent into `<config_dir>/skills/` by this layer, as a file the skill kind knew nothing about — on the grounds that a skill Resource is a bundle a person imports and curates, and no person can keep a bundle level with a catalogue that moves whenever curation runs. That reason has expired: a skill's master folder is now regenerated from the running build at every boot and whenever the catalogue changes ([skill-manager](../skill-manager/spec.md) "Regenerate Coffer's builtin skill from the build"), so "generated" and "registered as a Resource" stopped being alternatives. What the old rule bought was a folder nobody had to maintain; what it cost was a second delivery mechanism with its own writer and its own per-agent copies, invisible on the Skills surface, unreachable by `enabled` or scope, and outside every piece of machinery the skill kind already had — drift verification, repair, reclaim and the audit trail.

The per-agent copies of the retired `coffer-knowledge` delivery MUST be removed rather than left in an agent's skill directory describing a layer whose contract has moved. This layer MUST NOT push anything into a session of its own accord and MUST NOT write into any agent's own memory files: knowledge is pulled. Session-start delivery belongs to [memory](../memory/spec.md), which carries its own budget and its own consent. Coffer's own skill is indistinguishable from an imported one everywhere the skill kind touches it — listed, scoped, enabled, delivered, verified for drift and repaired by the same code — and the only thing that sets it apart is that its master folder is Coffer's to rewrite and its deletion is refused.

#### Scenario: Coffer's own skill is an ordinary skill resource
- **GIVEN** a daemon starting with a collection holding documents
- **WHEN** the boot refresh runs
- **THEN** there is one `coffer-guide` master folder under `~/.coffer/derived/skills/` and one `skill:coffer-guide` resource carrying the `builtin` source, and the skills listing shows it beside the user's imported skills
- **AND** this layer has written nothing into any agent's own skill directory itself, and nothing into any agent's memory files

#### Scenario: migration removes the retired knowledge skill and spares a foreign folder
- **GIVEN** two registered agents, one holding the old generated delivery at `<config_dir>/skills/coffer-knowledge` as a directory of real bytes and the other holding it as a symlink left by the delivery before it, and a third agent whose `skills/coffer-knowledge` is a folder a person put there, which carries neither of the two files the generated delivery always wrote
- **WHEN** the database is upgraded
- **THEN** the first two are gone from those agents' skill directories, so no agent is left holding a manual for a layer whose contract has moved
- **AND** the third is untouched — it is somebody else's skill that happens to share the name, and the sweep only removes what it can positively recognise as Coffer's own: a symlink, or a directory holding both `SKILL.md` and `README.md`

### Requirement: Deliver the guide as the shared-master link
The skill MUST reach each agent as the **ordinary shared-master link** of [skill-manager](../skill-manager/spec.md) "Deliver a skill as a directory link" — one master folder, one link per agent — and MUST NOT be written into an agent's directory as real bytes. **This too reverses what this requirement used to say.** The rule was that each agent's copy be independent bytes, because a link into a shared master was "a copy this layer cannot re-render, stale or reclaim". Neither half of that is true any more: the master is re-rendered in place at every boot and whenever the catalogue changes, which re-renders every agent's view of it at once; and reclaiming is the skill kind's own per-agent reconciliation against the delivery predicate ([skill-manager](../skill-manager/spec.md) "Reconcile deliveries per agent on every trigger"), which removes one agent's link without touching another's or the master. The text is the same for every agent (see "Serve every collection to every agent"), so per-agent bytes were buying independence nothing asked for while paying for it with a delivery path of this layer's own. Re-rendering MUST happen whenever the catalogue changes — after a curation pass or a promotion, or a collection's creation, rename or deletion, and on every sweep tick so a document a person added by hand is catalogued too — and MUST never raise: a failed render leaves the previous master exactly where it was, and the corpus stays readable at paths a person can still give an agent.

#### Scenario: every agent reaches the guide through the one master folder
- **GIVEN** two registered agents and the `coffer-guide` skill seeded
- **WHEN** each agent's `<config_dir>/skills/coffer-guide` is inspected
- **THEN** each is the ordinary Coffer-managed link into `~/.coffer/derived/skills/coffer-guide/`, not a directory of real bytes
- **AND** a re-render that changes the catalogue changes what both agents read in one write, while narrowing the skill's scope to one agent reclaims only the other agent's link and leaves the master untouched

### Requirement: Render the guide skill deterministically
The rendered `SKILL.md` MUST be a **pure function of the running build and the catalogue it is given**: the same build over the same collections MUST produce the same bytes, run after run and machine after machine. Nothing machine-specific may enter it — not an absolute home directory, not a timestamp, not a build path — and the skill's own config MUST likewise carry no timestamp of its generation.

**The reason is no longer convergence, and that changes what the requirement is worth saying.** It used to read "byte-identical on every machine running the same build against the same catalogue", with the hedge doing the real work, because the artifact converged: a purely local difference would have had two vaults overwriting each other's copy forever. It no longer converges at all ([vault-sync](../vault-sync/spec.md) "Withhold derived output in both halves") — every machine renders its own from files that converge plus its own reach, and two machines are *expected* to differ whenever their enabled sets differ, which is exactly what the hedge was excusing. What determinism buys now is local and still worth paying for: an unchanged vault re-rendering to the same bytes is what lets the seed skip the write, so a boot or a curation tick that changed nothing registers nothing, audits nothing and re-delivers nothing ([skill-manager](../skill-manager/spec.md) "Regenerate Coffer's builtin skill from the build") — and it is what makes the `version_hash` in the resource mean "the content moved" rather than "time passed".

The knowledge root MUST still be written in its `~`-relative form whenever it sits in its default place, so a path an agent reads is one a person can retype; a root that is not under the home directory MUST be written out in full, because an accurate path is worth more than a tidy one.

#### Scenario: the rendered skill is byte-identical on two machines
- **GIVEN** the same build and the same catalogue rendered twice, once with the knowledge root at each of two different home directories, and once again with the root outside the home directory
- **WHEN** the two default-placed renderings are compared byte for byte
- **THEN** they are identical, and the knowledge root appears in its `~`-relative form rather than as either home's absolute path
- **AND** the root outside the home directory is written out in full, and the skill's stored config carries no timestamp of when it was generated

### Requirement: Add no table and no directory outside the knowledge root
The knowledge layer MUST NOT add any table to Coffer's databases, and MUST NOT create a directory of its own outside the knowledge root. A collection is a resource file, `resources/knowledge/<name>.json` in the vault, like every other Resource; everything else this layer holds is a file the human can open, but for the one record of this machine's that says what curation last settled (see "Settle an item only after its pass completes").

#### Scenario: a collection is a resources row and a directory, nothing more
- **GIVEN** a database upgraded to head and a knowledge root under a temporary home
- **WHEN** a collection is created and material is submitted into it
- **THEN** no table in the history database is named for knowledge, and the collection is one resource of kind `knowledge`
- **AND** every file the layer wrote lies under the knowledge root, but for this machine's curation record

### Requirement: Report every pass outcome as a status
Every curation outcome MUST be reported as a `status`, and the route that runs a pass MUST answer **200** for each of them, because none is a fault of the request: `ok` when a pass ran and settled its item; `no_model` when no internal connection is configured (see "Promote material directly when no model is configured"); `up_to_date` when nothing is pending, in which case no pass runs and nothing is touched; `too_large` when the item is past the size one pass can hold, with `limit` naming the ceiling; `truncated` when the recursion limit cut the pass off (see "Bound a pass to eight writes"); and `failed` when the pass did not complete. The manual trigger MUST answer with the outcome of each pass it ran, in order, ending at the first `failed`, and `up_to_date` when nothing was pending. The route MUST answer **404** for an unknown collection and **409** while a pass over the same collection is running (see "Run one pass per collection at a time"). A `too_large` item MUST never be shown to the model and MUST never be left pending — left where it was it would be offered to every sweep and refused by every pass: material is promoted to a document as it stands, exactly as the no-model path promotes it, and reported in `promoted`; an edited document, which has nothing to promote, is recorded as settled and reported in `stamped`. Neither changes a word of the item.

#### Scenario: oversized material is promoted as it stands
- **GIVEN** a collection whose inbox holds one item of material longer than the item-size ceiling, and an internal connection configured
- **WHEN** a curation pass runs
- **THEN** it reports `too_large` with `limit` and lists in `promoted` the document the item became, whose body is the material as submitted and which is recorded as settled
- **AND** the model was shown nothing, the inbox is empty and nothing is pending

#### Scenario: an oversized edited document is stamped, not re-offered
- **GIVEN** a document a person edited past the item-size ceiling, owed a pass, and an internal connection configured
- **WHEN** a curation pass runs
- **THEN** it reports `too_large` with `limit` and names the document in `stamped`, and the document's body is exactly what the person wrote, recorded as settled
- **AND** the model was shown nothing and the sweep no longer finds the document pending

#### Scenario: a collection with nothing pending reports up to date
- **GIVEN** a collection holding only documents curation has already seen, and an internal connection configured
- **WHEN** a curation pass is run over it
- **THEN** it reports `up_to_date` with the collection's name and nothing else
- **AND** the model was shown nothing and every document is unchanged

### Requirement: Save a document edited in the web UI
`PUT /api/v1/knowledge/file` MUST replace a document's **body** with the text it is given and keep the document's frontmatter, and MUST take the fingerprint of the file the editor loaded: a file that changed on disk since is refused with `KNOWLEDGE_FILE_CONFLICT` (409) and left untouched. The refusal MUST carry what an editor needs to recover without a second save over the file — `saved: false`, and the document as it is on disk now, its body and its fingerprint — so the page can offer Reload, Compare and Copy my text. The read route MUST carry that fingerprint. The save changes the document's content in a commit naming the user, so the sweep treats it as a person's edit (see "Keep direct file edits a complete way to change knowledge", "Let newer statements win and a person's edit stand"), and an accepted save is a commit naming the user (see "Keep every document's history and undo a pass as a whole"). An inbox item and a path outside a document MUST be refused.

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

### Requirement: Keep every document's history and undo a pass as a whole
Every accepted write to a collection MUST be a git commit naming its writer ([Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer](../../../docs/decisions/every-vault-write-is-a-validated-commit-naming-its-writer.md)). The commits are the vault repository's, under `knowledge/` ([vault-storage](../vault-storage/spec.md) "Show, compare and restore any version of a vault file"): the knowledge root keeps no repository of its own, and the history it kept in one before the vault existed was replayed into the vault's by the one-time upgrade ([vault-storage](../vault-storage/spec.md) "Move an existing home into the vault layout once, on request, reversibly"). A person's save, restore, undo or delete names the user; material promoted on arrival names whoever submitted it — the user, or the agent named by the session's identity; a curation pass is **one commit** naming Coffer's curation and the item it curated — and, for an item an agent wrote, that agent, taken from the `knowledge_written` audit event of the submission; a change that arrives through vault sync names sync; and a change any other writer made in the tree — a person's own editor, an agent's file tools — MUST be committed as an edit on disk before Coffer's next commit, so it is never counted as Coffer's. A document's history MUST list its versions newest first with their writer and time, show the diff of each, and restore any version as a new commit. A pass MUST be undoable **as a whole**: undoing it puts every document it wrote or retired back exactly as it was before the pass, as one new commit naming the user, and does not put the item it consumed back in the inbox; when a later commit changed one of the same documents, the undo MUST be refused naming that document rather than overwrite the later change. Only a curation pass is undone this way — any single version is restored instead. The vault is a git repository on every machine that runs Coffer ([vault-storage](../vault-storage/spec.md) "Keep the vault a git repository whether or not it syncs"); a history read git cannot answer MUST answer 503 `KNOWLEDGE_HISTORY_UNAVAILABLE` while every write keeps working.

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
