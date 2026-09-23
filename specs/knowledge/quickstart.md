# Quickstart — Knowledge Layer

Knowledge is a directory of Markdown files under
`~/.coffer/knowledge/<collection>/`: **one tree of documents per collection**,
which you and Coffer's own model write together. An agent reads it with its own
`Read` and `Grep`, at an absolute path, through no tool of Coffer's. New
knowledge — a note an agent writes down, a document you upload — arrives as
**material** in a hidden inbox, and Coffer's curation pass merges what is new in
it into the documents. There is no index, so an edit is live on the very next
read. See [`spec.md`](./spec.md) and
[Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md).

## Make a collection first

Nothing auto-provisions. A **collection** is a top-level folder *and* one
`knowledge` Resource — you create it deliberately, and that is what gives it a
lifecycle and an on/off switch.

```bash
coffer knowledge create shopee -d "Internal systems — services, data plane, the chains between them."
coffer knowledge collections
```

`create` writes the directory, registers the Resource, and puts the
`--description` into the collection's `README.md`. That README's first paragraph
is the collection's one-line description everywhere one appears, so you change
it later by editing the file. The README is not a document: it is never curated,
listed or counted.

Write the description as though an agent will read it, because one will: it is
what the delivered skill says this collection is *about*, and it is the only part
of this layer that sits in a model's context whether or not knowledge is ever
touched. A collection that describes itself as "notes" is a collection nothing
recognises.

Every enabled collection is served to every agent. Switching one off is the only
gate:

```bash
coffer resource disable knowledge shopee
coffer resource enable knowledge shopee
```

That gate decides what an agent is **told**, not what a process can open: the
skill Coffer delivers to every agent stops mentioning a disabled
collection — its subjects, its catalogue and its paths all go with it — but an
agent holding a shell can still read the directory. The per-agent form of this
was withdrawn: it withheld a name from a reader who already had the root, which
is not an authorization.

Deleting a collection goes through the Resource framework, not a knowledge
route — same lifecycle, audit and cascade as any other resource:

```bash
coffer resource delete knowledge shopee
```

## Through an MCP client

**One tool: `coffer__write`.** There is no `list`, `grep`, `read`, `search` or
`delete`. Across 448 sessions after the corpus was built, no agent ever called
one of them and the skill describing them was never loaded once — a tool an agent
does not remember to call is not retrieval. Reading is the agent's own `Read` and
`Grep`, at the absolute paths the delivered skill carries.

```text
coffer__write(collection="coffer",
              title="Release process",
              description="How this repo cuts a release, and what not to do.",
              body="Deploys via `make release`, never `git push --tags`.")
```

It takes no path and no folder: what it writes is **new material**, and where it
belongs is curation's decision. Write the fact plainly — the next pass merges it
into whichever document owns that subject, deduplicating against what is already
there, so you do not have to check whether it repeats something. The answer says
`pending` while the material waits in the inbox, or `written` with a document
path when no internal model is configured and it became a document on the spot.

An agent finds the corpus through `coffer-guide`, the skill Coffer generates for
itself and delivers into every agent's skills directory: its description names
Coffer's own tools and the subjects your collections cover, and its body is
Coffer's manual followed by the whole catalogue — every document's path, title
and description, plus the knowledge root. It is one skill for both, because a
description is resident in every session while a body is paid for only when a
model opens it. You will see it on the Skills page beside your own, marked
built-in: it can be disabled or scoped like any other, but not deleted or edited,
because Coffer rewrites it at every start. Reading is then just:

```text
Read  ~/.coffer/knowledge/shopee/account/login-sessions.md
Grep  "account.session"  ~/.coffer/knowledge/shopee/
```

An agent may also **edit** a document it has read, with its own file tools, the
way you would in your editor; the next sweep carries the edit into the rest of
the collection. What it cannot do is delete one — there is no agent-facing
delete. No hook, no session injection, nothing written into an agent's own memory
files.

## CLI

Eight commands, all thin HTTP shells over the daemon. Paths are relative to the
knowledge root and start with the collection.

```bash
# Browse. `collections` shows the document count and the material still
# waiting in the inbox to be merged.
coffer knowledge collections
coffer knowledge ls shopee                         # one level: folders + documents
coffer knowledge ls shopee/account --json
coffer knowledge read shopee/account/login-sessions.md

# Submit new knowledge. It is queued as material; curation merges it.
coffer knowledge write -t "Release process" \
  -d "How this repo cuts a release, and what not to do." \
  -b "Deploys via \`make release\`, never \`git push --tags\`." \
  --in coffer

# Delete a document — any document; it is your collection.
coffer knowledge delete shopee/gateway-routing.md

# Upload a document: converted to Markdown and submitted as material.
coffer knowledge upload ./q3-review.pdf --collection shopee

# Curate one collection by hand (see below).
coffer knowledge curate shopee
coffer knowledge curate shopee --document shopee/account/login-sessions.md
```

`--json` works on `collections`, `ls` and `read`; `curate` always prints its
result as JSON, because the status is the answer. `write` prints the document
path when the material was promoted on the spot, and otherwise says it is queued.

**There is no `grep` and no `search` command.** The corpus is plain Markdown at a
path the group's own help names, so your own `grep` is already better than
anything this group could wrap — and unlike an agent, you are standing in a
shell.

## Edit in your own tools

The tree is yours as much as curation's. Fix a wrong line in your editor, add a
section, write a new document from scratch, delete one that went stale — there is
no import, no registration and no reindex. The sweep notices an edit within the
minute by comparing the file's modification time with the `coffer_curated_at`
stamp in its own frontmatter, and a pass carries it through the rest of the
collection: a correction you made in one document reaches the others that said
the old thing. **Your edit stands** — the pass is instructed never to revert or
reword it.

A document you add by hand should carry the same frontmatter Coffer writes, or
it will be catalogued with an empty description:

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

Any other key you add — `tags:`, `reviewed_by:` — survives Coffer's rewrites of
the file.

## Get a document in from wherever you are

Upload a document and Coffer converts it to Markdown, takes a title from it,
fills in a description, and **submits the text as material**: curation appends
what is new in it to the collection's documents, the way a note from an agent
is. Neither the file you sent nor the extracted text is kept as a file of its
own — what the collection holds is the knowledge, merged, and the document was
only its carrier.

```bash
coffer knowledge upload ./q3-review.pdf --collection shopee
coffer knowledge upload ./notes.docx --collection shopee
```

`POST /api/v1/knowledge/upload` is the same path (multipart: the file plus
`collection`), and so is the **Upload** button on a collection's page.

From your phone: forward the document to your Coffer channel and follow it with
`/save <collection>`. It stores nothing from anyone but the paired owner.

Supported inputs are whatever `markitdown` handles — PDF, .docx, .pptx, .xlsx,
HTML, EPUB — plus plain text, Markdown and CSV. Legacy `.doc`/`.ppt`, `.rtf` and
`.odt` are deliberately not among them: save as `.docx`/`.pptx` first. Anything
else is refused with its type named, and nothing half-converted is submitted —
including an image-only PDF, which converts without error into no text at all and
is refused for saying so.

## Curation

A bounded agentic pass over one collection, one item at a time. The item is
either **inbox material** — merged into whichever document owns that subject,
or into a new one when none does, and then deleted from the inbox — or a
**document someone edited** since curation last saw it, whose edit is carried
outward into the documents that disagree with it. Where new material contradicts
a document, the newer statement wins and the superseded one stays legible as a
dated correction.

```bash
coffer knowledge curate shopee
```

The web-UI equivalent is the **Curate** button. A background sweep also runs
passes on an interval (a minute by default), and it is **on by default**,
because it is what turns material into documents an agent reads. Each sweep
drains the inbox first, oldest first, then edited documents — at most five
passes per collection per sweep. Each pass is recorded in Coffer's audit log.

With no internal model configured (Settings → LLM connections) there is nothing
to merge with, so material does not wait: a submission becomes a document of its
own at the collection root immediately, and a pass run then promotes whatever is
still in the inbox and reports `no_model` with the paths it promoted.

One pass sees one item in full, at most five candidate documents in full, and
the collection's whole catalogue of titles — and may make at most eight writes,
so a note can never trigger a corpus-wide rewrite. A write whose body names
another knowledge file is refused outright: document paths move as the corpus is
reorganised, so a file name in prose is a link that rots. Documents name
subjects; the catalogue resolves subjects to paths, and the catalogue is
generated.

The switch is installation-wide and also names a machine, and the timer runs on
**that one only**. Two machines curating one corpus is the failure this prevents:
each merges the same material into a document, but into a *different* one, git
merges both cleanly, and you hold the same knowledge twice with nothing reported
as a conflict. With no owner chosen the switch means "here", which is the right
answer for a single machine. Passes also stand aside for sync: one never
overlaps a converge round, and never starts while a conflict or a pending
confirmation is outstanding. Only one pass per collection runs at a time — ask
for a second during one and it is refused rather than queued.

## Web UI

1. Sidebar → **Knowledge**. The list shows each collection's documents and the
   material still waiting to be merged. A collection opens as **one tree** of
   its documents.
2. Click a document to see it rendered **read-only**. The UI has no editor; the
   file and its containing folder each offer **open in external editor** and
   **reveal in file manager** (real OS actions performed by the local daemon;
   which editor opens is the global preferred-editor preference, spec ui-shell),
   and every document offers **delete**, naming the exact path first.
3. **Upload** submits a document to the collection in view, through the same
   conversion path the CLI and the channel use. **Curate** runs a pass now, and
   says so plainly if one is already in flight.

The page carries no search box of its own. The one input beside the tree narrows
the names already on screen, client-side.

## Where files live

```text
~/.coffer/
├── coffer.db                       # no knowledge tables at all — just the resources row per collection
└── knowledge/
    ├── shopee/
    │   ├── README.md               # first paragraph = the collection's description
    │   ├── account/
    │   │   └── login-sessions.md   # documents: yours and curation's, read by agents
    │   ├── gateway-routing.md
    │   └── .inbox/                 # hidden: material waiting to be merged
    └── coffer/
        ├── README.md
        └── release-process.md
```

`.inbox/` is the one hidden directory Coffer writes, and each item leaves it the
moment a pass has merged it. `.history/` and `.raw/` stay gone.

## Limits

- One pass: one item in full, at most five candidate documents, at most eight
  writes. A pass reports which bound stopped it.
- One sweep: at most five passes per collection.
- File names: a slug of the title, up to 80 characters, CJK kept as-is; a
  collision appends `-2`, `-3`, ….
- Catalogue size: no hard limit, but the design assumes a catalogue that fits in
  a skill body — measured at ~5.2K tokens for 58 documents.
- Upload: one file per call, with a size ceiling; a refusal names the limit, and
  a failed conversion submits nothing.
