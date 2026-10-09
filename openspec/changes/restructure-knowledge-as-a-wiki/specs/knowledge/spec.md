## ADDED Requirements

### Requirement: Keep sources and pages apart in each collection
Every collection MUST hold its knowledge in two places: `sources/`, the material that arrived — each upload and each file dropped into the inbox — kept as it came; and `pages/`, the wiki pages people and agents write from it. A Markdown file under `pages/` is a **page**, a Markdown file under `sources/` is a **source**, and any other file is a plain file that is listed but neither catalogued nor checked. The collection's `README.md` is its schema: what belongs in the collection, its page types and its conventions. Agents MUST be told never to edit a source (see "Teach writing and tidying in the guide").

#### Scenario: a collection keeps sources and pages apart
- **GIVEN** a `shopee` collection into which a file is uploaded and in which an agent writes a page
- **WHEN** the collection's tree and its catalogue are read
- **THEN** the upload is a source under `shopee/sources/` and the agent's page is under `shopee/pages/`
- **AND** the catalogue lists the page among the pages and the source among the sources, each read with the kind it has

### Requirement: Keep every upload as a source with its original
An upload MUST be converted to Markdown and kept as a **source**: `sources/<slug>.md` carrying the extracted Markdown with frontmatter, and, unless the upload already was that text (Markdown, plain text and other files read as they stand), its **original file** beside it as `sources/<slug>.<ext>`, named in the source's `original` key. Supported inputs MUST be exactly what the converters accept: what `markitdown` handles (PDF, `docx`, `pptx`, `xlsx`, `xls`, HTML, EPUB), CSV, and text read as it stands (Markdown, plain text, reStructuredText, and source and configuration files such as `py`, `ts`, `sql`, `yaml`, `json`, `log`); an unsupported type MUST be refused with the type named, and nothing is written. An upload takes no folder. A name collision suffixes the Markdown and the original alike.

#### Scenario: an upload is kept as a source with its original
- **GIVEN** a collection and a `team.csv` file
- **WHEN** it is uploaded through `POST /api/v1/knowledge/upload`
- **THEN** the answer is 201 and carries the source's path, the converter that ran, the title and a description
- **AND** the collection holds `sources/team.md` with the extracted Markdown and frontmatter `actor: user` and `original: team.csv`, and `sources/team.csv` with the uploaded bytes

#### Scenario: a Markdown upload is its own source
- **GIVEN** a collection and a `notes.md` file
- **WHEN** it is uploaded
- **THEN** the collection holds one new file, `sources/notes.md`, whose frontmatter carries no `original` key

#### Scenario: an upload of an unsupported type is refused with its reason
- **GIVEN** a collection, and a file whose type no converter handles — `archive.bin` at the service, `payload.exe` at the route
- **WHEN** it is uploaded
- **THEN** the service raises `UnsupportedDocument` and the route answers 400 `INGEST_REJECTED` whose details name `reason` `unsupported_type` and `doc_type` `exe`, and the collection is left with no new file at all

### Requirement: Link pages by slug and check every link
A page's **slug** is its file name without `.md`; its `aliases` frontmatter list gives it more names. A link in a page's body MUST be written `[[target]]` or `[[target|text]]`, outside code, and MUST name a slug or an alias, never a path. Coffer MUST resolve every link when a page is read, against every page's slug and aliases and every source's slug, case-insensitively: a link that names nothing is **dead**, and one that names more than one file is **ambiguous**. A page's read MUST carry each link with the path it resolves to, or none, so the web UI can follow it; a page's `sources` entries MUST be resolved against source slugs the same way.

#### Scenario: a page's links resolve by slug and alias
- **GIVEN** pages `session-ownership` with alias `sessions` and `cache-ttl`, and a page whose body links `[[session-ownership]]`, `[[sessions|the session service]]`, `[[cache-ttl]]` and `[[gone]]`
- **WHEN** that page is read
- **THEN** the first two links resolve to `pages/session-ownership.md`, the third to `pages/cache-ttl.md`, and `gone` resolves to nothing
- **AND** a `[[gone]]` inside a fenced code block is not counted as a link

### Requirement: Derive which sources wait from the pages that cite them
A page MUST name the sources it draws on in its `sources` frontmatter list, by slug. A source **waits** while no page cites it and its frontmatter does not set `ingest: skipped`; Coffer MUST keep no other record of which sources were integrated. A source's read MUST carry the pages that cite it and whether it waits, and a tree listing MUST mark each waiting source.

#### Scenario: a source waits until a page cites it or it is skipped
- **GIVEN** three sources, `a`, `b` and `c`, a page whose `sources` lists `a`, and `c` marked `ingest: skipped`
- **WHEN** the collection is checked and `a` and `b` are read
- **THEN** only `b` is waiting, `a` names the page that cites it, and the collection reports one waiting source

### Requirement: Check a collection mechanically on every read
Coffer MUST compute a collection's **findings** from its files on every read, keep none of them, and fix none of them: `dead_link` and `ambiguous_link` for each such link, with the page and the target; `duplicate_slug` for a slug or alias two pages share; `orphan_page` for a page no other page links to, when the collection holds two or more pages, except a page whose `type` is `overview`; `incomplete_page` for a page missing `title`, `type` or `description`; `unsourced_page` for a page with no `sources`; `missing_source` for a `sources` entry that names no source; and `waiting_source` for each waiting source (see "Derive which sources wait from the pages that cite them"). The route is `GET /api/v1/knowledge/collections/{uid}/check`, and the collection listing MUST carry its page, source, waiting-source and finding counts.

#### Scenario: a collection's check lists its mechanical findings
- **GIVEN** a collection holding a page with a dead link and no `type`, a second page nothing links to, a page citing a source that does not exist, and a waiting source
- **WHEN** `GET /api/v1/knowledge/collections/{uid}/check` is read
- **THEN** it lists a `dead_link`, an `incomplete_page`, an `orphan_page`, a `missing_source` and a `waiting_source` naming those files
- **AND** no file in the collection changed, and the collection listing carries the same finding count

### Requirement: Hand a check to the agent
A collection's read MUST carry `check_handoff`: a prompt the daemon writes, from the same hand-off module every other hand-off uses, that names the collection and its absolute path, carries its mechanical findings, and tells the agent to follow the `coffer-guide` section "Checking a collection" — report contradictions, stale statements, subjects covered twice and subjects that deserve a page of their own — and to change nothing. The collection page MUST offer **Check with agent** beside **Tidy**, sending the prompt the way Tidy does (see "Hand a tidy to the agent").

#### Scenario: a collection read carries its check hand-off
- **GIVEN** a `shopee` collection with a dead link
- **WHEN** the collection is read
- **THEN** its `check_handoff` prompt names `shopee` and its absolute path, carries the dead link, names the "Checking a collection" section of `coffer-guide`, and asks the agent to report and change nothing

## MODIFIED Requirements

### Requirement: Store each collection as one tree of Markdown files
Knowledge MUST be stored as files under `~/.coffer/vault/knowledge/<collection>/` — the knowledge root is the vault's `knowledge/` folder ([vault-storage](../vault-storage/spec.md) "Store state in five classes by nature") — each collection **one tree of Markdown files** that people and agents write together, divided by what a file is (a source or a page, see "Keep sources and pages apart in each collection") and never by who may write it. The files are the only copy; the system MUST NOT keep a retrieval index of any kind — no vectors, no sidecar, no FTS5, no chunking, no reindex, no cache — so every answer, the mechanical check included, is read off disk at call time.

#### Scenario: keep no index beside the documents
- **GIVEN** a `shopee` collection holding one page written through the agent's file tools
- **WHEN** the knowledge root is walked, and the page's file is then rewritten on disk by hand
- **THEN** the only files under the collection are the page itself and nothing Coffer derived from it — no index, sidecar or cache file
- **AND** the next read through the service returns the hand-written text, with no reindex step in between

### Requirement: Use the file path as a document's identity
A file's **path is its identity**, and a page's or a source's **slug** — its file name without `.md` — is the name links use (see "Link pages by slug and check every link"). There MUST be no separate id field in frontmatter and no id-to-path mapping anywhere. File names MUST be human-readable slugs derived from the title; a collision appends a short suffix. Two pages sharing a slug is a finding, not something Coffer resolves (see "Check a collection mechanically on every read").

#### Scenario: name a file by its title and suffix a collision
- **GIVEN** an empty `shopee` collection
- **WHEN** two pieces of material titled `Session Ownership` are submitted
- **THEN** the two sources are `shopee/sources/session-ownership.md` and `shopee/sources/session-ownership-2.md`
- **AND** neither file's frontmatter carries an `id` key

### Requirement: Carry title, description and actor in frontmatter
Every source MUST carry YAML frontmatter with `title`, `description`, `actor` (`agent` | `user`), `created_at` and `updated_at`, and `original` when its original file is kept; those are the keys Coffer writes. A page carries `title`, `type`, `description`, `sources`, `aliases`, `actor`, `created_at` and `updated_at`, written by whoever writes the page as the guide teaches; Coffer writes no page. Any other key a person put in a file MUST be kept, in place and with its value unchanged, whenever Coffer rewrites the file — a file is the person's as much as Coffer's.

#### Scenario: frontmatter carries title, description and actor
- **GIVEN** an empty `shopee` collection
- **WHEN** material is submitted into it with a title, a description and `actor` `user`
- **THEN** the source's YAML frontmatter holds `title`, `description`, `actor`, `created_at` and `updated_at`, carries the title and the actor it was given, and the body follows the fence unchanged

### Requirement: Allow nesting without giving it meaning
Inside `pages/` and `sources/` a collection MAY contain arbitrarily nested subdirectories, and the system MUST NOT assign them meaning or require them: `pages/` and `sources/` are the only directories that mean anything. The nesting is **chosen by whoever files a page** — a person or an agent — and either MAY create, move and remove directories under `pages/`.

#### Scenario: list and catalogue a nested document at its own path
- **GIVEN** a `shopee` collection holding a page a person filed at `shopee/pages/a/b/deep.md`
- **WHEN** the level `shopee/pages/a/b` is listed and the collection's catalogue is read
- **THEN** the listing names `shopee/pages/a/b/deep.md` as a page
- **AND** the catalogue carries it at that nested path, with no folder required or renamed

### Requirement: Hide every dot-prefixed entry
Hidden entries (dot-prefixed) MUST be excluded from every count and from the catalogue and the check, and no surface MUST list or read one: the tree route lists none, the read route refuses every hidden path, and a collection reports no count of what hides in it. A collection's `.inbox/` is an ordinary hidden entry whose files the sweep adopts as sources (see "Adopt a file dropped into the inbox"). `.history/` and `.raw/` do not exist: what a person or an agent replaced is kept in the collection's git history (see "Commit every knowledge write naming its writer"), and an upload's original is a visible file in `sources/` (see "Keep every upload as a source with its original").

#### Scenario: leave hidden entries out of every listing
- **GIVEN** a `shopee` collection holding one page, a file in `.inbox/`, and a file a person put under `.scratch/`
- **WHEN** the collection is listed, its page count read, its catalogue rendered and its tree requested
- **THEN** the page count is one and the catalogue names the one page only
- **AND** the tree lists the page and nothing from `.inbox/` or `.scratch/`, and the read route refuses a path under either

### Requirement: Keep the collection README out of the corpus
A collection's `README.md` MUST sit at the collection root and MUST NOT be listed as a page or a source or counted. It is the collection's schema: its first paragraph is the collection's description, and what it says about the collection's page types and conventions MUST take precedence over the guide's defaults, as the guide tells agents (see "Teach writing and tidying in the guide").

#### Scenario: keep the README out of listings, counts and curation
- **GIVEN** a `shopee` collection whose root holds a `README.md` edited after it was created and one page
- **WHEN** the collection is listed, counted and swept
- **THEN** the listing names only the page, the page count is one, and the README is never moved, adopted or catalogued as a page

### Requirement: Fill frontmatter on converted material
A source made from an upload MUST carry the frontmatter of "Carry title, description and actor in frontmatter" — `title` from the document (falling back to its file name) and `description` drawn from the document's opening prose.

#### Scenario: title an upload from its file name when it has no heading
- **GIVEN** a collection and a plain-text file `release-notes.txt` whose text has no heading and opens with a sentence of prose
- **WHEN** it is uploaded
- **THEN** the resulting source's frontmatter `title` is derived from the name `release-notes`
- **AND** its `description` is drawn from the text's opening prose rather than left empty

### Requirement: Bound uploads and leave nothing behind on failure
Upload MUST be bounded: one file per call, a size ceiling, and a refusal that names the limit. A conversion failure MUST leave nothing behind — no source, no original and no file in the collection's `.inbox/`.

#### Scenario: a document is never stored half-converted
- **GIVEN** a document whose converter succeeds but yields no text, as an image-only PDF does
- **WHEN** it is uploaded
- **THEN** the upload is refused with the reason naming the document type, and nothing is written — no source, no original

### Requirement: Merge the manual and the catalogue in the skill body
The skill's **body** MUST be one merged manual: Coffer's own — its one built-in tool, `coffer__search_tools`, and when to reach for it; the tiering contract that makes an unlisted upstream tool still callable; the knowledge root and the memory root, and that Coffer's distilled memory notes are Markdown under the latter which the agent finds by searching that directory with its own tools; that Coffer's own logs are read with `coffer log` and located with `coffer path logs`; that a skill's scripts keep their logs, operation journals and temp files under `~/.coffer/skill-data/<skill-name>/` (found with `coffer path skill-data`), never in the skill's own folder or elsewhere in `~/.coffer`, and that files there are deleted after the Skill working files retention window, so durable data does not belong there; that `coffer cli list` lists the command-line tools Coffer manages, what each is for and whether it is ready on this machine; the fact that Coffer reads an agent's memory and never writes it; that no Coffer tool waits on a human approval; and what does not belong in knowledge — **followed by** the catalogue: the path of the knowledge root, and, for each collection, its README's path, its pages grouped by `type` with each page's collection-relative path, title and description, and its waiting sources with their paths and titles. When the catalogue would exceed its budget it MUST first drop the descriptions, and then list only each collection's counts and the directories to search, saying that it was shortened. It MUST instruct the agent to read those files with its own tools, to grep `sources/` for an exact fact a page does not carry, to write what it learns that is durable straight into the collection's pages, and to integrate, tidy and check a collection when asked (see "Teach writing and tidying in the guide"); a change to a page is carried by the sweep into the vault's history (see "Treat a direct file edit as a complete change"). One skill, not a set: a frontmatter description is resident in every session whether the skill is opened or not, while a body is paid for only when a model reaches for it, so a second skill would spend the resident budget again to describe something most sessions never open.

#### Scenario: the skill body carries the catalogue and the absolute root
- **GIVEN** a collection holding three pages of two types and one waiting source
- **WHEN** the skill is rendered
- **THEN** its body carries each page's collection-relative path, title and description under its type, the waiting source's path and title, and the path of the knowledge root, and it instructs the agent to read those files with its own tools
- **AND** the frontmatter `description` names the collection's subject, taken from the collection's own `README.md`, so a model matching on it has something to match

#### Scenario: a catalogue past its budget shortens itself
- **GIVEN** collections whose full catalogue exceeds the budget
- **WHEN** the skill is rendered
- **THEN** the catalogue lists pages without their descriptions, or, past the budget again, each collection's counts and its `pages/` and `sources/` directories, and says the catalogue was shortened and to search those directories

#### Scenario: name one tool, both roots and the log reader in the manual
- **GIVEN** a vault with one collection
- **WHEN** the skill is rendered
- **THEN** its manual names exactly one built-in tool, `coffer__search_tools`, and names none of `coffer__write`, `coffer__recall` and `coffer__diagnose`
- **AND** it names the knowledge root and the memory root with the instruction to search them with the agent's own tools, tells the agent to write durable knowledge into a collection's pages itself, and names `coffer log` and `coffer path logs` as the way to read Coffer's own logs, and `coffer cli list` as the way to learn which command-line tools Coffer manages

#### Scenario: the manual says where a skill's scripts keep their files
- **GIVEN** a vault with one collection
- **WHEN** the skill is rendered, with or without the knowledge and memory features on
- **THEN** its manual says a skill's scripts write their logs, operation journals and temp files under `~/.coffer/skill-data/<skill-name>/`, found with `coffer path skill-data`
- **AND** it says never to write them inside the skill's own folder, that files there are deleted after the Skill working files retention window, and that durable data does not belong there

### Requirement: Adopt a file dropped into the inbox
An agent, another machine or an older guide MAY leave a Markdown file at `<collection>/.inbox/<any-name>.md`, with optional frontmatter. The sweep MUST recognise a new inbox file that no Coffer surface wrote, **normalise** it, and keep it as a source (see "Promote submitted material at once"):

- `title` is kept, else the first `# ` heading, else the file name's stem;
- `description` is kept, else the first prose paragraph, else the title — the same fallback an upload uses (see "Fill frontmatter on converted material");
- `actor` is kept as written (it is self-reported), else `agent`;
- `created_at` and `updated_at` are kept, else the time the sweep saw the file;
- every other key a writer set is kept.

Coffer MUST record one `knowledge_written` audit event per file, carrying `actor_reported: true` when the actor came from the file. A Markdown file in a top-level directory that is not a collection MUST be left alone and MUST NOT be catalogued: only a person creates a collection (see "Create collections only deliberately"). A non-Markdown file in an inbox MUST be left in place, logged, and not adopted.

#### Scenario: a bare inbox file is normalised and audited
- **GIVEN** a `shopee` collection, and a file `shopee/.inbox/cache-ttl.md` holding a `# Cache TTL` heading, a paragraph and no frontmatter
- **WHEN** the sweep runs
- **THEN** the resulting source's frontmatter carries `title` `Cache TTL`, a `description` drawn from the paragraph, `actor` `agent`, and `created_at` and `updated_at` set to when the sweep saw it, with the body unchanged
- **AND** one `knowledge_written` audit event is recorded with `actor_reported` false, and the file is no longer in `.inbox/`

#### Scenario: keys a writer set are kept
- **GIVEN** an inbox file whose frontmatter sets `actor` `user`, a `title`, and a `source` key
- **WHEN** the sweep adopts it
- **THEN** the title, the actor and the `source` key are as written on the resulting source, and the audit event records `actor_reported: true`

#### Scenario: a file outside a collection or that is not Markdown is not material
- **GIVEN** a Markdown file at `notes/.inbox/idea.md`, where `notes` is not a collection, and a `shopee/.inbox/data.bin` file
- **WHEN** the sweep runs
- **THEN** the first is left alone and appears in no catalogue, no `notes` collection is created, and the second stays in the inbox, is logged, and is not adopted

### Requirement: Teach writing and tidying in the guide
The `coffer-guide` skill MUST teach the agent that reads it to do the judgement Coffer does not do for it. Its knowledge sections MUST describe the layout — the README as the schema whose page types and conventions win over the guide's defaults, kept `sources/` and edited `pages/` — and carry **Writing a page** — put a durable fact straight into the collection's pages with the agent's own file tools, by these rules: find the fact's home (fold it into the page that owns the subject, and create a page under `pages/` only when none does), lose nothing, organise by subject and never by provenance, let the newer statement win unless the older one is shown to be right while keeping the superseded one legible, link other pages by `[[slug]]` and never by path, keep links whole when renaming a page (update the links to it, or keep its old slug in `aliases`), never edit a source except to mark it `ingest: skipped`, and give every page frontmatter with a `title`, a `type` (by default one of `concept`, `entity`, `how-to`, `decision` and `overview`), a `description` saying what question the page answers, the `sources` it draws on, any `aliases`, and `actor: agent`; **Integrating sources** — read each waiting source in full, fold what it says into the pages that own its subjects, create pages for subjects with none, add the source's slug to each such page's `sources`, and mark a source with nothing worth keeping `ingest: skipped`; **Tidying a collection** — read one collection's README and pages, merge pages that answer the same question, split one that answers several, correct what is wrong or contradictory, fix the dead links Coffer reports, and report what was merged, split, corrected and deleted; and **Checking a collection** — report contradictions, stale statements, subjects covered twice and subjects that deserve a page of their own, alongside Coffer's mechanical findings, and change nothing. The skill's resident description MUST name writing, tidying and checking knowledge, so an agent asked to organise knowledge (整理知识) recognises the skill. These sections MUST be present only while the `knowledge` feature is on.

#### Scenario: the rendered guide carries the writing and tidying sections
- **GIVEN** a vault with one collection and the `knowledge` feature on
- **WHEN** the guide skill is rendered
- **THEN** its body carries "Writing a page", "Integrating sources", "Tidying a collection" and "Checking a collection" sections
- **AND** its frontmatter description names writing, tidying and checking knowledge

#### Scenario: the writing section states the six rules
- **GIVEN** the rendered guide body
- **WHEN** the "Writing a page" section is read
- **THEN** it tells the agent to fold a fact into the page that owns its subject, to lose nothing, to organise by subject and never by provenance, that the newer statement wins unless the older is shown to be right, to link pages by `[[slug]]` and never by path and keep links whole on a rename, never to edit a source, and to give every page a title, a type, a description, its sources, any aliases and `actor: agent`

#### Scenario: the writing and tidying sections are absent while knowledge is off
- **GIVEN** the `knowledge` feature switched off
- **WHEN** the guide skill is rendered
- **THEN** none of "Writing a page", "Integrating sources", "Tidying a collection" and "Checking a collection" appears in the body, and the description does not name tidying knowledge

### Requirement: Hand a tidy to the agent
A collection's read MUST carry `tidy_handoff`: a prompt the daemon writes, from the same hand-off module every other hand-off uses, that names the collection, gives its absolute path, its page count and its waiting-source count, and tells the agent to integrate the waiting sources by the `coffer-guide` section "Integrating sources" and then to follow "Tidying a collection". `GET /api/v1/knowledge/tidy-handoff` MUST return the same kind of prompt for every collection at once: it asks the agent to work through the collections one at a time by those two sections, and carries the knowledge root's absolute path and one fact line per collection with its name, absolute path, page count and waiting-source count. The web UI MUST offer a **Tidy** button on a collection's page and a **Tidy all** button in the Knowledge page's header, which uses that route. Pressing either MUST start the hand-off agent in the person's preferred terminal with that prompt sent at once, as [web-ui](../web-ui/spec.md) "Hand a machine-dependent problem to an agent with one split button" says, and leave the page where it is. When no managed agent is available the button MUST offer **Copy prompt** only. Nothing MUST tidy unattended: Coffer starts no agent run of its own, and a collection is tidied only when a person presses Tidy or asks their own agent to.

#### Scenario: a collection read carries its tidy hand-off
- **GIVEN** a `shopee` collection holding pages and a waiting source
- **WHEN** the collection is read
- **THEN** its `tidy_handoff` prompt names `shopee`, carries the collection's absolute path under the knowledge root and its one waiting source, and names the "Integrating sources" and "Tidying a collection" sections of `coffer-guide`

#### Scenario: the knowledge tidy-all hand-off names every collection
- **GIVEN** two collections, `shopee` with three pages and `personal` with one
- **WHEN** `GET /api/v1/knowledge/tidy-handoff` is read
- **THEN** the prompt names the "Integrating sources" and "Tidying a collection" sections of `coffer-guide` and asks for the collections to be worked through one at a time
- **AND** it carries the knowledge root's absolute path and one fact line each for `shopee` (its path, 3 pages) and `personal` (its path, 1 page)

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
The daemon MUST run a **knowledge sweep** on a recurring timer, and the sweep MUST do exactly these things and call no model: adopt every file sitting in a collection's `.inbox/` as a source (see "Adopt a file dropped into the inbox"); file every Markdown document left in a collection outside `pages/`, `sources/` and hidden entries, other than the root `README.md`, and untouched for a minute, into `pages/` at the same relative path, suffixed on a collision, as one commit by the daemon that rewrites no content; commit every change found on disk under `knowledge/` as an edit on disk, so a person's editor or an agent's file tools is never counted as Coffer's (see "Commit every knowledge write naming its writer"); and re-render and re-seed the `coffer-guide` skill so a page added by hand is catalogued. The sweep MUST NOT hold the vault against a sync round: whatever it writes goes through the vault's ordinary writer. While the `knowledge` feature is switched off the sweep MUST skip its rounds ([experimental-features](../experimental-features/spec.md) "Close the knowledge feature's surfaces").

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

### Requirement: Promote submitted material at once
Material MUST NOT wait to be stored. A submission Coffer receives — an upload — MUST become a source on the spot, under `sources/`, with the frontmatter of "Carry title, description and actor in frontmatter" filled from its opening prose, named from its title (see "Use the file path as a document's identity"), and committed naming whoever submitted it. A file adopted from `.inbox/` becomes a source the same way. Whenever material is submitted or a sweep adopts or files a file, Coffer MUST announce the collection on the daemon's event stream as a `knowledge` event carrying the collection's uid, because the files change without any write to the collection's row ([resource-framework](../resource-framework/spec.md) "Announce every change on one daemon-wide event stream"). Every entrance Coffer serves submits through this one operation. Coffer merges nothing into a page: compiling a source into pages is the agent's work when the person presses Tidy (see "Hand a tidy to the agent"), and until then the source waits.

#### Scenario: an upload becomes a document at the collection root
- **GIVEN** a `shopee` collection
- **WHEN** a Markdown file is uploaded to it
- **THEN** the collection holds one new source under `shopee/sources/` whose body is the uploaded text, whose frontmatter carries a title, a description drawn from its opening prose and `actor` `user`, and whose commit names the user
- **AND** nothing is left in `shopee/.inbox/`, and the source is waiting

#### Scenario: an upload answers with the document it became
- **GIVEN** a `shopee` collection
- **WHEN** a document is uploaded once through `POST /api/v1/knowledge/upload`
- **THEN** the answer carries the new source's path and no `pending` field, and the source is in the collection's visible tree

#### Scenario: submitting material announces the collection on the event stream
- **GIVEN** a `shopee` collection and a client reading the event stream
- **WHEN** a document is uploaded to it
- **THEN** a `knowledge` event naming the collection's uid is announced

### Requirement: Treat a direct file edit as a complete change
Writing, editing or deleting a page directly in the collection's tree — by a person in their own editor, or by an agent with its own file tools — MUST remain a complete way to change knowledge: no import, no registration, no conversion step, and the change is live on the very next read. The change MUST be committed to the vault as an edit found on disk, by the sweep or by the next Coffer write, whichever comes first (see "Sweep the knowledge root on its mechanical duties"). Ingestion is an additional entrance, never a required one.

#### Scenario: an agent's new document is live at once and committed as a disk edit
- **GIVEN** a `shopee` collection and an agent that writes a Markdown page into its `pages/` with its own file tools
- **WHEN** the page is read before any sweep, and the knowledge sweep then runs
- **THEN** the read returns the agent's text with no import step in between
- **AND** the sweep commits the page as an edit found on disk

### Requirement: Follow edits across collections in one feed
The system MUST serve one feed of the recent changes to knowledge across every collection, newest first, paged by an opaque cursor ([resource-framework](../resource-framework/spec.md) "Page growing lists by an opaque cursor") and filterable to one collection: every page or source a person or an agent wrote, restored, filed or deleted, and every change from sync or from disk — each with its writer, its operation, its time, its collection and, for each file it touched, whether that file was added, changed or removed and how many lines were added and removed. A change an earlier version of Coffer made as a curation pass is listed with its writer. One change MUST be readable in full — every file it touched with its diff. The feed is `GET /api/v1/knowledge/changes`, the route a delete's Undo reads to find the delete it restores (see "Undo a knowledge delete from its toast") and the one a collection page's **Change log** reads (see "Show a collection as one tree of read-only documents in the web UI").

#### Scenario: recent changes lists edits across collections
- **GIVEN** a person's upload in one collection and an agent's edit on disk in another
- **WHEN** the feed is read, and read again filtered to one collection
- **THEN** both changes are listed newest first with their collections, writers and per-file line counts
- **AND** the filtered read holds only that collection's changes, and one change read in full carries each file's diff

### Requirement: Show a collection as one tree of read-only documents in the web UI
The web UI MUST present a collection as **one tree** of its files — no lanes, no filter or retrieval box — with the chosen file in the pane beside it, the same two panes a skill's Files tab is. At a collection's root the tree MUST show its two folders first, labelled **Pages** and **Sources**, then any other entry; a waiting source MUST carry a **Waiting** mark. The tree MUST name every collection, folder and file by its name on disk otherwise: a collection has no title (see "Name a collection by its folder and edit its description in place"). Its **Collections** header strip MUST carry **New collection** (a name and what belongs in it; the collection reaches every agent through the coffer-guide skill). The tree MUST show no hidden entry, and no collection or folder carries a count. Knowledge calls its files **pages** and **sources** everywhere (memory keeps *notes*).

A file's pane MUST carry no tabs. Its bar MUST name where the file is, then **History** (opening a drawer beside the file, `?history=1` in the address, with the file's versions in the vault, their diffs and **Restore this version…**, [web-ui](../web-ui/spec.md) "Show a vault file's history on a History tab"), a **Preview / Source** switch, **Open in editor** as a visible button, and a ⋯ menu holding **Reveal in Finder** and **Delete**. The file MUST stay in view while the drawer is open. Under a page's title one line MUST give its type, who wrote it and when it was created, and its sources, each opening that source and a missing one marked; a page's `[[links]]` MUST render as links that open the file they resolve to, a dead one marked in the danger tone. Under a source's title one line MUST say which pages cite it, or that it is waiting, and name its kept original. There is no side column. The pane MUST NOT edit the file: a person changes it in their own editor and an agent with its own file tools (see "Treat a direct file edit as a complete change"), and the next read shows the change.

A collection's page MUST show its folder name, its description edited in place (see "Name a collection by its folder and edit its description in place"), its properties — **Pages**, **Sources** (with how many wait) and **Folder** — and carry **Tidy** (see "Hand a tidy to the agent") and **Check with agent** (see "Hand a check to the agent"). Under the properties a **Check** section MUST list the collection's findings grouped by kind, each naming the file it concerns and opening it, or say that nothing was found (see "Check a collection mechanically on every read"); and a **Change log** section MUST list the collection's changes newest first — what each did, its writer and time, and the files it touched, each opening that file with its history drawer — with **Show more** while more are left. A collection with no pages and no sources shows the same page with one line saying so and how to fill it — upload a source, or drop Markdown files into the folder — and **Reveal in Finder**. The collection's ⋯ menu MUST hold **Reveal in Finder**, **Copy path** and **Delete collection** (see "Delete a document at once, a collection after asking, and offer Undo").

The page MUST offer **Upload** into a collection as its one primary action and no other form that adds a file: people write in their own editor, agents by writing files. With no collection open, the page shows its collections and **Tidy all**. The tree and the pane MUST extend to the bottom of the window and scroll inside.

The Knowledge page's title MUST carry the **Experimental** tag ([experimental-features](../experimental-features/spec.md)).

#### Scenario: the viewer shows one tree of documents
- **GIVEN** a collection page whose tree holds a page, a page inside a folder and a waiting source
- **WHEN** the page renders and a page's row is clicked
- **THEN** there is one tree — no lane headings, no filter input — showing Pages and Sources first, both pages and the source with its Waiting mark, and no hidden entry
- **AND** the page's pane carries no tabs, offers History, Preview and Source and Open in editor, and Reveal in Finder and Delete in its ⋯ menu

#### Scenario: a document's history opens in a drawer beside it
- **GIVEN** a page open in its collection's pane
- **WHEN** the user presses History
- **THEN** a drawer opens with the page's versions, the address carries `history=1`, and the page is still shown beside the drawer
- **AND** closing the drawer leaves the page as it was and drops `history=1` from the address

#### Scenario: a page shows its sources and resolves its links
- **GIVEN** a page citing an existing source and a missing one, whose body links one page that exists and one that does not
- **WHEN** it is opened in Preview
- **THEN** the line under its title names both sources, the existing one opening it and the missing one marked
- **AND** the existing link opens the page it names, and the dead link is marked in the danger tone

#### Scenario: the page's one primary action is Upload
- **GIVEN** the Knowledge page with a page open
- **WHEN** the user reads the header and the page's pane
- **THEN** Upload is the primary button
- **AND** no control on the page adds a file from a typed title and body, and the pane offers no Edit

#### Scenario: a document opens in the person's editor
- **GIVEN** a page open in a collection's pane
- **WHEN** the user chooses Open in editor, and then Reveal in Finder from its ⋯ menu
- **THEN** the daemon is asked to open the page's absolute path and then to reveal it
- **AND** the pane shows the page read-only, with Preview and Source, and its line read from the frontmatter

#### Scenario: a collection page shows its properties
- **GIVEN** a collection holding two pages and a waiting source
- **WHEN** its page renders
- **THEN** it shows the folder name, the description, the Pages, Sources (1 waiting) and Folder properties, a Tidy and a Check with agent button, a Check section listing the waiting source, and a Change log
- **AND** its ⋯ menu offers Reveal in Finder, Copy path and Delete collection

#### Scenario: a collection's change log opens a file at its history
- **GIVEN** a collection whose change log lists an agent's edit of a page
- **WHEN** the user chooses the page in that row
- **THEN** the page opens with its history drawer

### Requirement: Undo a knowledge delete from its toast
Deleting a file or a whole collection MUST keep what it removed in the vault's history, so the delete's toast can undo it. Undo MUST find the delete in the changes feed (see "Follow edits across collections in one feed") and restore exactly what it removed, as it was just before it: a file into its collection; a collection as a new collection of the same name with its pages, its sources and its `README.md`. A collection restore MUST write every file first and register the collection's row last, so a failure part-way leaves no row and no partial directory: what was written is removed again and the same restore can be tried afresh. The restore MUST be one new change naming the user, carrying the version of the delete it restored, and recorded as a `knowledge_edited` audit event; the delete itself stays in the history. A restore MUST be refused with nothing written when it would overwrite — a file at the same path, `409 KNOWLEDGE_RESTORE_CONFLICT` naming it, or a collection of the same name, `409 KNOWLEDGE_COLLECTION_EXISTS` — and a change that is not a delete MUST be refused with `400 KNOWLEDGE_NOT_A_DELETE`. The route is `POST /api/v1/knowledge/changes/{version}/restore`, the web UI's own. After the toast is gone the deleted file has no pane to open its history from; its versions stay in the vault's history, where git reads them.

#### Scenario: undo a collection delete
- **GIVEN** a collection holding a document and a `README.md`, which the user deletes
- **WHEN** the delete is found in the changes feed and restored
- **THEN** the collection is back under its name with its document and its README's description, as one new change by the user naming the delete it restored
- **AND** a second restore of the same delete is refused because a collection of that name exists, and writes nothing

#### Scenario: a collection undo that fails part-way leaves nothing behind
- **GIVEN** a deleted collection whose restore fails while one of its files is being written
- **WHEN** the user restores the delete
- **THEN** the restore fails, no collection of that name is registered, and no directory of that name is left on disk
- **AND** a second restore, once the cause is gone, succeeds

#### Scenario: undo a document delete
- **GIVEN** a document the user deletes
- **WHEN** the user restores the delete
- **THEN** the document is back at its path with the text it had, and the vault's history holds the restore after the delete

#### Scenario: an undo that would overwrite is refused
- **GIVEN** a deleted document whose path holds a new document again
- **WHEN** the user restores the delete
- **THEN** the restore is refused naming that document, and the new document is unchanged
- **AND** restoring a change that is not a delete is refused as not a delete

### Requirement: Commit every knowledge write naming its writer
Every accepted write to a collection MUST be a git commit naming its writer ([Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer](../../../docs/decisions/every-vault-write-is-a-validated-commit-naming-its-writer.md)). The commits are the vault repository's, under `knowledge/`: the knowledge root keeps no repository of its own. A person's upload, description edit, delete or Undo names the user; material kept on arrival names whoever submitted it — the user, or, for a file an agent dropped into the inbox, the actor the file reports; a loose document the sweep files into `pages/` names the daemon; a change that arrives through vault sync names sync; and a change any other writer made in the tree — a person's own editor, an agent's file tools — MUST be committed as an edit on disk before Coffer's next commit, so it is never counted as Coffer's. A commit an earlier version of Coffer made as a curation pass stays in the history under its writer. A file's history is read, and an earlier version restored as a new commit, in its history drawer ([vault-storage](../vault-storage/spec.md) "Show and restore any version of a vault file or folder"). The vault is a git repository on every machine that runs Coffer ([vault-storage](../vault-storage/spec.md) "Keep the vault a git repository whether or not it syncs"); a read of the changes feed git cannot answer MUST answer 503 `KNOWLEDGE_HISTORY_UNAVAILABLE` while every write keeps working. git is looked for on every read, so one removed while the daemon runs is answered the same way. When the cause is that git is not installed, the refusal's details MUST carry `reason: "git_missing"` and `handoff`, a prompt asking the person's agent to install git on this machine — naming its OS and architecture and what needed git — the way that fits the machine, confirming it with `git --version`; neither the prompt nor the error's message may name an install command.

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
People MUST manage knowledge in the web UI, and agents with the `coffer knowledge` commands: creating collections, uploading sources, reading pages and sources and opening them in their editor, reading a file's history and restoring an earlier version, checking a collection, tidying or checking a collection through their agent, deleting and undoing a delete, and editing a collection's description. The REST routes under `/api/v1/knowledge` behind those pages serve the web UI and the `coffer knowledge` commands, which call the same routes ([resource-framework](../resource-framework/spec.md) "Offer every management operation on the command line"): a route the web UI does not call MUST NOT exist, and there MUST be no route that creates or saves a page at a path — a person's text reaches knowledge through their own editor (see "Treat a direct file edit as a complete change") or as material like every other entrance (see "Promote submitted material at once"). There MUST be no route under `/api/v1/knowledge` that lists a file's versions, diffs a version or restores one: a file's history is read and restored through the vault's routes ([vault-storage](../vault-storage/spec.md) "Show and restore any version of a vault file or folder") in its history drawer. There MUST be no index, reindex, check-sources, update-source or embedding-configuration endpoint, no curate or undo-pass endpoint, no route that fixes a finding, no settings endpoint for the cwd-derived scope axis "Derive no boundary from the working directory" forbids, and no per-agent reach endpoint or enabled switch for this kind (see "Serve every collection to every agent"). Collection deletion goes through the Resource framework (`DELETE /api/v1/resources/{uid}`). The `coffer knowledge` commands MUST list, create, describe and delete collections, read a level of the tree, a collection's check and the changes feed, upload material, undo a delete and print the tidy hand-off; no command reads, writes or deletes a file's content, and there is no `coffer path` target for knowledge: a collection's files are plain files, so agents and people read, edit and delete them directly under the knowledge root that the `coffer-guide` skill names (see "Treat a direct file edit as a complete change").

#### Scenario: knowledge is managed on the command line, its documents as files
- **GIVEN** the `coffer` command tree
- **WHEN** the `knowledge` group is enumerated, and `coffer path` is run with a `knowledge` target
- **THEN** the group offers collections, create, describe, delete, tree, check, changes, restore and upload, and no command reads, writes or deletes a file
- **AND** `coffer path` refuses `knowledge` as an unknown target

#### Scenario: the routes are the web UI's, with no material or create-at-path route
- **GIVEN** the daemon's route table under `/api/v1/knowledge`
- **WHEN** it is enumerated
- **THEN** it offers create a collection, list a level, read, upload, delete a file, check a collection, the changes feed and restoring a delete, rewrite a description, and the tidy-all hand-off
- **AND** it carries no route that saves a file, no history, version or version-restore route, no `/material` route, no curate route, no undo route, no route that fixes a finding, no route that creates a file at a path, and no index, reindex, source, embedding, scope or reach endpoint

## RENAMED Requirements

- FROM: `### Requirement: Sweep the knowledge root on three mechanical duties`
- TO: `### Requirement: Sweep the knowledge root on its mechanical duties`

## REMOVED Requirements

### Requirement: Convert uploads into documents without keeping the original
**Reason**: An upload now becomes a source and its original is kept beside it, so a statement in a page can be traced back to what was uploaded.
**Migration**: See "Keep every upload as a source with its original". Uploads stored before this change stay where they are; the sweep files them into `pages/` (see "Sweep the knowledge root on its mechanical duties"), since they were written as documents.
