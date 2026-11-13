---
title: Knowledge
description: Keep what you and your agents know about your working environment as collections of Markdown files, each kept by its own rules file, which every agent reads with its own file tools, and ask your agent to tidy them.
---

# Knowledge

Knowledge is a directory of Markdown about your working environment — services, repositories, conventions, decisions, pitfalls — that every agent on your machine reads. Each collection is a folder that sets its own format in its own **rules file**, the way an Obsidian vault is laid out however you like; a new one can start as an LLM wiki, with pages compiled from kept sources. This page covers creating collections, adding files, how you and your agent change them, how your agent tidies a collection by its rules when you press **Tidy**, how a tidy lands as one change you can undo, the one thing Coffer checks (broken links), how to look back at a file's history and bring a version back, how to open a collection in Obsidian, and how agents find what is there.

## What knowledge is for

Knowledge holds facts about the world you work in: which team owns a service, how an internal API authenticates, why a migration is ordered the way it is. It arrives because you, or an agent working with you, put it there.

- **One copy for every agent.** Claude Code and Codex read the same files, so what one agent records in the morning another reads in the afternoon.
- **Plain files.** Every file is Markdown you can open, edit, grep and back up. Coffer keeps no index, no embeddings and no database copy of the content.
- **Each collection sets its own format.** How a collection is laid out, which frontmatter its files carry and how it is kept up to date are written in its rules file, which you and your agents can change. Coffer gives no folder, page type or frontmatter key a meaning of its own, and checks only that links lead somewhere.
- **Written together.** You edit files in your own editor; the Knowledge page shows them read-only and opens them there. Agents write with their own file tools, following the collection's rules file. When you press **Tidy**, your agent tidies the collection by those rules and fixes its broken links, and the whole tidy lands as one change you can undo. Coffer itself runs no model over your knowledge.

Knowledge is not [memory](/guides/memory). Memory is what agents learn while working, read out of their own memory stores. Knowledge is what somebody deliberately wrote down.

## How a collection is laid out

A **collection** is a top-level folder under the knowledge root. What is in it is up to the collection. One started from the **LLM wiki** template (see [Create a collection](#create-a-collection)) looks like this:

```text
~/.coffer/vault/knowledge/
└── payments/                        ← one collection
    ├── README.md                    ← its description, and what it declares to Coffer
    ├── AGENTS.md                    ← its rules file: how it is written and kept
    ├── index.md                     ← its start page
    ├── pages/
    │   ├── session-ownership.md
    │   └── gateway/
    │       └── rate-limits.md
    ├── sources/                     ← its uploads folder: uploads land here
    │   ├── release-notes.md         ←   an upload converted to Markdown
    │   └── gateway-design/          ←   an upload with pictures: one folder
    │       ├── gateway-design.md
    │       └── image-1.png
```

- **`README.md`** at the collection root says what the collection is. Its first paragraph, before its first `##` section, is the collection's description everywhere Coffer shows one, and it is what the `coffer-guide` skill tells agents the collection is about. Its frontmatter may declare three things to Coffer, all optional (see [What a README declares](#what-a-readme-declares)). It is never counted among the collection's files.
- **The rules file** says how the collection is written and kept: its layout, the frontmatter its files carry, what to read first, what a tidy checks. Agents read it before they write anything, and it wins over anything they would do by default. It is an ordinary file of the collection: change it to change how the collection is kept.
- **The start page**, such as an `index.md`, is where an agent begins reading, when the collection names one.
- **The uploads folder**, `sources/` unless the README names another, is where Coffer writes an upload, converted to Markdown (see [Upload a document](#upload-a-source)). An upload with pictures or attachments is a folder of its own there, the file and its pictures side by side; they sync with the collection and have history, like the Markdown. The file you uploaded is not put in the collection: Coffer keeps it on the Mac you uploaded it from (see [Pictures and the original file](#pictures-and-the-original-file)).
- **Every other file and folder** is the collection's own. Coffer lists it in the tree, checks its links and never moves it.
- **Hidden entries** (names starting with `.`) are left out of every count, the catalogue and the check, and the Knowledge page lists none of them. They are not synced and have no history.

A file's path is where it is; its **slug** — the file name without `.md` — is the name a `[[slug]]` link uses. A file name may hold any character but `/`, `\` and control characters, and may not start with `.`.

The knowledge root is inside the vault repository, at `~/.coffer/vault/knowledge`; the `coffer-guide` skill names it to every agent. It cannot be moved elsewhere: a tree outside the vault would be a tree its history cannot see.

### What a README declares {#what-a-readme-declares}

A collection's `README.md` may carry three keys in its frontmatter. Each is a path relative to the collection, and each is optional:

```markdown
---
rules: AGENTS.md
entry: index.md
uploads: sources
---

# payments

How payments are taken, settled and refunded.
```

| Key | Meaning | Without it |
| --- | --- | --- |
| `rules` | The file agents follow when they write or tidy here. It may be a file in another collection, `../shared/rules.md`, so several collections follow one set of rules. | The first of `AGENTS.md`, `CLAUDE.md` and `README.md` at the collection's root. |
| `entry` | The page an agent starts reading at. | None: the `coffer-guide` catalogue lists the collection's files by folder instead. |
| `uploads` | The folder an upload lands in, inside the collection. | `sources/`. |

A key that names a file that is not there, or a path that climbs out of the knowledge root, is read as not given. Every other key in the README, and every key in any other file, is the collection's own: Coffer reads no `type`, `sources`, `verified` or any other key, and asks no file for one.

### Frontmatter

Coffer requires none. Whatever frontmatter a collection's files carry is set by its rules file. Coffer reads only two keys, and only to show a file: `title`, the file's name in listings (else its first `#` heading, else its file name), and `aliases`, other names a `[[link]]` may use for the file, the key Obsidian reads too.

A file Coffer writes into the uploads folder carries the keys Coffer writes when it keeps one — `title`, `description`, `actor`, `created_at`, `updated_at`, and, for a file converted from an upload, `original` (the file's name) and `original_sha256` (its fingerprint), and, for an imported Confluence page, `origin` (where it came from) and `import_report` (what the import kept and left out). Leave those as they are. Frontmatter an uploaded Markdown file already had is kept in the one block, never a second block in the body. Any other key you or an agent add to a file is kept, with its value, whenever Coffer rewrites the file.

### Link files by slug or relative path {#link-pages-by-slug}

A file links to another by its slug, `[[session-ownership]]`, or `[[session-ownership|the session service]]` to choose the text shown. A link may also name one of a file's `aliases`. When two files share a slug, the one in the linking file's own folder wins.

An ordinary Markdown link by relative path works too: `[the cache](cache-ttl.md)`, `[the design](../sources/gateway-design.md)`. It is read relative to the file that holds it, as any Markdown reader reads it, and on the Knowledge page it opens the file it names, in another collection too.

Coffer resolves every link each time a file is read, ignoring case for slugs. A link that names nothing is **dead**, one that names more than one file is **ambiguous**, and a relative link that climbs out of the knowledge root is **outside**; all three are [broken links](#check-a-collection), and the Knowledge page marks a dead or outside link in the file. Links in the uploads folder are not checked, because imported material keeps its exporter's text as it was. A web link opens in your browser.

## Create a collection

Collections are created only on purpose, and only by a person. Reading, writing, an agent's working directory or a Markdown file an agent drops into some other folder never creates one.

<Shot name="knowledge-page" alt="The Knowledge page, with a collection and its documents." />

```text
Knowledge → Add → New collection… → Name, What belongs in here, Start from → Create collection
```

**New collection…** is also the button at the top of the tree. The **Add** menu says what each entry keeps: a new collection is kept in Coffer, synced to your other Macs, with its history, and tidied by your agent. This creates `~/.coffer/vault/knowledge/payments/` with a `README.md` that holds the name as its heading and what you typed as its description. **Start from** picks what else it starts with:

- **LLM wiki** (the default) adds `AGENTS.md` and `index.md`, and the README declares them as its `rules` and `entry`. The rules are those of a wiki your agent compiles from kept sources, after Andrej Karpathy's "LLM Wiki": uploads kept as sources under `sources/`, pages under `pages/` that each own one subject, cite the sources they draw on and carry the day they were last checked, an `index.md` listing every page, and a tidy that folds waiting sources into pages, rechecks pages older than 90 days and merges, splits and corrects pages.
- **Blank** writes the README only. Add a rules file when you want one, or let agents write the way the collection's files are already written.

The files are copied in once and are the collection's own from then on: change the rules, the interval, the page types or the layout in them, and agents follow the change. Coffer never reads the template again, so an update to Coffer does not change a collection's rules. On the command line, `coffer knowledge create --set name=payments --set template=blank` picks the template (see [`coffer knowledge create`](/reference/cli/knowledge#knowledge-create)).

A collection has no title: every page and listing shows it by its folder name. Its description is the opening paragraph of the README, before the first `##` section: change it on the collection's page (click the text; it saves when you leave the field) or in the file itself. Either way only that paragraph changes, and everything under it stays.

To rename a collection, choose **⋯ → Rename…** on its page and enter the new name. Its folder moves with it (`~/.coffer/vault/knowledge/<new-name>/`), the page stays on the same collection, and agents find it under the new name from the next catalogue. A name another collection already has, or that is not a valid folder name, is refused under the field and nothing changes.

The **Knowledge** page's tree lists every collection.

## Add knowledge

Knowledge grows as files in a collection. There are five ways in.

### From an agent: write into the collection {#from-an-agent-write-into-the-pages}

Agents file knowledge with their own file tools. An agent connected to Coffer reads the `coffer-guide` skill (see [Connect a client](/guides/connect-a-client)), which names the knowledge root and every collection with its rules file and start page, and tells it to read a collection's rules file before it writes anything there and to follow it. A collection with no rules file is written the way its existing files are written.

The guide also tells an agent to **write back what it works out**. When it answers your question by reading the code, a system or a document, and the collection does not already say it, it writes the answer where the collection's rules say before it finishes, and tells you in one line what it added. It does not write back a guess, an opinion, or something true only of that conversation. Every such write is in the collection's history, so you can undo it.

You can also ask directly: "write down what we just found out about the session TTL in the payments collection." The collection must already exist; only you create one. Whatever the agent writes is readable at once, and the next sweep commits it to the [history](#history-and-restore). It stays where the agent wrote it: Coffer moves no file.

### Upload a document {#upload-a-source}

Upload converts a file to Markdown and keeps it in the collection's uploads folder straight away, with the pictures it holds. The file you uploaded stays on this Mac only (see [Pictures and the original file](#pictures-and-the-original-file)).

```text
Knowledge → Add → Upload documents… → choose or drop files, pick the collection → Upload
```

The **Add** menu says what an upload keeps: each file is converted to Markdown and kept in the collection you pick, and synced with it. The upload dialog adds that pictures are kept with it and the file itself stays on this Mac.

| Accepted | Formats |
| --- | --- |
| Converted | `pdf`, `docx`, `pptx`, `xlsx`, `xls`, `html`, `htm`, `epub` |
| Tables | `csv`, `tsv` |
| A Confluence page | `json`, a page export (see [Import a Confluence page](#import-a-confluence-page)) |
| Taken as text | `md`, `markdown`, `mdx`, `txt`, `text`, `rst`, `json`, `yaml`, `yml`, `toml`, `ini`, `cfg`, `log`, `sql`, and common source files (`py`, `js`, `ts`, `go`, `rs`, `java`, `sh`, …) |

An uploaded PDF, for example, becomes `sources/gateway-design.md` (in the uploads folder the README names, when it names one), the extracted Markdown with frontmatter. When it has pictures, it becomes a folder instead: `sources/gateway-design/gateway-design.md` with `image-1.png` and the rest beside it, so the upload moves or is deleted as a whole. A file taken as text — Markdown, plain text, source code — is kept the same way. A name another file or folder there already has gets a suffix (`-2`).

You can pick or drop several files at once. Each is listed with its own state — waiting, converting, done, or failed with its reason — and they are sent one after another, so one failure does not stop the rest. A ZIP archive, or a file over 20 MB, is marked refused with its reason before anything is sent. A file that failed stays in the dialog so you can retry it, and one notice at the end says how many were kept and how many failed. The upload takes the collection, not a folder. An unsupported type is refused with the type named, and a conversion that produces no text — an image-only PDF, for example — is refused too. A refused file leaves nothing behind.

The kept file's `title` comes from the file (its frontmatter's `title`, a `# ` heading on its first line, or else the file name). Its `description` is its frontmatter's `description` or `summary`, else the opening prose, or its title when there is none. Any other frontmatter the file had is kept in its one frontmatter block. What happens to it next is the collection's rules: in an LLM wiki collection it is a source waiting to be folded into pages, which your agent does when you press **Tidy** (see [Tidy a collection](#tidy-a-collection)) or whenever you ask it to.

### Import a Confluence page {#import-a-confluence-page}

A Confluence page comes in as a page export: the JSON your Confluence tool writes for a page, with its storage format, title, id, version and URL, and its attachments when it downloaded them. Upload the `.json` file like any other, or from a terminal:

```sh
coffer knowledge upload payments account-core.json --attachments account-core-files/
```

`--attachments` adds the files in a folder downloaded beside the export, by their Confluence file names. Coffer turns the page into a Markdown file you can read, in the uploads folder:

- **The body reads as the page.** Each macro becomes what a reader of the page sees: a macro that only arranges its content (numbered headings, sections, columns, expand, tabs) gives that content back, an info, note, tip or warning panel becomes a labelled quote, a code block keeps its language, and a table with merged cells stays a table. What Confluence generates from elsewhere, such as a table of contents or a child-page list, is left out and said so. Nothing of Confluence's own markup shows when you read it.
- **Attachments are kept.** Pictures and files the page uses land beside the file, in the page's own folder in the uploads folder, and the file links them by name. A diagram shows as the page had it: an attached draw.io diagram as its picture, a draw.io link as that link, and a draw.io diagram drawn in the page as a **draw.io diagram** link that opens it in draw.io's viewer. The diagram travels in the part of the link after `#`, which your browser never sends to a server. A PlantUML diagram shows its source as a code block. Coffer downloads nothing, renders no diagram and sends nothing to an outside service.
- **The export itself is the converted file's original.** Like any upload's, it stays on the Mac you imported it on, outside the vault, and the line under its title reads **Original** and its name (see [Pictures and the original file](#pictures-and-the-original-file)).
- **Where it came from** goes in the file's one frontmatter block as `origin`: the Confluence URL, page id, space, version and when it was fetched. Under its title the Knowledge page shows **From confluence** and a link to the page.
- **What was left out is said.** `import_report` records whether the body converted fully, and, separately for attachments and macros, what was kept, missing or unsupported, with the reason. When anything is missing, the upload dialog stays open and lists it, and the file's line shows **Partial import**.

A page already in the collection, matched by its page id, is refused, and the dialog offers **Replace**. Run `coffer knowledge upload … --preview` first to see the title, the files and the report without writing anything. **Replace** (`--replace`) keeps the new version as a new file in a folder of its own (`-2`), and marks the older one `superseded_by` it, so your agent can tell which is current. Nothing is overwritten, and the change log's **Undo** brings the older state back.

A page imported before Coffer could read Confluence pages may still hold the export's markup in its file. The Knowledge page reads it converted, with a note that it does, and leaves the file as it is; import the page again with **Replace** to give it the layout above.

Not kept: an attachment of another page, an embed from another service (Google Drive, a Jira chart), and an attachment the export did not download. Each is listed as missing.

### Pictures and the original file {#pictures-and-the-original-file}

**Pictures.** Diagrams, charts and screenshots in a PDF, a slide deck, a Word document or a web page are kept with the converted file. They land beside the converted file, in a folder named after the upload, and the file links each one by name where it appeared; a PDF's pictures are listed after its text under **Images**, by the page they came from. On the Knowledge page they show inline as you read it, and a picture you open from the tree shows the picture. Agents open them like any other file. Not every picture is kept:

- small decorations — bullets, rules, icons, anything under 48 pixels on a side — are dropped;
- a picture repeated through the document, such as a logo on every slide, is kept once;
- a picture over 5 MB is dropped, and an upload keeps at most 40;
- a picture in a format a browser cannot show is saved as PNG.

The pictures sync to your other Macs with the collection and have history like any file in it. A scanned PDF whose pages are only pictures, with no text, is still refused.

**The original file.** The file you uploaded is kept on the Mac you uploaded it from, outside the vault, and never synced: originals such as decks and PDFs are large, and the Markdown and pictures are what agents read. The converted file names it, so when you open it on that Mac the line under its title reads **Original** and the file's name; click the name to open the file in its default app, to see the layout as it was. On your other Macs the line says **Original `<name>` is on the Mac it was uploaded from**. A Markdown or text upload is kept as it is, so there is no original to keep, unless converting it rewrote it (a Confluence export's storage markers made readable); then the file you uploaded is kept like any other.

### From a chat: ask your agent {#from-a-chat-ask-your-agent}

If you have a [channel](/guides/channels) paired, there is no knowledge command. Send the document or the conversation to the agent in the chat, in a direct chat or a group, and ask it to put that into knowledge, for example "save this into payments". The agent writes it into the collection with its own file tools, by the collection's rules.

### Edit a file yourself

Writing, editing or deleting a file in a collection with any editor is a complete way to change knowledge. There is no import step. The change is live on the next read, and the next sweep commits it to the history as an edit on disk. Write it the way the collection's rules file says; the [check](#check-a-collection) tells you about a link that leads nowhere.

On the Knowledge page, choose a file and use **Open in editor**, or the **⋯** menu's **Reveal in Finder**, to jump to the file. The Knowledge page itself never edits a file: it shows it read-only, and the next read shows whatever your editor or an agent saved. There is no unsaved state, no stale-save refusal and no leave-without-saving question, because nothing on the page holds your text. Open in editor uses the editor chosen in **Settings › General**.

To add a file, save it where the collection's rules say (**Reveal in Finder** on the collection). To add a document to convert, use **Add → Upload documents…**.

Agents do the same thing with their own file tools, by the collection's rules file, which the `coffer-guide` skill points them to (see [From an agent](#from-an-agent-write-into-the-pages)).

## Tidy a collection {#tidy-a-collection}

Over time a collection collects work to do: whatever its rules say should be kept up, and links that no longer lead anywhere. Coffer does not fix these itself. It hands the job to your agent, which reads the files with its own file tools and edits them by the collection's rules.

### Press Tidy

```text
Knowledge → choose the collection → Tidy
Knowledge → Tidy all   (every collection, one after another)
```

**Tidy** starts your default hand-off agent in your preferred terminal, with a prompt that names the collection, its folder, its rules file, its number of Markdown files and every broken link Coffer found (see [Check a collection](#check-a-collection)) as its first message. You watch the agent work in the terminal. **Tidy all**, in the Knowledge page's header, sends one prompt the same way that names every collection with its counts, including how many broken links it has, and asks the agent to go through them one at a time, reading each collection's broken links with `coffer knowledge check <collection>`. With no managed agent available, the button offers **Copy prompt** instead: paste it into whichever agent you use.

The prompt points the agent at the **Tidying a collection** section of the `coffer-guide` skill. Following it, the agent works through one collection at a time:

1. **Opens the tidy** with `coffer knowledge tidy-start <collection>` before it changes anything (see [A tidy is one change](#a-tidy-is-one-change)).
2. **Reads the collection's rules file and tidies by it.** What the rules say a tidy checks and fixes is the tidy. A collection started from the LLM wiki template, for instance, has the agent fold waiting sources into pages, recheck pages older than the interval, complete pages missing their frontmatter, merge and split pages and keep `index.md` current.
3. **Fixes every broken link** Coffer reported.
4. **Leaves alone what it is not sure about** — two files that disagree with nothing to tell which is right, a deletion of much text, a change to the rules file — and lists it in its report for you to decide.
5. **Finishes the tidy** with `coffer knowledge tidy-finish <collection> --set summary="<report>"`. The report says what it changed and what it left for you, and ends with **Gaps**: questions the collection cannot answer and sources worth finding — a spec, a runbook, a person to ask.

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

**Undo this tidy…** puts every file the tidy touched back as it was just before it: a file it changed gets its earlier text, a file it deleted comes back, and a file it created is removed. Coffer asks first, naming the tidy and how many files go back. The undo is one new change written by you, so the tidy stays in the history after it, and it is recorded in [Activity](/guides/activity).

If one of those files was edited after the tidy — by you, by another agent or by sync — the dialog lists it and undoes nothing until you choose **Undo anyway**, which discards those later edits too. They stay in the history, so a file's **History** can still bring them back.

On the command line, `coffer knowledge undo <version>` does the same, refused with `KNOWLEDGE_UNDO_CONFLICT` and the files' names when one was edited since; add `--set force=true` to undo anyway. The version is the change's, from `coffer knowledge changes`.

To put back only one file, open it, press **History**, choose the version before the tidy and press **Restore this version…** (see [History and restore](#history-and-restore)).

### Ask for a review only {#ask-for-a-review-only}

To hear what the agent would change before it changes anything, say so in the session Tidy opened: "don't change anything yet — tell me what you would do." The `coffer-guide` skill tells an agent asked only for a check or a review to report and change nothing. You can then tell it what to go ahead with.

### Nothing tidies on its own

Tidy runs only when you press it or ask your agent. Tidying never starts an agent run on its own, so nothing spends your quota or opens a conversation you did not start.

::: info What leaves your machine
Coffer sends nothing about your knowledge to any model. When you press Tidy, the files the agent reads go to that agent's own provider, as in any conversation with it.
:::

## Check a collection {#check-a-collection}

Coffer checks one thing, every time a collection is read, and fixes none of it: that every link leads somewhere. It checks nothing else, because nothing else depends on no format: whether a page is complete, current or well-sourced is for the collection's rules to say and your agent to judge. Fixing broken links is part of [Tidy](#tidy-a-collection), whose prompt carries the same list.

### Broken links {#what-coffer-finds-on-its-own}

The **Broken links** section of a collection's page lists them, grouped by kind. Each names the file by its title (hover to see its path), shows the link as written, and opens the file when you click it. With nothing to report, the section says so in one line.

| Kind | What it means |
| --- | --- |
| **Dead links** | A `[[link]]` that names no file or alias, or a relative link to a file that does not exist. |
| **Ambiguous links** | A `[[link]]` that names more than one file, none of them in the linking file's own folder. |
| **Links outside the knowledge folder** | A relative link that climbs out of the knowledge root. Point it at a file in a collection, or make it a web link. |

Every Markdown file in the collection is checked, the README and the rules file included, except the files in its uploads folder: imported material keeps its exporter's text as it was, and a `[[` in a Confluence macro is not a link. The broken links are worked out from the files on every read and stored nowhere, so they are current the moment a file changes. On the command line, `coffer knowledge check <collection>` prints the same list (see [`coffer knowledge`](/reference/cli/knowledge#knowledge-check)).

## What runs on its own {#what-runs-on-its-own}

A background **sweep** keeps the collections current. It runs when a file in a collection changes, and otherwise every 10 minutes, and calls no model. Each round it:

- commits to the history whatever changed in the tree since the last commit — your editor's saves and your agent's file edits — as an edit on disk, and
- re-renders the `coffer-guide` skill's catalogue, so a file you or an agent added by hand is counted.

It runs on every machine, takes no part in [vault sync](/guides/vault-sync)'s rounds and never waits for one, moves no file of yours and rewrites the text of none. It is skipped while the Knowledge feature is switched off (see [Experimental features](/guides/experimental-features)).

### Collections made before collections set their own format {#collections-from-before-pages-and-sources}

A collection made by an earlier Coffer keeps working as it is: no file is moved or rewritten, and the keys its files carry (`type`, `sources`, `verified` and the rest) stay as written, now the collection's own. Until its README names a `rules` file it is read by the first of `AGENTS.md`, `CLAUDE.md` and `README.md` at its root, so the README's **Page types** and **Rules** sections are its rules. To keep it as the wiki it was, ask your agent to copy the LLM wiki rules into an `AGENTS.md`, or add `rules:` and `entry:` to the README naming files the collection already keeps, such as its own `schema.md` and `index.md`. An earlier Coffer filed loose documents into `pages/` itself; those moves are in the **Change log**, written by **Coffer**, and can be restored from the history.

## How agents find knowledge

Coffer has **no tool for reading, listing or searching knowledge**. An agent reads the files by path with the tools it already has: `Read`, `Grep`, its shell.

What tells it where to look is Coffer's built-in [`coffer-guide` skill](/guides/skills#the-built-in-coffer-guide-skill), which Coffer links into every agent's skill folder:

- Its **description**, which is in every session, names the subjects of your collections, taken from each `README.md`, and says the skill teaches writing in and tidying knowledge.
- Its **body**, loaded when the agent opens the skill, gives the knowledge root's path and a catalogue of every collection: its description, its rules file and, when it names one, its start page with how many Markdown files it holds. A collection with no start page gets that count for each of its top-level folders. The catalogue names no file: the agent finds one from the start page or by searching the folder. The body also says what Coffer does with every collection, whatever its format, and the steps of a tidy.

The guide teaches no format: for that it sends the agent to each collection's rules file, which wins. When the start page does not lead an agent to what it is after, the guide tells it to grep the collection for the exact string.

Coffer rewrites the skill whenever the catalogue changes, so a new file appears in it within one sweep.

::: details Why no search tool
Agents reliably use the file tools they already have, and rarely remember to call a special-purpose retrieval tool. Handing them a catalogue and a path turns retrieval into something they already do well, and a literal `grep` over a few hundred files matches identifiers and names that fuzzy search would blur. See [Knowledge architecture](/architecture/knowledge) for the full reasoning.
:::

Write a good `README.md` for each collection: its first paragraph is what a model matches on when deciding whether your knowledge is relevant. Write a good rules file too: it is what agents follow.

## Browse and read

On the Knowledge page, choose the collection in the tree, then a file. They are also plain files: the knowledge root is `~/.coffer/vault/knowledge/` and each collection is a folder in it, so you can read and grep them with your own tools. A collection's **⋯** menu has **Copy path**.

The Knowledge page is one tree beside a reading pane, both filling the window under the page header. The title carries the **Experimental** tag; the header's actions are **Tidy all** and **Add**, the page's one primary button. **Add** opens a menu, each item with a line saying what it keeps in Coffer: **Upload documents…** (see [Upload a document](#upload-a-source)), **New collection…** (see [Create a collection](#create-a-collection)) and **Link an external folder…** (see [Link an external folder](#link-an-external-folder)). At the top of the tree, **Collections** has a **New collection** button; below it every collection by its folder name. Opening a collection shows its folders and files by their own names, folders first, each Markdown file with a document icon. The tree remembers what you opened and closed: leave the page or reload it and the same collections and folders are open when you come back. Switch to another page and return to **Knowledge** from the sidebar, and you land on the collection and document you had open.

**A collection.** Choosing a collection shows **Tidy** and a **⋯** menu in its pane bar. Below them come its folder name, what belongs in it (click it to edit; it saves when you leave the field or press **⌘Enter**, **Esc** cancels, and a toast offers **Undo**), and one summary line: how many Markdown files it holds, the folder's path with a copy button, and when it was last updated. A line under it names its **Rules** file and its **Start** page, each opening that file. A muted line says the collection is kept in Coffer: synced to your other Macs, its history kept, tidied by your agent. While an agent is tidying the collection, a notice says so (see [A tidy is one change](#a-tidy-is-one-change)). Then come two sections:

- **Broken links** lists the links Coffer found broken, by kind, each file by its title and opening when you click it (see [Check a collection](#check-a-collection)).
- **Change log** lists every change to the collection, newest first: what it did, who wrote it and when, and the files it touched by title, each opening at its history. A tidy is one entry with the agent's report and **Undo this tidy…** (see [Undo a tidy](#undo-a-tidy)); edits made on disk within 10 minutes of each other are one entry listing their files. **Show more** loads older changes.

The collection's **⋯** menu holds **Reveal in Finder**, **Open in Obsidian** when Obsidian is installed on this Mac (see [Open a collection in Obsidian](#open-a-collection-in-obsidian)), **Copy path**, **Rename…** and **Delete collection…**; a collection with nothing in it yet says so and reminds you that you can upload a document or drop Markdown files into its folder.

**A file.** Choosing a file shows it read-only. Its pane bar names where the file is, then carries **History** (see [History and restore](#history-and-restore)), a **Preview / Source** switch for Markdown, **Open in editor** as a button (see [Edit a file yourself](#edit-a-file-yourself)), and a **⋯** menu with **Reveal in Finder**, **Open in Obsidian** when it is installed, and **Delete**. Under the title one line says who created it and when, read from its frontmatter when it says, and, for an upload, **Original** with the file's name, which opens the file on the Mac it was uploaded from (see [Pictures and the original file](#pictures-and-the-original-file)). An imported Confluence page shows **From confluence** with a link to the page, and **Partial import** when something was left out.

In the text, every `[[link]]` and every relative link opens the file it names, in its own collection; a dead one is marked in red, with a tooltip saying nothing has that name, and one outside the knowledge is marked too. In a file in the uploads folder a `[[` is shown as written. A web link opens in your default browser in the app, and in a new tab in a browser. HTML in a file, such as a table an import kept, is shown as HTML, with scripts and comments removed. A ```` ```mermaid ```` block is drawn as its diagram, or shows its source when it cannot be drawn (see [Web UI](web-ui.md)). Inline code is set lighter than a code block, and a long path wraps at its `/`.

A picture a file links by relative path shows inline in Preview. Choosing a picture file in the tree, such as an upload's `image-1.png`, shows the picture.

The page has no search box and no per-collection switch: ⌘K jumps to a collection by name, and every collection reaches every agent. There is no form for typing a file into the Knowledge page: you write in your own editor, and agents by writing files.

## Open a collection in Obsidian {#open-a-collection-in-obsidian}

A collection is plain Markdown that [Obsidian](https://obsidian.md) reads as it is: open its folder, or the whole knowledge root, as an Obsidian vault and you can browse, search and edit the files there. `[[slug]]` links resolve by file name, as Obsidian resolves them, and `aliases` in frontmatter is the key Obsidian already reads. Coffer ignores hidden folders such as `.obsidian/`, where Obsidian keeps its settings: they are not committed, not catalogued and not synced.

When Obsidian is installed on this Mac, a collection's **⋯** menu and a file's **⋯** menu offer **Open in Obsidian**. The first time:

1. In Obsidian, choose **Open folder as vault** and pick the collection's folder, `~/.coffer/vault/knowledge/<collection>/`. `~/.coffer` is hidden: press **⌘⇧.** in the dialog to show it, or use **Copy path** on the collection and paste it with **⌘⇧G**.
2. In Obsidian's **Settings › Files and links**, set **Default location for new notes** to wherever the collection's rules put new files (`pages/` in an LLM wiki collection). Coffer moves no file; a note created anywhere else stays there. Set **New link format** to **Relative path to file** if you prefer path links: Coffer follows and checks them as well as `[[slug]]`.

An edit you save in Obsidian is like an edit in any editor: live at once, recorded as an edit on disk by the next sweep. Leave the files Coffer wrote into the uploads folder as the collection's rules say.

## Link an external folder {#link-an-external-folder}

If you already keep notes with your own tools, such as an Obsidian vault, a Logseq graph or a folder of Markdown in a repository, you can share that folder with your agents without moving it. Coffer calls it a linked folder.

```text
Knowledge → Add → Link an external folder… → Folder, Name → Link folder
```

**Folder** is the folder's absolute path, `/Users/you/Obsidian/Work` say. **Name** is how Coffer and your agents refer to it: it follows the folder's own name until you type one, and the folder on disk keeps its own name either way. On the command line the same thing is `coffer knowledge link --set folder=/Users/you/Obsidian/Work` (see [`coffer knowledge link`](/reference/cli/knowledge#knowledge-link)).

### What Coffer does with it {#what-coffer-does-with-a-linked-folder}

- **Shares it with every agent.** The folder gets its own section in the `coffer-guide` skill every agent reads: its path, its rules file, its start page when it names one, and otherwise every Markdown note by title. Agents read the notes where they are, with their own file tools.
- **Shows it on the Knowledge page.** The tree lists it with a linked-folder icon, and you can open and read any of its notes. Its page shows its name with an **External** tag and four facts: **Location** (its path, with **Reveal in Finder**), **Notes** (how many Markdown notes it holds), **Rules file**, **Start page** when its README names one, and **Managed by**: its own tools, with Coffer only sharing it with agents.
- **Reads it fresh each time.** Nothing is cached, so a note you save in Obsidian is what the page and your agents see next.

### What Coffer does not do {#what-coffer-does-not-do-with-a-linked-folder}

- **It copies nothing.** No file goes into `~/.coffer`. The folder stays the only copy.
- **It writes nothing into the folder.** You cannot upload into it, its notes have no **Delete**, its description (the first paragraph of its own `README.md`) is not edited here, and it has no **Tidy** and no **Broken links**.
- **It keeps no history.** Its notes have no **History**, its page has no **Change log**, and nothing can be undone through Coffer. Use the folder's own tools for that: Obsidian's file recovery, or git if the folder is a repository.
- **It does not sync it.** Neither the folder's files nor the link reach your other Macs through [vault sync](/guides/vault-sync). The link is recorded only on this Mac, in `~/.coffer/local/resources/knowledge/`, because the folder's path is true of this Mac only. To use the same notes on another Mac, keep the folder in step with its own tool (Obsidian Sync, iCloud Drive, git) and link it on that Mac as well.

### How agents write in it {#how-agents-write-in-a-linked-folder}

A linked folder is read the same way as a collection Coffer keeps (see [What a README declares](#what-a-readme-declares)): its **rules file** is the file its `README.md` names in `rules`, else the first of `AGENTS.md`, `CLAUDE.md` and `README.md` found at its root, and `entry` names its start page. Both must be inside the folder. The guide tells agents to follow the rules file before writing anything in the folder, and, when there is none, to write only the way its existing notes are written. So if you want agents to add notes to your vault, write your conventions in an `AGENTS.md` at its root; if you want them only to read it, say that there.

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

Every change to a collection is kept as a version: your uploads and deletes, what vault sync brought in, and a tidy, recorded as one change by the agent carrying its report, and edits made outside Coffer in your own editor or with an agent's file tools. Each change names its **writer** — `user`, `agent`, `sync` or `disk` (and, on versions an earlier Coffer wrote, `daemon` for its filing of loose documents into `pages/`, and `curation`) — so you can always tell who changed what. A collection's page lists its changes in its **Change log**.

The history is the vault repository's own: collections live under `knowledge/` in `~/.coffer/vault`, so `git -C ~/.coffer/vault log -- knowledge/<collection>/<path>` reads the same versions, and [vault sync](/guides/vault-sync) carries them to your other machines. Coffer needs `git` for the vault; without it the app shows [Coffer needs git](/guides/troubleshooting#coffer-needs-git) until it is installed. If git goes missing while the daemon runs, every write keeps working and the changes feed that a collection's Change log and a delete's **Undo** read is refused. The refusal carries a prompt for your agent to install git the way that fits your machine and confirm it with `git --version`.

### Bring back an earlier version

Press **History** in a file's pane bar. The history takes over the whole Knowledge area, with the tree and the file out of the way so the versions and the diff have room, and the page's address gains `?history=1`, so a link to it opens the history too. It holds one card split by a divider you can drag; its ✕ or **Esc** takes you back to the file.

- **Left: the versions, newest first,** under **Versions** with their count. Each row says what the version did (*Created*, *Edited* or *Deleted*, or *Restored the version of &lt;date&gt;*), who wrote it, when, and how many lines it moved (+N −M). The writer reads **You** (you, through Coffer), **Edited on disk** (your own editor, a shell, or an agent's own file tools), an agent by product name (when it wrote through a Coffer tool), **Coffer** or **Sync**. The newest is marked **Current** and is chosen when the history opens.
- **Right: the chosen version,** with its short id, writer and time, and the diff of every file it changed. For a version other than the current one, a switch picks what the diff shows: **Changes in this version** (against the version before it) or **Compare with current** (from that version to the file as it is now).

To go back, choose a version and press **Restore this version…**. Coffer asks first: the file goes back to that version **as a new version**, so nothing in the history is lost. The restore is written by you, shows in the history as *Restored the version of &lt;date&gt;*, and is recorded in [Activity](/guides/activity). If the file changed since you opened the history (a later version, or a save in your editor), the restore is refused with `VAULT_FILE_STALE` and the dialog says so; reopen the history and try again. Opening the history also records an edit you made on disk as a version of its own, so the newest version is always the file as it is.

You can read the same versions with git: `git -C ~/.coffer/vault log -p -- knowledge/<collection>/<path>`.

A deleted file has no pane to open its history from once the delete's toast is gone, but its versions are still in the vault's git history, so git can bring it back (see [Delete files and collections](#delete-files-and-collections)).

## Delete files and collections {#delete-files-and-collections}

Only a person deletes through Coffer. Coffer gives agents no tool that deletes knowledge, and you can delete any file, whoever wrote it. The change is also an ordinary file delete, so removing a file in your own editor works too and shows up in the history as an edit made on disk.

- **A file:** Knowledge → choose the file → **⋯** → **Delete**. It happens at once. Links to it from other files become dead links in the [check](#check-a-collection). An upload's pictures stay in its folder, and its original stays on the Mac it was uploaded from; delete them yourself if you no longer want them.
- **A whole collection, and every file in it:** Knowledge → choose the collection → **⋯** → **Delete collection…**. Coffer asks first, naming the collection and how many files go with it.

::: tip A delete can be undone
A delete is reported in a toast, *Deleted `<name>`*, with **Undo**, which puts back exactly what it removed — a file into its collection, a collection with all its files — as one new change by you. Undo is refused, with nothing written, when a file is back at the same path or a collection of the same name exists again. Once the toast is gone, the deleted file has no pane to open its history from, but its versions are still in the vault's history, so git can bring it back (`git -C ~/.coffer/vault log -- knowledge/<path>`); a deleted collection's files can be, but its registration cannot, which is why **Delete collection…** asks first.
:::

## What not to put in knowledge

- **Secrets.** No keys, tokens or passwords. Use [Secret store](/guides/secret-store).
- **What the code already says.** If an agent can read it in the repository, it does not belong here.
- **Scratch notes.** What goes in should still be true in a month.

## Troubleshooting

**A tidy rewrote a file badly.** Undo the whole tidy from its entry in the collection's **Change log** with **Undo this tidy…** (see [Undo a tidy](#undo-a-tidy)), or put back one file: open it, press **History**, choose a version from before the tidy and press **Restore this version…**.

**A tidy shows up as separate edits on disk.** The agent did not run `coffer knowledge tidy-start` first, or Coffer restarted while it worked. Its edits are all in the history, one per edit; restore a file from its **History**.

**The collection page says an agent is tidying, but nothing is happening.** The agent stopped without running `tidy-finish`. Ask it to finish, or wait: once the collection has sat unchanged for 30 minutes, Coffer closes the tidy and records it as *closed without a report*.

**A link shows in red.** It names no file or alias — usually a file that was renamed, moved or merged away. Fix the link, or add the old slug to the surviving file's `aliases`; **Tidy** fixes the broken links it finds.

**My documents moved into `pages/`.** An earlier Coffer filed loose Markdown into `pages/`; this one moves nothing. The move is in the **Change log** and can be restored from the history (see [Collections made before collections set their own format](#collections-from-before-pages-and-sources)).

**A Confluence page says Partial import.** Something on the page was not kept: the file's `import_report` names each item and why. An attachment the export did not download can be added with `--attachments` and the page imported again with `--replace`.

**A Confluence upload is refused as already imported.** The collection holds a file imported from the same page id. Press **Replace**, or run the upload with `--preview` and then `--replace`.

**Tidy offers only Copy prompt.** No managed agent is available. Add one under **Agents**, or paste the copied prompt into the agent you use; it must have the `coffer-guide` skill.

**Open in Obsidian is not in the menu.** Coffer offers it only when Obsidian is installed on this Mac, in `/Applications` or your own Applications folder.

**A file says its original is on another Mac.** The uploaded file is kept only on the Mac it was uploaded from. Open the converted file there, or upload the file again on this Mac.

**An upload's diagram is missing.** Pictures under 48 pixels on a side, over 5 MB, or past the 40th in one upload are not kept, and text drawn into a picture is kept as the picture, not as text. Check the original file on the Mac you uploaded it from.

**An agent does not use the knowledge.** Check that the `coffer-guide` skill is enabled and reaches that agent (its **Reach** button on the Skills page), and that the collection's `README.md` opens with a sentence naming its subjects.

**An agent ignores a collection's conventions.** Check that the collection's page names the rules file you expect under **Rules**. If not, add `rules: <file>` to the top of its `README.md`.

**A file an agent wrote never shows up.** A file written into a collection shows up on the next read, as long as it is inside an existing collection's folder and neither it nor a folder above it has a name starting with `.`.

## Related

- [Skills](/guides/skills) — the `coffer-guide` skill that carries the catalogue, points agents at each collection's rules file and gives the steps of a tidy
- [Memory](/guides/memory)
- [Vault sync](/guides/vault-sync) — what syncs, and why linked folders do not
- [Knowledge architecture](/architecture/knowledge)
- [`coffer knowledge` command reference](/reference/cli/knowledge)
- [MCP tools reference](/reference/mcp-tools)
- [Knowledge spec](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/knowledge/spec.md)
- [Knowledge Collections Own Their Format; Coffer Checks Only Links](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/knowledge-collections-own-their-format.md), [Knowledge Is Plain Files](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/knowledge-is-plain-files.md) [Tidying Knowledge Is the Agent's Job, One Hand-Off Recorded as One Change](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/tidying-knowledge-is-the-agents-job.md), [A Linked Knowledge Folder Is Shared in Place, Read-Only to Coffer, and Recorded Machine-Local](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/linked-knowledge-folders-are-read-only-and-machine-local.md) [Knowledge Sources Keep Their Images; Originals Stay on This Mac](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/knowledge-sources-keep-their-images-and-originals-stay-on-this-mac.md), [Knowledge Files Stay Where Their Writer Put Them](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/knowledge-files-stay-where-their-writer-put-them.md) and [Confluence Pages Import as Readable Sources](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/confluence-pages-import-as-readable-sources.md)
