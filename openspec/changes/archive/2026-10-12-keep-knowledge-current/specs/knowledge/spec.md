## ADDED Requirements

### Requirement: Mark a source superseded by the one that replaces it
A source MAY carry `superseded_by: <slug>` naming the newer source that replaces it — a newer version of the same document — added by an agent as it integrates the newer one, or by a person. Coffer MUST derive from it on every read, and record nothing: a page that cites the superseded source and no later source in its chain of replacements (v1 replaced by v2, v2 by v3: a page citing v1 and v3 is current) MUST be a `superseded_source` finding whose target is the cited slug and whose `others` holds the newest source in the chain; a chain that loops stops where it repeats. A superseded source MUST NOT wait, whether or not a page cites it, and a `superseded_by` that names no source MUST be a `missing_source` finding on the source itself. A superseded source stays where it is, and a page MAY still cite it for what used to be true. A source's read MUST carry its replacement resolved as a slug, a path (none when it names no source) and a title. The reasoning is [Knowledge Stays Current Through Flags Coffer Computes and an Agent Clears](../../../docs/decisions/knowledge-stays-current-through-flags-coffer-computes.md).

#### Scenario: a page that leans on a superseded source is flagged
- **GIVEN** sources `design-v1` superseded by `design-v2`, `design-v2` superseded by `design-v3`, and `design-v3`; a page `old` citing only `design-v1`, and a page `current` citing `design-v1` and `design-v3`
- **WHEN** the collection is checked and `design-v1` is read
- **THEN** the only `superseded_source` finding is on `old`, naming `design-v1` and `design-v3` as the newest replacement, and `design-v2` does not wait although no page cites it
- **AND** `design-v1`'s read names `design-v2` as its replacement and carries its summary

### Requirement: Ask for a recheck of a page after the collection's interval
A page MUST be **due a recheck** when its `verified` date is missing, is not a date, or is older than the collection's interval, and each such page MUST be a `stale_page` finding whose target is its `verified` value as written, none when it has none. The interval MUST be the `verify_after_days` key of the collection's README frontmatter, in days: 90 when the README sets none, `0` turns the check off for the collection, and a value that is not a whole number of days or is negative MUST be read as 90. A page due a recheck is flagged, never hidden: it stays in the catalogue and in Contents. A page's read and the files listing MUST carry whether it is due (`stale`). A tidy rechecks it and sets its `verified` to today (see "Teach writing and tidying in the guide"). The reasoning is [Knowledge Stays Current Through Flags Coffer Computes and an Agent Clears](../../../docs/decisions/knowledge-stays-current-through-flags-coffer-computes.md).

#### Scenario: a page not checked for too long is flagged
- **GIVEN** on 2026-10-12 a collection with a page verified 2026-09-01, one verified 2026-06-01 and one with no `verified`
- **WHEN** the collection is checked, then again with `verify_after_days: 200` in its README, then with `verify_after_days: 0`
- **THEN** the first check finds `stale_page` on the page with no date, with no target, and on the page verified 2026-06-01, with that date
- **AND** the second finds only the page with no date, and the third finds none

### Requirement: Start a collection's README with its rules written out
Creating a collection Coffer keeps — and editing the description of one that has no `README.md` — MUST write its `README.md` as frontmatter `verify_after_days: 90`, a heading with the collection's name, its description when it has one, then a **Page types** section listing `overview`, `concept`, `entity`, `how-to` and `decision`, each with one line on what it holds, and a **Rules** section: one subject per page, links by `[[slug]]`, every page's `sources` and `verified`, and what `verify_after_days` does. The defaults are written out so the person sees what they can change; what they change there wins over the guide's defaults (see "Keep the collection README out of the corpus"). The description MUST be read only from before the first `##` section, so a README with no description has none rather than its first rule, and editing the description MUST rewrite or insert that paragraph and keep the sections under it as they are.

#### Scenario: a new collection's README lists its rules
- **GIVEN** a new collection `shopee` with the description "How the shop is built."
- **WHEN** its README is written
- **THEN** it opens with frontmatter `verify_after_days: 90`, the heading `shopee` and the description, and lists the page types `overview`, `concept`, `entity`, `how-to` and `decision`
- **AND** the collection's description is "How the shop is built." and its interval is 90 days

## MODIFIED Requirements

### Requirement: Carry title, description and actor in frontmatter
Every source MUST carry YAML frontmatter with `title`, `description`, `actor` (`agent` | `user`), `created_at` and `updated_at`; those are the keys Coffer writes. An agent or a person MAY add three more to a source, which describe it without changing what it says: `ingest: skipped` (see "Derive which sources wait from the pages that cite them"), `superseded_by: <slug>` (see "Mark a source superseded by the one that replaces it") and `summary`, one or two sentences on what it says. A page carries `title`, `type`, `description`, `sources`, `aliases`, `actor`, `created_at` and `updated_at`, and may carry `verified: YYYY-MM-DD`, when it was last checked against its sources or the code, all written by whoever writes the page as the guide teaches; Coffer writes no page. A page's read MUST return its `verified` value as written, empty when it has none. Any other key a person put in a file MUST be kept, in place and with its value unchanged, whenever Coffer rewrites the file — a file is the person's as much as Coffer's.

#### Scenario: frontmatter carries title, description and actor
- **GIVEN** an empty `shopee` collection
- **WHEN** material is submitted into it with a title, a description and `actor` `user`
- **THEN** the source's YAML frontmatter holds `title`, `description`, `actor`, `created_at` and `updated_at`, carries the title and the actor it was given, and the body follows the fence unchanged

### Requirement: Keep the collection README out of the corpus
A collection's `README.md` MUST sit at the collection root and MUST NOT be listed as a page or a source or counted. It is the collection's schema: its first paragraph before its first `##` section is the collection's description, its frontmatter `verify_after_days` sets how long a page's check holds (see "Ask for a recheck of a page after the collection's interval"), and what it says about the collection's page types and rules MUST take precedence over the guide's defaults, as the guide tells agents (see "Teach writing and tidying in the guide").

#### Scenario: keep the README out of listings, counts and curation
- **GIVEN** a `shopee` collection whose root holds a `README.md` edited after it was created and one page
- **WHEN** the collection is listed, counted and swept
- **THEN** the listing names only the page, the page count is one, and the README is never moved, adopted or catalogued as a page

### Requirement: Create collections only deliberately
A **collection** is one `knowledge` Resource, of one of two sorts: a collection Coffer keeps, which is a top-level subdirectory of the knowledge root, or a linked folder, which is a folder the person keeps elsewhere on this machine (see "Link a folder the person keeps themselves"). Either MUST be created deliberately — through the web UI's **New collection…** or **Link an external folder…**, or the `coffer knowledge create` and `coffer knowledge link` commands over the same routes — and MUST NOT be provisioned by a read, a write, a file an agent wrote, or an agent's working directory. Creating a collection Coffer keeps creates its directory and nothing inside it but its `README.md` (see "Start a collection's README with its rules written out"); linking a folder creates nothing in the folder.

#### Scenario: an unknown collection is an error, never auto-created
- **GIVEN** a knowledge root with no `typo` collection in it
- **WHEN** the web UI's read route is asked for the collection `typo`
- **THEN** it answers 404 and no `typo` directory exists afterwards: a read never provisions a collection

### Requirement: Read a collection's description from its README
A collection's one-line description MUST be the first paragraph of its `README.md` before its first `##` section, where its rules begin, absent when there is none, and MUST be read off disk on every listing. It MUST NOT be stored in the database — not even in the `resources` row's own generic `description` column, which for this kind stays empty: a copy written once and read by nothing is wrong from the first time the person edits the file. It is also what the delivered skill's own description draws on (see "Describe Coffer and the collections' subjects in the skill description"), so a collection that fails to describe itself is a collection an agent never recognises. Each listing MUST also carry when the collection's newest document was written (`updated_at`, absent for a collection holding none), read off the files' times, which is what the Overview's Knowledge tile words as "edited today 13:30".

#### Scenario: a collection lists when its newest document was written
- **GIVEN** a collection holding two documents written at different times, and an empty one
- **WHEN** the collections are listed
- **THEN** the first carries the later document's write time as `updated_at` and the empty one carries none

#### Scenario: the catalogue lists collections with their README description
- **GIVEN** a collection created with the description "First description", whose `README.md` is then edited by hand to open with "Edited by hand."
- **WHEN** the collections are listed
- **THEN** the collection's `description` is the README's first paragraph as edited, not the string the creation call supplied — the description is read off disk on every listing, never out of a row

### Requirement: Teach writing and tidying in the guide
The `coffer-guide` skill MUST teach the agent that reads it to do the judgement Coffer does not do for it. Its knowledge sections MUST describe the layout — the README as the schema whose page types and conventions win over the guide's defaults, kept `sources/` and edited `pages/` — and carry **Writing a page** — put a durable fact straight into the collection's pages with the agent's own file tools, by these rules: find the fact's home (fold it into the page that owns the subject, and create a page under `pages/` only when none does), lose nothing, organise by subject and never by provenance, let the newer statement win unless the older one is shown to be right while keeping the superseded one legible, link other pages by `[[slug]]` and never by path, keep links whole when renaming a page (update the links to it, or keep its old slug in `aliases`), never edit a source except to add `ingest: skipped`, `superseded_by` or `summary`, and give every page frontmatter with a `title`, a `type` (by default one of `concept`, `entity`, `how-to`, `decision` and `overview`), a `description` saying what question the page answers, the `sources` it draws on, any `aliases`, when it was last checked against its sources or the code as `verified: YYYY-MM-DD`, and `actor: agent`; where a page's facts came from belongs in `sources` and `verified`, never in a paragraph of the body listing what was read; and write back what it works out: an answer to the developer's question found by reading a source, the code or a system, which the pages do not already say, goes into the page that owns the subject before the agent finishes, with what it read added to `sources` when it is a source, `verified` set to today, and one line telling the developer what it added — never a guess, an opinion or something true only of that conversation; **Integrating sources** — read each waiting source in full, fold what it says into the pages that own its subjects, create pages for subjects with none, add the source's slug to each such page's `sources`, give the source a `summary`, mark an older source it replaces `superseded_by: <its slug>` and recheck the pages that cite the older one, and mark a source with nothing worth keeping `ingest: skipped`; and **Tidying a collection** — one collection at a time: run `coffer knowledge tidy-start <collection>` before changing anything, integrate its waiting sources, fix the mechanical findings the prompt lists or `coffer knowledge check <collection>` prints, recheck each stale page against its sources or the code and set its `verified` to today (a page it cannot recheck keeps its date and goes into its report), give every source without a `summary` one, read the README and the pages, merge pages that answer the same question, split one that answers several, correct what is wrong, stale or contradictory, give a subject mentioned across pages but owned by none a page of its own, leave alone what it is not sure about — two pages that disagree with nothing to tell which is right, a deletion of much text, a change to the README's page types — and list it in its report, then run `coffer knowledge tidy-finish <collection> --set summary="<report>"` with a report of the sources integrated or skipped, what was merged, split, corrected, rechecked and deleted, and what is left for the developer to decide, ending with **Gaps**: questions the pages cannot answer, subjects mentioned across pages but owned by none, and sources worth finding; asked only for a check or a review, it reports what it would do and changes nothing. There MUST be no separate checking section. The skill's resident description MUST name writing, tidying and checking knowledge, so an agent asked to organise knowledge (整理知识) recognises the skill. These sections MUST be present only while the `knowledge` feature is on.

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
Tidy MUST be the one hand-off of a collection's maintenance: there is no separate report-only check. A collection's read MUST carry `tidy_handoff`: a prompt the daemon writes, from the same hand-off module every other hand-off uses, that names the collection, gives its absolute path, its page count, its waiting-source count and its mechanical findings (see "Check a collection mechanically on every read") — at most 40 lines, then how many were left out — and tells the agent, by the `coffer-guide` sections "Integrating sources" and "Tidying a collection", to run `coffer knowledge tidy-start <collection>` before changing anything, to integrate the waiting sources, then fix the mechanical findings, then merge, split and correct the pages, to recheck every stale page and set its `verified` to today and give every source without a `summary` one, to leave alone anything it is not sure about and list it in its report, and to finish with `coffer knowledge tidy-finish <collection>` carrying that report, which ends with the gaps it found: questions the pages cannot answer and sources worth finding (see "Record a tidy as one change"). `GET /api/v1/knowledge/tidy-handoff` MUST return the same kind of prompt for every collection at once: it asks the agent to work through the collections one at a time by those two sections and the same steps, tells it to read each collection's findings with `coffer knowledge check <collection>`, and carries the knowledge root's absolute path and one fact line per collection with its name, absolute path, page count, waiting-source count and finding count. The web UI MUST offer a **Tidy** button on a collection's page and a **Tidy all** button in the Knowledge page's header, which uses that route. Pressing either MUST start the hand-off agent in the person's preferred terminal with that prompt sent at once, as [web-ui](../web-ui/spec.md) "Hand a machine-dependent problem to an agent with one split button" says, and leave the page where it is. When no managed agent is available the button MUST offer **Copy prompt** only. Nothing MUST tidy unattended: Coffer starts no agent run of its own, and a collection is tidied only when a person presses Tidy or asks their own agent to.

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

### Requirement: Derive which sources wait from the pages that cite them
A page MUST name the sources it draws on in its `sources` frontmatter list, by slug. A source **waits** while no page cites it and its frontmatter sets neither `ingest: skipped` nor `superseded_by` (see "Mark a source superseded by the one that replaces it"); Coffer MUST keep no other record of which sources were integrated. A source's read MUST carry the pages that cite it, whether it waits, what replaces it and its `summary`, and a tree listing MUST mark each waiting source.

#### Scenario: a source waits until a page cites it or it is skipped
- **GIVEN** three sources, `a`, `b` and `c`, a page whose `sources` lists `a`, and `c` marked `ingest: skipped`
- **WHEN** the collection is checked and `a` and `b` are read
- **THEN** only `b` is waiting, `a` names the page that cites it, and the collection reports one waiting source

### Requirement: Check a collection mechanically on every read
Coffer MUST compute a collection's **findings** from its files on every read, keep none of them, and fix none of them: `dead_link` and `ambiguous_link` for each such link, with the page and the target; `duplicate_slug` for a slug or alias two pages share; `orphan_page` for a page no other page links to, when the collection holds two or more pages, except a page whose `type` is `overview`; `incomplete_page` for a page missing `title`, `type` or `description`; `unsourced_page` for a page with no `sources`; `missing_source` for a `sources` entry that names no source, and for a source whose `superseded_by` names no source; `superseded_source` for a page that cites a superseded source and no later source in its chain of replacements (see "Mark a source superseded by the one that replaces it"); `stale_page` for a page due a recheck (see "Ask for a recheck of a page after the collection's interval"); and `waiting_source` for each waiting source (see "Derive which sources wait from the pages that cite them"). The route is `GET /api/v1/knowledge/collections/{uid}/check`, and the collection listing MUST carry its page, source, waiting-source and finding counts.

#### Scenario: a collection's check lists its mechanical findings
- **GIVEN** a collection holding a page with a dead link and no `type`, a second page nothing links to, a page citing a source that does not exist, and a waiting source
- **WHEN** `GET /api/v1/knowledge/collections/{uid}/check` is read
- **THEN** it lists a `dead_link`, an `incomplete_page`, an `orphan_page`, a `missing_source` and a `waiting_source` naming those files
- **AND** no file in the collection changed, and the collection listing carries the same finding count

### Requirement: Merge the manual and the catalogue in the skill body
The skill's **body** MUST be one merged manual: Coffer's own — its one built-in tool, `coffer__search_tools`, and when to reach for it; the tiering contract that makes an unlisted upstream tool still callable; the knowledge root; that Coffer's own logs are read with `coffer log` and located with `coffer path logs`; that a skill's scripts keep their logs, operation journals and temp files under `~/.coffer/skill-data/<skill-name>/` (found with `coffer path skill-data`), never in the skill's own folder or elsewhere in `~/.coffer`, and that files there are deleted after the Skill working files retention window, so durable data does not belong there; that `coffer cli list` lists the command-line tools Coffer manages, what each is for and whether it is ready on this machine; that no Coffer tool waits on a human approval; and what does not belong in knowledge — **followed by** the catalogue: the path of the knowledge root, and, for each collection, its README's path, its pages grouped by `type` with each page's collection-relative path, title and description, and every source with its path and title, marked "(waiting)" while it waits or "(superseded by `sources/<file>`)" when another source replaces it, followed by its `summary`. A linked folder's section MUST instead say that it is a folder the developer keeps with their own tools which Coffer only shares, give its path with the home folder written as `~`, tell the agent to follow the folder's own rules file (`AGENTS.md`, `CLAUDE.md` or `README.md`, the first present at its root) before writing anything in it, or with none to write only the way its notes are already written, say that Coffer's `pages/`, `sources/`, inbox and tidy do not apply there, and list its Markdown notes with their folder-relative paths and titles; the catalogue MUST say that a linked folder is read at its own path, not under the knowledge root. When the catalogue would exceed its budget it MUST first drop the descriptions and summaries and list only the waiting sources, and then list only each collection's counts and the directories to search (a linked folder's note count), saying that it was shortened. It MUST instruct the agent to read those files with its own tools, to grep `sources/` for an exact fact a page does not carry, to write what it learns that is durable straight into the collection's pages, and to integrate, tidy and check a collection when asked (see "Teach writing and tidying in the guide"); a change to a page is carried by the sweep into the vault's history (see "Treat a direct file edit as a complete change"). The manual MUST name no memory directory: an agent reaches memory through its own native memory ([memory](../memory/spec.md) "Deliver no memory into a session"). One skill, not a set: a frontmatter description is resident in every session whether the skill is opened or not, while a body is paid for only when a model reaches for it, so a second skill would spend the resident budget again to describe something most sessions never open.

#### Scenario: the skill body carries the catalogue and the absolute root
- **GIVEN** a collection holding three pages of two types and one waiting source
- **WHEN** the skill is rendered
- **THEN** its body carries each page's collection-relative path, title and description under its type, the waiting source's path and title, and the path of the knowledge root, and it instructs the agent to read those files with its own tools
- **AND** the frontmatter `description` names the collection's subject, taken from the collection's own `README.md`, so a model matching on it has something to match

#### Scenario: the catalogue marks a superseded source and shows summaries
- **GIVEN** a collection holding a source `v1` with a summary whose `superseded_by` names `v2`, and `v2` with a summary of its own
- **WHEN** the catalogue is rendered at full detail
- **THEN** `v1` is listed as superseded by `sources/v2.md`, followed by its summary
- **AND** `v2` is listed with its summary and no mark

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

A file's pane MUST carry no tabs. Its bar MUST name where the file is, then **History** (opening the file's history over the whole Knowledge area, `?history=1` in the address, with the file's versions in the vault, their diffs and **Restore this version…**, [web-ui](../web-ui/spec.md) "Show a vault file's history on a History tab"), a **Preview / Source** switch, **Open in editor** as a visible button, and a ⋯ menu holding **Reveal in Finder**, **Open in Obsidian** when it is installed (see "Open a collection in Obsidian when it is installed") and **Delete**. While the history is open the tree and the file MUST make way for it, so the versions and the diff have the area to themselves; its ✕ or Esc brings the file back. Under a page's title one line MUST give its type, who wrote it and when it was created, **verified <date>** when the page carries `verified`, a **Needs rechecking** mark when the page is due a recheck (with "never checked" when it carries no `verified`), and its sources, each opening that source and a missing one marked; a page's `[[links]]` MUST render as links that open the file they resolve to, a dead one marked in the danger tone. Inline code MUST read lighter than a code block, and a long path MUST wrap at its `/`. Under a source's title one line MUST say which pages cite it, or that it is waiting, and, when another source replaces it, **Superseded by** that source as a link opening it (struck through when `superseded_by` names no source). There is no side column. The pane MUST NOT edit the file: a person changes it in their own editor and an agent with its own file tools (see "Treat a direct file edit as a complete change"), and the next read shows the change.

The page of a collection Coffer keeps MUST show, under a pane bar carrying **Tidy** (see "Hand a tidy to the agent") and a ⋯ menu, its folder name as its heading, its description edited in place (see "Name a collection by its folder and edit its description in place"), and **one summary line** — how many pages, how many sources with how many wait, the folder's path with a copy button, and when it was last updated — then a muted line saying the collection is managed by Coffer: synced to the person's other Macs, its history kept, tidied by their agent. While an agent has a tidy of the collection open (`tidy_running`), the page MUST say that an agent is tidying it and that its edits will appear as one change when it finishes (see "Record a tidy as one change"). Below come three sections. **To do** MUST list the collection's findings (see "Check a collection mechanically on every read") grouped by kind, the most severe kind first, each naming the page by its title, with its path on hover, and opening it — a page citing an outdated source with the source it cites and the title of its newest replacement, under **Pages citing an outdated source**, and a page due a recheck with when it was last checked, or "never checked", under **Pages to recheck**; the minor kinds — pages without sources and pages nothing links to — MUST be folded into one collapsed row; with nothing found it is one line saying so. **Contents** lists the collection's pages by type and its sources (see "Show a collection's contents by page type"). **Change log** MUST list the collection's changes newest first — what each did, its writer and time, and the files it touched by title, each opening that file at its history — with a tidy shown as one entry (see "Record a tidy as one change"), and **Show more** while more are left. A collection with no pages and no sources shows the same page with one line saying so and how to fill it — upload a source, or drop Markdown files into the folder — and **Reveal in Finder**. The collection's ⋯ menu MUST hold **Reveal in Finder**, **Open in Obsidian** when it is installed, **Copy path**, **Rename…** and **Delete collection…** (see "Delete a document at once, a collection after asking, and offer Undo"). There is no other hand-off button on the page. A linked folder's page and its files differ from all of this as "Leave a linked folder to its own tools" says.

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

### Requirement: Show a collection's contents by page type
`GET /api/v1/knowledge/collections/{uid}/files` (command `coffer knowledge files`) MUST return every page and source of one collection, read off disk on every call, each with its path, title, description, writer, time, kind (`page`, `source` or `file`), a page's `type` and whether it is due a recheck (`stale`), and for a source whether it waits, what replaces it (`superseded_by`), its `summary`, how many pages cite it (`cited_count`) and whether it is marked skipped. A collection's page in the web UI MUST show them under **Contents** as one card per page type — `overview`, `concept`, `entity`, `how-to` and `decision` in that order, then the types the collection's README defines by name, then pages with no type — each card with the type's icon, how many pages it holds and the first few page titles, each opening its page, then how many more; and a **Sources** card listing the sources the same way — the waiting ones first, then the current ones, the superseded ones last, struck through and muted — each with its state (waiting, used by N pages, skipped or superseded) and its `summary` under it. The tree MUST mark each page with the same icon as its type's card, a page whose type has no icon of its own a generic page icon and an untyped page an untyped icon; a source carries the source icon, and a waiting source keeps its **Waiting** mark.

#### Scenario: a collection lists its pages and sources with their types
- **GIVEN** a `shopee` collection holding a page of type `concept` and a waiting source
- **WHEN** `GET /api/v1/knowledge/collections/{uid}/files` is read
- **THEN** it lists the page with kind `page` and type `concept`, and the source with kind `source`, marked waiting

#### Scenario: contents shows each source's state and summary, superseded last
- **GIVEN** a collection holding a superseded source `Design v1` with a summary, a current source Release notes with a summary and no page citing it, and a page
- **WHEN** its page renders
- **THEN** the Sources card lists Release notes first, used by 0 pages, with its summary
- **AND** it lists Design v1 after it, marked superseded, with its summary

#### Scenario: the tree marks each page with its type's icon
- **GIVEN** a collection holding an `overview` page, a page of a type the README defines, a page with no type and a waiting source
- **WHEN** the collection is opened in the tree
- **THEN** the overview page carries the overview icon, the custom-typed page the generic page icon, the untyped page the untyped icon, and the source the source icon with its Waiting mark
