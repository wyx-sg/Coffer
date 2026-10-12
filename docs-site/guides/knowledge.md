---
title: Knowledge
description: Keep what you and your agents know about your working environment as a wiki of Markdown pages compiled from kept sources, which every agent reads with its own file tools, and ask your agent to tidy it.
---

# Knowledge

Knowledge is a directory of Markdown about your working environment — services, repositories, conventions, decisions, pitfalls — that every agent on your machine reads. Each collection is a small wiki: the material you upload is kept as **sources**, and your agent compiles it into **pages** that link to each other. This page covers creating collections, adding sources and pages, how you and your agent change them, how your agent integrates sources, fixes what Coffer found and tidies pages when you press **Tidy**, how a tidy lands as one change you can undo, how Coffer checks a collection and keeps it current, how to look back at a file's history and bring a version back, how to open a collection in Obsidian, and how agents find what is there.

## What knowledge is for

Knowledge holds facts about the world you work in: which team owns a service, how an internal API authenticates, why a migration is ordered the way it is. It arrives because you, or an agent working with you, put it there.

- **One copy for every agent.** Claude Code and Codex read the same files, so what one agent records in the morning another reads in the afternoon.
- **Plain files.** Every page and every source is a Markdown file you can open, edit, grep and back up. Coffer keeps no index, no embeddings and no database copy of the content.
- **Sources kept, pages compiled.** What you upload is kept as a Markdown source, and a page names the sources it draws on, so a statement can always be traced back to the source it came from. The pages are where the knowledge grows: each page is about one subject, says which sources it draws on, and links to the pages it relates to.
- **Written together.** You edit pages in your own editor; the Knowledge page shows them read-only and opens them there. Agents write pages with their own file tools, following the rules in the `coffer-guide` skill: a fact goes into the page that already owns its subject. When you press **Tidy**, your agent folds the sources that are still waiting into the pages, fixes what Coffer found, then merges, splits and corrects the pages, and the whole tidy lands as one change you can undo. Coffer itself runs no model over your knowledge.

Knowledge is not [memory](/guides/memory). Memory is what agents learn while working, read out of their own memory stores. Knowledge is what somebody deliberately wrote down.

## How a collection is laid out

A **collection** is a top-level folder under the knowledge root:

```text
~/.coffer/vault/knowledge/
└── payments/                        ← one collection
    ├── README.md                    ← the schema: what belongs here, page types, rules
    ├── sources/
    │   ├── gateway-design.md        ← a source: the upload converted to Markdown
    │   └── oncall-notes.md          ← a source from a Markdown upload
    ├── pages/
    │   ├── session-ownership.md     ← a page
    │   └── gateway/
    │       └── rate-limits.md       ← nesting is allowed and means nothing
    └── .inbox/                      ← hidden: a drop zone, kept as sources at the next sweep
```

- **`README.md`** at the collection root is the collection's **schema**. Its first paragraph, before its first `##` section, is the collection's description everywhere Coffer shows one, and it is what the `coffer-guide` skill tells agents the collection is about. Its **Page types** and **Rules** sections, and anything else it says about the conventions the collection uses, take precedence over the guide's defaults. `verify_after_days` in its frontmatter sets how long a page's check holds (see [Pages due a recheck](#pages-due-a-recheck)). It is never listed as a page or a source, or counted.
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
verified: 2026-10-12
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
| `verified` | The date (`YYYY-MM-DD`) the page was last checked against its sources or the code. The page's line in the reader shows it. A page without it, or with one older than the collection's `verify_after_days`, is [due a recheck](#pages-due-a-recheck). Where a page's facts came from belongs here and in `sources`, not in a paragraph of the body listing what was read. |
| `actor` | `user` or `agent` — who wrote the page. |
| `created_at`, `updated_at` | Timestamps. |

Coffer writes no page itself: whoever writes a page gives it these keys, as the `coffer-guide` skill teaches agents. A page that lacks `title`, `type` or `description`, names no `sources` or has no `verified`, still works; it shows up as a finding when the collection is [checked](#check-a-collection).

A source carries the keys Coffer writes when it keeps one — `title`, `description`, `actor`, `created_at`, `updated_at`. An agent, or you, may add three more, which describe the source without changing what it says:

| Key | Meaning |
| --- | --- |
| `summary` | One or two sentences on what the source says, written by the agent when it integrates or tidies. The catalogue and the collection's **Contents** show it. |
| `superseded_by` | The slug of a newer source that replaces this one, such as the next version of a design doc (see [When a source is replaced](#when-a-source-is-replaced)). |
| `ingest: skipped` | For a source with nothing worth a page, so it stops waiting. |

Any other key you add to a file is kept, with its value, whenever Coffer rewrites the file.

### Link pages by slug {#link-pages-by-slug}

A page links to another by its slug, never by its path: `[[session-ownership]]`, or `[[session-ownership|the session service]]` to choose the text shown. A link may also name one of a page's `aliases`, or a source's slug. Paths change as a collection is tidied; slugs do not change unless a page is renamed, and the `coffer-guide` skill tells agents to update the links to a page they rename, or to keep its old slug in `aliases`.

Coffer resolves every link each time a page is read, ignoring case. A link that names nothing is **dead**, and one that names more than one file is **ambiguous**; both are reported by the [check](#check-a-collection), and the Knowledge page marks a dead link in the page.

### Sources wait until a page cites them {#sources-wait-until-a-page-cites-them}

A source **waits** while no page lists it in `sources` and it is marked neither `ingest: skipped` nor `superseded_by`. Nothing else records which sources have been integrated: as soon as a page cites a source, it stops waiting. The Knowledge page marks a waiting source **Waiting**, the collection's page counts them, the `coffer-guide` catalogue names them, and **Tidy** asks your agent to integrate them first.

## Create a collection

Collections are created only on purpose, and only by a person. Reading, writing, an agent's working directory or a Markdown file an agent drops into some other folder never creates one.

<Shot name="knowledge-page" alt="The Knowledge page, with a collection and its documents." />

```text
Knowledge → Add → New collection… → Name, What belongs in here → Create collection
```

**New collection…** is also the button at the top of the tree. The **Add** menu says what each entry keeps: a new collection is kept in Coffer, synced to your other Macs, with its history, and tidied by your agent. This creates `~/.coffer/vault/knowledge/payments/` and its `README.md`; `pages/` and `sources/` appear as soon as something is written into them. The README starts with the defaults written out, so you can see what your agents follow and change it:

```markdown
---
verify_after_days: 90
---

# payments

How payments are taken, settled and refunded.

## Page types

- `overview`: where to start. What this collection covers and which pages to read first.
- `concept`: what something is and why it works the way it does.
- `entity`: one service, system or team. What it owns and how to reach it.
- `how-to`: the steps for one task.
- `decision`: a choice that was made, the options and the reason.

## Rules

- One subject per page. Link related pages with `[[slug]]`.
- Every page lists the sources it draws on in `sources`, and the day it was last
  checked against them or the code in `verified`.
- `verify_after_days` at the top of this file is how many days a check holds
  before Coffer asks for another. `0` turns it off.
```

Change the page types or add rules of your own here; agents follow this file over their defaults. A collection has no title: every page and listing shows it by its folder name. Its description is the opening paragraph of the README, before the first `##` section: change it on the collection's page (click the text; it saves when you leave the field) or in the file itself. Either way only that paragraph changes, and everything under it — the page types and rules included — stays.

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
6. Never edit a source, except to add `ingest: skipped`, `superseded_by` or a `summary`.
7. Give every page a `title`, a `type`, a one-line `description` saying what question it answers, the `sources` it draws on, any `aliases`, the date it last checked the page against its sources or the code as `verified`, and `actor: agent`. Where the page's facts came from goes in `sources` and `verified`, never in a paragraph listing what it read.

The guide also tells an agent to **write back what it works out**. When it answers your question by reading a source, the code or a system, and the pages do not already say it, it writes the answer into the page that owns the subject before it finishes, adds what it read to `sources` when that is a source, sets `verified` to today, and tells you in one line what it added. It does not write back a guess, an opinion, or something true only of that conversation. Every such write is in the collection's history, so you can undo it.

You can also ask directly: "write down what we just found out about the session TTL in the payments collection." The collection must already exist; only you create one. Whatever the agent writes is readable at once, and the next sweep commits it to the [history](#history-and-restore). A page an agent writes in the wrong place — at the collection root, say — is moved into `pages/` within a minute.

### Upload a source {#upload-a-source}

Upload converts a file to Markdown and keeps it in the collection as a source straight away. Only the Markdown is kept: the file you uploaded is not stored, so keep your own copy if you need it.

```text
Knowledge → Add → Upload documents… → choose or drop files, pick the collection → Upload
```

The **Add** menu says what an upload keeps: each file is converted to Markdown and kept as a source in the collection you pick, and synced with it.

| Accepted | Formats |
| --- | --- |
| Converted | `pdf`, `docx`, `pptx`, `xlsx`, `xls`, `html`, `htm`, `epub` |
| Tables | `csv`, `tsv` |
| Taken as text | `md`, `markdown`, `mdx`, `txt`, `text`, `rst`, `json`, `yaml`, `yml`, `toml`, `ini`, `cfg`, `log`, `sql`, and common source files (`py`, `js`, `ts`, `go`, `rs`, `java`, `sh`, …) |

An uploaded PDF, for example, becomes `sources/gateway-design.md`, the extracted Markdown with frontmatter, and nothing else. A file taken as text — Markdown, plain text, source code — becomes a source the same way. A name another source already has gets a suffix (`-2`).

You can pick or drop several files at once. Each is listed with its own state — waiting, converting, done, or failed with its reason — and they are sent one after another, so one failure does not stop the rest. A ZIP archive, or a file over 20 MB, is marked refused with its reason before anything is sent. A file that failed stays in the dialog so you can retry it, and one notice at the end says how many were kept and how many failed. The upload takes the collection, not a folder. An unsupported type is refused with the type named, and a conversion that produces no text — an image-only PDF, for example — is refused too. A refused file leaves nothing behind.

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

To add a page, save a Markdown file under the collection's `pages/` folder (**Reveal in Finder** on the collection). To add material, use **Add → Upload documents…**, or drop a Markdown file into the collection's `.inbox/`. Leave sources as they are: a source is the record of what arrived.

Agents do the same thing with their own file tools, by the writing rules the `coffer-guide` skill gives them (see [From an agent](#from-an-agent-write-into-the-pages)).

## Tidy a collection {#tidy-a-collection}

Over time a collection collects work to do: sources no page has drawn on yet, two pages that answer the same question, one that answers several, a statement a newer page contradicts, a link that no longer names a page. Coffer does not fix these itself. It hands the job to your agent, which reads the files with its own file tools and edits the pages.

### Press Tidy

```text
Knowledge → choose the collection → Tidy
Knowledge → Tidy all   (every collection, one after another)
```

**Tidy** starts your default hand-off agent in your preferred terminal, with a prompt that names the collection, its folder, its number of pages and waiting sources, and every finding Coffer listed under the collection's **To do** (see [What Coffer finds on its own](#what-coffer-finds-on-its-own)) as its first message. You watch the agent work in the terminal. **Tidy all**, in the Knowledge page's header, sends one prompt the same way that names every collection with its counts, including how many findings it has, and asks the agent to go through them one at a time, reading each collection's findings with `coffer knowledge check <collection>`. With no managed agent available, the button offers **Copy prompt** instead: paste it into whichever agent you use.

The prompt points the agent at the **Integrating sources** and **Tidying a collection** sections of the `coffer-guide` skill. Following them, the agent works through one collection at a time:

1. **Opens the tidy** with `coffer knowledge tidy-start <collection>` before it changes anything (see [A tidy is one change](#a-tidy-is-one-change)).
2. **Integrates the waiting sources**, oldest first: reads each one in full, folds what it says into the pages that own its subjects, creates a page for a subject no page owns, adds the source's slug to the `sources` of every page it changed, and gives the source a `summary`. When the source replaces an older one, it marks the older one `superseded_by` and rechecks the pages that cite it. A source with nothing worth keeping — a duplicate, an empty export — is marked `ingest: skipped` instead.
3. **Fixes what Coffer found**: dead and ambiguous links, orphan and incomplete pages, pages without sources, missing sources, pages citing an outdated source. It **rechecks every page due a recheck** against its sources or the code, fixes what changed and sets its `verified` to today; a page it cannot recheck keeps its date and goes into its report. It gives every source without a `summary` one.
4. Reads the collection's `README.md` and every page's title and description, then the pages in full.
5. **Merges** pages that answer the same question into one, keeping every fact and every source, keeps the merged-away slug in the survivor's `aliases`, and deletes the pages it merged away.
6. **Splits** a page that answers several unrelated questions, one subject per page, linked to each other.
7. **Corrects** what is wrong, stale or contradictory by the rule that the newer statement wins unless the older is shown to be right, rewrites a description that does not say what question its page answers, and gives a subject mentioned across pages but owned by none a page of its own.
8. **Leaves alone what it is not sure about** — two pages that disagree with nothing to tell which is right, a deletion of much text, a change to the README's page types — and lists it in its report for you to decide.
9. **Finishes the tidy** with `coffer knowledge tidy-finish <collection> --set summary="<report>"`. The report says which sources it integrated or skipped, what it merged, split, corrected, rechecked and deleted, and what it left for you. It ends with **Gaps**: questions the pages cannot answer, subjects mentioned across pages but owned by none, and sources worth finding — a spec, a runbook, a person to ask.

It changes nothing that does not need changing. You can also ask any agent that has the `coffer-guide` skill to do this in your own words: "tidy up the payments knowledge."

### A tidy is one change {#a-tidy-is-one-change}

From `tidy-start` to `tidy-finish`, Coffer keeps the agent's edits in that collection together instead of recording them one file at a time:

- The collection's page says that an agent is tidying it and that its edits will appear as one change when it finishes. The files on disk change as the agent works, and every read shows them.
- Nothing commits those edits in the meantime: not the sweep, not the vault's own scanner. A [vault sync](/guides/vault-sync) round that would change one of those files waits, as it does for any edit not yet in the history.
- When the agent finishes, every edit is recorded as **one change** by the agent, with its report. The collection's **Change log** shows it as one entry: the agent, the time, the report and the files by title.
- A tidy that changed nothing records nothing.
- An agent that never finishes does not hold the collection for ever: once the collection has sat unchanged for 30 minutes, Coffer closes the tidy and records what it changed as one change, shown as *closed without a report*.
- Whatever changed in the collection before `tidy-start` is recorded first as the edit on disk it was, so the tidy holds only the agent's work.

Coffer remembers an open tidy only while it runs: if Coffer restarts during a tidy, the edits made so far are recorded as ordinary edits on disk, and nothing is lost but the grouping. An agent that skips `tidy-start` gets the same result.

### Undo a tidy {#undo-a-tidy}

```text
Knowledge → choose the collection → Change log → the tidy → Undo this tidy…
```

**Undo this tidy…** puts every file the tidy touched back as it was just before it: a page it changed gets its earlier text, a page it deleted comes back, and a page it created is removed. Coffer asks first, naming the tidy and how many files go back. The undo is one new change written by you, so the tidy stays in the history after it, and it is recorded in [Activity](/guides/activity).

If one of those files was edited after the tidy — by you, by another agent or by sync — the dialog lists it and undoes nothing until you choose **Undo anyway**, which discards those later edits too. They stay in the history, so a file's **History** can still bring them back.

On the command line, `coffer knowledge undo <version>` does the same, refused with `KNOWLEDGE_UNDO_CONFLICT` and the files' names when one was edited since; add `--set force=true` to undo anyway. The version is the change's, from `coffer knowledge changes`.

To put back only one page, open it, press **History**, choose the version before the tidy and press **Restore this version…** (see [History and restore](#history-and-restore)).

### Ask for a review only {#ask-for-a-review-only}

To hear what the agent would change before it changes anything, say so in the session Tidy opened: "don't change anything yet — tell me what you would do." The `coffer-guide` skill tells an agent asked only for a check or a review to report and change nothing. You can then tell it what to go ahead with.

### Nothing tidies on its own

Tidy runs only when you press it or ask your agent. Coffer starts no agent run of its own, so nothing spends your quota or opens a conversation you did not start.

::: info What leaves your machine
Coffer sends nothing about your knowledge to any model. When you press Tidy, the files the agent reads go to that agent's own provider, as in any conversation with it.
:::

## Check a collection {#check-a-collection}

Coffer finds what can be found mechanically, every time a collection is read, and fixes none of it. Fixing it is part of [Tidy](#tidy-a-collection), whose prompt carries the same list.

### What Coffer finds on its own {#what-coffer-finds-on-its-own}

The **To do** section of a collection's page lists these findings, grouped by kind with the most serious first. Each names the page by its title (hover to see its path) and opens it when you click it. The minor kinds — pages without sources and pages nothing links to — are folded into one row you can open. With nothing to report, the section says so in one line.

| Finding | What it means |
| --- | --- |
| **Dead links** | A `[[link]]` that names no page, alias or source. |
| **Ambiguous links** | A `[[link]]` that names more than one file. |
| **Names used twice** | Two pages share a slug, or an alias names two pages. |
| **Missing sources** | A page's `sources` names a source that does not exist, or a source's `superseded_by` names one that does not. |
| **Pages citing an outdated source** | A page cites a superseded source and none of the sources that replace it (see [When a source is replaced](#when-a-source-is-replaced)). The row names the source it cites and its newest replacement. |
| **Waiting sources** | A source no page cites and not marked `ingest: skipped` or `superseded_by`. |
| **Incomplete pages** | A page missing its `title`, `type` or `description`. |
| **Pages to recheck** | A page whose `verified` date is missing or older than the collection's interval (see [Pages due a recheck](#pages-due-a-recheck)). The row says when it was last checked, or *never checked*. |
| **Pages without sources** | A page whose `sources` is empty. |
| **Pages nothing links to** | A page no other page links to, once the collection has two or more pages. Pages of type `overview` are exempt: they are entry points. |

The findings are worked out from the files on every read and stored nowhere, so they are current the moment a file changes. They are hints, not errors: a page you wrote without sources still works. On the command line, `coffer knowledge check <collection>` prints the same list (see [`coffer knowledge`](/reference/cli/knowledge#knowledge-check)).

### When a source is replaced {#when-a-source-is-replaced}

Sources go out of date: a newer design doc or runbook replaces the one your pages were written from. Mark the old source with the slug of the new one:

```markdown
---
title: Gateway design (2025)
superseded_by: gateway-design-2026
---
```

Your agent adds this line itself when it integrates a source that replaces another. From then on every page that cites the old source and none of the newer ones is listed under **Pages citing an outdated source**, and the next tidy rechecks it against the new source. Replacements can chain: if `v1` is replaced by `v2` and `v2` by `v3`, a page that cites `v1` and `v3` is current. The old source stays where it is and stops waiting, because a page may still cite it for what used to be true; opening it shows **Superseded by** and a link to its replacement, and the catalogue marks it so agents know it is no longer evidence. A `superseded_by` that names no source is listed under **Missing sources**.

### Pages due a recheck {#pages-due-a-recheck}

A page can drift from the world while its sources stay the same: the code or the system it describes changes. Every page carries `verified`, the day it was last checked against its sources or the code, and a page whose `verified` is missing or older than the collection's interval is listed under **Pages to recheck**. Opening it shows **Needs rechecking**, and *never checked* when it has no date. It is only flagged: it stays in the catalogue and agents still read it.

The interval is 90 days. Set another in the README's frontmatter — `verify_after_days: 30` for a runbook collection, say — or `0` to turn the check off for that collection. A negative value, or one that is not a whole number of days, is read as 90. A tidy rechecks each page it lists and sets its `verified` to today.

The first time you open a collection after updating, every page without `verified` is listed. Press **Tidy** and the agent rechecks them.

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
- Its **body**, loaded when the agent opens the skill, gives the knowledge root's path and a catalogue of every collection: its README, its pages grouped by `type` with each page's path, title and description, and its sources, each marked *(waiting)* or *(superseded by …)* and followed by its `summary`. It also carries the layout, the rules for writing a page, and the steps for integrating sources and tidying described above.

When the pages do not carry what an agent is after, the guide tells it to grep the collection's `sources/` for the exact string. A large catalogue is shortened to fit: first the descriptions and summaries are left out and only the waiting sources are listed, and if it is still too long only each collection's counts are listed with the folders to search, and the skill says so.

Coffer rewrites the skill whenever the catalogue changes, so a new page appears in it within one sweep.

::: details Why no search tool
Agents reliably use the file tools they already have, and rarely remember to call a special-purpose retrieval tool. Handing them a catalogue and a path turns retrieval into something they already do well, and a literal `grep` over a few hundred files matches identifiers and names that fuzzy search would blur. See [Knowledge architecture](/architecture/knowledge) for the full reasoning.
:::

Write a good `README.md` for each collection: its first paragraph is what a model matches on when deciding whether your knowledge is relevant, and what it says about page types and rules is what agents follow.

## Browse and read

On the Knowledge page, choose the collection in the tree, then a page or a source. They are also plain files: the knowledge root is `~/.coffer/vault/knowledge/` and each collection is a folder in it, so you can read and grep them with your own tools. A collection's **⋯** menu has **Copy path**.

The Knowledge page is one tree beside a reading pane, both filling the window under the page header. The title carries the **Experimental** tag; the header's actions are **Tidy all** and **Add**, the page's one primary button. **Add** opens a menu, each item with a line saying what it keeps in Coffer: **Upload documents…** (see [Upload a source](#upload-a-source)), **New collection…** (see [Create a collection](#create-a-collection)) and **Link an external folder…** (see [Link an external folder](#link-an-external-folder)). At the top of the tree, **Collections** has a **New collection** button; below it every collection by its folder name. Opening a collection shows **Pages** and **Sources** first, then anything else in it; every file is shown by its file name, each page with its type's icon, each source with the source icon, and a source still waiting to be integrated carries a **Waiting** mark. The tree remembers what you opened and closed: leave the page or reload it and the same collections and folders are open when you come back.

**A collection.** Choosing a collection shows **Tidy** and a **⋯** menu in its pane bar. Below them come its folder name, what belongs in it (click it to edit; it saves when you leave the field or press **⌘Enter**, **Esc** cancels, and a toast offers **Undo**), and one summary line: how many pages, how many sources and how many of them wait, the folder's path with a copy button, and when it was last updated. A muted line under it says the collection is managed by Coffer: synced to your other Macs, its history kept, tidied by your agent. While an agent is tidying the collection, a notice says so (see [A tidy is one change](#a-tidy-is-one-change)). Then come three sections:

- **To do** lists what Coffer found in the collection's files, most serious first, each page by its title and opening when you click it, including **Pages citing an outdated source** and **Pages to recheck** (see [What Coffer finds on its own](#what-coffer-finds-on-its-own)).
- **Contents** shows the collection's pages by type — overview, concept, entity, how-to and decision, then the types the README defines, then pages with no type — one card each, with the type's icon, how many pages it holds and the first few titles, then how many more; a **Sources** card lists the sources — the waiting ones first, then the rest, the superseded ones last and struck through — each with its state (*waiting*, *used by N pages*, *skipped* or *superseded*) and its summary under it. Each title opens its file.
- **Change log** lists every change to the collection, newest first: what it did, who wrote it and when, and the files it touched by title, each opening at its history. A tidy is one entry with the agent's report and **Undo this tidy…** (see [Undo a tidy](#undo-a-tidy)); edits made on disk within 10 minutes of each other are one entry listing their files. **Show more** loads older changes.

The collection's **⋯** menu holds **Reveal in Finder**, **Open in Obsidian** when Obsidian is installed on this Mac (see [Open a collection in Obsidian](#open-a-collection-in-obsidian)), **Copy path**, **Rename…** and **Delete collection…**; a collection with nothing in it yet says so and reminds you that you can upload a source or drop Markdown files into its folder.

**A page or a source.** Choosing a file shows it read-only. Its pane bar names where the file is, then carries **History** (see [History and restore](#history-and-restore)), a **Preview / Source** switch for Markdown, **Open in editor** as a button (see [Edit a file yourself](#edit-a-file-yourself)), and a **⋯** menu with **Reveal in Finder**, **Open in Obsidian** when it is installed, and **Delete**. Under the title one line describes the file, read from its frontmatter:

- For a **page**: its type, who wrote it and when it was created, **verified** and the date when the page carries `verified`, **Needs rechecking** when it is [due a recheck](#pages-due-a-recheck) (with *never checked* when it has no date), and its sources, each opening that source; a source the page names that does not exist is struck through. In the text, every `[[link]]` is a link to the page or source it names; a dead one is marked in red, with a tooltip saying nothing has that name. Inline code is set lighter than a code block, and a long path wraps at its `/`.
- For a **source**: **Superseded by** and a link to the source that replaces it, when one does; **Cited by N pages**, each opening that page, or **Waiting** when no page cites it yet.

The page has no search box and no per-collection switch: ⌘K jumps to a collection by name, and every collection reaches every agent. There is no form for typing a page into the Knowledge page: you write in your own editor, and agents by writing files.

## Open a collection in Obsidian {#open-a-collection-in-obsidian}

A collection is plain Markdown that [Obsidian](https://obsidian.md) reads as it is: open its folder, or the whole knowledge root, as an Obsidian vault and you can browse, search and edit the pages there. `[[slug]]` links resolve by file name, as Obsidian resolves them, and `aliases` in frontmatter is the key Obsidian already reads. Coffer ignores hidden folders such as `.obsidian/`, where Obsidian keeps its settings: they are not committed, not catalogued and not synced.

When Obsidian is installed on this Mac, a collection's **⋯** menu and a file's **⋯** menu offer **Open in Obsidian**. The first time:

1. In Obsidian, choose **Open folder as vault** and pick the collection's folder, `~/.coffer/vault/knowledge/<collection>/`. `~/.coffer` is hidden: press **⌘⇧.** in the dialog to show it, or use **Copy path** on the collection and paste it with **⌘⇧G**.
2. In Obsidian's **Settings › Files and links**, set **Default location for new notes** to the collection's `pages/` folder. A Markdown file left outside `pages/` and `sources/` is filed into `pages/` by the sweep within a minute, so a note created at the vault's root would move.

An edit you save in Obsidian is like an edit in any editor: live at once, recorded as an edit on disk by the next sweep. Leave the files under `sources/` as they are.

## Link an external folder {#link-an-external-folder}

If you already keep notes with your own tools, such as an Obsidian vault, a Logseq graph or a folder of Markdown in a repository, you can share that folder with your agents without moving it. Coffer calls it a linked folder.

```text
Knowledge → Add → Link an external folder… → Folder, Name → Link folder
```

**Folder** is the folder's absolute path, `/Users/you/Obsidian/Work` say. **Name** is how Coffer and your agents refer to it: it follows the folder's own name until you type one, and the folder on disk keeps its own name either way. On the command line the same thing is `coffer knowledge link --set folder=/Users/you/Obsidian/Work` (see [`coffer knowledge link`](/reference/cli/knowledge#knowledge-link)).

### What Coffer does with it {#what-coffer-does-with-a-linked-folder}

- **Shares it with every agent.** The folder gets its own section in the `coffer-guide` skill every agent reads: its path, its rules file and every Markdown note by title. Agents read the notes where they are, with their own file tools.
- **Shows it on the Knowledge page.** The tree lists it with a linked-folder icon, and you can open and read any of its notes. Its page shows its name with an **External** tag and four facts: **Location** (its path, with **Reveal in Finder**), **Notes** (how many Markdown notes it holds), **Rules file**, and **Managed by**: its own tools, with Coffer only sharing it with agents.
- **Reads it fresh each time.** Nothing is cached, so a note you save in Obsidian is what the page and your agents see next.

### What Coffer does not do {#what-coffer-does-not-do-with-a-linked-folder}

- **It copies nothing.** No file goes into `~/.coffer`. The folder stays the only copy.
- **It writes nothing into the folder.** You cannot upload into it, its notes have no **Delete**, its description (the first paragraph of its own `README.md`) is not edited here, and it has no **Tidy**, no **To do**, no inbox and no filing of notes into `pages/`. Coffer's `pages/` and `sources/` layout does not apply to it.
- **It keeps no history.** Its notes have no **History**, its page has no **Change log**, and nothing can be undone through Coffer. Use the folder's own tools for that: Obsidian's file recovery, or git if the folder is a repository.
- **It does not sync it.** Neither the folder's files nor the link reach your other Macs through [vault sync](/guides/vault-sync). The link is recorded only on this Mac, in `~/.coffer/local/resources/knowledge/`, because the folder's path is true of this Mac only. To use the same notes on another Mac, keep the folder in step with its own tool (Obsidian Sync, iCloud Drive, git) and link it on that Mac as well.

### How agents write in it {#how-agents-write-in-a-linked-folder}

The folder's **rules file** is the first of `AGENTS.md`, `CLAUDE.md` and `README.md` found at its root. The guide tells agents to follow that file before writing anything in the folder, and, when there is none, to write only the way its existing notes are written. Coffer's own rules for a collection (pages under `pages/`, sources kept apart, page types in frontmatter, the inbox, Tidy) do not apply there. So if you want agents to add notes to your vault, write your conventions in an `AGENTS.md` at its root; if you want them only to read it, say that there.

### Large folders {#large-linked-folders}

Coffer skips hidden folders, such as `.obsidian/` and `.git/`, and `node_modules`. It reads at most 5000 Markdown notes from one folder, and a file over 2 MB is listed but not shown on the page. To share only part of a large vault, link a subfolder of it instead of the whole vault.

### Folders that cannot be linked {#folders-that-cannot-be-linked}

The folder must exist and be given as an absolute path. Coffer's own folder, `~/.coffer`, cannot be linked, and neither can a folder that holds it, such as your home folder or the disk root. These are refused with [`KNOWLEDGE_FOLDER_REFUSED`](/reference/error-codes). A folder that is already linked, or a name another collection has, is refused with `KNOWLEDGE_COLLECTION_EXISTS`.

### Rename or disconnect {#rename-or-disconnect-a-linked-folder}

A linked folder's **⋯** menu holds **Reveal in Finder**, **Open in Obsidian** when Obsidian is installed, **Copy path**, **Rename…** and **Disconnect…**. **Rename…** changes only the name Coffer and your agents use. **Disconnect…** asks first; afterwards agents stop seeing the folder, and every file in it stays where it is.

## Every collection reaches every agent

A collection has no on/off switch and no per-agent reach: every collection is available to every agent, a linked folder too, and a collection leaves agents' `coffer-guide` skill only by being deleted (a linked folder by **Disconnect…**, which leaves its files alone).

::: warning Not access control
The skill hands agents the knowledge root, and an agent can read anything under it with its own tools. Keep nothing in a collection that an agent on this machine should not read.
:::

## History and restore

Every change to a collection is kept as a version: your uploads and deletes, a file dropped into the inbox and kept as a source, the sweep filing loose documents into `pages/`, what vault sync brought in, and a tidy, recorded as one change by the agent carrying its report, and edits made outside Coffer in your own editor or with an agent's file tools. Each change names its **writer** — `user`, `agent`, `daemon` (Coffer filing a loose document into `pages/`), `sync` or `disk` (and `curation` on versions an earlier Coffer wrote) — so you can always tell who changed what. A collection's page lists its changes in its **Change log**.

The history is the vault repository's own: collections live under `knowledge/` in `~/.coffer/vault`, so `git -C ~/.coffer/vault log -- knowledge/<collection>/<path>` reads the same versions, and [vault sync](/guides/vault-sync) carries them to your other machines. Coffer needs `git` for the vault; without it the app shows [Coffer needs git](/guides/troubleshooting#coffer-needs-git) until it is installed. If git goes missing while the daemon runs, every write keeps working and the changes feed that a collection's Change log and a delete's **Undo** read is refused. The refusal carries a prompt for your agent to install git the way that fits your machine and confirm it with `git --version`.

### Bring back an earlier version

Press **History** in a page's or a source's pane bar. The history takes over the whole Knowledge area, with the tree and the file out of the way so the versions and the diff have room, and the page's address gains `?history=1`, so a link to it opens the history too. It holds one card split by a divider you can drag; its ✕ or **Esc** takes you back to the file.

- **Left: the versions, newest first,** under **Versions** with their count. Each row says what the version did (*Created*, *Edited* or *Deleted*, or *Restored the version of &lt;date&gt;*), who wrote it, when, and how many lines it moved (+N −M). The writer reads **You** (you, through Coffer), **Edited on disk** (your own editor, a shell, or an agent's own file tools), an agent by product name (when it wrote through a Coffer tool), **Coffer** or **Sync**. The newest is marked **Current** and is chosen when the history opens.
- **Right: the chosen version,** with its short id, writer and time, and the diff of every file it changed. For a version other than the current one, a switch picks what the diff shows: **Changes in this version** (against the version before it) or **Compare with current** (from that version to the file as it is now).

To go back, choose a version and press **Restore this version…**. Coffer asks first: the file goes back to that version **as a new version**, so nothing in the history is lost. The restore is written by you, shows in the history as *Restored the version of &lt;date&gt;*, and is recorded in [Activity](/guides/activity). If the file changed since you opened the history (a later version, or a save in your editor), the restore is refused with `VAULT_FILE_STALE` and the dialog says so; reopen the history and try again. Opening the history also records an edit you made on disk as a version of its own, so the newest version is always the file as it is.

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

**A tidy rewrote a page badly.** Undo the whole tidy from its entry in the collection's **Change log** with **Undo this tidy…** (see [Undo a tidy](#undo-a-tidy)), or put back one page: open it, press **History**, choose a version from before the tidy and press **Restore this version…**.

**A tidy shows up as separate edits on disk.** The agent did not run `coffer knowledge tidy-start` first, or Coffer restarted while it worked. Its edits are all in the history, one per edit; restore a page from its **History**.

**The collection page says an agent is tidying, but nothing is happening.** The agent stopped without running `tidy-finish`. Ask it to finish, or wait: once the collection has sat unchanged for 30 minutes, Coffer closes the tidy and records it as *closed without a report*.

**Every page is listed under Pages to recheck after updating.** Those pages have no `verified` date yet. Press **Tidy**: the agent rechecks each one and sets its date. To stop the check for a collection, set `verify_after_days: 0` in its README.

**A source stays Waiting after a tidy.** No page lists its slug in `sources`. Ask your agent to integrate it, or, if nothing in it is worth a page, to mark it `ingest: skipped`.

**A link shows in red.** It names no page, alias or source — usually a page that was renamed or merged away. Fix the link, or add the old slug to the surviving page's `aliases`; **Tidy** fixes the dead links it finds.

**My documents moved into `pages/`.** That is the sweep filing loose Markdown into the collection's layout (see [Collections from before pages and sources](#collections-from-before-pages-and-sources)). Write new pages under `pages/`; the move is in the **Change log** and can be restored from the history.

**Tidy offers only Copy prompt.** No managed agent is available. Add one under **Agents**, or paste the copied prompt into the agent you use; it must have the `coffer-guide` skill.

**A note made in Obsidian moved into `pages/`.** Obsidian created it at the vault's root, and the sweep filed it. Set Obsidian's default location for new notes to the collection's `pages/` folder (see [Open a collection in Obsidian](#open-a-collection-in-obsidian)).

**Open in Obsidian is not in the menu.** Coffer offers it only when Obsidian is installed on this Mac, in `/Applications` or your own Applications folder.

**An agent does not use the knowledge.** Check that the `coffer-guide` skill is enabled and reaches that agent (its **Reach** button on the Skills page), and that the collection's `README.md` opens with a sentence naming its subjects.

**A file an agent wrote never shows up.** A page written into a collection shows up on the next read. A file left in `.inbox/` must be Markdown, directly in the `.inbox/` folder of an existing collection, and becomes a source at the next sweep, within about a minute; a file anywhere else is left alone, and a file that is not Markdown is not kept as a source.

## Related

- [Skills](/guides/skills) — the `coffer-guide` skill that carries the catalogue and the writing, integrating and tidying rules
- [Memory](/guides/memory)
- [Vault sync](/guides/vault-sync) — what syncs, and why linked folders do not
- [Knowledge architecture](/architecture/knowledge)
- [`coffer knowledge` command reference](/reference/cli/knowledge)
- [MCP tools reference](/reference/mcp-tools)
- [Knowledge spec](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/knowledge/spec.md)
- [Knowledge Is a Wiki of Pages Compiled From Kept Sources](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/knowledge-is-a-wiki-of-pages-compiled-from-kept-sources.md), [Knowledge Is Plain Files](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/knowledge-is-plain-files.md) [Tidying Knowledge Is the Agent's Job, One Hand-Off Recorded as One Change](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/tidying-knowledge-is-the-agents-job.md), [Knowledge Stays Current Through Flags Coffer Computes and an Agent Clears](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/knowledge-stays-current-through-flags-coffer-computes.md) and [A Linked Knowledge Folder Is Shared in Place, Read-Only to Coffer, and Recorded Machine-Local](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/linked-knowledge-folders-are-read-only-and-machine-local.md)
