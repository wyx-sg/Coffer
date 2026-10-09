---
title: Knowledge
description: Keep what you and your agents know about your working environment as a wiki of Markdown pages compiled from kept sources, which every agent reads with its own file tools, and ask your agent to tidy and check it.
---

# Knowledge

Knowledge is a directory of Markdown about your working environment — services, repositories, conventions, decisions, pitfalls — that every agent on your machine reads. Each collection is a small wiki: the material you upload is kept as **sources**, and your agent compiles it into **pages** that link to each other. This page covers creating collections, adding sources and pages, how you and your agent change them, how your agent integrates sources and tidies pages when you press **Tidy**, how Coffer checks a collection and how your agent reviews it, how to look back at a file's history and bring a version back, and how agents find what is there.

## What knowledge is for

Knowledge holds facts about the world you work in: which team owns a service, how an internal API authenticates, why a migration is ordered the way it is. It arrives because you, or an agent working with you, put it there.

- **One copy for every agent.** Claude Code and Codex read the same files, so what one agent records in the morning another reads in the afternoon.
- **Plain files.** Every page and every source is a Markdown file you can open, edit, grep and back up. Coffer keeps no index, no embeddings and no database copy of the content.
- **Sources kept, pages compiled.** What you upload is kept as a Markdown source, and a page names the sources it draws on, so a statement can always be traced back to the source it came from. The pages are where the knowledge grows: each page is about one subject, says which sources it draws on, and links to the pages it relates to.
- **Written together.** You edit pages in your own editor; the Knowledge page shows them read-only and opens them there. Agents write pages with their own file tools, following the rules in the `coffer-guide` skill: a fact goes into the page that already owns its subject. When you press **Tidy**, your agent folds the sources that are still waiting into the pages, then merges, splits and corrects the pages. Coffer itself runs no model over your knowledge.

Knowledge is not [memory](/guides/memory). Memory is what agents learn while working, read out of their own memory stores. Knowledge is what somebody deliberately wrote down.

## How a collection is laid out

A **collection** is a top-level folder under the knowledge root:

```text
~/.coffer/vault/knowledge/
└── payments/                        ← one collection
    ├── README.md                    ← the schema: what belongs here, page types, conventions
    ├── sources/
    │   ├── gateway-design.md        ← a source: the upload converted to Markdown
    │   └── oncall-notes.md          ← a source from a Markdown upload
    ├── pages/
    │   ├── session-ownership.md     ← a page
    │   └── gateway/
    │       └── rate-limits.md       ← nesting is allowed and means nothing
    └── .inbox/                      ← hidden: a drop zone, kept as sources at the next sweep
```

- **`README.md`** at the collection root is the collection's **schema**. Its first paragraph is the collection's description everywhere Coffer shows one, and it is what the `coffer-guide` skill tells agents the collection is about. Whatever else it says about the page types and conventions the collection uses takes precedence over the guide's defaults. It is never listed as a page or a source, or counted.
- **`sources/`** keeps the material that arrived: every upload and every file dropped into the inbox, converted to Markdown. Only the Markdown is kept, not the file you uploaded, so the collection stays one tree of Markdown every agent can read. Agents read sources and never edit them.
- **`pages/`** holds the wiki itself: the pages you and your agents write and keep up to date. This is what agents read first.
- **Folders** inside `pages/` and `sources/` are optional and carry no meaning. You or your agent can create, move and remove them. `pages/` and `sources/` are the only folders that mean anything.
- **Any other file** in a collection is listed in the tree but neither catalogued nor checked. A Markdown file left outside `pages/` and `sources/` is moved into `pages/` by the sweep (see [What runs on its own](#what-runs-on-its-own)).
- **Hidden entries** (names starting with `.`) are left out of every count, the catalogue and the check, and the Knowledge page lists none of them. The one Coffer reads is `.inbox/`: a Markdown file left there is kept as a source at the next sweep (see [A file in the inbox](#a-file-in-the-inbox)).

A file's path is where it is; its **slug** — the file name without `.md` — is the name links use. File names are slugs of the title, with a suffix such as `-2` on a collision.

The knowledge root is inside the vault repository, at `~/.coffer/vault/knowledge`; the `coffer-guide` skill names it to every agent. It cannot be moved elsewhere: a tree outside the vault would be a tree its history cannot see.

### Frontmatter

Every page carries YAML frontmatter:

```markdown
---
title: Session ownership
type: concept
description: Which service owns a login session, and how long it lives.
sources: [gateway-design, oncall-notes]
aliases: [sessions]
actor: agent
created_at: 2026-09-20T08:14:03.512840+00:00
updated_at: 2026-09-22T10:02:41.090311+00:00
---

The `account-session` service owns ... see [[rate-limits|the gateway's limits]].
```

| Key | Meaning |
| --- | --- |
| `title` | The page's title. |
| `type` | What kind of page it is: `concept`, `entity`, `how-to`, `decision` or `overview`, unless the collection's README defines its own types. Agents see the catalogue grouped by it. |
| `description` | One sentence on what question the page answers. Agents see it in the catalogue. |
| `sources` | The slugs of the sources the page draws on. A source no page lists here is still [waiting](#sources-wait-until-a-page-cites-them). |
| `aliases` | Other names a link may use for this page, such as an old slug after a rename. |
| `actor` | `user` or `agent` — who wrote the page. |
| `created_at`, `updated_at` | Timestamps. |

Coffer writes no page itself: whoever writes a page gives it these keys, as the `coffer-guide` skill teaches agents. A page that lacks `title`, `type` or `description`, or names no `sources`, still works; it shows up as a finding when the collection is [checked](#check-a-collection).

A source carries the keys Coffer writes when it keeps one — `title`, `description`, `actor`, `created_at`, `updated_at`. The one key an agent may add to a source is `ingest: skipped`, for a source with nothing worth a page.

Any other key you add to a file is kept, with its value, whenever Coffer rewrites the file.

### Link pages by slug {#link-pages-by-slug}

A page links to another by its slug, never by its path: `[[session-ownership]]`, or `[[session-ownership|the session service]]` to choose the text shown. A link may also name one of a page's `aliases`, or a source's slug. Paths change as a collection is tidied; slugs do not change unless a page is renamed, and the `coffer-guide` skill tells agents to update the links to a page they rename, or to keep its old slug in `aliases`.

Coffer resolves every link each time a page is read, ignoring case. A link that names nothing is **dead**, and one that names more than one file is **ambiguous**; both are reported by the [check](#check-a-collection), and the Knowledge page marks a dead link in the page.

### Sources wait until a page cites them {#sources-wait-until-a-page-cites-them}

A source **waits** while no page lists it in `sources` and it is not marked `ingest: skipped`. Nothing else records which sources have been integrated: as soon as a page cites a source, it stops waiting. The Knowledge page marks a waiting source **Waiting**, the collection's page counts them, the `coffer-guide` catalogue names them, and **Tidy** asks your agent to integrate them first.

## Create a collection

Collections are created only on purpose, and only by a person. Reading, writing, an agent's working directory or a Markdown file an agent drops into some other folder never creates one.

<Shot name="knowledge-page" alt="The Knowledge page, with a collection and its documents." />

```text
Knowledge → New collection → Name, What belongs in here → Create collection
```

This creates `~/.coffer/vault/knowledge/payments/` and a `README.md` holding the description; `pages/` and `sources/` appear as soon as something is written into them. A collection has no title: every page and listing shows it by its folder name. Its description is the opening paragraph of the README: change it on the collection's page (click the text; it saves when you leave the field) or in the file itself. Either way only that paragraph changes, and anything written under it — page types and conventions included — stays.

To rename a collection, choose **⋯ → Rename…** on its page and enter the new name. Its folder moves with it (`~/.coffer/vault/knowledge/<new-name>/`), the page stays on the same collection, and agents find it under the new name from the next catalogue. A name another collection already has, or that is not a valid folder name, is refused under the field and nothing changes.

The **Knowledge** page's tree lists every collection.

## Add knowledge

Material comes in as a source, and knowledge grows as pages. There are five ways in.

### From an agent: write into the pages {#from-an-agent-write-into-the-pages}

Agents file knowledge with their own file tools. An agent connected to Coffer reads the `coffer-guide` skill (see [Connect a client](/guides/connect-a-client)), which names the knowledge root and the collections and teaches seven rules for writing a page:

1. Find the fact's home: fold it into the page under `pages/` that already owns its subject, and create a new page only when none does.
2. Lose nothing: every fact already in a page survives the edit.
3. Organise by subject, never by who or when.
4. Where two statements disagree, the newer wins unless the older is shown to be right by a source, a date, a command's output or the code. The superseded one stays legible.
5. Link other pages by `[[slug]]`, never by path; when renaming a page, update the links to it or keep its old slug in `aliases`.
6. Never edit a source, except to mark it `ingest: skipped`.
7. Give every page a `title`, a `type`, a one-line `description` saying what question it answers, the `sources` it draws on, any `aliases`, and `actor: agent`.

You can also ask directly: "write down what we just found out about the session TTL in the payments collection." The collection must already exist; only you create one. Whatever the agent writes is readable at once, and the next sweep commits it to the [history](#history-and-restore). A page an agent writes in the wrong place — at the collection root, say — is moved into `pages/` within a minute.

### Upload a source {#upload-a-source}

Upload converts a file to Markdown and keeps it in the collection as a source straight away. Only the Markdown is kept: the file you uploaded is not stored, so keep your own copy if you need it.

```text
Knowledge → Upload → choose a file and the collection → Upload
```

| Accepted | Formats |
| --- | --- |
| Converted | `pdf`, `docx`, `pptx`, `xlsx`, `xls`, `html`, `htm`, `epub` |
| Tables | `csv`, `tsv` |
| Taken as text | `md`, `markdown`, `mdx`, `txt`, `text`, `rst`, `json`, `yaml`, `yml`, `toml`, `ini`, `cfg`, `log`, `sql`, and common source files (`py`, `js`, `ts`, `go`, `rs`, `java`, `sh`, …) |

An uploaded PDF, for example, becomes `sources/gateway-design.md`, the extracted Markdown with frontmatter, and nothing else. A file taken as text — Markdown, plain text, source code — becomes a source the same way. A name another source already has gets a suffix (`-2`).

One file per upload, at most 20 MB; the upload takes the collection, not a folder. An unsupported type is refused with the type named, and a conversion that produces no text — an image-only PDF, for example — is refused too. A refused upload leaves nothing behind.

The source's `title` comes from the file (a `# ` heading on its first line, or else the file name). Its `description` is taken from the opening prose, or its title when there is none. The source then [waits](#sources-wait-until-a-page-cites-them): folding what it says into the pages is your agent's job when you press **Tidy** (see [Tidy a collection](#tidy-a-collection)), or whenever you ask it to.

### A file in the inbox {#a-file-in-the-inbox}

A Markdown file can also arrive at a collection's hidden `.inbox/` folder: from an agent outside Coffer, from another machine, or from an older guide.

```text
~/.coffer/vault/knowledge/payments/.inbox/session-ttl.md
```

The file name does not matter, and frontmatter is optional. The next sweep keeps the file as a source under `sources/`, filling in whatever it lacks:

| Frontmatter | Filled from |
| --- | --- |
| `title` | The first `# ` heading, else the file name. |
| `description` | The first paragraph, else the title. |
| `actor` | `agent`, unless the file says otherwise. |
| `created_at`, `updated_at` | The time the sweep saw the file. |

Anything the writer did set is kept, other keys included, and each file is recorded in the audit log. Like an upload, the new source waits until a page cites it. Only a collection's own `.inbox/` counts. A Markdown file written into a top-level folder that is not a collection is left alone and never catalogued, because only a person creates a collection. A file in an inbox that is not Markdown stays where it is.

### From a chat: ask your agent {#from-a-chat-ask-your-agent}

If you have a [channel](/guides/channels) paired, there is no knowledge command. Send the document or the conversation to the agent in the chat, in a direct chat or a group, and ask it to put that into knowledge, for example "save this into payments". The agent writes it into the collection's pages with its own file tools, by the same rules as any other page.

### Edit a file yourself

Writing, editing or deleting a page in the collection's `pages/` folder with any editor is a complete way to change knowledge. There is no import step. The change is live on the next read, and the next sweep commits it to the history as an edit on disk. Give a page you write the same frontmatter an agent would (see [Frontmatter](#frontmatter)); the [check](#check-a-collection) tells you what is missing.

On the Knowledge page, choose a page or a source and use **Open in editor**, or the **⋯** menu's **Reveal in Finder**, to jump to the file. The Knowledge page itself never edits a file: it shows it read-only, and the next read shows whatever your editor or an agent saved. There is no unsaved state, no stale-save refusal and no leave-without-saving question, because nothing on the page holds your text. Open in editor uses the editor chosen in **Settings › General**.

To add a page, save a Markdown file under the collection's `pages/` folder (**Reveal in Finder** on the collection). To add material, use **Upload**, or drop a Markdown file into the collection's `.inbox/`. Leave sources as they are: a source is the record of what arrived.

Agents do the same thing with their own file tools, by the writing rules the `coffer-guide` skill gives them (see [From an agent](#from-an-agent-write-into-the-pages)).

## Tidy a collection {#tidy-a-collection}

Over time a collection collects work to do: sources no page has drawn on yet, two pages that answer the same question, one that answers several, a statement a newer page contradicts, a link that no longer names a page. Coffer does not fix these itself. It hands the job to your agent, which reads the files with its own file tools and edits the pages.

### Press Tidy

```text
Knowledge → choose the collection → Tidy
Knowledge → Tidy all   (every collection, one after another)
```

**Tidy** starts your default hand-off agent in your preferred terminal, with a prompt that names the collection, its folder, its number of pages and its number of waiting sources as its first message. You watch the agent work in the terminal. **Tidy all**, in the Knowledge page's header, sends one prompt the same way that names every collection with the same counts and asks the agent to go through them one at a time. With no managed agent available, the button offers **Copy prompt** instead: paste it into whichever agent you use.

The prompt points the agent at the **Integrating sources** and **Tidying a collection** sections of the `coffer-guide` skill. Following them, the agent works through one collection at a time:

1. **Integrates the waiting sources**, oldest first: reads each one in full, folds what it says into the pages that own its subjects, creates a page for a subject no page owns, and adds the source's slug to the `sources` of every page it changed. A source with nothing worth keeping — a duplicate, an empty export — is marked `ingest: skipped` instead.
2. Reads the collection's `README.md` and every page's title and description, then the pages in full.
3. **Merges** pages that answer the same question into one, keeping every fact and every source, keeps the merged-away slug in the survivor's `aliases`, and deletes the pages it merged away.
4. **Splits** a page that answers several unrelated questions, one subject per page, linked to each other.
5. **Fixes** what is wrong or contradictory by the rule that the newer statement wins unless the older is shown to be right, the links Coffer reports as dead, and a description that does not say what question its page answers.
6. Reports which sources it integrated or skipped, and what it merged, split, corrected and deleted.

It changes nothing that does not need changing. You can also ask any agent that has the `coffer-guide` skill to do this in your own words: "tidy up the payments knowledge."

### Nothing tidies on its own

Tidy runs only when you press it or ask your agent. Coffer starts no agent run of its own, so nothing spends your quota or opens a conversation you did not start.

### If a tidy goes wrong

Every edit the agent makes is a version in the [history](#history-and-restore), written as an edit on disk. Open the page, press **History** in its pane bar, choose the version before the edit and press **Restore this version…** (see [History and restore](#history-and-restore)). The collection's **Change log** lists every change the tidy made, each file opening with its history.

::: info What leaves your machine
Coffer sends nothing about your knowledge to any model. When you press Tidy or Check with agent, the files the agent reads go to that agent's own provider, as in any conversation with it.
:::

## Check a collection {#check-a-collection}

Checking comes in two layers. Coffer finds what can be found mechanically, every time a collection is read, and fixes none of it. What takes judgement you hand to your agent with **Check with agent**, which reports and changes nothing.

### What Coffer finds on its own {#what-coffer-finds-on-its-own}

The **Check** section of a collection's page lists these findings, grouped by kind, each naming the file it concerns and opening it when you click it. With nothing to report it says **Nothing found.**

| Finding | What it means |
| --- | --- |
| **Dead links** | A `[[link]]` that names no page, alias or source. |
| **Ambiguous links** | A `[[link]]` that names more than one file. |
| **Names used twice** | Two pages share a slug, or an alias names two pages. |
| **Missing sources** | A page's `sources` names a source that does not exist. |
| **Incomplete pages** | A page missing its `title`, `type` or `description`. |
| **Pages without sources** | A page whose `sources` is empty. |
| **Pages nothing links to** | A page no other page links to, once the collection has two or more pages. Pages of type `overview` are exempt: they are entry points. |
| **Waiting sources** | A source no page cites and not marked `ingest: skipped`. |

The findings are worked out from the files on every read and stored nowhere, so they are current the moment a file changes. They are hints, not errors: a page you wrote without sources still works. On the command line, `coffer knowledge check <collection>` prints the same list (see [`coffer knowledge`](/reference/cli/knowledge#knowledge-check)).

### Check with agent {#check-with-agent}

```text
Knowledge → choose the collection → Check with agent
```

**Check with agent**, beside **Tidy**, hands the collection to your agent the way Tidy does, with a prompt that carries Coffer's findings and points at the **Checking a collection** section of the `coffer-guide` skill. The agent reads the README, the pages and, where a claim needs it, the sources they cite, and reports:

- statements that contradict each other, naming both pages;
- statements a newer source or page shows to be stale;
- subjects covered twice, by pages that should be one;
- subjects mentioned across pages that deserve a page of their own;
- Coffer's findings, each with what it would do about it.

It writes, moves and deletes nothing. You decide what to fix, and can then press **Tidy** or ask the agent to fix specific points.

## What runs on its own {#what-runs-on-its-own}

A background **sweep** keeps the collections current. It runs about once a minute and calls no model. Each round it:

- keeps files dropped into a collection's `.inbox/` as sources (see [A file in the inbox](#a-file-in-the-inbox)),
- files a Markdown file left in a collection outside `pages/` and `sources/` — other than the README, and once nobody has touched it for a minute — into `pages/` at the same relative path, adding a suffix if that name is taken, without changing its text,
- commits to the history whatever changed in the tree since the last commit — your editor's saves and your agent's file edits — as an edit on disk, and
- re-renders the `coffer-guide` skill's catalogue, so a page you or an agent added by hand is listed.

It runs on every machine, takes no part in [vault sync](/guides/vault-sync)'s rounds and never waits for one, and rewrites the text of no file. It is skipped while the Knowledge feature is switched off (see [Experimental features](/guides/experimental-features)).

### Collections from before pages and sources {#collections-from-before-pages-and-sources}

A collection made before pages and sources existed holds its documents at its root and in folders of its own. The first sweep after you update moves every one of them into `pages/`, keeping their folders, as one change written by **Coffer** that you can see in the collection's **Change log** and undo from the history. Their text is unchanged; what they lack — a `type`, `sources` — shows up in the [check](#check-a-collection), and a **Tidy** fills it in.

## How agents find knowledge

Coffer has **no tool for reading, listing or searching knowledge**. An agent reads the files by path with the tools it already has: `Read`, `Grep`, its shell.

What tells it where to look is Coffer's built-in [`coffer-guide` skill](/guides/skills#the-built-in-coffer-guide-skill), which Coffer links into every agent's skill folder:

- Its **description**, which is in every session, names the subjects of your collections, taken from each `README.md`, and says the skill teaches writing, tidying and checking knowledge.
- Its **body**, loaded when the agent opens the skill, gives the knowledge root's path and a catalogue of every collection: its README, its pages grouped by `type` with each page's path, title and description, and the sources still waiting to be integrated. It also carries the layout, the rules for writing a page, and the steps for integrating sources, tidying and checking described above.

When the pages do not carry what an agent is after, the guide tells it to grep the collection's `sources/` for the exact string. A large catalogue is shortened to fit: first the descriptions are left out, and if it is still too long only each collection's counts are listed with the folders to search, and the skill says so.

Coffer rewrites the skill whenever the catalogue changes, so a new page appears in it within one sweep.

::: details Why no search tool
Agents reliably use the file tools they already have, and rarely remember to call a special-purpose retrieval tool. Handing them a catalogue and a path turns retrieval into something they already do well, and a literal `grep` over a few hundred files matches identifiers and names that fuzzy search would blur. See [Knowledge architecture](/architecture/knowledge) for the full reasoning.
:::

Write a good `README.md` for each collection: its first paragraph is what a model matches on when deciding whether your knowledge is relevant, and what it says about page types and conventions is what agents follow.

## Browse and read

On the Knowledge page, choose the collection in the tree, then a page or a source. They are also plain files: the knowledge root is `~/.coffer/vault/knowledge/` and each collection is a folder in it, so you can read and grep them with your own tools. A collection's **⋯** menu has **Copy path**.

The Knowledge page is one tree beside a reading pane, both filling the window under the page header. The title carries the **Experimental** tag; the header's actions are **Tidy all** and **Upload**, the page's one primary button. At the top of the tree, **Collections** has a **New collection** button; below it every collection by its folder name. Opening a collection shows **Pages** and **Sources** first, then anything else in it; every file is shown by its file name, and a source still waiting to be integrated carries a **Waiting** mark.

**A collection.** Choosing a collection shows its folder name, what belongs in it (click it to edit; it saves when you leave the field or press **⌘Enter**, **Esc** cancels, and a toast offers **Undo**) and its properties: **Pages**, **Sources** (with how many are waiting) and **Folder**, with **Tidy** and **Check with agent** beside them. Below come two sections:

- **Check** lists what Coffer found in the collection's files, grouped by kind, each file opening when you click it (see [What Coffer finds on its own](#what-coffer-finds-on-its-own)).
- **Change log** lists every change to the collection, newest first: what it did, who wrote it and when, and the files it touched, each opening with its history beside it. **Show more** loads older changes.

The collection's **⋯** menu holds **Reveal in Finder**, **Copy path**, **Rename…** and **Delete collection…**; a collection with nothing in it yet says so and reminds you that you can upload a source or drop Markdown files into its folder.

**A page or a source.** Choosing a file shows it read-only. Its pane bar names where the file is, then carries **History** (see [History and restore](#history-and-restore)), a **Preview / Source** switch for Markdown, **Open in editor** as a button (see [Edit a file yourself](#edit-a-file-yourself)), and a **⋯** menu with **Reveal in Finder** and **Delete**. Under the title one line describes the file, read from its frontmatter:

- For a **page**: its type, who wrote it and when it was created, and its sources, each opening that source; a source the page names that does not exist is struck through. In the text, every `[[link]]` is a link to the page or source it names; a dead one is marked in red, with a tooltip saying nothing has that name.
- For a **source**: **Cited by N pages**, each opening that page, or **Waiting** when no page cites it yet.

The page has no search box and no per-collection switch: ⌘K jumps to a collection by name, and every collection reaches every agent. There is no form for typing a page into the Knowledge page: you write in your own editor, and agents by writing files.

## Every collection reaches every agent

A collection has no on/off switch and no per-agent reach: every collection is available to every agent, and a collection leaves agents' `coffer-guide` skill only by being deleted.

::: warning Not access control
The skill hands agents the knowledge root, and an agent can read anything under it with its own tools. Keep nothing in a collection that an agent on this machine should not read.
:::

## History and restore

Every change to a collection is kept as a version: your uploads and deletes, a file dropped into the inbox and kept as a source, the sweep filing loose documents into `pages/`, what vault sync brought in, and edits made outside Coffer in your own editor or with an agent's file tools — which is how a tidy shows up. Each change names its **writer** — `user`, `agent`, `daemon` (Coffer filing a loose document into `pages/`), `sync` or `disk` (and `curation` on versions an earlier Coffer wrote) — so you can always tell who changed what. A collection's page lists its changes in its **Change log**.

The history is the vault repository's own: collections live under `knowledge/` in `~/.coffer/vault`, so `git -C ~/.coffer/vault log -- knowledge/<collection>/<path>` reads the same versions, and [vault sync](/guides/vault-sync) carries them to your other machines. Coffer needs `git` for the vault; without it the app shows [Coffer needs git](/guides/troubleshooting#coffer-needs-git) until it is installed. If git goes missing while the daemon runs, every write keeps working and the changes feed that a collection's Change log and a delete's **Undo** read is refused. The refusal carries a prompt for your agent to install git the way that fits your machine and confirm it with `git --version`.

### Bring back an earlier version

Press **History** in a page's or a source's pane bar. The history opens in a drawer beside the file, which stays in view, and the page's address gains `?history=1`, so a link to it opens the drawer too. The drawer holds one card split by a divider you can drag; press **History** again, its ✕ or **Esc** to close it.

- **Left: the versions, newest first,** under **Versions** with their count. Each row says what the version did (*Created*, *Edited* or *Deleted*, or *Restored the version of &lt;date&gt;*), who wrote it, when, and how many lines it moved (+N −M). The writer reads **You** (you, through Coffer), **Edited on disk** (your own editor, a shell, or an agent's own file tools), an agent by product name (when it wrote through a Coffer tool), **Coffer** or **Sync**. The newest is marked **Current** and is chosen when the drawer opens.
- **Right: the chosen version,** with its short id, writer and time, and the diff of every file it changed. For a version other than the current one, a switch picks what the diff shows: **Changes in this version** (against the version before it) or **Compare with current** (from that version to the file as it is now).

To go back, choose a version and press **Restore this version…**. Coffer asks first: the file goes back to that version **as a new version**, so nothing in the history is lost. The restore is written by you, shows in the history as *Restored the version of &lt;date&gt;*, and is recorded in [Activity](/guides/activity). If the file changed since you opened the drawer (a later version, or a save in your editor), the restore is refused with `VAULT_FILE_STALE` and the dialog says so; reopen the history and try again. Opening the history also records an edit you made on disk as a version of its own, so the newest version is always the file as it is.

You can read the same versions with git: `git -C ~/.coffer/vault log -p -- knowledge/<collection>/<path>`.

A deleted file has no pane to open its history from once the delete's toast is gone, but its versions are still in the vault's git history, so git can bring it back (see [Delete files and collections](#delete-files-and-collections)).

## Delete files and collections {#delete-files-and-collections}

Only a person deletes through Coffer. Coffer gives agents no tool that deletes knowledge, and you can delete any page or source, whoever wrote it. The change is also an ordinary file delete, so removing a file in your own editor works too and shows up in the history as an edit made on disk.

- **A page or a source:** Knowledge → choose the file → **⋯** → **Delete**. It happens at once. Deleting a source that pages still cite leaves those pages with a missing source in the [check](#check-a-collection).
- **A whole collection, and every file in it:** Knowledge → choose the collection → **⋯** → **Delete collection…**. Coffer asks first, naming the collection and how many files go with it.

::: tip A delete can be undone
A delete is reported in a toast, *Deleted `<name>`*, with **Undo**, which puts back exactly what it removed — a file into its collection, a collection with its pages, its sources and its README — as one new change by you. Undo is refused, with nothing written, when a file is back at the same path or a collection of the same name exists again. Once the toast is gone, the deleted file has no pane to open its history from, but its versions are still in the vault's history, so git can bring it back (`git -C ~/.coffer/vault log -- knowledge/<path>`); a deleted collection's files can be, but its registration cannot, which is why **Delete collection…** asks first.
:::

## What not to put in knowledge

- **Secrets.** No keys, tokens or passwords. Use [Secret store](/guides/secret-store).
- **What the code already says.** If an agent can read it in the repository, it does not belong here.
- **Scratch notes.** What goes in should still be true in a month.

## Troubleshooting

**A tidy rewrote a page badly.** Open the page, press **History**, choose a version from before the tidy and press **Restore this version…**. The collection's **Change log** shows every file the tidy touched.

**A source stays Waiting after a tidy.** No page lists its slug in `sources`. Ask your agent to integrate it, or, if nothing in it is worth a page, to mark it `ingest: skipped`.

**A link shows in red.** It names no page, alias or source — usually a page that was renamed or merged away. Fix the link, or add the old slug to the surviving page's `aliases`; **Tidy** fixes the dead links it finds.

**My documents moved into `pages/`.** That is the sweep filing loose Markdown into the collection's layout (see [Collections from before pages and sources](#collections-from-before-pages-and-sources)). Write new pages under `pages/`; the move is in the **Change log** and can be restored from the history.

**Tidy offers only Copy prompt.** No managed agent is available. Add one under **Agents**, or paste the copied prompt into the agent you use; it must have the `coffer-guide` skill. **Check with agent** works the same way.

**An agent does not use the knowledge.** Check that the `coffer-guide` skill is enabled and reaches that agent (its **Reach** button on the Skills page), and that the collection's `README.md` opens with a sentence naming its subjects.

**A file an agent wrote never shows up.** A page written into a collection shows up on the next read. A file left in `.inbox/` must be Markdown, directly in the `.inbox/` folder of an existing collection, and becomes a source at the next sweep, within about a minute; a file anywhere else is left alone, and a file that is not Markdown is not kept as a source.

## Related

- [Skills](/guides/skills) — the `coffer-guide` skill that carries the catalogue and the writing, integrating, tidying and checking rules
- [Memory](/guides/memory)
- [Knowledge architecture](/architecture/knowledge)
- [`coffer knowledge` command reference](/reference/cli/knowledge)
- [MCP tools reference](/reference/mcp-tools)
- [Knowledge spec](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/knowledge/spec.md)
- [Knowledge Is a Wiki of Pages Compiled From Kept Sources](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/knowledge-is-a-wiki-of-pages-compiled-from-kept-sources.md), [Knowledge Is Plain Files](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/knowledge-is-plain-files.md) and [Tidying Knowledge Is the Agent's Job](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/tidying-knowledge-is-the-agents-job.md)
