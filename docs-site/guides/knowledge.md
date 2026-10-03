---
title: Knowledge
description: Keep what you and your agents know about your working environment as folders of Markdown that every agent reads with its own file tools.
---

# Knowledge

Knowledge is a directory of Markdown documents about your working environment — services, repositories, conventions, decisions, traps — that every agent on your machine reads. This page covers creating collections, adding and editing documents, how Coffer's curation folds new items into the documents, how to look back at every change and undo one, and how agents find what is there.

## What knowledge is for

Knowledge holds facts about the world you work in: which team owns a service, how an internal API authenticates, why a migration is ordered the way it is. It arrives because you, or an agent working with you, put it there.

- **One copy for every agent.** Claude Code and Codex read the same files, so what one agent records in the morning another reads in the afternoon.
- **Plain files.** Each document is a Markdown file you can open, edit, grep and back up. Coffer keeps no index, no embeddings and no database copy of the content.
- **Written together.** You edit documents on the Knowledge page or in your own editor. Agents submit new items. Coffer's curation folds each item into the documents that already cover the subject, so a fact lives in one place instead of piling up as notes.

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
    └── .inbox/                 ← hidden: items waiting to be curated
```

- **Documents** are the Markdown files in the collection. A document's path is its identity; there is no separate id. File names are slugs of the title, with a suffix such as `-2` on a collision.
- **Folders** inside a collection are optional and carry no meaning. You, or curation, can create, move and remove them.
- **`README.md`** at the collection root describes the collection. Its first paragraph is the collection's description everywhere Coffer shows one, and it is what the `coffer-guide` skill tells agents the collection is about. It is never listed as a document, counted or curated.
- **Hidden entries** (names starting with `.`) are left out of every document count and the catalogue. Inside a collection Coffer writes exactly one: the `.inbox/` folder, where submitted items wait to be curated. The Knowledge page shows `.inbox/` as the collection's **Inbox**, with how many items wait; its items can be read but not edited or deleted, and no other hidden entry is listed.

The knowledge root is inside the vault repository, `~/.coffer/vault`, and `coffer path knowledge` prints it. It cannot be moved elsewhere: a tree outside the vault would be a tree its history cannot see.

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
| `actor` | `user` or `agent` — who wrote the item it came from. |
| `created_at`, `updated_at` | Timestamps. |

Any other key you add is kept, with its value, whenever Coffer rewrites the file. Coffer writes nothing into a document to remember what curation has seen: that is kept on this machine in `~/.coffer/local/curation.json`, as the content each document had when curation last settled it.

::: tip Name the subject, not the file
A document must not refer to another knowledge file by its file name or path, because paths change as curation reorganises a collection. Write "see the gateway rate-limit notes", not "see `gateway/rate-limits.md`". Curation refuses to write a document that breaks this rule.
:::

## Create a collection

Collections are created only on purpose. Reading, writing or an agent's working directory never creates one.

::: code-group

```sh [CLI]
coffer knowledge add payments --description "Payments platform: ownership, APIs, data flows."
```

```text [Web UI]
Knowledge → New collection → Name, What belongs in here → Create collection
```

:::

This creates `~/.coffer/vault/knowledge/payments/` and, when you give a description, a `README.md` holding it. On the Knowledge page, **New collection** asks for both the name and what belongs in the collection. A collection has no title: every page and listing shows it by its folder name. Its description is the opening paragraph of the README: change it on the collection's page (click the text; it saves when you leave the field), with `coffer knowledge edit payments --description "…"`, or in the file itself. Either way only that paragraph changes, and anything written under it stays. `coffer knowledge edit payments --name <new>` renames the collection and moves its directory with it.

List what you have:

```sh
coffer knowledge list
```

The **Knowledge** page's tree shows the same list, each collection with its number of documents and, under it, its **Inbox** with how many items wait. That count is the only place items waiting show up: the sidebar has no badge for them.

## Add knowledge

There are six ways in. Five of them submit an **item** into the collection's hidden `.inbox/`; curation then folds it into the documents. The sixth — editing a file yourself — changes a document directly.

### From an agent: `coffer__write`

An agent connected to Coffer's MCP gateway (see [Connect a client](/guides/connect-a-client)) has one knowledge tool, `coffer__write`. It takes a `collection`, a `title`, a `description` and a `body`. The agent does not choose a file or a folder, and does not have to check whether the fact is already written down; curation decides where it belongs.

The `coffer-guide` skill tells agents to reach for `coffer__write` when they learn something durable. You can also ask directly: "write down what we just found out about the session TTL in the payments collection."

A write naming a collection that does not exist is refused, and the error lists the collections that are available.

### From the CLI: `coffer knowledge write`

```sh
coffer knowledge write --collection payments \
  --title "Session TTL" \
  --description "Where the session TTL is set and its current value." \
  --body "The TTL is 30 days, set in account-session's config key session.ttl_days."
```

### Upload a document

Upload converts a file to Markdown and submits the text as an item. Neither the original file nor the extracted text is kept as a file of its own; what is new in it is folded into the collection's documents. With Coffer's engine not set there is nothing to curate with, so the upload is added to the collection as a document straight away, and the Upload dialog says so.

::: code-group

```sh [CLI]
coffer knowledge upload ./session-design.pdf --collection payments
```

```text [Web UI]
Knowledge → Upload → choose a file and the collection → Upload
```

:::

| Accepted | Formats |
| --- | --- |
| Converted | `pdf`, `docx`, `pptx`, `xlsx`, `xls`, `html`, `htm`, `epub` |
| Tables | `csv`, `tsv` |
| Taken as text | `md`, `markdown`, `mdx`, `txt`, `text`, `rst`, `json`, `yaml`, `yml`, `toml`, `ini`, `cfg`, `log`, `sql`, and common source files (`py`, `js`, `ts`, `go`, `rs`, `java`, `sh`, …) |

One file per upload, at most 20 MB. An unsupported type is refused with the type named (`INGEST_REJECTED`), and a conversion that produces no text — an image-only PDF, for example — is refused too. A refused upload leaves nothing behind.

The item's `title` comes from the document (a `# ` heading on its first line, or else the file name). Its `description` is written by Coffer's model when one is configured, and taken from the document's opening prose when not.

### From your phone: `/kb` in a channel

If you have a [channel](/guides/channels) paired, send a document to it as an attachment, then send:

```text
/kb payments
```

Coffer saves the attachment into that collection through the same upload path and replies with a confirmation naming the file and the collection. With no name, or a name that is not one of your collections, it offers a card listing your collections to pick from. Only the channel's owner can save.

### Edit a file yourself

Writing, editing or deleting a Markdown file in the collection folder with any editor is a complete way to change knowledge. There is no import step. The change is live on the next read, and the next curation sweep notices the edit (its content differs from what curation last settled, and the change was not curation's own or another machine's) and carries it through to the rest of the collection.

On the Knowledge page, choose a document and use **Edit** to change it in place, or the **⋯** menu's **Open in editor** or **Reveal in Finder** to jump to the file. The editor holds the document's body only: its front matter is shown above it, read-only, as *Kept by curation*. The editor is the one place that saves on request: **Discard** drops your changes and **Save** (**⌘S**) keeps them, and leaving with unsaved changes asks whether to leave without saving; the tree marks the open document with a dot meanwhile. A save that finds the file changed on disk since the page loaded it, by your own editor or by a curation pass, is refused as a conflict (`KNOWLEDGE_FILE_CONFLICT`) and the file is left as it is. The page says the document changed on disk and your text was not saved, and offers **Compare**, **Copy my text** and **Reload** — never a second save over it. **Compare** puts the two versions side by side with their diff: **Keep my edit** or **Take the version on disk**; whichever you leave out stays in the document's History. **Reload** takes what is on disk and asks first, because it drops your text. The saved file counts as your edit, exactly like one made in your own editor. From the CLI, edit the file under `coffer path knowledge <collection>` with your own editor.

Agents may do the same thing with their own file tools: the `coffer-guide` skill tells them they can correct or extend a document they have read by editing it.

## Curation

Curation is how items become knowledge. It is a short, bounded pass driven by Coffer's own model (the model configured under **Settings › General → Coffer's model**; see [Model providers](/guides/providers)).

### What a pass does

Each pass takes **one item**: the oldest item in a collection's inbox, or a document someone edited since curation last saw it. The model is given:

- the item in full,
- up to five candidate documents in full, chosen by literal matching of distinctive strings from the item, and
- the collection's full catalogue of titles and descriptions, so it can open a new document when none of the candidates is the right home.

It can list, read, write and retire documents in that one collection and nothing else — not the inbox, not the `README.md`, not another collection. It then folds what is new into the right document, or opens a new one.

The model is instructed on two rules:

- **Newer statements win.** When an item contradicts a document, the newer statement is kept and the superseded one stays legible as a dated correction.
- **Your edits stand.** When the item is a document you edited, the pass never reverts or rewords your text. It carries your change outward — correcting other documents that disagree, moving a section that belongs elsewhere.

When the pass completes, the curated item is deleted from the inbox, and an edited document is recorded as settled at its new content. A pass that does not complete leaves its item where it was, to be tried again. Each pass is one change in the [history](#history-and-undo), so you can read what it did and undo it.

### Limits

| Limit | Value |
| --- | --- |
| Writes per pass (a retire counts as one) | 8 |
| Candidate documents shown in full | 5 |
| Largest item a pass takes | 120,000 characters |
| Passes per collection per sweep | 5 |
| Passes running per collection at once | 1 |

A pass can only retire a document whose content it has already written elsewhere in the same pass. An item larger than the size limit is never shown to the model: an inbox item is kept as a document as it stands, and an edited document is simply recorded as settled. An item that hits the pass's step limit three times in a row is also kept as it stands and not offered again.

### When curation runs

Curation runs on a background sweep, every hour by default, starting about a minute after the daemon starts. New items are therefore curated within the hour; to have them curated now, curate by hand (below). Each sweep takes inbox items first, oldest first, then edited documents, and runs a few passes per collection.

Change the switch or the interval from the Knowledge page's header: **Automatic · hourly** beside the title opens a popover with the switch, the interval, when the last pass ran and the next one is due, and **Curate now**. On the CLI:

```sh
coffer config list engine.upkeep.
coffer config set engine.upkeep.curate.interval 300
coffer config set engine.upkeep.curate.enabled off
```

The shortest interval is 60 seconds. A changed interval applies without a restart. With the sweep off, new items wait in the inbox until you curate by hand, and edits are carried through only then.

### Curate by hand

Curating by hand drains a collection: it takes everything pending when it starts — inbox items oldest first, then documents edited since curation last saw them — and runs one pass per item, one after another, until none is left. It is not tied to the owner machine (pressing the button chooses this one), but like the sweep it is refused with `KNOWLEDGE_CURATION_HELD` (409) while a sync conflict or confirmation waits for you. Inbox items are ordered by when they were submitted (the `created_at` in the item itself), never by file time.

::: code-group

```sh [CLI]
# everything pending in the collection
coffer knowledge curate payments

# carry one edited document through, and nothing else
coffer knowledge curate payments --document gateway/rate-limits.md
```

```text [Web UI]
Knowledge → the collection's Inbox → Curate now
Knowledge → Recent changes → Curate now   (every collection with items waiting)
```

:::

While it waits on a terminal, the CLI shows progress (`curating… 2 of 5 done`), then prints one line per pass and a summary:

```text
1 of 3: ok payments/.inbox/session-ttl.md (2 written, 0 retired)
2 of 3: ok payments/.inbox/rate-limit-change.md (1 written, 1 retired)
3 of 3: ok payments/gateway/rate-limits.md (1 written, 0 retired)
payments: curated 3 of 3
```

`--json` prints the whole answer for scripts, and `coffer daemon status` lists the runs in flight.

- The run **stops at the first failed pass**. The items after it stay pending for the next run or sweep.
- A `truncated` or `too_large` pass does not stop it.
- With no model configured, the first pass turns the whole inbox into documents and the run ends with `no_model`.
- Items that arrive while a run is going wait for the next run or sweep.

Every pass reports a status:

| Status | Meaning |
| --- | --- |
| `ok` | The pass ran and settled its item. |
| `up_to_date` | Nothing is waiting. |
| `no_model` | No internal model is configured; the pending items became documents as they stood. |
| `too_large` | The item is over the size limit; it was kept as it stands. |
| `truncated` | The pass hit its step limit. What it wrote is kept and the item is tried again later. |
| `failed` | The pass did not finish. Nothing was lost; the item is tried again. |

A request while a run is already going over the same collection is refused with `UPKEEP_ALREADY_RUNNING` rather than queued.

### Without an internal model

If Coffer's model is not configured, nothing waits: each submission becomes a document at the collection root immediately, as written, and a manual pass promotes anything already in the inbox and reports `no_model`. Nothing is curated, but everything is readable. Edited documents need nothing.

### On more than one machine

A pass rewrites documents that [vault sync](/guides/vault-sync) carries between machines. If two machines both curated, the same item would be folded into two different documents. So curation runs on one **owner machine** only.

- With no owner named, curation runs wherever the vault is open — correct for a single machine.
- To name the owner: once the vault spans several Macs, the Knowledge header's **Automatic** popover shows **Curation runs on** with a picker of the Macs; or run `coffer config set engine.curate_owner this` on the Mac that should curate.
- `coffer config get engine.curate_owner` reports the current owner, and flags an owner that no known machine claims (in that state curation runs nowhere); `coffer config unset engine.curate_owner` removes it.

Curation and a sync round never run at the same time, and curation is skipped while a sync conflict or confirmation is outstanding.

::: info What leaves your machine
Curation sends the item, its candidate documents and the catalogue to the model endpoint you configured. Upload also sends the start of a document to that endpoint to write its description. Nothing else in the knowledge layer sends content anywhere.
:::

## How agents find knowledge

Coffer has **no tool for reading, listing or searching knowledge**. An agent reads the files by path with the tools it already has: `Read`, `Grep`, its shell.

What tells it where to look is Coffer's built-in [`coffer-guide` skill](/guides/skills#the-built-in-coffer-guide-skill), which Coffer links into every agent's skill folder:

- Its **description**, which is in every session, names the subjects of your collections, taken from each `README.md`.
- Its **body**, loaded when the agent opens the skill, gives the knowledge root's path and a catalogue of every document in every collection: its path, title and description.

Coffer rewrites the skill whenever the catalogue changes, so a new document appears in it within one sweep.

::: details Why no search tool
Agents reliably use the file tools they already have, and rarely remember to call a special-purpose retrieval tool. Handing them a catalogue and a path turns retrieval into something they already do well, and a literal `grep` over a few hundred files matches identifiers and names that fuzzy search would blur. See [Knowledge architecture](/architecture/knowledge) for the full reasoning.
:::

Write a good `README.md` for each collection: its first paragraph is what a model matches on when deciding whether your knowledge is relevant.

## Browse and read

::: code-group

```sh [CLI]
coffer path knowledge payments          # the collection's directory
ls "$(coffer path knowledge payments)"/gateway
cat "$(coffer path knowledge payments)"/session-ownership.md
```

```text [Web UI]
Knowledge → choose the collection in the tree → choose a document
```

:::

The Knowledge page is one tree beside a reading pane, both filling the window under the page header. The title carries the **Experimental** tag; the header's actions are **Automatic · hourly** (curation's switch, interval and **Curate now**) and **Upload**, the page's one primary button — secondary while you are editing a document. At the top of the tree, **Collections** has a **New collection** button; below it every collection by its folder name, each opening to its **Inbox** and its documents, each shown by its file name. The Inbox node is the only one with a number: how many items are waiting. **Recent changes** sits above the collections. Choosing a collection shows its folder name, what belongs in it (click it to edit; it saves when you leave the field or press **⌘Enter**, **Esc** cancels, and a toast offers **Undo**) and its properties: **Documents**, **Inbox** (*N waiting* with **Open Inbox**, or *Nothing*), **Last curated** (a time, or *Never*) and **Folder**. While a Curate now run is draining the Inbox the page reads **Curating · n of m**. The collection's **⋯** menu holds **Reveal in Finder**, **Copy path** and **Delete collection**; a collection with nothing in it yet says so and reminds you that you can upload one or drop Markdown files into its folder. Choosing a document renders it with **Edit** (see [Edit a file yourself](#edit-a-file-yourself)), a **Preview / Source** switch for Markdown and a **⋯** menu — **Open in editor**, **Reveal in Finder**, **Delete document** — on two tabs: **Document** and **History** (see [History and undo](#history-and-undo)). Under the title one line says who wrote it, with a **See the pass** link when curation did, and when it was created. The Inbox lists the items waiting to be curated — *curated automatically within the hour* — with a quiet **Curate now**; an item opens read-only, with who wrote it and when, and it leaves the Inbox once curation has filed it. A manual **Curate now** ends with one summary toast; what became of an item that could not be curated (too large, cut off, over the step limit) is written on that change's row in Recent changes.

The page has no search box and no per-collection switch: ⌘K jumps to a collection by name, and every collection reaches every agent. There is no form for typing a document into the page: you write through **Edit**, and agents through `coffer__write`. While Coffer's engine is not set there is no Inbox, no Automatic control and no Curate now; in the control's place **Curation needs Coffer’s engine** leads to **Settings › General**, and until then items become documents as they arrive.

The documents are plain files: `coffer path knowledge` prints the knowledge root, and `coffer path knowledge <collection>` one collection's directory, so you read and grep them with your own tools.

## Every collection reaches every agent

A collection has no on/off switch and no per-agent reach: every collection is available to every agent, and a collection leaves agents' `coffer-guide` skill only by being deleted. `coffer knowledge` has no `enable` or `disable`, and the generic enable and disable routes refuse a collection with `RESOURCE_NOT_TOGGLEABLE`.

::: warning Not access control
The skill hands agents the knowledge root, and an agent can read anything under it with its own tools. Keep nothing in a collection that an agent on this machine should not read.
:::

## History and undo

Every change to a collection is kept as a version: your saves and deletes, each curation pass, a submission that became a document at once, what vault sync brought in, and edits made outside Coffer in your own editor or with an agent's file tools. Each change names its **writer** — `user`, `agent`, `curation` (with the item it curated and who submitted it), `sync` or `disk` — so you can always tell who changed what.

The history is the vault repository's own: collections live under `knowledge/` in `~/.coffer/vault`, so `coffer vault history knowledge/<collection>/<path>` reads the same versions, and [vault sync](/guides/vault-sync) carries them to your other machines. Coffer needs `git` for the vault; without it the daemon does not start and names the install step. If git goes missing while the daemon runs, every write keeps working and the history commands answer `KNOWLEDGE_HISTORY_UNAVAILABLE`. That refusal carries a prompt for your agent to install git the way that fits your machine and confirm it with `git --version`: the History tab (*History needs git*) and **Recent changes** (*Recent changes needs git*) show one row with **Check again** and **Ask an agent ▾** — its menu copies the prompt — and the history commands print it.

### Look at a document's history

```sh
coffer knowledge history payments/session-ownership.md               # its versions, newest first
coffer knowledge history payments/session-ownership.md --version 3f2a9c1   # one version's diff
```

Put any version back with:

```sh
coffer knowledge restore payments/session-ownership.md 3f2a9c1
```

A restore is a new version of its own, written by you; the history before it stays. Curation treats it like any edit of yours and carries it through to the rest of the collection. A deleted document is restored the same way, from the version before the delete.

### See recent changes

```sh
coffer knowledge changes                 # every collection, newest first
coffer knowledge changes --collection payments   # one collection
coffer knowledge changes 8d41e07         # one change in full, with each document's diff
```

Each change lists its writer, its time, its collection and every document it added, modified or removed, with line counts. The items still waiting in each inbox are listed separately, with who submitted them and when.

On the Knowledge page, a document's **History** tab is one list of its versions, newest first, with their writers and line counts. Choose a row and it expands in place to its diff: **Changes in this version** (against the version before) or **Compare with current**, with **Restore this version** on every version but the current one. A curation's row links to **See the pass**. If the history cannot be read, the tab shows one **Load error** row with **Retry** and **Open Activity**, and the Document tab keeps working. **Recent changes**, at the top of the tree, is the timeline across every collection for the last seven days, grouped by day, with **Collection** and **Author** filters and **Clear filters** (your choice stays in the page's address), and the items waiting and **Curate now** above it — while a run is going it reads **Curating · n of m**. A curation pass links to **See the pass**, which shows every document it touched, each with its diff and a link to its History; a delete carries **Restore** (see [Delete documents and collections](#delete-documents-and-collections)).

### Undo a curation pass

If a pass did something you disagree with, undo it as a whole:

```sh
coffer knowledge undo 8d41e07
```

Every document the pass wrote or retired goes back exactly as it was before the pass, and documents it created are removed, in one new change written by you. Curation does not redo the pass afterwards. The item the pass curated stays out of the inbox; its text is still in the history.

On the Knowledge page, open the pass from **Recent changes** (or **See the pass** under a document it wrote) and choose **Undo this pass**; the page asks first, listing each document and what the undo does to it. A refused undo closes the question and says in one sentence which document changed since, with **Open its History**, where you can restore a single version; an undone pass reads **Undone**, with who undid it and when.

- If a later change touched one of the pass's documents, the undo is refused with `KNOWLEDGE_UNDO_CONFLICT` naming that document, and nothing is written. Edit or restore that document instead — or undo the pass by hand while keeping the later edits: the refusal carries a prompt for your agent, offered on the pass's page and printed by `coffer knowledge undo`, that names the pass, each document it touched, the ones edited since, and `git -C ~/.coffer/vault show <version> -- knowledge` for reading what the pass did. The agent edits only the files; Coffer records what it writes as an edit on disk.
- When the pass merged nothing — there was no model, the item was too large, or curation gave up on it — the document it created was the item as it stood, so the undo puts the item back in the Inbox as well. Nothing you submitted is lost.
- Only a curation pass can be undone this way (`KNOWLEDGE_NOT_A_PASS` otherwise). For any other change, restore the document's earlier version.

## Delete documents and collections

Only a person deletes. No agent-facing tool can delete knowledge, and you can delete any document, whoever wrote it.

::: code-group

```sh [CLI]
rm "$(coffer path knowledge payments)"/gateway/rate-limits.md
```

```text [Web UI]
Knowledge → choose the document → ⋯ → Delete document
```

:::

To delete a whole collection, and every file in it:

::: code-group

```sh [CLI]
coffer knowledge rm payments
```

```text [Web UI]
Knowledge → choose the collection → ⋯ → Delete collection
```

:::

::: tip A delete can be restored
In the web UI a delete happens at once: no confirmation, no typed name, and a toast, *Deleted `<name>`*, with **Undo**. A deleted document or collection stays in the [history](#history-and-undo), so **Undo** puts it back even after the toast is gone. **Recent changes** lists the delete with **Restore**, which puts back exactly what it removed — a document into its collection, a collection with its documents, its README and the items that were waiting in its Inbox — as one new change by you. On the CLI, find the delete with `coffer knowledge changes` and run `coffer knowledge restore --deleted <version>`. A restore is refused, with nothing written, when a document is back at the same path or a collection of the same name exists again.
:::

## What not to put in knowledge

- **Secrets.** No keys, tokens or passwords. Use [Secret store](/guides/secret-store).
- **What the code already says.** If an agent can read it in the repository, it does not belong here.
- **Scratch notes.** What goes in should still be true in a month.

## Troubleshooting

**Pending items never get curated.** Check that curation is switched on (`coffer config get engine.upkeep.curate.enabled`), that this machine is the owner or no owner is set (`coffer config get engine.curate_owner`), and that Coffer's model is configured. Run `coffer knowledge curate <collection>` to see the status of every pass.

**Curation rewrote a document badly.** Find the pass with `coffer knowledge changes --collection <collection>`, read it with `coffer knowledge changes <version>`, and undo it with `coffer knowledge undo <version>`, or restore just that document with `coffer knowledge restore`.

**An agent does not use the knowledge.** Check that the `coffer-guide` skill is enabled and reaches that agent (`coffer skill scope coffer-guide`), and that the collection's `README.md` opens with a sentence naming its subjects.

**`coffer__write` is missing from the agent's tools.** The agent is not connected to Coffer (`coffer agent connect <agent>`).

## Related

- [Skills](/guides/skills) — the `coffer-guide` skill that carries the catalogue
- [Memory](/guides/memory)
- [Knowledge architecture](/architecture/knowledge)
- [MCP tools reference](/reference/mcp-tools)
- [Knowledge spec](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/knowledge/spec.md)
- [Knowledge Is Plain Files](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/knowledge-is-plain-files.md) and [Aggregate the Agents' Memory; Never Write It](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/aggregate-agent-memory-never-write-it.md)
