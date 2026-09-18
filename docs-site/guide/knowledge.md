# Knowledge

**Knowledge** is Coffer's one store of everything your agents should know — what you or an agent wrote down, and the documents you uploaded. It is a directory of Markdown files under `~/.coffer/knowledge/`, and those files are the whole of it. There is no index: no vector store, no full-text tables, nothing in `coffer.db` to keep in step with the disk. A file you edited in your own editor, a file an agent just wrote, and a file `git` pulled in all look the same to Coffer, because there is nothing in between.

What the layer adds on top of the directory is **curation**: you write things down as they come to you, and Coffer's own model folds each one into a document worth reading. So there are two lanes — what people contribute, and what an agent reads — and the second is derived from the first.

## Collections

A collection is a resource named `knowledge:<name>` and the directory `~/.coffer/knowledge/<name>/`. The two appear together, and only because you said so — nothing creates a collection as a side effect of a read or a write, so a name you typo'd is an error rather than a new, silently empty collection.

```bash
coffer knowledge create handbook --description "Company onboarding docs"
coffer knowledge collections
coffer resource delete knowledge:handbook     # collection lifecycle is a Resource concern
```

A collection describes itself in its own `README.md`, which sits at the collection root outside both lanes. That first paragraph is the description — it is read off disk on every listing, never copied into the database, and it is what the skill Coffer delivers to your agents draws on. A collection that fails to describe itself is a collection an agent never recognises.

A collection carries **no per-agent reach**: every enabled collection is served to every agent, and switching one off is the only way to take it out of what Coffer serves.

```bash
coffer resource disable knowledge:handbook
coffer resource enable knowledge:handbook
```

It could once be activated for some agents and not others. That was withdrawn, because it never authorized anything: what Coffer hands an agent is a catalogue of absolute paths into a directory that agent can already grep, so leaving a collection out of one agent's catalogue prevented a mistaken read at best and nothing at all at worst. Switching a collection off is a **delivery** gate for the same reason — a disabled collection is one no skill names, not one no process can open.

## The two lanes

```
~/.coffer/knowledge/handbook/
├── README.md          # what this collection is for
├── sources/           # what you and your agents contribute
└── topics/            # what curation derives, and what agents read
```

The division means exactly one thing: **who may write here**. `sources/` has three entrances — a person with their own editor, an upload, and `coffer__write` — and curation never touches it. `topics/` has one writer, the curation pass, and no other surface may write, move or delete a file in it.

**Sources are the truth; topics are derived.** Delete `topics/` and re-run curation and you get a corpus carrying the same facts. That inversion is what makes an unattended rewriter safe to run: the thing being rewritten is never the only copy. It is also why the lanes are directories rather than a frontmatter key — "who may write here" is the one property a key inside a file cannot carry.

Below `sources/` you nest folders however you like, and Coffer assigns none of that structure any meaning. The nesting under `topics/` is curation's own, and it may create and remove directories there.

Every Markdown file in either lane carries frontmatter with `title`, `description`, `actor` and timestamps. A file's **path is its identity** — names are readable slugs derived from the title, and there is no id anywhere. A source additionally picks up `coffer_ingested_at` once curation has consumed it: Coffer's watermark, compared against the file's own modification time, which is how a sweep knows what it still owes without any state file. Coffer writes no hidden directories of its own.

## Writing a source

```bash
coffer knowledge write --in handbook \
  --title "Package manager" \
  --description "Which package manager every repo here uses, and why" \
  --body "Prefer pnpm over npm in all repos."

coffer knowledge ls handbook/sources          # one level of the lane
coffer knowledge read handbook/sources/package-manager.md
coffer knowledge delete handbook/sources/package-manager.md
```

A write is stored verbatim — no LLM, no conversion, no indexing step — and it always lands in `sources/`. You never spell that segment: which lane a write goes to is not something a surface gets to choose. `--folder` nests it if you want.

Dropping a Markdown file into `sources/` with any editor is an equally complete way to add knowledge. Nothing has to be imported or registered; the next sweep notices the file by its modification time.

Deleting is a person's action, and only in `sources/`. A topic document has no delete: it is generated, and the answer to a wrong one is a new source saying what is actually true.

## Uploading documents

Hand Coffer a file in any format and it converts it to Markdown and files the result in `sources/`, keeping the original beside it.

```bash
coffer knowledge upload ./onboarding.pdf --collection handbook
coffer knowledge upload ./notes.docx --collection handbook --folder onboarding
```

- Conversion covers what [markitdown](https://github.com/microsoft/markitdown) handles — pdf, docx, pptx, xlsx, html and more — plus plain text and CSV. An unsupported type is refused by name, never stored half-converted, and a failed conversion leaves neither file behind.
- Both files land in `sources/`: the original under its own name, byte-identical to what you sent, and the extracted Markdown beside it. A Markdown or text upload is its own original, so it lands once rather than twice.
- One file per call, a 20 MB ceiling, and a refusal that names the limit.
- The description is optional input but never optional output. With no internal model connection configured, Coffer draws one from the document's own opening prose rather than leaving the catalogue entry blank.

A document sent to a Coffer channel rides the same entrance, so your phone and the Knowledge page are two ends of one path into `sources/`.

## Curation

A collection accumulates the way notes do: the same fact written twice from two sessions, one file that grew until it covers four subjects, a correction that contradicts what is already there. Nothing about that is wrong at write time, which is why writing stays dumb. The sorting out is a **curation pass** — a bounded agentic rewrite, driven by your internal model connection, that reads one source and folds it into `topics/`.

A pass is deliberately small:

- It sees **one source in full**, at most **five** candidate topic documents in full, and the collection's whole catalogue of titles and descriptions. Candidates are found by matching distinctive strings from the source against `topics/`; the catalogue is there so the model can conclude that none of them is the right home and open a new document instead.
- It may make at most **eight writes**, so one source can never trigger a corpus-wide rewrite.
- It **preserves every fact it is shown**. Merging integrates rather than regenerates, and a document may only be retired when the same pass has written its content somewhere else.
- Where a source contradicts a topic document, the **source wins**, and the result keeps the superseded statement legible as a dated correction. Knowledge is about a world that changes, and when it changed is itself worth keeping.
- A topic document may not name another knowledge file by path. That is enforced at the write rather than asked for in a prompt, because a hand-maintained map of generated paths is what rotted last time: 343 of 398 cross-references in this corpus had been broken by renames the prose never saw.

Passes run when material changes — immediately for the entrances Coffer serves itself, and on an interval sweep that finds files you changed out of band. Run one by hand whenever you want:

```bash
coffer knowledge curate handbook
coffer knowledge curate handbook --source handbook/sources/package-manager.md
```

The answer is a status: `ok`, `up_to_date`, `no_model` when no internal connection is configured, `too_large`, or `failed`. With no connection the pass is a clean no-op — no topic written, no watermark set, nothing created. Only one pass per collection runs at a time, whoever started it; a second trigger is refused rather than queued.

Two switches govern the unattended sweep, and both are read on every tick: whether it is on, and which single machine owns it. A vault that spans machines must curate on exactly one of them, because two machines rewriting the same files produce two different documents that git would merge as two additions. It defaults **on**, because curation is the only path from a source to something an agent reads.

## How an agent reads it

**There is no retrieval tool, and that is the design.** An audit of 448 Claude Code sessions after this corpus was built found that the delivered skill had never once been loaded and that no knowledge tool had ever been called. A tool an agent does not remember to call is not retrieval — and every agent Coffer supports already has `Read` and `Grep`, which need no remembering. So the layer's whole job is to put the right absolute paths in front of the model.

It does that with **Coffer's own skill**, `coffer-guide` — one skill carrying both Coffer's manual and this catalogue, because a skill's description is resident in every session while its body costs nothing until a model opens it:

- Its **frontmatter description** names Coffer's own tools and the subjects your collections cover, in their READMEs' own words. That line is the only part of this layer always in a model's context, so it carries specifics a model can match — the version it replaces described the layer instead, and across those 448 sessions no model ever recognised it.
- Its **body** is Coffer's manual first, then the knowledge root and, for every topic document, its path, title and description. Measured at ~5.2K tokens for 58 documents, and paid only when the model opens it. Once it has, it never has to guess what exists or what a file is called.

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

Deleting a collection is a Resource operation: `coffer resource delete knowledge:<name>`. So is switching one off: `coffer resource disable knowledge:<name>`.

## The REST surface

The daemon serves knowledge under `/api/v1/knowledge`. These routes are the *user's* surface, and there is nothing per-agent about them or about what an agent reaches: a collection is either enabled for everyone or served to nobody.

| Route                                                | Purpose                                      |
| ---------------------------------------------------- | -------------------------------------------- |
| `GET`/`POST` `/api/v1/knowledge/collections`         | List collections; create one.                |
| `GET` `/api/v1/knowledge/tree?path=…`                | One level of one lane.                       |
| `GET`/`PUT`/`DELETE` `/api/v1/knowledge/file`        | Read a file from either lane; write a source; delete a source. |
| `POST` `/api/v1/knowledge/upload`                    | Convert a document and file it.              |
| `POST` `/api/v1/knowledge/collections/{name}/curate` | Run a curation pass now.                     |

A read answers with the file's absolute path and its containing folder's absolute path, so whatever you hand the answer to can open it directly.

There is no index, reindex, search or embedding-configuration route, and no per-agent reach route for this kind. Deleting a whole collection goes through the kind-agnostic resource route, `DELETE /api/v1/resources/knowledge/{name}` — there is no `DELETE /api/v1/knowledge/collections/{name}`.

## The MCP tool

Every connected MCP client gets exactly **one** built-in knowledge tool.

| Tool            | What it does                                                            |
| --------------- | ----------------------------------------------------------------------- |
| `coffer__write` | File a source in a named collection from a title, description and body. |

Writing is where an agent genuinely needs Coffer: the collection, the lane, the frontmatter and the audit entry are Coffer's to decide, and it is the one place an invocation record still gets written. A write naming a collection that does not exist or is disabled is refused with the collections that *are* available — which turns a dead end into a correction for a model that reached for the tool without opening its skill.

There is no `coffer__list`, `coffer__grep`, `coffer__read`, `coffer__search` or `coffer__delete`. Reading is the agent's own `Read` and `Grep` against the paths its skill gave it; deleting is a person's action on the human surfaces.

Agents both read and write here: a source one agent files becomes, after the next pass, part of what the next agent reads — which is the point of keeping this in Coffer rather than in any single agent's own store.

## In the web UI

Knowledge is one page under **Resources**. `/knowledge` lists your collections with a description, a count for each lane and an on/off control, and **New collection** creates one. The two lanes are counted apart on purpose: they answer different questions — how much you have contributed, and how much of it an agent can read today.

`/knowledge/:collection` opens one collection as **two trees**, `sources/` and `topics/`, with the file you pick rendered read-only beside them. A source offers delete — naming the exact path first — plus open in your external editor and reveal in your file manager. A topic document offers none of those and is labelled as written by curation. The header carries **Upload** and a manual curation trigger that tells you when a pass is already in flight.

There is no search box on the page. The one input beside a tree narrows the names already on screen, client-side — retrieval here is reading a catalogue, not querying an index.

[Memory →](/guide/memory)
