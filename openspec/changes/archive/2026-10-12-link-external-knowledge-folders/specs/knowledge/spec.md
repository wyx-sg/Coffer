## ADDED Requirements

### Requirement: Link a folder the person keeps themselves
A person MUST be able to link a folder they keep with their own tools anywhere on this machine — an Obsidian vault, say — as a collection, through the Knowledge page's **Add → Link an external folder…** and `coffer knowledge link`, both over `POST /api/v1/knowledge/collections/link` with the folder's absolute path and an optional name. Linking MUST copy nothing into Coffer: the folder stays where it is, the only copy, and the system only shares it with agents. The name MUST default to the folder's own name and is a label, not a directory. A name another collection holds MUST be refused, and a folder already linked MUST be refused under the name it was linked as, both with `409 KNOWLEDGE_COLLECTION_EXISTS`. A folder that does not exist, a path that is not absolute, and Coffer's own home or any folder holding it — the home folder and the disk root included — MUST be refused with `400 KNOWLEDGE_FOLDER_REFUSED`. The link MUST be recorded as one `knowledge` resource whose config is `{"folder": "<absolute path>"}`, filed in the machine-local class under `~/.coffer/local/resources/knowledge/` and never in the vault, so it is never committed or synced ([vault-sync](../vault-sync/spec.md) "Keep machine-local state out of the repository"); on another machine the person links that machine's copy of the folder.

A linked folder MUST be listed with the other collections, carrying `linked`, its Markdown `note_count`, its `rules_file` (the first of `AGENTS.md`, `CLAUDE.md` and `README.md` present at its root, empty when none), its description read from the first paragraph of its own `README.md`, its absolute path and when its newest note was written; a folder that has gone missing MUST list with no notes rather than fail the listing. Every walk of a linked folder MUST skip hidden entries and `node_modules`, and stop at 5000 Markdown files; a file over 2 MB MUST be listed but its content not read into the page. A person who wants to share only part of a large folder links a subfolder. A linked folder MUST appear in the `coffer-guide` catalogue as "Merge the manual and the catalogue in the skill body" says, and the guide MUST be re-rendered when one is linked or disconnected, and by the next sweep after one is renamed.

The link dialog MUST say that the files stay where they are and nothing is copied into Coffer, that Coffer does not sync the folder, tidy it, keep its history or upload into it, and that agents follow its own `AGENTS.md`, `CLAUDE.md` or `README.md`. Its name field MUST follow the folder's name until the person types one, and a linked folder MUST open on the Knowledge page once it is linked. The reasoning is [A Linked Knowledge Folder Is Shared in Place, Read-Only to Coffer, and Recorded Machine-Local](../../../docs/decisions/linked-knowledge-folders-are-read-only-and-machine-local.md).

#### Scenario: a linked folder is listed and shared without being copied
- **GIVEN** a folder outside Coffer's home holding Markdown notes, an `AGENTS.md`, a `README.md` and a hidden `.obsidian/` folder
- **WHEN** it is linked through `POST /api/v1/knowledge/collections/link` with no name
- **THEN** it is listed under the folder's name, marked `linked`, with its four Markdown notes, `AGENTS.md` as its rules file, its README's first paragraph as its description and its absolute path
- **AND** nothing is written under the vault's knowledge root or into the folder, and its resource file lies under `local/resources/knowledge/` naming the folder, with none under the vault's `resources/knowledge/`

#### Scenario: the guide lists a linked folder with its own path and rules
- **GIVEN** a collection Coffer keeps and a linked folder `Work` under the home folder, with an `AGENTS.md` and one note
- **WHEN** the guide skill is rendered
- **THEN** the catalogue carries a section for `Work` marked as a linked folder that gives its path with the home folder written as `~`, tells the agent to follow its own `AGENTS.md`, and lists the note by its folder-relative path and title
- **AND** the rendered text holds no absolute home path, and the skill's description names the folder's subject from its README

#### Scenario: the link dialog says the files stay where they are
- **GIVEN** the Knowledge page
- **WHEN** the user picks Link an external folder… from the Add menu and enters a folder's path
- **THEN** the dialog's note says the files stay where they are, nothing is copied into Coffer, and Coffer doesn't sync it, tidy it, keep its history or upload into it
- **AND** the name follows the folder's name, Link folder sends the folder and the name, and the page opens the linked folder

### Requirement: Leave a linked folder to its own tools
A linked folder MUST be read by Coffer and never written. Coffer MUST NOT upload into it, delete a file from it, edit its description, check it, tidy it, undo or restore anything in it, or keep or show its history, and every route that would do one of these for a linked folder MUST answer `409 KNOWLEDGE_COLLECTION_LINKED` and change nothing. The sweep MUST leave it alone: no inbox adoption, no filing of loose Markdown into `pages/`, no commit of its edits. None of Coffer's wiki rules apply to it — no `pages/` and `sources/`, no page types, no waiting sources, no findings — and the tidy-all hand-off and the changes feed leave it out. Its tree and its files MUST be readable through the same tree and file routes as any collection, by `<name>/<path inside the folder>`, each read carrying the file's and its folder's absolute paths and the note's title (its frontmatter `title`, else its first `# ` heading, else its file name); a hidden entry, or a path that would leave the folder through `..` or a symlink, MUST be refused. Renaming a linked folder MUST change only its label, and deleting its resource — **Disconnect…** in the web UI — MUST stop sharing it and leave every file in the folder where it is. An agent MAY write in a linked folder only by that folder's own rules file, never by the guide's rules for a collection Coffer keeps (see "Teach writing and tidying in the guide").

In the web UI a linked folder's page MUST show its name with an **External** tag and, in place of a collection's summary line, To do, Contents and Change log, its facts under "About this folder": **Location** (its path, with **Reveal in Finder**), **Notes** (its Markdown note count), **Rules file** (or None) and **Managed by** — its own tools; Coffer only shares it with agents and copies, syncs, tidies and records nothing there. The page MUST carry no **Tidy**, and its ⋯ menu MUST hold **Reveal in Finder**, **Open in Obsidian** when it is installed, **Copy path**, **Rename…** and **Disconnect…**, which asks first and says the folder's files stay where they are, and no **Delete collection…**. A linked folder's file MUST open read-only with no **History** and no **Delete**. The upload dialog MUST NOT offer a linked folder.

#### Scenario: a linked folder is read but never written
- **GIVEN** a linked folder `Work` holding notes and a hidden `.obsidian/` folder
- **WHEN** its tree, a note and its files are read, and then a file delete, a check, a tidy start, a description edit and an upload into it are asked for
- **THEN** the reads answer with its visible folders and notes, the note's title and its absolute path, and no hidden entry
- **AND** each of the five answers 409 `KNOWLEDGE_COLLECTION_LINKED`, reading a hidden file is refused, and every file in the folder is byte for byte as it was

#### Scenario: disconnecting a linked folder leaves its files alone
- **GIVEN** a linked folder
- **WHEN** it is renamed through the kind-agnostic update and then deleted
- **THEN** both succeed, no collection is listed afterwards, and every file in the folder is as it was

#### Scenario: a linked folder's page shows who manages it
- **GIVEN** a linked folder `Work` with 12 Markdown notes and an `AGENTS.md`
- **WHEN** its page is opened
- **THEN** its heading carries the External tag, and its facts give its path, 12 Markdown notes, `AGENTS.md`, and that its own tools manage it and Coffer only shares it with agents
- **AND** the page has no Tidy, To do or Contents, reads no check and no change log for it, and its ⋯ menu offers Disconnect… and not Delete collection…

#### Scenario: a linked folder's note has no history or delete
- **GIVEN** a note of a linked folder open on the Knowledge page
- **WHEN** its pane bar and its ⋯ menu are read
- **THEN** there is no History button, and the menu offers no Delete…

#### Scenario: an upload never lands in a linked folder
- **GIVEN** a linked folder open on the Knowledge page
- **WHEN** the user opens Upload documents… from the Add menu and opens its collection picker
- **THEN** the linked folder is not among the collections offered

## MODIFIED Requirements

### Requirement: Store each collection as one tree of Markdown files
Knowledge Coffer keeps MUST be stored as files under `~/.coffer/vault/knowledge/<collection>/` — the knowledge root is the vault's `knowledge/` folder ([vault-storage](../vault-storage/spec.md) "Store state in five classes by nature") — each collection **one tree of Markdown files** that people and agents write together, divided by what a file is (a source or a page, see "Keep sources and pages apart in each collection") and never by who may write it. The files are the only copy; the system MUST NOT keep a retrieval index of any kind — no vectors, no sidecar, no FTS5, no chunking, no reindex, no cache — so every answer, the mechanical check included, is read off disk at call time. A linked folder is the one collection stored elsewhere: its files stay in the folder the person keeps, and Coffer reads them there, with no index either (see "Link a folder the person keeps themselves").

#### Scenario: keep no index beside the documents
- **GIVEN** a `shopee` collection holding one page written through the agent's file tools
- **WHEN** the knowledge root is walked, and the page's file is then rewritten on disk by hand
- **THEN** the only files under the collection are the page itself and nothing Coffer derived from it — no index, sidecar or cache file
- **AND** the next read through the service returns the hand-written text, with no reindex step in between

### Requirement: Create collections only deliberately
A **collection** is one `knowledge` Resource, of one of two sorts: a collection Coffer keeps, which is a top-level subdirectory of the knowledge root, or a linked folder, which is a folder the person keeps elsewhere on this machine (see "Link a folder the person keeps themselves"). Either MUST be created deliberately — through the web UI's **New collection…** or **Link an external folder…**, or the `coffer knowledge create` and `coffer knowledge link` commands over the same routes — and MUST NOT be provisioned by a read, a write, a file an agent wrote, or an agent's working directory. Creating a collection Coffer keeps creates its directory and nothing inside it but an optional `README.md`; linking a folder creates nothing in the folder.

#### Scenario: an unknown collection is an error, never auto-created
- **GIVEN** a knowledge root with no `typo` collection in it
- **WHEN** the web UI's read route is asked for the collection `typo`
- **THEN** it answers 404 and no `typo` directory exists afterwards: a read never provisions a collection

### Requirement: Present knowledge as files on disk
What this layer serves is **files on disk**, and the system MUST describe it as such wherever it is presented: a delivered path is the whole of the access story, because an agent handed the knowledge root reads anything under it with the shell tools it already has. Every collection is served to every agent (see "Serve every collection to every agent"), and nothing about a collection may be presented as a filesystem boundary: a collection has no switch that would hide it from a process that can open the directory. A linked folder is presented the same way, as files at its own absolute path, which its section of the catalogue names (see "Merge the manual and the catalogue in the skill body").

#### Scenario: the guide hands over files to read with the agent's own tools
- **GIVEN** a collection holding one document
- **WHEN** the guide skill's catalogue is rendered
- **THEN** it tells the agent to read each document at `<root>/<collection>/<path>` with its own file tool and names the directory the collection's files live under
- **AND** it names no Coffer tool as the way to read a document

### Requirement: Let only a person delete a document
Deleting a document through Coffer MUST be a person's action, and it MUST be allowed for **any** document in a collection Coffer keeps, whoever wrote it: the tree is the person's as much as an agent's. A linked folder's files are not Coffer's to delete, and the route refuses them (see "Leave a linked folder to its own tools"). The REST route and the web UI MUST offer it, and each deletion through them MUST record a `knowledge_deleted` audit event. A person may equally delete the file itself in the collection's directory under the knowledge root, and the deletion is live on the next read and the next catalogue (see "Treat a direct file edit as a complete change"). Coffer offers no tool that deletes anything.

#### Scenario: delete a document an agent wrote
- **GIVEN** two documents in `shopee/` whose frontmatter `actor` is `agent`
- **WHEN** a person deletes one through `DELETE` on the knowledge route, and removes the other's file from the `shopee` directory under the knowledge root
- **THEN** both files are gone from the tree, and neither is listed or catalogued afterwards
- **AND** a `knowledge_deleted` audit event is recorded for the one deleted through the route

### Requirement: Add no table and no directory outside the knowledge root
The knowledge layer MUST NOT add any table to Coffer's databases, and MUST NOT create a directory or a record of its own outside the knowledge root. A collection Coffer keeps is a resource file, `resources/knowledge/<name>.json` in the vault, like every other Resource. A linked folder is the same resource file filed in the machine-local class, under `~/.coffer/local/resources/knowledge/`, because the folder's path is true of this machine only ([vault-storage](../vault-storage/spec.md) "Store state in five classes by nature"); Coffer MUST create nothing inside a linked folder. Everything else this layer holds is a file the human can open.

#### Scenario: a collection is a resource file and a directory, nothing more
- **GIVEN** a database upgraded to head and a knowledge root under a temporary home
- **WHEN** a collection is created and material is submitted into it
- **THEN** no table in the history database is named for knowledge, and the collection is one resource of kind `knowledge`
- **AND** every file the layer wrote lies under the knowledge root

### Requirement: Serve every collection to every agent
Every collection MUST be named, catalogued and served to **every** agent, a linked folder too, under its own path and with its own rules file (see "Link a folder the person keeps themselves"), and a collection MUST NOT carry the Resource framework's per-agent reach or an enabled switch: the kind declares itself non-toggleable ([resource-framework](../resource-framework/spec.md) "Address every resource by an immutable uid through one kind-agnostic surface"). A collection leaves every agent's delivered skill only by being deleted; for a linked folder that is **Disconnect…**, which leaves its files where they are. A file written under a top-level directory that is not a collection MUST be left alone and MUST NOT be catalogued (see "Adopt a file dropped into the inbox").

#### Scenario: every collection is in every agent's skill
- **GIVEN** two collections, `shopee` and `personal`, both holding documents, one of them stored disabled by an earlier version
- **WHEN** the database is migrated and the guide skill is re-rendered and seeded into its master folder
- **THEN** the master `SKILL.md` names both collections and lists both catalogues
- **AND** a request to disable either collection through the generic resource route is refused and changes nothing

### Requirement: Name a collection by its folder and edit its description in place
A collection MUST carry no title: every surface — the web UI's tree, its pickers and its collection view, and the command palette — MUST show a collection by its folder name (a linked folder by the name it was linked under, the folder's own by default), and the collection routes MUST carry no `title` field. A title sent for a collection through the kind-agnostic update MUST be refused as a validation error, with nothing changed. What a collection is about MUST be its description, the opening paragraph of its `README.md` (see "Read a collection's description from its README"), and the web UI's collection view MUST show it as text that is edited **in place**: choosing it opens it for editing, leaving the field or pressing ⌘Enter saves it, Esc cancels, and a saved edit reports a toast with **Undo**. A save rewrites exactly that paragraph and leaves the rest of the README as it was, as one change naming the user, audited as an edit of the collection, and re-renders the guide skill; Undo puts the previous paragraph back as a change of its own. The route is `PUT /api/v1/knowledge/collections/{uid}/description`, the web UI's own. An empty description MUST be refused. A linked folder's description is read from its own `README.md` the same way, and is not edited through Coffer (see "Leave a linked folder to its own tools"). Creating a collection in the web UI MUST ask for its name and for what belongs in it, both required. The collection's ⋯ menu in the web UI MUST offer **Rename…**, a dialog with the name field that sends the kind-agnostic update (`PATCH /api/v1/resources/{uid}` with the new `name`); the directory of a collection Coffer keeps MUST move with the name, while a linked folder's rename changes only its label and the folder on disk keeps its name; the page MUST stay on the same collection, whose address carries its uid. A refused name — taken by another collection or a folder already there, or not a valid folder name — MUST be shown under the field with the dialog still open and nothing changed.

#### Scenario: a collection carries no title
- **GIVEN** a collection
- **WHEN** it is listed, and a title is then sent for it through the kind-agnostic update
- **THEN** the listing carries its name and no title, and the update is refused as a validation error with the title still empty

#### Scenario: edit a collection's description in place
- **GIVEN** a collection whose README opens with a heading, a paragraph and a section a person wrote under it
- **WHEN** the user edits its description
- **THEN** only the opening paragraph is rewritten, the collection lists the new description, and the edit is one change by the user, audited as an edit of the README
- **AND** an empty description is refused, and the web UI saves on leaving the field, cancels on Esc, and offers Undo in its toast

#### Scenario: rename a collection from its menu
- **GIVEN** a collection open in the web UI
- **WHEN** the user picks Rename… from its ⋯ menu and enters a new name
- **THEN** the kind-agnostic update is sent with that name, the dialog closes, a toast names the new name, the collection list is read again and the page stays on the same collection
- **AND** a name the server refuses is shown under the field and the dialog stays open

### Requirement: Manage knowledge in the web UI and on the command line
People MUST manage knowledge in the web UI, and agents with the `coffer knowledge` commands: creating collections, linking a folder the person keeps themselves (see "Link a folder the person keeps themselves"), uploading sources, reading pages and sources and opening them in their editor, reading a file's history and restoring an earlier version, checking a collection, listing its contents, tidying a collection through their agent and undoing a tidy, deleting and undoing a delete, and editing a collection's description. The REST routes under `/api/v1/knowledge` behind those pages serve the web UI and the `coffer knowledge` commands, which call the same routes ([resource-framework](../resource-framework/spec.md) "Offer every management operation on the command line"): a route the web UI does not call MUST NOT exist, except the two a tidying agent calls to open and close its tidy, and there MUST be no route that creates or saves a page at a path — a person's text reaches knowledge through their own editor (see "Treat a direct file edit as a complete change") or as material like every other entrance (see "Promote submitted material at once"). There MUST be no route under `/api/v1/knowledge` that lists a file's versions, diffs a version or restores one: a file's history is read and restored through the vault's routes ([vault-storage](../vault-storage/spec.md) "Show and restore any version of a vault file or folder") in its history drawer. There MUST be no index, reindex, check-sources, update-source or embedding-configuration endpoint, no curate or undo-pass endpoint, no route that fixes a finding, no settings endpoint for the cwd-derived scope axis "Derive no boundary from the working directory" forbids, and no per-agent reach endpoint or enabled switch for this kind (see "Serve every collection to every agent"). Collection deletion goes through the Resource framework (`DELETE /api/v1/resources/{uid}`). The `coffer knowledge` commands MUST list, create, link, describe and delete collections, read a level of the tree, a collection's check, its contents and the changes feed, upload material, undo a delete, open and finish a tidy (`tidy-start`, `tidy-finish`), undo a tidy (`undo`) and print the tidy hand-off; no command reads, writes or deletes a file's content, and there is no `coffer path` target for knowledge: a collection's files are plain files, so agents and people read, edit and delete them directly under the knowledge root that the `coffer-guide` skill names (see "Treat a direct file edit as a complete change").

#### Scenario: knowledge is managed on the command line, its documents as files
- **GIVEN** the `coffer` command tree
- **WHEN** the `knowledge` group is enumerated, and `coffer path` is run with a `knowledge` target
- **THEN** the group offers collections, create, describe, delete, tree, check, files, changes, restore, undo, tidy-start, tidy-finish and upload, and no command reads, writes or deletes a file
- **AND** `coffer path` refuses `knowledge` as an unknown target

#### Scenario: the routes are the web UI's, with no material or create-at-path route
- **GIVEN** the daemon's route table under `/api/v1/knowledge`
- **WHEN** it is enumerated
- **THEN** it offers create a collection, link a folder, list a level, read, upload, delete a file, check a collection, list a collection's files, the changes feed, restoring a delete, undoing a change, starting and finishing a tidy, rewrite a description, and the tidy-all hand-off
- **AND** it carries no route that saves a file, no history, version or version-restore route, no `/material` route, no curate route, no route that fixes a finding, no route that creates a file at a path, and no index, reindex, source, embedding, scope or reach endpoint

### Requirement: Merge the manual and the catalogue in the skill body
The skill's **body** MUST be one merged manual: Coffer's own — its one built-in tool, `coffer__search_tools`, and when to reach for it; the tiering contract that makes an unlisted upstream tool still callable; the knowledge root; that Coffer's own logs are read with `coffer log` and located with `coffer path logs`; that a skill's scripts keep their logs, operation journals and temp files under `~/.coffer/skill-data/<skill-name>/` (found with `coffer path skill-data`), never in the skill's own folder or elsewhere in `~/.coffer`, and that files there are deleted after the Skill working files retention window, so durable data does not belong there; that `coffer cli list` lists the command-line tools Coffer manages, what each is for and whether it is ready on this machine; that no Coffer tool waits on a human approval; and what does not belong in knowledge — **followed by** the catalogue: the path of the knowledge root, and, for each collection, its README's path, its pages grouped by `type` with each page's collection-relative path, title and description, and its waiting sources with their paths and titles. A linked folder's section MUST instead say that it is a folder the developer keeps with their own tools which Coffer only shares, give its path with the home folder written as `~`, tell the agent to follow the folder's own rules file (`AGENTS.md`, `CLAUDE.md` or `README.md`, the first present at its root) before writing anything in it, or with none to write only the way its notes are already written, say that Coffer's `pages/`, `sources/`, inbox and tidy do not apply there, and list its Markdown notes with their folder-relative paths and titles; the catalogue MUST say that a linked folder is read at its own path, not under the knowledge root. When the catalogue would exceed its budget it MUST first drop the descriptions, and then list only each collection's counts and the directories to search (a linked folder's note count), saying that it was shortened. It MUST instruct the agent to read those files with its own tools, to grep `sources/` for an exact fact a page does not carry, to write what it learns that is durable straight into the collection's pages, and to integrate, tidy and check a collection when asked (see "Teach writing and tidying in the guide"); a change to a page is carried by the sweep into the vault's history (see "Treat a direct file edit as a complete change"). The manual MUST name no memory directory: an agent reaches memory through its own native memory ([memory](../memory/spec.md) "Deliver no memory into a session"). One skill, not a set: a frontmatter description is resident in every session whether the skill is opened or not, while a body is paid for only when a model reaches for it, so a second skill would spend the resident budget again to describe something most sessions never open.

#### Scenario: the skill body carries the catalogue and the absolute root
- **GIVEN** a collection holding three pages of two types and one waiting source
- **WHEN** the skill is rendered
- **THEN** its body carries each page's collection-relative path, title and description under its type, the waiting source's path and title, and the path of the knowledge root, and it instructs the agent to read those files with its own tools
- **AND** the frontmatter `description` names the collection's subject, taken from the collection's own `README.md`, so a model matching on it has something to match

#### Scenario: a catalogue past its budget shortens itself
- **GIVEN** collections whose full catalogue exceeds the budget
- **WHEN** the skill is rendered
- **THEN** the catalogue lists pages without their descriptions, or, past the budget again, each collection's counts and its `pages/` and `sources/` directories, and says the catalogue was shortened and to search those directories

#### Scenario: name one tool, the knowledge root and the log reader in the manual
- **GIVEN** a vault with one collection
- **WHEN** the skill is rendered
- **THEN** its manual names exactly one built-in tool, `coffer__search_tools`, and names none of `coffer__write`, `coffer__recall` and `coffer__diagnose`
- **AND** it names the knowledge root and no memory directory, tells the agent to write durable knowledge into a collection's pages itself, and names `coffer log` and `coffer path logs` as the way to read Coffer's own logs, and `coffer cli list` as the way to learn which command-line tools Coffer manages

#### Scenario: the manual says where a skill's scripts keep their files
- **GIVEN** a vault with one collection
- **WHEN** the skill is rendered, with or without the knowledge and memory features on
- **THEN** its manual says a skill's scripts write their logs, operation journals and temp files under `~/.coffer/skill-data/<skill-name>/`, found with `coffer path skill-data`
- **AND** it says never to write them inside the skill's own folder, that files there are deleted after the Skill working files retention window, and that durable data does not belong there

### Requirement: Show a collection as one tree of read-only documents in the web UI
The web UI MUST present a collection as **one tree** of its files — no lanes, no filter or retrieval box — with the chosen file in the pane beside it, the same two panes a skill's Files tab is. At a collection's root the tree MUST show its two folders first, labelled **Pages** and **Sources**, then any other entry; each page MUST carry its type's icon and a source the source icon (see "Show a collection's contents by page type"), and a waiting source MUST carry a **Waiting** mark. The tree MUST name every collection, folder and file by its name on disk otherwise: a collection has no title (see "Name a collection by its folder and edit its description in place"). Its **Collections** header strip MUST carry **New collection** (a name and what belongs in it; the collection reaches every agent through the coffer-guide skill). A linked folder MUST carry the linked-folder icon in the tree. The tree MUST show no hidden entry, and no collection or folder carries a count. The tree MUST come back as the person left it: which collections and folders they opened or closed is kept in the browser, so leaving the page, reloading it or opening it again restores them, and what is on screen is open on the way to it unless they closed it. Knowledge calls its files **pages** and **sources** everywhere.

A file's pane MUST carry no tabs. Its bar MUST name where the file is, then **History** (opening the file's history over the whole Knowledge area, `?history=1` in the address, with the file's versions in the vault, their diffs and **Restore this version…**, [web-ui](../web-ui/spec.md) "Show a vault file's history on a History tab"), a **Preview / Source** switch, **Open in editor** as a visible button, and a ⋯ menu holding **Reveal in Finder**, **Open in Obsidian** when it is installed (see "Open a collection in Obsidian when it is installed") and **Delete**. While the history is open the tree and the file MUST make way for it, so the versions and the diff have the area to themselves; its ✕ or Esc brings the file back. Under a page's title one line MUST give its type, who wrote it and when it was created, **verified <date>** when the page carries `verified`, and its sources, each opening that source and a missing one marked; a page's `[[links]]` MUST render as links that open the file they resolve to, a dead one marked in the danger tone. Inline code MUST read lighter than a code block, and a long path MUST wrap at its `/`. Under a source's title one line MUST say which pages cite it, or that it is waiting. There is no side column. The pane MUST NOT edit the file: a person changes it in their own editor and an agent with its own file tools (see "Treat a direct file edit as a complete change"), and the next read shows the change.

The page of a collection Coffer keeps MUST show, under a pane bar carrying **Tidy** (see "Hand a tidy to the agent") and a ⋯ menu, its folder name as its heading, its description edited in place (see "Name a collection by its folder and edit its description in place"), and **one summary line** — how many pages, how many sources with how many wait, the folder's path with a copy button, and when it was last updated — then a muted line saying the collection is managed by Coffer: synced to the person's other Macs, its history kept, tidied by their agent. While an agent has a tidy of the collection open (`tidy_running`), the page MUST say that an agent is tidying it and that its edits will appear as one change when it finishes (see "Record a tidy as one change"). Below come three sections. **To do** MUST list the collection's findings (see "Check a collection mechanically on every read") grouped by kind, the most severe kind first, each naming the page by its title, with its path on hover, and opening it; the minor kinds — pages without sources and pages nothing links to — MUST be folded into one collapsed row; with nothing found it is one line saying so. **Contents** lists the collection's pages by type and its sources (see "Show a collection's contents by page type"). **Change log** MUST list the collection's changes newest first — what each did, its writer and time, and the files it touched by title, each opening that file at its history — with a tidy shown as one entry (see "Record a tidy as one change"), and **Show more** while more are left. A collection with no pages and no sources shows the same page with one line saying so and how to fill it — upload a source, or drop Markdown files into the folder — and **Reveal in Finder**. The collection's ⋯ menu MUST hold **Reveal in Finder**, **Open in Obsidian** when it is installed, **Copy path**, **Rename…** and **Delete collection…** (see "Delete a document at once, a collection after asking, and offer Undo"). There is no other hand-off button on the page. A linked folder's page and its files differ from all of this as "Leave a linked folder to its own tools" says.

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

### Requirement: Add documents and collections from one Add menu
The Knowledge page's header MUST carry **Tidy all** and one primary **Add** menu button, and no separate Upload button. Each of its items MUST carry a one-line description saying what it keeps in Coffer: **Upload documents…** — converted to Markdown and kept as sources in the collection the person picks, synced with it — **New collection…** — kept in Coffer, synced to the person's other Macs, with history, tidied by their agent — and **Link an external folder…** — the files stay where they are and are only shared with agents; nothing is copied into Coffer, synced or tidied (see "Link a folder the person keeps themselves"). The upload dialog MUST offer only the collections Coffer keeps, never a linked folder. Upload MUST accept several files at once, picked or dropped, and list each with its own state — waiting, converting, done, or failed with its reason. A file it will refuse — a ZIP archive, or one over 20 MB — MUST be shown as refused, with its reason, before anything is sent. The files MUST be sent one after another, one per call to `POST /api/v1/knowledge/upload` (see "Bound uploads and leave nothing behind on failure"), each succeeding or failing on its own; a failed one MUST stay in the dialog to be retried; and one toast at the end MUST sum up how many were kept and how many failed.

#### Scenario: the Add menu says what each entry keeps in Coffer
- **GIVEN** the Knowledge page with a page open
- **WHEN** the user opens the header's Add menu
- **THEN** it offers Upload documents…, New collection… and Link an external folder…, each with its one-line description, and the header carries no separate Upload button
- **AND** no control on the page adds a file from a typed title and body, and the pane offers no Edit

#### Scenario: upload several files at once, each with its own outcome
- **GIVEN** the upload dialog and a collection picked
- **WHEN** the user drops a Markdown file, a PDF the server refuses, a ZIP archive and a file over 20 MB, and uploads
- **THEN** the ZIP archive and the large file are shown refused with their reasons before anything is sent, and are not sent
- **AND** the other two are sent one after another, the Markdown file ends done and the PDF failed with its reason and stays to be retried, and one toast sums up one kept and one failed
