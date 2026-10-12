## RENAMED Requirements

- FROM: `### Requirement: Show a collection as one tree of read-only documents in the web UI`
- TO: `### Requirement: Show a collection as one tree of read-only documents in the web UI (before a tidy became one change)`

## REMOVED Requirements

### Requirement: Hand a check to the agent
**Reason**: Tidy is the one hand-off. Its prompt carries the mechanical findings a check prompt carried, and it tells the agent to leave alone what it is unsure of and list it in its report, which is what a report-only check was for. A person who wants only a review says so to the agent the Tidy prompt started, and the guide tells the agent to change nothing then. See ADR `tidying-knowledge-is-the-agents-job`.
**Migration**: `check_handoff` is gone from the collection read and **Check with agent** from the collection page. The marker of "a collection read carries its check hand-off" moves to "the tidy hand-off carries the findings and the tidy commands" under "Hand a tidy to the agent".

### Requirement: Show a collection as one tree of read-only documents in the web UI (before a tidy became one change)
**Reason**: A MODIFIED block cannot drop or rename a scenario, and this requirement loses "a collection page shows its properties" (the Pages / Sources / Folder rows, the Check section and Check with agent) and "the page's one primary action is Upload" (Upload moved into the Add menu). It is renamed out of the way, removed, and added again under its own title (see ADDED below).
**Migration**: "a collection page shows its properties" becomes "the collection page shows a summary line, its to-do list, its contents and its change log"; "the page's one primary action is Upload" becomes "the Add menu says what each entry keeps in Coffer", under "Add documents and collections from one Add menu".

## MODIFIED Requirements

### Requirement: Carry title, description and actor in frontmatter
Every source MUST carry YAML frontmatter with `title`, `description`, `actor` (`agent` | `user`), `created_at` and `updated_at`; those are the keys Coffer writes. A page carries `title`, `type`, `description`, `sources`, `aliases`, `actor`, `created_at` and `updated_at`, and may carry `verified: YYYY-MM-DD`, when it was last checked against its sources or the code, all written by whoever writes the page as the guide teaches; Coffer writes no page. A page's read MUST return its `verified` value as written, empty when it has none. Any other key a person put in a file MUST be kept, in place and with its value unchanged, whenever Coffer rewrites the file — a file is the person's as much as Coffer's.

#### Scenario: frontmatter carries title, description and actor
- **GIVEN** an empty `shopee` collection
- **WHEN** material is submitted into it with a title, a description and `actor` `user`
- **THEN** the source's YAML frontmatter holds `title`, `description`, `actor`, `created_at` and `updated_at`, carries the title and the actor it was given, and the body follows the fence unchanged

### Requirement: Teach writing and tidying in the guide
The `coffer-guide` skill MUST teach the agent that reads it to do the judgement Coffer does not do for it. Its knowledge sections MUST describe the layout — the README as the schema whose page types and conventions win over the guide's defaults, kept `sources/` and edited `pages/` — and carry **Writing a page** — put a durable fact straight into the collection's pages with the agent's own file tools, by these rules: find the fact's home (fold it into the page that owns the subject, and create a page under `pages/` only when none does), lose nothing, organise by subject and never by provenance, let the newer statement win unless the older one is shown to be right while keeping the superseded one legible, link other pages by `[[slug]]` and never by path, keep links whole when renaming a page (update the links to it, or keep its old slug in `aliases`), never edit a source except to mark it `ingest: skipped`, and give every page frontmatter with a `title`, a `type` (by default one of `concept`, `entity`, `how-to`, `decision` and `overview`), a `description` saying what question the page answers, the `sources` it draws on, any `aliases`, when it was last checked against its sources or the code as `verified: YYYY-MM-DD`, and `actor: agent`; where a page's facts came from belongs in `sources` and `verified`, never in a paragraph of the body listing what was read; **Integrating sources** — read each waiting source in full, fold what it says into the pages that own its subjects, create pages for subjects with none, add the source's slug to each such page's `sources`, and mark a source with nothing worth keeping `ingest: skipped`; and **Tidying a collection** — one collection at a time: run `coffer knowledge tidy-start <collection>` before changing anything, integrate its waiting sources, fix the mechanical findings the prompt lists or `coffer knowledge check <collection>` prints, read the README and the pages, merge pages that answer the same question, split one that answers several, correct what is wrong, stale or contradictory, give a subject mentioned across pages but owned by none a page of its own, leave alone what it is not sure about — two pages that disagree with nothing to tell which is right, a deletion of much text, a change to the README's page types — and list it in its report, then run `coffer knowledge tidy-finish <collection> --set summary="<report>"` with a report of the sources integrated or skipped, what was merged, split, corrected and deleted, and what is left for the developer to decide; asked only for a check or a review, it reports what it would do and changes nothing. There MUST be no separate checking section. The skill's resident description MUST name writing, tidying and checking knowledge, so an agent asked to organise knowledge (整理知识) recognises the skill. These sections MUST be present only while the `knowledge` feature is on.

#### Scenario: the rendered guide carries the writing and tidying sections
- **GIVEN** a vault with one collection and the `knowledge` feature on
- **WHEN** the guide skill is rendered
- **THEN** its body carries "Writing a page", "Integrating sources" and "Tidying a collection" sections and no "Checking a collection" section
- **AND** its frontmatter description names writing, tidying and checking knowledge

#### Scenario: the writing section states the six rules
- **GIVEN** the rendered guide body
- **WHEN** the "Writing a page" section is read
- **THEN** it tells the agent to fold a fact into the page that owns its subject, to lose nothing, to organise by subject and never by provenance, that the newer statement wins unless the older is shown to be right, to link pages by `[[slug]]` and never by path and keep links whole on a rename, never to edit a source, and to give every page a title, a type, a description, its sources, any aliases, a `verified` date and `actor: agent`

#### Scenario: the writing and tidying sections are absent while knowledge is off
- **GIVEN** the `knowledge` feature switched off
- **WHEN** the guide skill is rendered
- **THEN** none of "Writing a page", "Integrating sources" and "Tidying a collection" appears in the body, and the description does not name tidying knowledge

### Requirement: Hand a tidy to the agent
Tidy MUST be the one hand-off of a collection's maintenance: there is no separate report-only check. A collection's read MUST carry `tidy_handoff`: a prompt the daemon writes, from the same hand-off module every other hand-off uses, that names the collection, gives its absolute path, its page count, its waiting-source count and its mechanical findings (see "Check a collection mechanically on every read") — at most 40 lines, then how many were left out — and tells the agent, by the `coffer-guide` sections "Integrating sources" and "Tidying a collection", to run `coffer knowledge tidy-start <collection>` before changing anything, to integrate the waiting sources, then fix the mechanical findings, then merge, split and correct the pages, to leave alone anything it is not sure about and list it in its report, and to finish with `coffer knowledge tidy-finish <collection>` carrying that report (see "Record a tidy as one change"). `GET /api/v1/knowledge/tidy-handoff` MUST return the same kind of prompt for every collection at once: it asks the agent to work through the collections one at a time by those two sections and the same steps, tells it to read each collection's findings with `coffer knowledge check <collection>`, and carries the knowledge root's absolute path and one fact line per collection with its name, absolute path, page count, waiting-source count and finding count. The web UI MUST offer a **Tidy** button on a collection's page and a **Tidy all** button in the Knowledge page's header, which uses that route. Pressing either MUST start the hand-off agent in the person's preferred terminal with that prompt sent at once, as [web-ui](../web-ui/spec.md) "Hand a machine-dependent problem to an agent with one split button" says, and leave the page where it is. When no managed agent is available the button MUST offer **Copy prompt** only. Nothing MUST tidy unattended: Coffer starts no agent run of its own, and a collection is tidied only when a person presses Tidy or asks their own agent to.

#### Scenario: a collection read carries its tidy hand-off
- **GIVEN** a `shopee` collection holding pages and a waiting source
- **WHEN** the collection is read
- **THEN** its `tidy_handoff` prompt names `shopee`, carries the collection's absolute path under the knowledge root and its one waiting source, and names the "Integrating sources" and "Tidying a collection" sections of `coffer-guide`

#### Scenario: the tidy hand-off carries the findings and the tidy commands
- **GIVEN** a `shopee` collection with a page holding a dead link
- **WHEN** the collection is read
- **THEN** its `tidy_handoff` prompt carries the collection's absolute path and the dead link with its page and target, and names `coffer knowledge tidy-start <collection>` and `coffer knowledge tidy-finish <collection>`
- **AND** the read carries no `check_handoff`

#### Scenario: the knowledge tidy-all hand-off names every collection
- **GIVEN** two collections, `shopee` with three pages and `personal` with one
- **WHEN** `GET /api/v1/knowledge/tidy-handoff` is read
- **THEN** the prompt names the "Integrating sources" and "Tidying a collection" sections of `coffer-guide` and asks for the collections to be worked through one at a time
- **AND** it carries the knowledge root's absolute path and one fact line each for `shopee` (its path, 3 pages) and `personal` (its path, 1 page), each with its waiting-source and finding counts

#### Scenario: Tidy all sends the prompt like Tidy does
- **GIVEN** the Knowledge page header and a managed agent available
- **WHEN** the user presses Tidy all
- **THEN** the hand-off agent starts in the preferred terminal with the all-collections prompt sent once, and the page stays where it is
- **AND** with no managed agent available the button offers Copy prompt only

#### Scenario: Tidy sends the prompt to the default managed agent at once
- **GIVEN** a collection page and a managed agent available
- **WHEN** the user presses Tidy
- **THEN** the hand-off agent starts in the preferred terminal with the collection's tidy prompt sent once, and the page stays where it is

#### Scenario: Tidy offers only Copy prompt with no managed agent
- **GIVEN** a collection page and no managed agent available
- **WHEN** the user presses Tidy
- **THEN** the page offers Copy prompt carrying the collection's tidy prompt and starts no terminal

### Requirement: Sweep the knowledge root on its mechanical duties
The daemon MUST run a **knowledge sweep** on a recurring timer, and the sweep MUST do exactly these things and call no model: adopt every file sitting in a collection's `.inbox/` as a source (see "Adopt a file dropped into the inbox"); file every Markdown document left in a collection outside `pages/`, `sources/` and hidden entries, other than the root `README.md`, and untouched for a minute, into `pages/` at the same relative path, suffixed on a collision, as one commit by the daemon that rewrites no content; commit every change found on disk under `knowledge/` as an edit on disk, so a person's editor or an agent's file tools is never counted as Coffer's (see "Commit every knowledge write naming its writer"), except in a collection an agent is tidying, whose edits wait for the tidy to close (see "Record a tidy as one change"); close every tidy whose collection has sat unchanged for 30 minutes; and re-render and re-seed the `coffer-guide` skill so a page added by hand is catalogued. The sweep MUST NOT hold the vault against a sync round: whatever it writes goes through the vault's ordinary writer. While the `knowledge` feature is switched off the sweep MUST skip its rounds ([experimental-features](../experimental-features/spec.md) "Close the knowledge feature's surfaces").

#### Scenario: a sweep catalogues a document added by hand
- **GIVEN** a collection and a Markdown page a person adds under its `pages/` in their own editor
- **WHEN** the knowledge sweep runs
- **THEN** the page is committed as an edit on disk and the re-rendered guide's catalogue lists it

#### Scenario: a sweep promotes a file dropped into the inbox
- **GIVEN** a Markdown file dropped into `shopee/.inbox/`
- **WHEN** the knowledge sweep runs
- **THEN** the file is a source under `shopee/sources/` and `.inbox/` no longer holds it

#### Scenario: a sweep files a loose document into pages
- **GIVEN** a collection holding `infra/cache.md` and `notes.md` outside `pages/` and `sources/`, both untouched for over a minute, and a `README.md` at its root
- **WHEN** the knowledge sweep runs
- **THEN** they are `pages/infra/cache.md` and `pages/notes.md` with their text unchanged, moved in one commit by the daemon, and the README has not moved

#### Scenario: a sweep runs while a sync round waits
- **GIVEN** a sync round that waits for a person and a file in an inbox
- **WHEN** the knowledge sweep runs
- **THEN** it does not wait for the round, and the file is adopted through the vault's ordinary writer

#### Scenario: a switched-off knowledge feature skips the sweep
- **GIVEN** the `knowledge` feature switched off and a file in an inbox
- **WHEN** the sweep's timer fires
- **THEN** nothing is adopted, moved, committed or re-rendered, and the collections stay on disk untouched

### Requirement: Treat a direct file edit as a complete change
Writing, editing or deleting a page directly in the collection's tree — by a person in their own editor, or by an agent with its own file tools — MUST remain a complete way to change knowledge: no import, no registration, no conversion step, and the change is live on the very next read. The change MUST be committed to the vault as an edit found on disk, by the sweep or by the next Coffer write, whichever comes first (see "Sweep the knowledge root on its mechanical duties"), unless an agent has a tidy of that collection open: then it is committed with the rest of the tidy when the tidy closes (see "Record a tidy as one change"). Ingestion is an additional entrance, never a required one.

#### Scenario: an agent's new document is live at once and committed as a disk edit
- **GIVEN** a `shopee` collection and an agent that writes a Markdown page into its `pages/` with its own file tools
- **WHEN** the page is read before any sweep, and the knowledge sweep then runs
- **THEN** the read returns the agent's text with no import step in between
- **AND** the sweep commits the page as an edit found on disk

### Requirement: Follow edits across collections in one feed
The system MUST serve one feed of the recent changes to knowledge across every collection, newest first, paged by an opaque cursor ([resource-framework](../resource-framework/spec.md) "Page growing lists by an opaque cursor") and filterable to one collection: every page or source a person or an agent wrote, restored, filed or deleted, every tidy, and every change from sync or from disk — each with its writer, its operation, its summary, its time, its collection and, for each file it touched, whether that file was added, changed or removed and how many lines were added and removed. A tidy is listed as one change whose operation is `tidy`, whose summary is the agent's report and whose `status` is `reported`, or `expired` when Coffer closed it (see "Record a tidy as one change"); an Undo carries the version it undid in `undoes`. A change an earlier version of Coffer made as a curation pass is listed with its writer. One change MUST be readable in full — every file it touched with its diff. The feed is `GET /api/v1/knowledge/changes`, the route a delete's Undo reads to find the delete it restores (see "Undo a knowledge delete from its toast") and the one a collection page's **Change log** reads (see "Show a collection as one tree of read-only documents in the web UI").

#### Scenario: recent changes lists edits across collections
- **GIVEN** a person's upload in one collection and an agent's edit on disk in another
- **WHEN** the feed is read, and read again filtered to one collection
- **THEN** both changes are listed newest first with their collections, writers and per-file line counts
- **AND** the filtered read holds only that collection's changes, and one change read in full carries each file's diff

### Requirement: Commit every knowledge write naming its writer
Every accepted write to a collection MUST be a git commit naming its writer ([Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer](../../../docs/decisions/every-vault-write-is-a-validated-commit-naming-its-writer.md)). The commits are the vault repository's, under `knowledge/`: the knowledge root keeps no repository of its own. A person's upload, description edit, delete, Undo of a delete or Undo of a tidy names the user; material kept on arrival names whoever submitted it — the user, or, for a file an agent dropped into the inbox, the actor the file reports; a tidy names the agent (see "Record a tidy as one change"); a loose document the sweep files into `pages/` names the daemon; a change that arrives through vault sync names sync; and a change any other writer made in the tree — a person's own editor, an agent's file tools outside a tidy — MUST be committed as an edit on disk before Coffer's next commit, so it is never counted as Coffer's. A commit an earlier version of Coffer made as a curation pass stays in the history under its writer. A file's history is read, and an earlier version restored as a new commit, in its history drawer ([vault-storage](../vault-storage/spec.md) "Show and restore any version of a vault file or folder"). The vault is a git repository on every machine that runs Coffer ([vault-storage](../vault-storage/spec.md) "Keep the vault a git repository whether or not it syncs"); a read of the changes feed git cannot answer MUST answer 503 `KNOWLEDGE_HISTORY_UNAVAILABLE` while every write keeps working. git is looked for on every read, so one removed while the daemon runs is answered the same way. When the cause is that git is not installed, the refusal's details MUST carry `reason: "git_missing"` and `handoff`, a prompt asking the person's agent to install git on this machine — naming its OS and architecture and what needed git — the way that fits the machine, confirming it with `git --version`; neither the prompt nor the error's message may name an install command.

#### Scenario: knowledge writes are commits naming their writers
- **GIVEN** a source that an upload created for the user, that an agent then edited on disk
- **WHEN** the user then uploads another document and the vault's commits under `knowledge/` are read
- **THEN** the first source's commits name the user and then an edit on disk, and the second upload's commit holds only the new source and names the user

#### Scenario: an edit on disk becomes a commit of its own
- **GIVEN** a page a person edits in their own editor, outside Coffer
- **WHEN** Coffer then makes its next knowledge write
- **THEN** the edited page is committed first as its own edit on disk, and Coffer's commit holds only what Coffer wrote

#### Scenario: no git hands installing it to an agent
- **GIVEN** a machine with no git
- **WHEN** a document is written and the changes feed is then read
- **THEN** the write works and the read is refused `KNOWLEDGE_HISTORY_UNAVAILABLE` with reason `git_missing` and a prompt to install git naming this machine and `git --version`, and neither the prompt nor the message names an install command

### Requirement: Manage knowledge in the web UI and on the command line
People MUST manage knowledge in the web UI, and agents with the `coffer knowledge` commands: creating collections, uploading sources, reading pages and sources and opening them in their editor, reading a file's history and restoring an earlier version, checking a collection, listing its contents, tidying a collection through their agent and undoing a tidy, deleting and undoing a delete, and editing a collection's description. The REST routes under `/api/v1/knowledge` behind those pages serve the web UI and the `coffer knowledge` commands, which call the same routes ([resource-framework](../resource-framework/spec.md) "Offer every management operation on the command line"): a route the web UI does not call MUST NOT exist, except the two a tidying agent calls to open and close its tidy, and there MUST be no route that creates or saves a page at a path — a person's text reaches knowledge through their own editor (see "Treat a direct file edit as a complete change") or as material like every other entrance (see "Promote submitted material at once"). There MUST be no route under `/api/v1/knowledge` that lists a file's versions, diffs a version or restores one: a file's history is read and restored through the vault's routes ([vault-storage](../vault-storage/spec.md) "Show and restore any version of a vault file or folder") in its history drawer. There MUST be no index, reindex, check-sources, update-source or embedding-configuration endpoint, no curate or undo-pass endpoint, no route that fixes a finding, no settings endpoint for the cwd-derived scope axis "Derive no boundary from the working directory" forbids, and no per-agent reach endpoint or enabled switch for this kind (see "Serve every collection to every agent"). Collection deletion goes through the Resource framework (`DELETE /api/v1/resources/{uid}`). The `coffer knowledge` commands MUST list, create, describe and delete collections, read a level of the tree, a collection's check, its contents and the changes feed, upload material, undo a delete, open and finish a tidy (`tidy-start`, `tidy-finish`), undo a tidy (`undo`) and print the tidy hand-off; no command reads, writes or deletes a file's content, and there is no `coffer path` target for knowledge: a collection's files are plain files, so agents and people read, edit and delete them directly under the knowledge root that the `coffer-guide` skill names (see "Treat a direct file edit as a complete change").

#### Scenario: knowledge is managed on the command line, its documents as files
- **GIVEN** the `coffer` command tree
- **WHEN** the `knowledge` group is enumerated, and `coffer path` is run with a `knowledge` target
- **THEN** the group offers collections, create, describe, delete, tree, check, files, changes, restore, undo, tidy-start, tidy-finish and upload, and no command reads, writes or deletes a file
- **AND** `coffer path` refuses `knowledge` as an unknown target

#### Scenario: the routes are the web UI's, with no material or create-at-path route
- **GIVEN** the daemon's route table under `/api/v1/knowledge`
- **WHEN** it is enumerated
- **THEN** it offers create a collection, list a level, read, upload, delete a file, check a collection, list a collection's files, the changes feed, restoring a delete, undoing a change, starting and finishing a tidy, rewrite a description, and the tidy-all hand-off
- **AND** it carries no route that saves a file, no history, version or version-restore route, no `/material` route, no curate route, no route that fixes a finding, no route that creates a file at a path, and no index, reindex, source, embedding, scope or reach endpoint

## ADDED Requirements

### Requirement: Show a collection as one tree of read-only documents in the web UI
The web UI MUST present a collection as **one tree** of its files — no lanes, no filter or retrieval box — with the chosen file in the pane beside it, the same two panes a skill's Files tab is. At a collection's root the tree MUST show its two folders first, labelled **Pages** and **Sources**, then any other entry; each page MUST carry its type's icon and a source the source icon (see "Show a collection's contents by page type"), and a waiting source MUST carry a **Waiting** mark. The tree MUST name every collection, folder and file by its name on disk otherwise: a collection has no title (see "Name a collection by its folder and edit its description in place"). Its **Collections** header strip MUST carry **New collection** (a name and what belongs in it; the collection reaches every agent through the coffer-guide skill). The tree MUST show no hidden entry, and no collection or folder carries a count. The tree MUST come back as the person left it: which collections and folders they opened or closed is kept in the browser, so leaving the page, reloading it or opening it again restores them, and what is on screen is open on the way to it unless they closed it. Knowledge calls its files **pages** and **sources** everywhere.

A file's pane MUST carry no tabs. Its bar MUST name where the file is, then **History** (opening the file's history over the whole Knowledge area, `?history=1` in the address, with the file's versions in the vault, their diffs and **Restore this version…**, [web-ui](../web-ui/spec.md) "Show a vault file's history on a History tab"), a **Preview / Source** switch, **Open in editor** as a visible button, and a ⋯ menu holding **Reveal in Finder**, **Open in Obsidian** when it is installed (see "Open a collection in Obsidian when it is installed") and **Delete**. While the history is open the tree and the file MUST make way for it, so the versions and the diff have the area to themselves; its ✕ or Esc brings the file back. Under a page's title one line MUST give its type, who wrote it and when it was created, **verified <date>** when the page carries `verified`, and its sources, each opening that source and a missing one marked; a page's `[[links]]` MUST render as links that open the file they resolve to, a dead one marked in the danger tone. Inline code MUST read lighter than a code block, and a long path MUST wrap at its `/`. Under a source's title one line MUST say which pages cite it, or that it is waiting. There is no side column. The pane MUST NOT edit the file: a person changes it in their own editor and an agent with its own file tools (see "Treat a direct file edit as a complete change"), and the next read shows the change.

A collection's page MUST show, under a pane bar carrying **Tidy** (see "Hand a tidy to the agent") and a ⋯ menu, its folder name as its heading, its description edited in place (see "Name a collection by its folder and edit its description in place"), and **one summary line** — how many pages, how many sources with how many wait, the folder's path with a copy button, and when it was last updated — then a muted line saying the collection is managed by Coffer: synced to the person's other Macs, its history kept, tidied by their agent. While an agent has a tidy of the collection open (`tidy_running`), the page MUST say that an agent is tidying it and that its edits will appear as one change when it finishes (see "Record a tidy as one change"). Below come three sections. **To do** MUST list the collection's findings (see "Check a collection mechanically on every read") grouped by kind, the most severe kind first, each naming the page by its title, with its path on hover, and opening it; the minor kinds — pages without sources and pages nothing links to — MUST be folded into one collapsed row; with nothing found it is one line saying so. **Contents** lists the collection's pages by type and its sources (see "Show a collection's contents by page type"). **Change log** MUST list the collection's changes newest first — what each did, its writer and time, and the files it touched by title, each opening that file at its history — with a tidy shown as one entry (see "Record a tidy as one change"), and **Show more** while more are left. A collection with no pages and no sources shows the same page with one line saying so and how to fill it — upload a source, or drop Markdown files into the folder — and **Reveal in Finder**. The collection's ⋯ menu MUST hold **Reveal in Finder**, **Open in Obsidian** when it is installed, **Copy path**, **Rename…** and **Delete collection…** (see "Delete a document at once, a collection after asking, and offer Undo"). There is no other hand-off button on the page.

The page MUST offer no form that adds a file from a typed title and body: people write in their own editor, agents by writing files, and material arrives through the header's **Add** menu (see "Add documents and collections from one Add menu"). With no collection open, the page shows its collections. The tree and the pane MUST extend to the bottom of the window and scroll inside.

The Knowledge page's title MUST carry the **Experimental** tag ([experimental-features](../experimental-features/spec.md)).

#### Scenario: the viewer shows one tree of documents
- **GIVEN** a collection page whose tree holds a page, a page inside a folder and a waiting source
- **WHEN** the page renders and a page's row is clicked
- **THEN** there is one tree — no lane headings, no filter input — showing Pages and Sources first, both pages and the source with its Waiting mark, and no hidden entry
- **AND** the page's pane carries no tabs, offers History, Preview and Source and Open in editor, and Reveal in Finder and Delete in its ⋯ menu

#### Scenario: a document's history takes the whole knowledge area
- **GIVEN** a page open in its collection's pane
- **WHEN** the user presses History
- **THEN** the page's versions open over the whole Knowledge area, the address carries `history=1`, and neither the page nor the tree is shown beside them
- **AND** closing the history brings the page and the tree back and drops `history=1` from the address

#### Scenario: the tree comes back as the person left it
- **GIVEN** a person who opened two collections and one collection's Sources folder
- **WHEN** they leave the Knowledge page and come back
- **THEN** the same collections and the Sources folder are open, and the Pages folder they never opened is closed
- **AND** a collection they then close is still closed when they come back again

#### Scenario: a page shows its sources and resolves its links
- **GIVEN** a page citing an existing source and a missing one, whose body links one page that exists and one that does not
- **WHEN** it is opened in Preview
- **THEN** the line under its title names both sources, the existing one opening it and the missing one marked
- **AND** the existing link opens the page it names, and the dead link is marked in the danger tone

#### Scenario: a document opens in the person's editor
- **GIVEN** a page open in a collection's pane
- **WHEN** the user chooses Open in editor, and then Reveal in Finder from its ⋯ menu
- **THEN** the daemon is asked to open the page's absolute path and then to reveal it
- **AND** the pane shows the page read-only, with Preview and Source, and its line read from the frontmatter

#### Scenario: the collection page shows a summary line, its to-do list, its contents and its change log
- **GIVEN** a collection holding two pages of different types, a page with a dead link and a page with no sources, and a waiting source
- **WHEN** its page renders
- **THEN** it shows the folder name, the description, one summary line reading its page count, its source count with 1 waiting, its folder path with a copy button and when it was updated, and the line saying it is managed by Coffer
- **AND** To do lists the dead link before the waiting source, each naming its page by title, with the page without sources folded into one collapsed row; Contents shows a card per page type and a Sources card; and the Change log lists the collection's changes
- **AND** the pane bar offers Tidy and no Check with agent, and its ⋯ menu offers Reveal in Finder, Copy path, Rename… and Delete collection…

#### Scenario: a collection's change log opens a file at its history
- **GIVEN** a collection whose change log lists an agent's edit of a page
- **WHEN** the user chooses the page in that row
- **THEN** the page opens at its history

### Requirement: Show a collection's contents by page type
`GET /api/v1/knowledge/collections/{uid}/files` (command `coffer knowledge files`) MUST return every page and source of one collection, read off disk on every call, each with its path, title, description, writer, time, kind (`page`, `source` or `file`), a page's `type` and whether a source waits. A collection's page in the web UI MUST show them under **Contents** as one card per page type — `overview`, `concept`, `entity`, `how-to` and `decision` in that order, then the types the collection's README defines by name, then pages with no type — each card with the type's icon, how many pages it holds and the first few page titles, each opening its page, then how many more; and a **Sources** card listing the sources the same way, a waiting one marked. The tree MUST mark each page with the same icon as its type's card, a page whose type has no icon of its own a generic page icon and an untyped page an untyped icon; a source carries the source icon, and a waiting source keeps its **Waiting** mark.

#### Scenario: a collection lists its pages and sources with their types
- **GIVEN** a `shopee` collection holding a page of type `concept` and a waiting source
- **WHEN** `GET /api/v1/knowledge/collections/{uid}/files` is read
- **THEN** it lists the page with kind `page` and type `concept`, and the source with kind `source`, marked waiting

#### Scenario: the tree marks each page with its type's icon
- **GIVEN** a collection holding an `overview` page, a page of a type the README defines, a page with no type and a waiting source
- **WHEN** the collection is opened in the tree
- **THEN** the overview page carries the overview icon, the custom-typed page the generic page icon, the untyped page the untyped icon, and the source the source icon with its Waiting mark

### Requirement: Record a tidy as one change
A tidy MUST land in a collection's history as **one** change. The agent the Tidy prompt starts opens a tidy with `POST /api/v1/knowledge/collections/{uid}/tidy/start` (`coffer knowledge tidy-start <collection>`) before it changes anything, and closes it with `POST /api/v1/knowledge/collections/{uid}/tidy/finish` (`coffer knowledge tidy-finish <collection>`) whose body carries its report as `summary`. Opening a tidy MUST first commit whatever already changed in the collection as the edit on disk it is, and starting an open tidy again keeps it. While a tidy is open the collection's edits MUST stay uncommitted in the working tree: the vault's scanner, the knowledge sweep and a sync round leave them alone, and a sync round whose incoming changes touch one of those files waits, as it does for any uncommitted edit ([vault-storage](../vault-storage/spec.md) "Keep the last valid version when a hand edit is invalid"). Finishing MUST commit every one of them as one commit by the `agent` writer whose operation is `tidy`, whose summary is the report and whose status is `reported`, and answer that change; a tidy that changed nothing commits nothing and answers `change: null`. Finishing with no tidy open MUST still commit the collection's uncommitted edits as a tidy. The sweep MUST close a tidy whose collection has sat unchanged for 30 minutes, committing what it changed with no report and status `expired`, so no collection stays paused. Which tidies are open lives in the daemon's memory only: a restart forgets an open tidy, and its edits are then committed as ordinary edits on disk. A collection's read MUST carry `tidy_running`. Starting and finishing a tidy are each audited as a `knowledge_edited` event.

A collection page's **Change log** MUST show a tidy as one entry: the agent, the time, its report — or that it was closed without a report — the files it touched by title, collapsed when there are many, and **Undo this tidy…** (see "Undo a tidy"). Edits on disk outside a tidy that follow each other within 10 minutes MUST show as one entry listing their files.

#### Scenario: a tidy's edits land as one change with its report
- **GIVEN** a `shopee` collection holding a committed page
- **WHEN** an agent starts a tidy, edits that page and writes a new one, the vault settles, and the agent finishes the tidy with a report
- **THEN** while the tidy was open the collection read `tidy_running` and neither edit was committed
- **AND** finishing answers one change by the `agent` writer, operation `tidy`, status `reported`, the report as its summary, holding both pages, which is the newest entry of the collection's feed, and the collection no longer reads `tidy_running`

#### Scenario: a tidy shows in the change log as one entry with its report and Undo
- **GIVEN** a collection whose feed holds a tidy that touched three pages, an expired tidy, and two edits on disk five minutes apart
- **WHEN** its page renders
- **THEN** the Change log shows the tidy as one entry naming the agent, its time, its report, its three pages by title and Undo this tidy…
- **AND** the expired tidy reads closed without a report, and the two edits on disk are one entry listing both files

### Requirement: Undo a tidy
`POST /api/v1/knowledge/changes/{version}/undo` (`coffer knowledge undo <version>`) MUST put every file the change touched back as it was just before it: a file the change edited or removed gets its earlier bytes back, and a file it added is removed. The undo MUST be one new commit by the user, operation `restore`, carrying in `undoes` the version it undid, and recorded as a `knowledge_edited` audit event naming the files and any later edits it discarded. When a file has been edited since the change, the undo MUST be refused with `409 KNOWLEDGE_UNDO_CONFLICT` whose details list those files in `documents`, and write nothing, unless the body sets `force: true`. A version that changed no knowledge file, or whose files are already as they were before it, MUST be refused with `400 KNOWLEDGE_NOT_A_CHANGE`. The web UI offers it as **Undo this tidy…** on a tidy's Change log entry: a confirmation names the tidy and how many files go back; when files were edited since, it lists them by title and offers **Undo anyway**, which sends `force`.

#### Scenario: undo a tidy
- **GIVEN** a tidy that edited a page and added another
- **WHEN** the tidy is undone
- **THEN** the edited page holds its text from before the tidy and the added page is gone, as one new change by the user with operation `restore` whose `undoes` names the tidy

#### Scenario: undoing a tidy asks before discarding later edits
- **GIVEN** a tidy that edited a page, which a person edited again afterwards
- **WHEN** the tidy is undone
- **THEN** the undo is refused `KNOWLEDGE_UNDO_CONFLICT` naming the page, and the person's edit is still on disk
- **AND** undoing it again with `force` puts the page back as it was before the tidy

#### Scenario: undoing a tidy whose files changed since asks first
- **GIVEN** a tidy in a collection's Change log, one of whose pages was edited after it
- **WHEN** the user chooses Undo this tidy… and confirms
- **THEN** the dialog names the edited page by title and offers Undo anyway, and nothing is undone until the user chooses it
- **AND** choosing Undo anyway sends the undo with `force`, and the Change log shows the undo

### Requirement: Add documents and collections from one Add menu
The Knowledge page's header MUST carry **Tidy all** and one primary **Add** menu button, and no separate Upload button. Each of its items MUST carry a one-line description saying what it keeps in Coffer: **Upload documents…** — converted to Markdown and kept as sources in the collection the person picks, synced with it — and **New collection…** — kept in Coffer, synced to the person's other Macs, with history, tidied by their agent. Upload MUST accept several files at once, picked or dropped, and list each with its own state — waiting, converting, done, or failed with its reason. A file it will refuse — a ZIP archive, or one over 20 MB — MUST be shown as refused, with its reason, before anything is sent. The files MUST be sent one after another, one per call to `POST /api/v1/knowledge/upload` (see "Bound uploads and leave nothing behind on failure"), each succeeding or failing on its own; a failed one MUST stay in the dialog to be retried; and one toast at the end MUST sum up how many were kept and how many failed.

#### Scenario: the Add menu says what each entry keeps in Coffer
- **GIVEN** the Knowledge page with a page open
- **WHEN** the user opens the header's Add menu
- **THEN** it offers Upload documents… and New collection…, each with its one-line description, and the header carries no separate Upload button
- **AND** no control on the page adds a file from a typed title and body, and the pane offers no Edit

#### Scenario: upload several files at once, each with its own outcome
- **GIVEN** the upload dialog and a collection picked
- **WHEN** the user drops a Markdown file, a PDF the server refuses, a ZIP archive and a file over 20 MB, and uploads
- **THEN** the ZIP archive and the large file are shown refused with their reasons before anything is sent, and are not sent
- **AND** the other two are sent one after another, the Markdown file ends done and the PDF failed with its reason and stays to be retried, and one toast sums up one kept and one failed

### Requirement: Open a collection in Obsidian when it is installed
A collection's folder MUST open as an Obsidian vault with nothing converted: its pages are plain Markdown, a `[[slug]]` link resolves by file name as Obsidian resolves it, and `aliases` frontmatter is the key Obsidian reads. Coffer MUST keep Obsidian's own files out of the collection: `.obsidian/` and every other hidden entry is neither committed, catalogued nor synced (see "Hide every dot-prefixed entry"). Obsidian MUST be among the editors the daemon detects. The web UI MUST offer **Open in Obsidian** in a collection's ⋯ menu and in a file's ⋯ menu only when the daemon detects Obsidian on this machine, opening the collection's folder, or the file, with it.

#### Scenario: Open in Obsidian shows only when Obsidian is installed
- **GIVEN** a collection open in the Knowledge page with a page chosen
- **WHEN** the daemon's detected editors include Obsidian, and then when they do not
- **THEN** with Obsidian detected the collection's and the page's ⋯ menus offer Open in Obsidian, which asks the daemon to open the collection's folder or the page's path with Obsidian
- **AND** without it neither menu names Obsidian
