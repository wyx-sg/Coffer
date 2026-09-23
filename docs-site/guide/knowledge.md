# Knowledge

**Knowledge** is Coffer's one store of everything your agents should know — what you or an agent wrote down, and the documents you uploaded. It is a directory of Markdown files under `~/.coffer/knowledge/`, and those files are the whole of it. There is no index: no vector store, no full-text tables, nothing in `coffer.db` to keep in step with the disk. A file you edited in your own editor, a file an agent just wrote, and a file `git` pulled in all look the same to Coffer, because there is nothing in between.

What the layer adds on top of the directory is **curation**. Knowledge is written by you and your agents together: a document can be edited by either of you, and anything new — an upload, a note an agent files, a message you save from your phone — arrives as **material** that Coffer's own model merges into the documents already there. Every upload adds the knowledge in it to the collection; it does not add another file to wade through.

## Collections

A collection is a resource named `knowledge:<name>` and the directory `~/.coffer/knowledge/<name>/`. The two appear together, and only because you said so — nothing creates a collection as a side effect of a read or a write, so a name you typo'd is an error rather than a new, silently empty collection.

```bash
coffer knowledge create handbook --description "Company onboarding docs"
coffer knowledge collections
coffer resource delete knowledge handbook     # collection lifecycle is a Resource concern
```

A collection describes itself in its own `README.md`, at the collection root. That first paragraph is the description — it is read off disk on every listing, never copied into the database, and it is what the skill Coffer delivers to your agents draws on. The README is not content: it is never curated, listed or counted. A collection that fails to describe itself is a collection an agent never recognises.

A collection carries **no per-agent reach**: every enabled collection is served to every agent, and switching one off is the only way to take it out of what Coffer serves.

```bash
coffer resource disable knowledge handbook
coffer resource enable knowledge handbook
```

It could once be activated for some agents and not others. That was withdrawn, because it never authorized anything: what Coffer hands an agent is a catalogue of absolute paths into a directory that agent can already grep, so leaving a collection out of one agent's catalogue prevented a mistaken read at best and nothing at all at worst. Switching a collection off is a **delivery** gate for the same reason — a disabled collection is one no skill names, not one no process can open.

## One tree of documents

```
~/.coffer/knowledge/handbook/
├── README.md          # what this collection is for
├── onboarding/        # nesting is yours and curation's alike
│   └── first-week.md
├── package-manager.md
└── .inbox/            # hidden: material waiting to be merged
```

A collection is **one tree of Markdown documents**, and it is what an agent reads. You edit a document in your own editor; an agent may edit one with its own file tools; the curation pass rewrites documents as it merges new material in. Nobody owns a lane, because there are no lanes: the documents are co-written, and folders mean whatever whoever made them meant.

New knowledge does not land in the tree directly. It waits in the collection's hidden `.inbox/` until a pass folds it into the documents, and the inbox item is deleted the moment that happens. The inbox is the one hidden directory Coffer writes; nothing lists it, no catalogue names it, and no surface can address a path inside it.

Every document carries frontmatter with `title`, `description`, `actor` and timestamps, plus `coffer_curated_at` — when curation last had it in front of it. Any other key you put there is kept. A file's **path is its identity** — names are readable slugs derived from the title (up to 80 characters, CJK kept as-is, `-2`, `-3`, … on a collision), and there is no id anywhere. The stamp is also how a sweep knows what it owes: a document whose modification time is newer than its stamp is one somebody edited since, with no state file anywhere.

## Adding knowledge

```bash
coffer knowledge write --in handbook \
  --title "Package manager" \
  --description "Which package manager every repo here uses, and why" \
  --body "Prefer pnpm over npm in all repos."

coffer knowledge ls handbook                  # one level of the tree
coffer knowledge read handbook/package-manager.md
coffer knowledge delete handbook/package-manager.md
```

`write` submits **material**: it goes into the inbox, and the next pass merges it into whichever document owns that subject, deduplicating against what is already there. So write the fact plainly — you do not have to find where it belongs or check whether it repeats something. The command answers with whether the material is queued or, when no internal model is configured, which document it became.

Editing a document directly is an equally complete way to add knowledge. Change a line in your editor, add a section, drop in a new Markdown file — nothing has to be imported or registered. The next sweep notices the edit by its modification time and carries it into the rest of the collection: a correction you made in one document reaches the others that say the same thing. It never reverts what you wrote.

A document you add by hand should carry the same frontmatter Coffer writes, or it is catalogued with an empty description — and the description is what an agent picks a document by:

```markdown
---
title: Session ownership
description: Which service owns a login session, and what reads it.
actor: user
created_at: '2026-09-12T04:18:33Z'
updated_at: '2026-09-12T04:18:33Z'
---

Login state is owned by `account.session`.
```

Deleting is a person's action, and any document may be deleted. No agent-facing tool deletes anything.

## Uploading documents

Hand Coffer a file in any format and it converts it to Markdown and submits the result as material, exactly as `write` does. The knowledge in it is merged into the collection's documents; neither the file you sent nor the extracted text is kept as a file of its own.

```bash
coffer knowledge upload ./onboarding.pdf --collection handbook
```

- Conversion covers what [markitdown](https://github.com/microsoft/markitdown) handles — pdf, docx, pptx, xlsx, html, epub and more — plus plain text, Markdown and CSV. Legacy `.doc`/`.ppt`, `.rtf` and `.odt` are deliberately not among them: save as `.docx`/`.pptx` first. An unsupported type is refused by name, never stored half-converted, and a failed conversion leaves nothing behind — including an image-only PDF, which converts without error into no text at all and is refused for saying so.
- One file per call, a 20 MB ceiling, and a refusal that names the limit.
- The description is optional input but never optional output. With no internal model connection configured, Coffer draws one from the document's own opening prose rather than leaving it blank.

A document forwarded to a Coffer channel and followed by `/save <collection>` rides the same entrance — accepted only from the channel's paired owner — so your phone and the Knowledge page are two ends of one path into a collection.

## Curation

A collection accumulates the way notes do: the same fact arriving twice from two sessions, an upload that half-overlaps a document you already have, a correction that contradicts what is already there. Nothing about that is wrong at write time, which is why writing stays dumb. The sorting out is a **curation pass** — a bounded agentic rewrite, driven by your internal model connection, that takes one pending item and folds it into the documents.

A pass is deliberately small:

- It takes **one item** — a piece of inbox material, or a document someone edited — plus at most **five** candidate documents in full and the collection's whole catalogue of titles and descriptions. Candidates are found by matching distinctive strings from the item against the documents; the catalogue is there so the model can conclude that none of them is the right home and open a new document instead.
- Its tools are `list_documents`, `read_document`, `write_document` and `retire_document`, fenced to the one collection. It may make at most **eight writes**, so one item can never trigger a corpus-wide rewrite.
- It **preserves every fact it is shown**. Merging integrates rather than regenerates, and a document may only be retired when the same pass has written its content somewhere else — enforced at the tool: a retire is refused unless the pass has seen the document (in its brief or by reading it) and has since written a different document.
- **A person's edit stands.** When the item is a document you edited, the pass carries your change outward and never reverts or rewords it.
- Where new material contradicts a document, the **newer statement wins**, and the result keeps the superseded one legible as a dated correction. Knowledge is about a world that changes, and when it changed is itself worth keeping.
- A document may not name another knowledge file by path. That is enforced at the write rather than asked for in a prompt, because a hand-maintained map of generated paths is what rotted last time: 343 of 398 cross-references in this corpus had been broken by renames the prose never saw.

A sweep runs every minute. It drains each collection's inbox first — until material is merged it is knowledge no agent can read — and then any document edited since curation last stamped it. Run a pass by hand whenever you want:

```bash
coffer knowledge curate handbook
coffer knowledge curate handbook --document handbook/package-manager.md
```

The answer is a status: `ok`, `up_to_date`, `no_model` when no internal connection is configured, `too_large`, or `failed`. A pass that fails leaves its item as it was, so the next sweep tries again. Only one pass per collection runs at a time, whoever started it; a second trigger is refused rather than queued.

**With no internal model, nothing waits.** Material is promoted to a document of its own the moment it arrives, as it stands, and a pass over a collection with anything left in its inbox promotes all of it and reports `no_model` with the documents it produced. You get a less tidy collection, but never knowledge sitting where no agent can read it.

Two switches govern the unattended sweep, and both are read on every tick: whether it is on, and which single machine owns it (**Settings → Coffer's model**, under *Automatic upkeep*). A vault that spans machines must curate on exactly one of them, because two machines merging the same material produce two different documents that git would merge as two additions. With no owner chosen the switch means "here", which is the right answer for a single machine. It defaults **on**, because it is what turns new material into something an agent reads.

Curation also stands aside for [sync](/guide/sync): a pass never overlaps a converge round, and none starts while a round is waiting on you to resolve a conflict or confirm a change.

## How an agent reads it

**There is no retrieval tool, and that is the design.** An audit of 448 Claude Code sessions after this corpus was built found that the delivered skill had never once been loaded and that no knowledge tool had ever been called. A tool an agent does not remember to call is not retrieval — and every agent Coffer supports already has `Read` and `Grep`, which need no remembering. So the layer's whole job is to put the right absolute paths in front of the model.

It does that with **Coffer's own skill**, `coffer-guide` — one skill carrying both Coffer's manual and this catalogue, because a skill's description is resident in every session while its body costs nothing until a model opens it:

- Its **frontmatter description** names Coffer's own tools and the subjects your collections cover, in their READMEs' own words. That line is the only part of this layer always in a model's context, so it carries specifics a model can match — the version it replaces described the layer instead, and across those 448 sessions no model ever recognised it.
- Its **body** is Coffer's manual first, then the knowledge root and, for every document, its path, title and description. Measured at ~5.2K tokens for 58 documents, and paid only when the model opens it. Once it has, it never has to guess what exists or what a file is called.

It is a real skill like any you import — you will find it on the Skills page, marked **built-in**, delivered into each agent by the same links as the rest. What makes it Coffer's is that Coffer writes it: the folder is rewritten at every start and whenever the catalogue moves, so editing it has no lasting effect and deleting it is refused. Disabling it, or narrowing which agents it reaches, stays yours.

Nothing is pushed into a session. Knowledge is pulled; session-start delivery is [memory](/guide/memory)'s job, with its own ceiling and its own consent.

::: tip Coffer embeds nothing
Ranked semantic retrieval over a vector sidecar was built, shipped and then deliberately removed. What replaces conceptual recall is the model reading a catalogue, which works while the catalogue fits in context — into the hundreds of files. Literal matching is a placeholder, not a verdict.
:::

## The CLI

Everything above lives under one group, `coffer knowledge`:

| Area        | Commands                                     |
| ----------- | -------------------------------------------- |
| Collections | `collections` · `create`                     |
| Files       | `ls` · `read` · `write` · `delete` · `upload` |
| Curation    | `curate`                                     |

`--json` works on `collections`, `ls` and `read`; `curate` always prints its result as JSON, because the status is the answer. There is deliberately no `grep` or `search` command: the corpus is plain Markdown at a path the group's help names, so your own `grep` is already better than anything this group could wrap.

Deleting a collection is a Resource operation: `coffer resource delete knowledge <name>`. So is switching one off: `coffer resource disable knowledge <name>`.

## The REST surface

The daemon serves knowledge under `/api/v1/knowledge`. These routes are the *user's* surface, and there is nothing per-agent about them or about what an agent reaches: a collection is either enabled for everyone or served to nobody.

| Route                                                | Purpose                                      |
| ---------------------------------------------------- | -------------------------------------------- |
| `GET`/`POST` `/api/v1/knowledge/collections`         | List collections, each with its document and pending counts; create one. |
| `GET` `/api/v1/knowledge/tree?path=…`                | One level of one collection.                 |
| `GET`/`DELETE` `/api/v1/knowledge/file`              | Read a document; delete one.                 |
| `POST` `/api/v1/knowledge/material`                  | Submit new material to a collection.         |
| `POST` `/api/v1/knowledge/upload`                    | Convert a document and submit it as material. |
| `POST` `/api/v1/knowledge/collections/{uid}/curate`  | Run a curation pass now.                     |

A read answers with the file's absolute path and its containing folder's absolute path, so whatever you hand the answer to can open it directly.

There is no index, reindex, search or embedding-configuration route, and no per-agent reach route for this kind. Deleting a whole collection goes through the kind-agnostic resource route, `DELETE /api/v1/resources/{uid}` — there is no `DELETE /api/v1/knowledge/collections/{uid}`. There is no route that writes a document either: you edit one in your own editor, and it is live on the very next read.

## The MCP tool

Every connected MCP client gets exactly **one** built-in knowledge tool.

| Tool            | What it does                                                            |
| --------------- | ----------------------------------------------------------------------- |
| `coffer__write` | Submit new material to a named collection from a title, description and body. |

Writing is where an agent genuinely needs Coffer: the collection, the inbox, the frontmatter and the audit entry are Coffer's to decide, and it is the one place an invocation record still gets written. A write naming a collection that does not exist or is disabled is refused with the collections that *are* available — which turns a dead end into a correction for a model that reached for the tool without opening its skill.

There is no `coffer__list`, `coffer__grep`, `coffer__read`, `coffer__search` or `coffer__delete`. Reading is the agent's own `Read` and `Grep` against the paths its skill gave it; deleting is a person's action on the human surfaces.

Agents both read and write here: material one agent files becomes, after the next pass, part of what the next agent reads — which is the point of keeping this in Coffer rather than in any single agent's own store.

## In the web UI

Knowledge is one page under **Resources**. `/knowledge` lists your collections with a description, how many documents each holds and how much material is still waiting to be merged, and an on/off control; **New collection** creates one. The two counts are apart on purpose: pending material is exactly what an agent cannot read yet.

`/knowledge/:collection` opens one collection as **one tree** of documents, with the file you pick rendered read-only beside it. Every document offers open in your external editor, reveal in your file manager, and delete — naming the exact path first. The header carries **Upload** and a manual curation trigger that tells you when a pass is already in flight.

There is no search box on the page. The one input beside a tree narrows the names already on screen, client-side — retrieval here is reading a catalogue, not querying an index.

[Memory →](/guide/memory)
