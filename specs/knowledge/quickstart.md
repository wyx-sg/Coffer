# Quickstart — Knowledge Layer

Knowledge is a directory of Markdown files under
`~/.coffer/knowledge/<collection>/`, in two lanes. You and your agents write
**source material** into `sources/`; Coffer's own model folds it into **topic
documents** under `topics/`, and `topics/` is what an agent reads — with its own
`Read` and `Grep`, at an absolute path, through no tool of Coffer's. There is no
index, so what one of you writes the other sees as soon as the next pass lands
it. See [`spec.md`](./spec.md) and
[Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md).

## Make a collection first

Nothing auto-provisions. A **collection** is a top-level folder *and* one
`knowledge` Resource — you create it deliberately, and that is what makes it
something you can authorize per agent.

```bash
coffer knowledge create shopee -d "Internal systems — services, data plane, the chains between them."
coffer knowledge collections
```

`create` writes the directory *and both lanes*, registers the Resource, and puts
the `--description` into the collection's `README.md`. That README's first
paragraph is the collection's one-line description everywhere one appears, so you
change it later by editing the file.

Write the description as though an agent will read it, because one will: it is
what the delivered skill says this collection is *about*, and it is the only part
of this layer that sits in a model's context whether or not knowledge is ever
touched. A collection that describes itself as "notes" is a collection nothing
recognises.

Every enabled collection is served to every agent. Switching one off is the only
gate:

```bash
coffer resource disable knowledge:shopee
coffer resource enable knowledge:shopee
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
coffer resource delete knowledge:shopee
```

## Through an MCP client

**One tool: `coffer__write`.** There is no `list`, `grep`, `read`, `search` or
`delete`. Across 448 sessions after the corpus was built, no agent ever called
one of them and the skill describing them was never loaded once — a tool an agent
does not remember to call is not retrieval. Reading is now the agent's own
`Read` and `Grep`, at the absolute paths the delivered skill carries.

```text
coffer__write(collection="coffer",
              title="Release process",
              description="How this repo cuts a release, and what not to do.",
              body="Deploys via `make release`, never `git push --tags`.",
              folder="ops")          # optional, inside sources/
```

It takes no lane and no path: a write lands in that collection's `sources/`, and
which lane a file belongs in is not something a caller chooses. Write the fact
plainly — the next curation pass decides where it belongs and merges it with what
is already there, so you do not have to check whether it repeats something.
`folder` is optional filing inside `sources/`, nothing more.

An agent finds the corpus through `coffer-guide`, the skill Coffer generates for
itself and delivers into every agent's skills directory: its description names
Coffer's own tools and the subjects your collections cover, and its body is
Coffer's manual followed by the whole catalogue — every topic document's path,
title and description, plus the knowledge root. It is one skill for both, because
a description is resident in every session while a body is paid for only when a
model opens it. You will see it on the Skills page beside your own, marked
built-in: it can be disabled or scoped like any other, but not deleted or edited,
because Coffer rewrites it at every start. Reading is then just:

```text
Read  ~/.coffer/knowledge/shopee/topics/account/login-sessions.md
Grep  "account.session"  ~/.coffer/knowledge/shopee/topics/
```

No hook, no session injection, nothing written into an agent's own memory files.

## CLI

Eight commands, all thin HTTP shells over the daemon. Paths are relative to the
knowledge root and carry the lane, because the lane is part of where a file is:
`ls shopee` shows you the two lanes, and every path below one of them names it.

```bash
# Browse. `collections` shows both lane counts — sources with no topics means
# the collection has not been curated yet.
coffer knowledge collections
coffer knowledge ls shopee/sources                 # one level: folders + files
coffer knowledge ls shopee/topics/account --json
coffer knowledge read shopee/topics/account/login-sessions.md

# Write a source. The `sources/` segment is added for you.
coffer knowledge write -t "Release process" \
  -d "How this repo cuts a release, and what not to do." \
  -b "Deploys via \`make release\`, never \`git push --tags\`." \
  --in coffer --folder ops

# Delete one source. A topic document is refused: it is derived, and the next
# pass would put it back.
coffer knowledge delete coffer/sources/release-process.md

# Upload a document; it lands in sources/ with its original beside it.
coffer knowledge upload ./q3-review.pdf --collection shopee

# Curate one collection by hand (see below).
coffer knowledge curate shopee
coffer knowledge curate shopee --source shopee/sources/q3-review.md
```

`--json` works on `collections`, `ls` and `read`; `curate` always prints its
result as JSON, because the status is the answer.

**There is no `grep` and no `search` command.** The corpus is plain Markdown at a
path the group's own help names, so your own `grep` is already better than
anything this group could wrap — and unlike an agent, you are standing in a
shell.

## Write in your own tools

The filesystem is always an entrance to `sources/`. Drop a Markdown file in from
Finder, fix a wrong line in your editor, delete one that went stale — the sweep
notices within the minute by comparing the file's modification time with the
`coffer_ingested_at` stamp in its own frontmatter, and folds the change into the
topics. There is no import, no registration and no reindex.

A file you add by hand should carry the same frontmatter Coffer writes, or it
will curate with an empty title and description:

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

**Do not edit `topics/`.** Those files are generated and the next pass will
overwrite them. A correction goes into `sources/` as a note saying what is
actually true; curation carries it through, and where a source contradicts a
topic document the source wins.

## Get a document in from wherever you are

The filesystem is only an entrance while you are sitting at the machine, so there
is a second one for everything else. Upload a document and Coffer converts it to
Markdown, names the file from its title, fills in a description, and keeps the
bytes you sent as an ordinary visible file beside it in `sources/`:

```bash
coffer knowledge upload ./q3-review.pdf --collection shopee
coffer knowledge upload ./notes.docx --collection shopee --folder account
```

`POST /api/v1/knowledge/upload` is the same path (multipart: the file, plus
`collection` and an optional `folder`), and so is the **Upload** button on a
collection's page.

From your phone: forward the document to your Coffer channel and say which
collection it belongs in. The bot confirms the collection before it stores
anything, and stores nothing from anyone but the paired owner.

Supported inputs are whatever `markitdown` handles — PDF, .docx, .pptx, .xlsx,
HTML, EPUB — plus plain text, Markdown and CSV. Legacy `.doc`/`.ppt`, `.rtf` and
`.odt` are deliberately not among them: save as `.docx`/`.pptx` first. Anything
else is refused with its type named, and nothing half-converted is left behind —
including an image-only PDF, which converts without error into no text at all and
is refused for saying so.

Afterwards both files are ordinary sources, indistinguishable from what you put
there by hand.

## Curation

A bounded agentic pass over one collection: it reads `sources/` and writes
`topics/`, merging each new or changed source into whichever document owns that
subject and deduplicating against what is there. It cannot touch `sources/` at
all — that is what makes it safe to run unattended, and why there is no archive
of what it replaced. The material every topic is derived from is still on disk,
untouched, so deleting `topics/` entirely and re-running curation gives you back
a corpus carrying the same facts.

With no internal model configured (Settings → LLM connections) a pass is a clean
no-op reporting `no_model`, and it leaves the watermark unset — so the material
is curated the day you configure a connection rather than being silently skipped
forever.

```bash
coffer knowledge curate shopee
```

The web-UI equivalent is the **Curate** button. A background sweep also runs the
pass on an interval, and unlike the tidy pass it replaces it is **on by default**,
because it is the only path from a source to something an agent can read: an
installation where it never runs has an empty `topics/` lane forever. Each pass
is recorded in Coffer's audit log.

One pass sees one source in full, at most five candidate documents in full, and
the collection's whole catalogue of titles — and may make at most eight writes,
so a note can never trigger a corpus-wide rewrite. A write whose body names
another knowledge file is refused outright: topic paths move as the corpus is
reorganised, so a file name in prose is a link that rots. Documents name
subjects; the catalogue resolves subjects to paths, and the catalogue is
generated.

The switch is installation-wide and also names a machine, and the timer runs on
**that one only**. Two machines curating one corpus is the failure this prevents:
each merges the same material into a topic document, but into a *different* one,
git merges both cleanly, and you hold the same knowledge twice with nothing
reported as a conflict. With no owner chosen the switch means "here", which is
the right answer for a single machine. Passes also stand aside for sync: one
never overlaps a converge round, and never starts while a conflict or a pending
confirmation is outstanding. Only one pass per collection runs at a time — ask
for a second during one and it is refused rather than queued.

## Web UI

1. Sidebar → **Knowledge**. A collection opens as **two trees**: `sources/`,
   which is yours, and `topics/`, which is curation's.
2. Click a file in either to see it rendered **read-only**. The UI has no editor;
   the file and its containing folder each offer **open in external editor** and
   **reveal in file manager** (real OS actions performed by the local daemon;
   which editor opens is the global preferred-editor preference, spec ui-shell).
   A source also offers **delete**, naming the exact path first. A topic document
   offers neither — it is labelled as written by curation, and deleting one by
   hand would only last until the next pass.
3. **Upload** files a document into the collection in view, through the same
   conversion path the CLI and the channel use. **Curate** runs a pass now, and
   says so plainly if one is already in flight.

The page carries no search box of its own. The one input beside a tree narrows
the names already on screen, client-side.

## Where files live

```text
~/.coffer/
├── coffer.db                       # no knowledge tables at all — just the resources row per collection
└── knowledge/
    ├── shopee/
    │   ├── README.md               # first paragraph = the collection's description
    │   ├── sources/                # yours: hand-written notes, coffer__write, uploads
    │   │   ├── account/
    │   │   │   └── session-ownership.md
    │   │   ├── q3-review.pdf       # the bytes you sent, visible…
    │   │   └── q3-review.md        # …and the Markdown extracted from them
    │   └── topics/                 # curation's, and all an agent reads
    │       ├── account/
    │       │   └── login-sessions.md
    │       └── gateway-routing.md
    └── coffer/
        ├── README.md
        ├── sources/
        └── topics/
```

Coffer writes no hidden directory of its own any more. `.history/` is gone
because a topic document is no longer the only copy of what it says, and `.raw/`
is gone because the only thing hiding an uploaded original bought was keeping it
out of an index that no longer exists.

## Limits

- One pass: one source in full, at most five candidate documents, at most eight
  writes. A pass reports which bound stopped it.
- File names: a slug of the title, up to 80 characters, CJK kept as-is; a
  collision appends `-2`, `-3`, ….
- Catalogue size: no hard limit, but the design assumes a catalogue that fits in
  a skill body — measured at ~5.2K tokens for 58 documents.
- Upload: one file per call, with a size ceiling; a refusal names the limit, and
  a failed conversion leaves neither the Markdown nor the original behind.
