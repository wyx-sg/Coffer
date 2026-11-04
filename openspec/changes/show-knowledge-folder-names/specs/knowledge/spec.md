## MODIFIED Requirements

### Requirement: Show a collection as one tree of read-only documents in the web UI
The web UI MUST present a collection as **one tree** of its files — no lanes, no filter or retrieval box — with the chosen file in the pane beside it, the same two panes a skill's Files tab is. At a collection's root the tree MUST show its two folders first, named `pages` and `sources`, then any other entry; each page MUST carry its type's icon and a source the source icon (see "Show a collection's contents by page type"), and a waiting source MUST carry a **Waiting** mark. The tree MUST name every collection, folder and file by its exact name on disk in every interface language, with folder names never translated: a collection has no title (see "Name a collection by its folder and edit its description in place"). Its **Collections** header strip MUST carry **New collection** (a name and what belongs in it; the collection reaches every agent through the coffer-guide skill). A linked folder MUST carry the linked-folder icon in the tree. The tree MUST show no hidden entry, and no collection or folder carries a count. The tree MUST come back as the person left it: which collections and folders they opened or closed is kept in the browser, so leaving the page, reloading it or opening it again restores them, and what is on screen is open on the way to it unless they closed it. Going to another page and coming back through the sidebar MUST return to the collection and document last open, not to the bare landing. Knowledge calls its files **pages** and **sources** everywhere.

A file's pane MUST carry no tabs. Its bar MUST name where the file is, then **History** (opening the file's history over the whole Knowledge area, `?history=1` in the address, with the file's versions in the vault, their diffs and **Restore this version…**, [web-ui](../web-ui/spec.md) "Show a vault file's history on a History tab"), a **Preview / Source** switch, **Open in editor** as a visible button, and a ⋯ menu holding **Reveal in Finder**, **Open in Obsidian** when it is installed (see "Open a collection in Obsidian when it is installed") and **Delete**. While the history is open the tree and the file MUST make way for it, so the versions and the diff have the area to themselves; its ✕ or Esc brings the file back. Under a page's title one line MUST give its type, who wrote it and when it was created, **verified <date>** when the page carries `verified`, a **Needs rechecking** mark when the page is due a recheck (with "never checked" when it carries no `verified`), and its sources, each opening that source and a missing one marked. In every Markdown file, a `[[link]]` and a link by relative path MUST render as links that open the file they resolve to in the Knowledge page, in its own collection, a dead or outside one marked in the danger tone with a tooltip saying which; a web link MUST open in the browser — in the desktop app through the daemon, in the default browser (see [daemon](../daemon/spec.md) "Open web links in the default browser"). HTML a document holds (the tables an imported page keeps as HTML) MUST render sanitised: its structure, links and pictures shown, its scripts, embeds, styles, event handlers and comments dropped, so a document never runs code and a comment never shows as text. A source whose `readable_body` differs from its body (see "Import a Confluence page as a readable source with its attachments") MUST show that in Preview with a note that the file itself is unchanged; Source shows the file as it is. Inline code MUST read lighter than a code block, and a long path MUST wrap at its `/`. Under a source's title one line MUST say which pages cite it, or that it is waiting, and, when another source replaces it, **Superseded by** that source as a link opening it (struck through when `superseded_by` names no source). A source made from an uploaded file MUST also name its original there (see "Keep an upload's original on this Mac only"), and an imported page where it came from — the system, the page as a link, its version and when it was fetched — with **Partial import** when its import left something behind, naming what on hover. A Markdown document's pictures linked by relative path MUST show inline, and a picture file MUST open as the picture (see "Keep the pictures of an upload beside its source"). There is no side column. The pane MUST NOT edit the file: a person changes it in their own editor and an agent with its own file tools (see "Treat a direct file edit as a complete change"), and the next read shows the change.

The page of a collection Coffer keeps MUST show, under a pane bar carrying **Tidy** (see "Hand a tidy to the agent") and a ⋯ menu, its folder name as its heading, its description edited in place (see "Name a collection by its folder and edit its description in place"), and **one summary line** — how many pages, how many sources with how many wait, the folder's path with a copy button, and when it was last updated — then a muted line saying the collection is managed by Coffer: synced to the person's other Macs, its history kept, tidied by their agent. While an agent has a tidy of the collection open (`tidy_running`), the page MUST say that an agent is tidying it and that its edits will appear as one change when it finishes (see "Record a tidy as one change"). Below come three sections. **To do** MUST list the collection's findings (see "Check a collection mechanically on every read") grouped by kind, the most severe kind first, each naming the page by its title, with its path on hover, and opening it — a page citing an outdated source with the source it cites and the title of its newest replacement, under **Pages citing an outdated source**, and a page due a recheck with when it was last checked, or "never checked", under **Pages to recheck**; the minor kinds — pages without sources and pages nothing links to — MUST be folded into one collapsed row; with nothing found it is one line saying so. **Contents** lists the collection's pages by type and its sources (see "Show a collection's contents by page type"). **Change log** MUST list the collection's changes newest first — what each did, its writer and time, and the files it touched by title, each opening that file at its history — with a tidy shown as one entry (see "Record a tidy as one change"), and **Show more** while more are left. A collection with no pages and no sources shows the same page with one line saying so and how to fill it — upload a source, or drop Markdown files into the folder — and **Reveal in Finder**. The collection's ⋯ menu MUST hold **Reveal in Finder**, **Open in Obsidian** when it is installed, **Copy path**, **Rename…** and **Delete collection…** (see "Delete a document at once, a collection after asking, and offer Undo"). There is no other hand-off button on the page. A linked folder's page and its files differ from all of this as "Leave a linked folder to its own tools" says.

The page MUST offer no form that adds a file from a typed title and body: people write in their own editor, agents by writing files, and material arrives through the header's **Add** menu (see "Add documents and collections from one Add menu"). With no collection open, the page shows its collections. The tree and the pane MUST extend to the bottom of the window and scroll inside.

The Knowledge page's title MUST carry the **Experimental** tag ([experimental-features](../experimental-features/spec.md)).

#### Scenario: the viewer shows one tree of documents
- **GIVEN** a collection page whose tree holds a page, a page inside a folder and a waiting source
- **WHEN** the page renders and a page's row is clicked
- **THEN** there is one tree — no lane headings, no filter input — showing `pages` and `sources` first, both pages and the source with its Waiting mark, and no hidden entry
- **AND** the folder names stay `pages` and `sources` when the interface language is Chinese
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

#### Scenario: the sidebar returns to the open document
- **GIVEN** a person reading a document in a collection
- **WHEN** they open another page from the sidebar and then Knowledge again
- **THEN** the same collection and document are open, with the tree expanded to it

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

#### Scenario: to do lists pages on an outdated source and pages to recheck
- **GIVEN** a collection whose check finds a page citing the superseded source `design-v1`, whose newest replacement is Release notes, a page never checked and a page last checked on 2026-05-01
- **WHEN** its page renders
- **THEN** To do lists Pages citing an outdated source with "cites design-v1, replaced by Release notes"
- **AND** it lists Pages to recheck with "never checked" and "last checked 2026-05-01"

#### Scenario: a page due a recheck says so
- **GIVEN** a page that carries no `verified` and is due a recheck
- **WHEN** it is opened
- **THEN** the line under its title carries Needs rechecking and "never checked"

#### Scenario: a superseded source names its replacement
- **GIVEN** a source whose `superseded_by` names Release notes
- **WHEN** it is opened
- **THEN** the line under its title says Superseded by, with Release notes as a link

#### Scenario: a collection's change log opens a file at its history
- **GIVEN** a collection whose change log lists an agent's edit of a page
- **WHEN** the user chooses the page in that row
- **THEN** the page opens at its history
