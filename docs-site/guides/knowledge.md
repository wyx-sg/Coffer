---
title: Knowledge
description: Keep what you and your agents know about your working environment as folders of Markdown that every agent reads with its own file tools, and ask your agent to tidy them.
---

# Knowledge

Knowledge is a directory of Markdown documents about your working environment — services, repositories, conventions, decisions, pitfalls — that every agent on your machine reads. This page covers creating collections, adding and reading documents, how you and your agent change them, how your agent tidies them when you press **Tidy**, how to look back at a document's history and bring a version back, and how agents find what is there.

## What knowledge is for

Knowledge holds facts about the world you work in: which team owns a service, how an internal API authenticates, why a migration is ordered the way it is. It arrives because you, or an agent working with you, put it there.

- **One copy for every agent.** Claude Code and Codex read the same files, so what one agent records in the morning another reads in the afternoon.
- **Plain files.** Each document is a Markdown file you can open, edit, grep and back up. Coffer keeps no index, no embeddings and no database copy of the content.
- **Written together.** You edit documents in your own editor; the Knowledge page shows them read-only and opens them there. Agents write into the documents with their own file tools, following the rules in the `coffer-guide` skill: a fact goes into the document that already covers its subject. When documents drift into overlap, you press **Tidy** and your agent merges, splits and corrects them. Coffer itself runs no model over your knowledge.

Knowledge is not [memory](/guides/memory). Memory is what agents learn while working, read out of their own memory stores. Knowledge is what somebody deliberately wrote down.

## How a collection is laid out

A **collection** is a top-level folder under the knowledge root:

```text
~/.coffer/vault/knowledge/
└── payments/                     ← one collection
    ├── README.md               ← what this collection is about
    ├── session-ownership.md    ← a document
    ├── gateway/
    │   └── rate-limits.md      ← nesting is allowed and means nothing
    └── .inbox/                 ← hidden: a drop zone, adopted at the next sweep
```

- **Documents** are the Markdown files in the collection. A document's path is its identity; there is no separate id. File names are slugs of the title, with a suffix such as `-2` on a collision.
- **Folders** inside a collection are optional and carry no meaning. You or your agent can create, move and remove them.
- **`README.md`** at the collection root describes the collection. Its first paragraph is the collection's description everywhere Coffer shows one, and it is what the `coffer-guide` skill tells agents the collection is about. It is never listed as a document or counted.
- **Hidden entries** (names starting with `.`) are left out of every document count and the catalogue, and the Knowledge page lists none of them. The one Coffer reads is `.inbox/`: a Markdown file left there is turned into a document at the next sweep (see [A file in the inbox](#a-file-in-the-inbox)).

The knowledge root is inside the vault repository, at `~/.coffer/vault/knowledge`; the `coffer-guide` skill names it to every agent. It cannot be moved elsewhere: a tree outside the vault would be a tree its history cannot see.

### Frontmatter

Every document carries YAML frontmatter:

```markdown
---
title: Session ownership
description: Which service owns user sessions, and where the TTL is configured.
actor: user
created_at: 2026-09-20T08:14:03.512840+00:00
updated_at: 2026-09-22T10:02:41.090311+00:00
---

The `account-session` service owns ...
```

| Key | Meaning |
| --- | --- |
| `title` | The document's title. |
| `description` | One sentence on what the document covers. Agents see it in the catalogue. |
| `actor` | `user` or `agent` — who wrote the document. |
| `created_at`, `updated_at` | Timestamps. |

Any other key you add is kept, with its value, whenever Coffer rewrites the file. Coffer writes nothing else into a document.

::: tip Name the subject, not the file
A document must not refer to another knowledge file by its file name or path, because paths change as a collection is tidied. Write "see the gateway rate-limit notes", not "see `gateway/rate-limits.md`". The `coffer-guide` skill tells agents this rule.
:::

## Create a collection

Collections are created only on purpose, and only by a person. Reading, writing, an agent's working directory or a Markdown file an agent drops into some other folder never creates one.

```text
Knowledge → New collection → Name, What belongs in here → Create collection
```

This creates `~/.coffer/vault/knowledge/payments/` and a `README.md` holding the description. A collection has no title: every page and listing shows it by its folder name. Its description is the opening paragraph of the README: change it on the collection's page (click the text; it saves when you leave the field) or in the file itself. Either way only that paragraph changes, and anything written under it stays.

To rename a collection, choose **⋯ → Rename…** on its page and enter the new name. Its folder moves with it (`~/.coffer/vault/knowledge/<new-name>/`), the page stays on the same collection, and agents find it under the new name from the next catalogue. A name another collection already has, or that is not a valid folder name, is refused under the field and nothing changes.

The **Knowledge** page's tree lists every collection, each with its number of documents.

## Add knowledge

There are five ways in, and each one ends in a document you can read at once.

### From an agent: write into the documents

Agents file knowledge with their own file tools. An agent connected to Coffer reads the `coffer-guide` skill (see [Connect a client](/guides/connect-a-client)), which names the knowledge root and the collections and teaches six rules for writing something down:

1. Find the fact's home: fold it into the document that already answers its question, and create a new file only when none does.
2. Lose nothing: every fact already in a document survives the edit.
3. Organise by subject, never by who or when.
4. Where two statements disagree, the newer wins unless the older is shown to be right by a source, a date, a command's output or the code. The superseded one stays legible.
5. Never name another knowledge file; name the subject.
6. Give every document a `title`, a one-line `description` saying what question it answers, and `actor: agent`.

You can also ask directly: "write down what we just found out about the session TTL in the payments collection." The collection must already exist; only you create one. Whatever the agent writes is readable at once, and the next sweep commits it to the [history](#history-and-restore).

### A file in the inbox {#a-file-in-the-inbox}

A Markdown file can also arrive at a collection's hidden `.inbox/` folder: from an agent outside Coffer, from another machine, or from an older guide.

```text
~/.coffer/vault/knowledge/payments/.inbox/session-ttl.md
```

The file name does not matter, and frontmatter is optional. The next sweep turns the file into a document at the collection root, filling in whatever it lacks:

| Frontmatter | Filled from |
| --- | --- |
| `title` | The first `# ` heading, else the file name. |
| `description` | The first paragraph, else the title. |
| `actor` | `agent`, unless the file says otherwise. |
| `created_at`, `updated_at` | The time the sweep saw the file. |

Anything the writer did set is kept, other keys included, and each file is recorded in the audit log. Only a collection's own `.inbox/` counts. A Markdown file written into a top-level folder that is not a collection is left alone and never catalogued, because only a person creates a collection. A file in an inbox that is not Markdown stays where it is.

### Upload a document

Upload converts a file to Markdown and adds it to the collection as a document straight away. Neither the original file nor the extracted text is kept as a file of its own.

```text
Knowledge → Upload → choose a file and the collection → Upload
```

| Accepted | Formats |
| --- | --- |
| Converted | `pdf`, `docx`, `pptx`, `xlsx`, `xls`, `html`, `htm`, `epub` |
| Tables | `csv`, `tsv` |
| Taken as text | `md`, `markdown`, `mdx`, `txt`, `text`, `rst`, `json`, `yaml`, `yml`, `toml`, `ini`, `cfg`, `log`, `sql`, and common source files (`py`, `js`, `ts`, `go`, `rs`, `java`, `sh`, …) |

One file per upload, at most 20 MB. An unsupported type is refused with the type named, and a conversion that produces no text — an image-only PDF, for example — is refused too. A refused upload leaves nothing behind.

The document's `title` comes from the file (a `# ` heading on its first line, or else the file name). Its `description` is taken from the document's opening prose, or its title when there is none. An upload adds the document as it stands; folding it into an existing document is tidying (see [Tidy a collection](#tidy-a-collection)).

### From a chat: ask your agent {#from-a-chat-ask-your-agent}

If you have a [channel](/guides/channels) paired, there is no knowledge command. Send the document or the conversation to the agent in the chat, in a direct chat or a group, and ask it to put that into knowledge, for example "save this into payments". The agent writes it with its own file tools, the same way it writes any other knowledge file.

### Edit a file yourself

Writing, editing or deleting a Markdown file in the collection folder with any editor is a complete way to change knowledge. There is no import step. The change is live on the next read, and the next sweep commits it to the history as an edit on disk.

On the Knowledge page, choose a document and use **Open in editor**, or the **⋯** menu's **Reveal in Finder**, to jump to the file. The page itself never edits a document: it shows the document read-only, and the next read shows whatever your editor or an agent saved. There is no unsaved state, no stale-save refusal and no leave-without-saving question, because nothing on the page holds your text. Open in editor uses the editor chosen in **Settings › General**.

To add a document, drop a Markdown file into the collection's folder (**Reveal in Finder** on the collection) or use **Upload**.

Agents do the same thing with their own file tools, by the writing rules the `coffer-guide` skill gives them (see [From an agent](#from-an-agent-write-into-the-documents)).

## Tidy a collection {#tidy-a-collection}

Over time a collection collects overlap: two documents that answer the same question, one that answers several, a statement a newer document contradicts. Coffer does not fix these itself. It hands the job to your agent, which reads the documents with its own file tools and edits them.

### Press Tidy

```text
Knowledge → choose the collection → Tidy
Knowledge → Tidy all   (every collection, one after another)
```

**Tidy** starts your default hand-off agent in your preferred terminal, with a prompt that names the collection and its folder as its first message. You watch the agent work in the terminal. **Tidy all**, in the Knowledge page's header, sends one prompt the same way that names every collection and asks the agent to go through them one at a time. With no managed agent available, the button offers **Copy prompt** instead: paste it into whichever agent you use.

The prompt points the agent at the **Tidying a collection** section of the `coffer-guide` skill. Following it, the agent works through one collection at a time:

1. Reads the collection's `README.md` and every document's title and description, then the documents in full.
2. **Merges** documents that answer the same question into one, keeping every fact, and deletes the ones it merged away.
3. **Splits** a document that answers several unrelated questions, one subject per file.
4. **Fixes** what is wrong or contradictory by the rule that the newer statement wins unless the older is shown to be right, and rewrites a description that does not say what question its document answers.
5. Reports what it merged, split, corrected and deleted.

It changes nothing that does not need changing. You can also ask any agent that has the `coffer-guide` skill to do this in your own words: "tidy up the payments knowledge."

### Nothing tidies on its own

Tidy runs only when you press it or ask your agent. Coffer starts no agent run of its own, so nothing spends your quota or opens a conversation you did not start.

### If a tidy goes wrong

Every edit the agent makes is a version in the [history](#history-and-restore), written as an edit on disk. Open the document's **History** tab, choose the version before the edit and press **Restore this version…** (see [History and restore](#history-and-restore)).

::: info What leaves your machine
Coffer sends nothing about your knowledge to any model. When you press Tidy, the documents the agent reads go to that agent's own provider, as in any conversation with it.
:::

## What runs on its own {#what-runs-on-its-own}

A background **sweep** keeps the collections current. It runs about once a minute and calls no model. Each round it:

- turns files dropped into a collection's `.inbox/` into documents (see [A file in the inbox](#a-file-in-the-inbox)),
- commits to the history whatever changed in the tree since the last commit — your editor's saves and your agent's file edits — as an edit on disk, and
- re-renders the `coffer-guide` skill's catalogue, so a document you or an agent added by hand is listed.

It runs on every machine, takes no part in [vault sync](/guides/vault-sync)'s rounds and never waits for one, and rewrites no existing document. It is skipped while the Knowledge feature is switched off (see [Experimental features](/guides/experimental-features)).

## How agents find knowledge

Coffer has **no tool for reading, listing or searching knowledge**. An agent reads the files by path with the tools it already has: `Read`, `Grep`, its shell.

What tells it where to look is Coffer's built-in [`coffer-guide` skill](/guides/skills#the-built-in-coffer-guide-skill), which Coffer links into every agent's skill folder:

- Its **description**, which is in every session, names the subjects of your collections, taken from each `README.md`.
- Its **body**, loaded when the agent opens the skill, gives the knowledge root's path and a catalogue of every document in every collection: its path, title and description. It also carries the writing rules and the tidying steps described above.

Coffer rewrites the skill whenever the catalogue changes, so a new document appears in it within one sweep.

::: details Why no search tool
Agents reliably use the file tools they already have, and rarely remember to call a special-purpose retrieval tool. Handing them a catalogue and a path turns retrieval into something they already do well, and a literal `grep` over a few hundred files matches identifiers and names that fuzzy search would blur. See [Knowledge architecture](/architecture/knowledge) for the full reasoning.
:::

Write a good `README.md` for each collection: its first paragraph is what a model matches on when deciding whether your knowledge is relevant.

## Browse and read

On the Knowledge page, choose the collection in the tree, then a document. The documents are also plain files: the knowledge root is `~/.coffer/vault/knowledge/` and each collection is a folder in it, so you can read and grep them with your own tools. A collection's **⋯** menu has **Copy path**.

The Knowledge page is one tree beside a reading pane, both filling the window under the page header. The title carries the **Experimental** tag; the header's actions are **Tidy all** and **Upload**, the page's one primary button. At the top of the tree, **Collections** has a **New collection** button; below it every collection by its folder name, each opening to its documents shown by their file names. Choosing a collection shows its folder name, what belongs in it (click it to edit; it saves when you leave the field or press **⌘Enter**, **Esc** cancels, and a toast offers **Undo**) and its properties: **Documents** and **Folder**, with **Tidy** beside them. The collection's **⋯** menu holds **Reveal in Finder**, **Copy path**, **Rename…** and **Delete collection**; a collection with nothing in it yet says so and reminds you that you can upload one or drop Markdown files into its folder. Choosing a document shows it read-only, with a **Preview / Source** switch for Markdown, **Open in editor** as a button (see [Edit a file yourself](#edit-a-file-yourself)) and a **Document** and a **History** tab in its pane bar (see [History and restore](#history-and-restore)), and a **⋯** menu with **Reveal in Finder** and **Delete document**. Under the title one line says who wrote it and when it was created, read from the document's front matter.

The page has no search box and no per-collection switch: ⌘K jumps to a collection by name, and every collection reaches every agent. There is no form for typing a document into the page: you write in your own editor, and agents by writing files.

## Every collection reaches every agent

A collection has no on/off switch and no per-agent reach: every collection is available to every agent, and a collection leaves agents' `coffer-guide` skill only by being deleted.

::: warning Not access control
The skill hands agents the knowledge root, and an agent can read anything under it with its own tools. Keep nothing in a collection that an agent on this machine should not read.
:::

## History and restore

Every change to a collection is kept as a version: your deletes, an upload or dropped file that became a document at once, what vault sync brought in, and edits made outside Coffer in your own editor or with an agent's file tools — which is how a tidy shows up. Each change names its **writer** — `user`, `agent`, `sync` or `disk` (and `curation` on versions an earlier Coffer wrote) — so you can always tell who changed what.

The history is the vault repository's own: collections live under `knowledge/` in `~/.coffer/vault`, so `git -C ~/.coffer/vault log -- knowledge/<collection>/<path>` reads the same versions, and [vault sync](/guides/vault-sync) carries them to your other machines. Coffer needs `git` for the vault; without it the app shows [Coffer needs git](/guides/troubleshooting#coffer-needs-git) until it is installed. If git goes missing while the daemon runs, every write keeps working and the changes feed a delete's **Undo** reads is refused. The refusal carries a prompt for your agent to install git the way that fits your machine and confirm it with `git --version`.

### Bring back an earlier version

A document has two tabs in its pane bar: **Document**, the one that opens, and **History**. **History** is one card split by a divider you can drag.

- **Left: the versions, newest first,** under **Versions** with their count. Each row says what the version did (*Created*, *Edited* or *Deleted*, or *Restored the version of &lt;date&gt;*), who wrote it, when, and how many lines it moved (+N −M). The writer reads **You** (you, through Coffer), **Edited on disk** (your own editor, a shell, or an agent's own file tools), an agent by product name (when it wrote through a Coffer tool), **Coffer** or **Sync**. The newest is marked **Current** and is chosen when the tab opens.
- **Right: the chosen version,** with its short id, writer and time, and the diff of every file it changed. For a version other than the current one, a switch picks what the diff shows: **Changes in this version** (against the version before it) or **Compare with current** (from that version to the file as it is now).

To go back, choose a version and press **Restore this version…**. Coffer asks first: the file goes back to that version **as a new version**, so nothing in the history is lost. The restore is written by you, shows in the history as *Restored the version of &lt;date&gt;*, and is recorded in [Activity](/guides/activity). If the file changed since you opened the tab (a later version, or a save in your editor), the restore is refused with `VAULT_FILE_STALE` and the dialog says so; reopen the tab and try again. Opening the tab also records an edit you made on disk as a version of its own, so the newest version is always the file as it is.

You can read the same versions with git: `git -C ~/.coffer/vault log -p -- knowledge/<collection>/<path>`.

A deleted document has no page to open a **History** tab from once the delete's toast is gone, but its versions are still in the vault's git history, so git can bring it back (see [Delete documents and collections](#delete-documents-and-collections)).

## Delete documents and collections

Only a person deletes through Coffer. Coffer gives agents no tool that deletes knowledge, and you can delete any document, whoever wrote it. The change is also an ordinary file delete, so removing a file in your own editor works too and shows up in the history as an edit made on disk.

- **A document:** Knowledge → choose the document → **⋯** → **Delete document**. It happens at once.
- **A whole collection, and every file in it:** Knowledge → choose the collection → **⋯** → **Delete collection**. Coffer asks first, naming the collection and how many documents it holds.

::: tip A delete can be undone
A delete is reported in a toast, *Deleted `<name>`*, with **Undo**, which puts back exactly what it removed — a document into its collection, a collection with its documents and its README — as one new change by you. Undo is refused, with nothing written, when a document is back at the same path or a collection of the same name exists again. Once the toast is gone, the deleted document has no page to open a **History** tab from, but its versions are still in the vault's history, so git can bring it back (`git -C ~/.coffer/vault log -- knowledge/<path>`); a deleted collection's files can be, but its registration cannot, which is why **Delete collection** asks first.
:::

## What not to put in knowledge

- **Secrets.** No keys, tokens or passwords. Use [Secret store](/guides/secret-store).
- **What the code already says.** If an agent can read it in the repository, it does not belong here.
- **Scratch notes.** What goes in should still be true in a month.

## Troubleshooting

**A tidy rewrote a document badly.** Open the document's **History** tab, choose a version from before the tidy and press **Restore this version…**.

**Tidy offers only Copy prompt.** No managed agent is available. Add one under **Agents**, or paste the copied prompt into the agent you use; it must have the `coffer-guide` skill.

**An agent does not use the knowledge.** Check that the `coffer-guide` skill is enabled and reaches that agent (its **Reach** button on the Skills page), and that the collection's `README.md` opens with a sentence naming its subjects.

**A file an agent wrote never shows up.** A document written into a collection shows up on the next read. A file left in `.inbox/` must be Markdown, directly in the `.inbox/` folder of an existing collection, and becomes a document at the next sweep, within about a minute; a file anywhere else is left alone, and a file that is not Markdown is not turned into a document.

## Related

- [Skills](/guides/skills) — the `coffer-guide` skill that carries the catalogue and the writing and tidying rules
- [Memory](/guides/memory)
- [Knowledge architecture](/architecture/knowledge)
- [MCP tools reference](/reference/mcp-tools)
- [Knowledge spec](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/knowledge/spec.md)
- [Knowledge Is Plain Files](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/knowledge-is-plain-files.md) and [Tidying Knowledge Is the Agent's Job](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/tidying-knowledge-is-the-agents-job.md)
