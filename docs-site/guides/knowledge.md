---
title: Knowledge
description: Keep what you and your agents know about your working environment as folders of Markdown that every agent reads with its own file tools.
---

# Knowledge

Knowledge is a directory of Markdown documents about your working environment — services, repositories, conventions, decisions, traps — that every agent on your machine reads. This page covers creating collections, adding and editing documents, how Coffer's curation pass merges new material, and how agents find what is there.

::: warning Experimental feature
Knowledge is an [experimental feature](/guides/experimental-features) with the key `knowledge`. It is on by default in `dev` builds and off by default in `stable` builds. Switch it on under **Settings → General → Experimental features**, or run `coffer daemon features enable knowledge`. While it is off, the Knowledge page, the `/api/v1/knowledge` routes and the `coffer__write` tool are unavailable, and nothing you stored is deleted.
:::

## What knowledge is for

Knowledge holds facts about the world you work in: which team owns a service, how an internal API authenticates, why a migration is ordered the way it is. It arrives because you, or an agent working with you, put it there.

- **One copy for every agent.** Claude Code and Codex read the same files, so what one agent records in the morning another reads in the afternoon.
- **Plain files.** Each document is a Markdown file you can open, edit, grep and back up. Coffer keeps no index, no embeddings and no database copy of the content.
- **Written together.** You edit documents in your own editor. Agents submit new material. Coffer's curation pass merges that material into the documents that already cover the subject, so a fact lives in one place instead of piling up as notes.

Knowledge is not [memory](/guides/memory). Memory is what agents learn while working, read out of their own memory stores. Knowledge is what somebody deliberately wrote down.

## How a collection is laid out

A **collection** is a top-level folder under the knowledge root:

```text
~/.coffer/knowledge/
└── payments/                     ← one collection
    ├── README.md               ← what this collection is about
    ├── session-ownership.md    ← a document
    ├── gateway/
    │   └── rate-limits.md      ← nesting is allowed and means nothing
    └── .inbox/                 ← hidden: material waiting to be merged
```

- **Documents** are the Markdown files in the collection. A document's path is its identity; there is no separate id. File names are slugs of the title, with a suffix such as `-2` on a collision.
- **Folders** inside a collection are optional and carry no meaning. You, or curation, can create, move and remove them.
- **`README.md`** at the collection root describes the collection. Its first paragraph is the collection's description everywhere Coffer shows one, and it is what the `coffer-guide` skill tells agents the collection is about. It is never listed as a document, counted or curated.
- **Hidden entries** (names starting with `.`) are left out of every listing, count and catalogue. Coffer writes exactly one: the `.inbox/` folder, where submitted material waits to be merged.

To move the knowledge root, set `COFFER_KNOWLEDGE_ROOT` in the daemon's environment.

### Frontmatter

Every document carries YAML frontmatter:

```markdown
---
title: Session ownership
description: Which service owns user sessions, and where the TTL is configured.
actor: user
created_at: 2026-09-20T08:14:03.512840+00:00
updated_at: 2026-09-22T10:02:41.090311+00:00
coffer_curated_at: 2026-09-22T10:02:41.090311+00:00
---

The `account-session` service owns ...
```

| Key | Meaning |
| --- | --- |
| `title` | The document's title. |
| `description` | One sentence on what the document covers. Agents see it in the catalogue. |
| `actor` | `user` or `agent` — who wrote the material it came from. |
| `created_at`, `updated_at` | Timestamps. |
| `coffer_curated_at` | Written by Coffer when curation has seen the document. Curation uses it to tell whether you edited the file since. |

Any other key you add is kept, with its value, whenever Coffer rewrites the file.

::: tip Name the subject, not the file
A document must not refer to another knowledge file by its file name or path, because paths change as curation reorganises a collection. Write "see the gateway rate-limit notes", not "see `gateway/rate-limits.md`". Curation refuses to write a document that breaks this rule.
:::

## Create a collection

Collections are created only on purpose. Reading, writing or an agent's working directory never creates one.

::: code-group

```sh [CLI]
coffer knowledge create payments --description "Payments platform: ownership, APIs, data flows."
```

```text [Web UI]
Knowledge → New collection → Name, Description → Create
```

:::

This creates `~/.coffer/knowledge/payments/` and, when you give a description, a `README.md` holding it. From then on the README is the description; edit the file to change it.

List what you have:

```sh
coffer knowledge collections
```

The **Knowledge** page shows the same list with each collection's description, its number of documents, and how much material is **Pending**.

## Add knowledge

There are five ways in. Four of them submit **material** into the collection's hidden `.inbox/`; curation then merges it into the documents. The fifth — editing a file yourself — changes a document directly.

### From an agent: `coffer__write`

An agent connected to Coffer's MCP gateway (see [Connect a client](/guides/connect-a-client)) has one knowledge tool, `coffer__write`. It takes a `collection`, a `title`, a `description` and a `body`. The agent does not choose a file or a folder, and does not have to check whether the fact is already written down; curation decides where it belongs.

The `coffer-guide` skill tells agents to reach for `coffer__write` when they learn something durable. You can also ask directly: "write down what we just found out about the session TTL in the payments collection."

A write naming a collection that does not exist or is disabled is refused, and the error lists the collections that are available.

### From the CLI: `coffer knowledge write`

```sh
coffer knowledge write --in payments \
  --title "Session TTL" \
  --description "Where the session TTL is set and its current value." \
  --body "The TTL is 30 days, set in account-session's config key session.ttl_days."
```

### Upload a document

Upload converts a file to Markdown and submits the text as material. Neither the original file nor the extracted text is kept as a file of its own; what is new in it is merged into the collection's documents.

::: code-group

```sh [CLI]
coffer knowledge upload ./session-design.pdf --collection payments
```

```text [Web UI]
Knowledge → choose the collection → Upload → pick a file
```

:::

| Accepted | Formats |
| --- | --- |
| Converted | `pdf`, `docx`, `pptx`, `xlsx`, `xls`, `html`, `htm`, `epub` |
| Tables | `csv`, `tsv` |
| Taken as text | `md`, `markdown`, `mdx`, `txt`, `text`, `rst`, `json`, `yaml`, `yml`, `toml`, `ini`, `cfg`, `log`, `sql`, and common source files (`py`, `js`, `ts`, `go`, `rs`, `java`, `sh`, …) |

One file per upload, at most 20 MB. An unsupported type is refused with the type named (`INGEST_REJECTED`), and a conversion that produces no text — an image-only PDF, for example — is refused too. A refused upload leaves nothing behind.

The material's `title` comes from the document (a `# ` heading on its first line, or else the file name). Its `description` is written by Coffer's model when one is configured, and taken from the document's opening prose when not.

### From your phone: `/save` in a channel

If you have a [channel](/guides/channels) paired, send a document to it as an attachment, then send:

```text
/save payments
```

Coffer saves the attachment into that collection through the same upload path and replies with a confirmation naming the file and the collection. With no name, or a name that is not an enabled collection, it offers a card listing your collections to pick from. Only the channel's owner can save.

### Edit a file yourself

Writing, editing or deleting a Markdown file in the collection folder with any editor is a complete way to change knowledge. There is no import step. The change is live on the next read, and the next curation sweep notices the edit (by its modification time) and carries it through to the rest of the collection.

On the Knowledge page, choose a document and use **Open in editor** or **Reveal in Finder** to jump to the file.

Agents may do the same thing with their own file tools: the `coffer-guide` skill tells them they can correct or extend a document they have read by editing it.

## Curation

Curation is how material becomes knowledge. It is a short, bounded pass driven by Coffer's own model (the model configured under **Settings → Coffer's model**; see [Model providers](/guides/providers)).

### What a pass does

Each pass takes **one item**: the oldest piece of material in a collection's inbox, or a document someone edited since curation last saw it. The model is given:

- the item in full,
- up to five candidate documents in full, chosen by literal matching of distinctive strings from the item, and
- the collection's full catalogue of titles and descriptions, so it can open a new document when none of the candidates is the right home.

It can list, read, write and retire documents in that one collection and nothing else — not the inbox, not the `README.md`, not another collection. It then merges what is new into the right document, or opens a new one.

The model is instructed on two rules:

- **Newer statements win.** When material contradicts a document, the newer statement is kept and the superseded one stays legible as a dated correction.
- **Your edits stand.** When the item is a document you edited, the pass never reverts or rewords your text. It carries your change outward — correcting other documents that disagree, moving a section that belongs elsewhere.

When the pass completes, merged material is deleted from the inbox, and an edited document is stamped with `coffer_curated_at`. A pass that does not complete leaves its item where it was, to be tried again.

### Limits

| Limit | Value |
| --- | --- |
| Writes per pass (a retire counts as one) | 8 |
| Candidate documents shown in full | 5 |
| Largest item a pass takes | 120,000 characters |
| Passes per collection per sweep | 5 |
| Passes running per collection at once | 1 |

A pass can only retire a document whose content it has already written elsewhere in the same pass. An item larger than the size limit is never shown to the model: material is kept as a document as it stands, and an edited document is simply stamped. An item that hits the pass's step limit three times in a row is also kept as it stands and not offered again.

### When curation runs

Curation runs on a background sweep, every 60 seconds by default, starting about a minute after the daemon starts. Each sweep takes inbox material first, oldest first, then edited documents.

Change the switch or the interval under **Settings → Coffer's model → Automatic upkeep → Merge new knowledge into documents**, or on the CLI:

```sh
coffer engine upkeep list
coffer engine upkeep set curate --interval 300
coffer engine upkeep set curate --off
```

The shortest interval is 60 seconds. A changed interval applies without a restart. With the sweep off, new material waits in the inbox until you run a pass by hand, and edits are not carried through.

### Run a pass by hand

::: code-group

```sh [CLI]
# the next pending item
coffer knowledge curate payments

# carry one edited document through
coffer knowledge curate payments --document gateway/rate-limits.md
```

```text [Web UI]
Knowledge → choose the collection → Curate
```

:::

Every pass reports a status:

| Status | Meaning |
| --- | --- |
| `ok` | The pass ran and settled its item. |
| `up_to_date` | Nothing is waiting. |
| `no_model` | No internal model is configured; pending material became documents as it stood. |
| `too_large` | The item is over the size limit; it was kept as it stands. |
| `truncated` | The pass hit its step limit. What it wrote is kept and the item is tried again later. |
| `failed` | The pass did not finish. Nothing was lost; the item is tried again. |

A request while a pass is already running over the same collection is refused with `UPKEEP_ALREADY_RUNNING` rather than queued. `coffer engine upkeep runs` shows which passes are running now.

### Without an internal model

If Coffer's model is not configured, nothing waits: each submission becomes a document at the collection root immediately, as written, and a manual pass promotes anything already in the inbox and reports `no_model`. Nothing is merged, but everything is readable. Edited documents need nothing.

### On more than one machine

A pass rewrites documents that [vault sync](/guides/vault-sync) carries between machines. If two machines both curated, the same material would be merged into two different documents. So curation runs on one **owner machine** only.

- With no owner named, curation runs wherever the vault is open — correct for a single machine.
- To name this machine: **Settings → Coffer's model → Automatic upkeep → Run curation on this machine**, or `coffer engine curate-owner set`.
- `coffer engine curate-owner show` reports the current owner, and flags an owner that no known machine claims (in that state curation runs nowhere); `coffer engine curate-owner clear` removes it.

Curation and a sync round never run at the same time, and curation is skipped while a sync conflict or confirmation is outstanding.

::: info What leaves your machine
Curation sends the item, its candidate documents and the catalogue to the model endpoint you configured. Upload also sends the start of a document to that endpoint to write its description. Nothing else in the knowledge layer sends content anywhere.
:::

## How agents find knowledge

Coffer has **no tool for reading, listing or searching knowledge**. An agent reads the files by path with the tools it already has: `Read`, `Grep`, its shell.

What tells it where to look is Coffer's built-in [`coffer-guide` skill](/guides/skills#the-built-in-coffer-guide-skill), which Coffer links into every agent's skill folder:

- Its **description**, which is in every session, names the subjects of your enabled collections, taken from each `README.md`.
- Its **body**, loaded when the agent opens the skill, gives the knowledge root's path and a catalogue of every document in every enabled collection: its path, title and description.

Coffer rewrites the skill whenever the catalogue changes, so a new document appears in it within one sweep.

::: details Why no search tool
Agents reliably use the file tools they already have, and rarely remember to call a special-purpose retrieval tool. Handing them a catalogue and a path turns retrieval into something they already do well, and a literal `grep` over a few hundred files matches identifiers and names that fuzzy search would blur. See [Knowledge architecture](/architecture/knowledge) for the full reasoning.
:::

Write a good `README.md` for each collection: its first paragraph is what a model matches on when deciding whether your knowledge is relevant.

## Browse and read

::: code-group

```sh [CLI]
coffer knowledge ls payments            # one level: folders and files
coffer knowledge ls payments/gateway
coffer knowledge read payments/session-ownership.md
```

```text [Web UI]
Knowledge → choose the collection
```

:::

The collection page shows one tree of documents beside a read-only preview. The **Filter by name…** box narrows the names already shown; it does not search content. The page shows how many new items are waiting to be merged, and the preview shows when each document was last curated. Inbox items are never listed.

`coffer knowledge read --json` includes the absolute path of the file and of its folder.

## Enable or disable a collection

A collection has one switch: enabled or disabled. Every enabled collection is available to every agent; there is no per-agent reach for knowledge.

A disabled collection is left out of the `coffer-guide` skill entirely — its name, description and catalogue — and `coffer__write` refuses to write into it.

::: code-group

```sh [CLI]
coffer resource disable knowledge payments
coffer resource enable knowledge payments
```

```text [Web UI]
Knowledge → the Status control on the collection's row
```

:::

::: warning Disabled is not hidden on disk
Disabling stops Coffer from naming a collection to agents. It does not protect the files: the skill hands agents the knowledge root, and an agent can still read anything under it with its own tools.
:::

## Delete documents and collections

Only a person deletes. No agent-facing tool can delete knowledge, and you can delete any document, whoever wrote it.

::: code-group

```sh [CLI]
coffer knowledge delete payments/gateway/rate-limits.md
```

```text [Web UI]
Knowledge → choose the collection → choose the document → Delete document
```

:::

To delete a whole collection, and every file in it:

::: code-group

```sh [CLI]
coffer resource delete knowledge payments
```

```text [Web UI]
Knowledge → the delete action on the collection's row
          (or select several rows → Delete)
```

:::

::: danger
The files are the only copy. Coffer keeps no history of deleted or rewritten documents. If you use [vault sync](/guides/vault-sync), the vault's git history is your record.
:::

## What not to put in knowledge

- **Secrets.** No keys, tokens or passwords. Use [Credentials](/guides/credentials).
- **What the code already says.** If an agent can read it in the repository, it does not belong here.
- **Scratch notes.** What goes in should still be true in a month.

## Troubleshooting

**Pending material never gets merged.** Check that curation is switched on (`coffer engine upkeep list`), that this machine is the owner or no owner is set (`coffer engine curate-owner show`), and that Coffer's model is configured. Run `coffer knowledge curate <collection>` to see the status of one pass.

**An agent does not use the knowledge.** Check that the collection is enabled, that the `coffer-guide` skill is enabled and reaches that agent (`coffer scope show skill coffer-guide`), and that the collection's `README.md` opens with a sentence naming its subjects.

**`coffer__write` is missing from the agent's tools.** The `knowledge` feature is switched off on this machine, or Coffer's MCP server is not installed for that agent (`coffer agent mcp install <agent>`).

## Related

- [Skills](/guides/skills) — the `coffer-guide` skill that carries the catalogue
- [Memory](/guides/memory)
- [Experimental features](/guides/experimental-features)
- [Knowledge architecture](/architecture/knowledge)
- [MCP tools reference](/reference/mcp-tools)
- [Knowledge spec](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/knowledge/spec.md)
- [Knowledge Is Plain Files](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/knowledge-is-plain-files.md) and [One Shared Knowledge Store Across Agents](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/agent-native-shared-memory.md)
