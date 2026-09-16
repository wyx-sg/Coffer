# Quickstart — Knowledge Layer

Knowledge is a directory of Markdown files under
`~/.coffer/knowledge/<collection>/`. An agent finds what it needs by reading a
generated catalogue and grepping, the way it navigates a codebase — or by
searching a distinctive phrase and getting back the files that hold it; you find
it by opening a folder. There is no index, so what one of you writes the other
sees immediately. See [`spec.md`](./spec.md) and
[Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md).

## Make a collection first

Nothing auto-provisions. A **collection** is a top-level folder *and* one
`knowledge` Resource — you create it deliberately, and that is what makes it
something you can authorize per agent.

```bash
coffer knowledge create shopee -d "Internal systems — services, data plane, the chains between them."
coffer knowledge collections
```

`create` writes the directory, registers the Resource, and puts the
`--description` into the collection's `README.md`. The catalogue's one-line
description of a collection is always that README's first paragraph, so you can
change it later by editing the file.

Only the agents a collection is scoped to can see it:

```bash
coffer scope set knowledge:shopee --agents claude_code
coffer scope show knowledge:shopee
coffer scope clear knowledge:shopee          # back to every agent
```

Deleting a collection goes through the Resource framework, not a knowledge
route — same lifecycle, audit and cascade as any other resource:

```bash
coffer resource delete knowledge:shopee
```

## Through an MCP client (the primary surface)

Six built-in tools. No scope argument, no mode, no `top_k`: a call spans every
collection the agent is authorized for. Upload is deliberately not one of them —
a document enters through a human surface.

- `coffer__list(path?)` — the catalogue, **one level at a time**. With no
  argument it names every collection you may read, each with its description
  and file count. With a path it returns that directory's immediate
  subdirectories and files, each file with its `title` and `description`.
- `coffer__grep(pattern, collection?, max_matches?)` — ripgrep over the files,
  literal or regex, returning file, line number and matching line. No
  tokenizer, so CJK matches like anything else.
- `coffer__read(path)` — one file in full, plus its absolute path.
- `coffer__write(title, description, body, directory | path)` — create a file
  in `directory` (the name is slugified from `title`), or replace the file at
  `path`. Exactly one of the two.
- `coffer__delete(path)` — remove a file from disk.
- `coffer__search(query)` — the same literal matcher `grep` uses, reported a
  **file** at a time rather than a line at a time: each hit is a path, its
  `title` and `description`, and the lines that matched. Matching is literal,
  so give it a distinctive word or an exact phrase, not a question in your own
  words (FR-016).

The motion is catalogue-then-grep — descend to choose *which file*, grep to find
*which line*:

```text
coffer__list()                              # → every collection, with its
                                            #   description and file count
coffer__list(path="shopee")                 # → account/, gateway-routing.md, …
coffer__list(path="shopee/account")         # → titles + descriptions
coffer__read(path="shopee/account/session-ownership.md")

coffer__grep(pattern="account.session")     # when you know the literal string
coffer__grep(pattern="部署流程", collection="shopee")

coffer__search(query="account.session")     # skip the descent: which FILES
                                            #   contain it, with their titles

coffer__write(title="Release process",
              description="How this repo cuts a release, and what not to do.",
              body="Deploys via `make release`, never `git push --tags`.",
              directory="coffer")
```

Agents learn the layer exists from the `coffer-knowledge` skill Coffer delivers
through its normal skill channel — no hook, no session injection, nothing
written into an agent's own memory files.

## CLI

Ten commands, all thin HTTP shells over the daemon. Paths are relative to the
knowledge root.

```bash
# Browse.
coffer knowledge collections                       # every collection
coffer knowledge ls shopee                         # one level: folders + files
coffer knowledge ls shopee/account --json
coffer knowledge read shopee/account/session-ownership.md

# Search the files themselves. There is no index; this is the search.
# `grep` reports a line at a time, `search` a file at a time.
coffer knowledge grep "account.session"
coffer knowledge grep "部署流程" --in shopee        # great for CJK — no tokenizer
coffer knowledge grep "make release" --json
coffer knowledge search "account.session"          # the files, with their
                                                   #   title and description

# Write. Exactly one of --in (create here) or --path (replace this).
coffer knowledge write -t "Release process" \
  -d "How this repo cuts a release, and what not to do." \
  -b "Deploys via \`make release\`, never \`git push --tags\`." \
  --in coffer
coffer knowledge write -t "Release process" -d "…" -b "…" --path coffer/release-process.md

# Delete one file.
coffer knowledge delete coffer/release-process.md

# Upload a document; it lands as Markdown with its original kept aside.
coffer knowledge upload ./q3-review.pdf --collection shopee

# Tidy one collection (see below).
coffer knowledge tidy shopee
```

`--json` works on `collections`, `ls`, `read`, `grep` and `search`.

## Curate in your own tools

The filesystem is always an entrance. Drop a Markdown file into a collection
from Finder, fix a wrong line in your editor, delete one that went stale —
every change is live for the next call with no import, no reindex and nothing
to reconcile, because the file **is** the knowledge.

A file you add by hand should carry the same frontmatter Coffer writes, or it
will show up in the catalogue with an empty title and description:

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

## Get a document in from wherever you are

The filesystem is only an entrance while you are sitting at the machine, so
there is a second one for everything else. Upload a document and Coffer converts
it to Markdown, names the file from its title, fills in a description, and keeps
the bytes you sent under the collection's hidden `.raw/` in case the conversion
needs redoing:

```bash
coffer knowledge upload ./q3-review.pdf --collection shopee
coffer knowledge upload ./notes.docx --collection shopee --directory account
```

`POST /api/v1/knowledge/upload` is the same path (multipart: the file, plus
`collection` and an optional `directory`), and so is the **Upload** button on a
collection's page.

From your phone: forward the document to your Coffer channel and say which
collection it belongs in. The bot confirms the collection before it stores
anything, and stores nothing from anyone but the paired owner.

Supported inputs are whatever `markitdown` handles — PDF, .docx, .pptx, .xlsx,
HTML, EPUB — plus plain text, Markdown and CSV. Legacy `.doc`/`.ppt`, `.rtf` and
`.odt` are deliberately not among them: save as `.docx`/`.pptx` first. Anything
else is refused with its type named, and nothing half-converted is left behind:
one file per call, a size ceiling, and a refusal that says what the limit is.

Afterwards it is an ordinary file in a collection, indistinguishable from one you
wrote by hand.

## Tidy

A bounded agentic pass over one collection: it merges duplicates and rewrites
them into coherent documents, copying every prior revision into the hidden
`.history/` first. With no internal model configured (Settings → LLM
connections) it is a clean no-op.

```bash
coffer knowledge tidy shopee
```

The web-UI equivalent is the **Tidy** button. A background worker can also run
the pass on an interval, but it is **off by default** and installation-wide —
turn it on deliberately in Settings, because it rewrites files you and
your agents manage together with no diff to approve. Each pass is recorded in
Coffer's audit log.

Once your vault converges with a sync remote, that switch also names a machine,
and the timer runs on **that one only**. Two machines tidying one corpus is the
failure this prevents: each merges the same pair of notes into a topic document,
but into a *different* one, git merges both cleanly, and you end up holding the
same knowledge twice with nothing reported as a conflict. With no owner chosen
the switch means "here", which is the right answer for a single machine. Passes
also stand aside for sync: one never overlaps a converge round, and never starts
while a conflict or a pending confirmation is outstanding. Only one pass per
collection runs at a time — click **Tidy** during one and it is refused rather
than queued.

## Web UI

1. Sidebar → **Knowledge**. One tree, no tabs: the collections, then whatever
   you nested inside them.
2. Click a file to see it rendered **read-only**. The UI has no editor; the
   file and its containing folder each offer **open in external editor** and
   **reveal in file manager** (real OS actions performed by the local daemon;
   which editor opens is the global preferred-editor preference, spec
   web-ui). Your edit takes effect immediately — there is nothing to
   reconcile.
3. **Upload** files a document into the collection in view, through the same
   conversion path the CLI and the channel use.

The page carries no search box of its own. The one input beside the tree narrows
the names already on screen, client-side; reading the files themselves is what
`search` and `grep` are for, and their callers are the agents' tools and the
CLI.

## Where files live

```text
~/.coffer/
├── coffer.db                       # no knowledge tables at all — just the resources row per collection
└── knowledge/
    ├── shopee/
    │   ├── README.md               # first paragraph = the collection's description
    │   ├── account/
    │   │   └── session-ownership.md
    │   ├── gateway-routing.md
    │   ├── .history/               # revisions the tidy pass replaced (hidden)
    │   └── .raw/                   # originals of uploaded documents (hidden)
    └── coffer/
        ├── README.md
        └── release-process.md
```

Both hidden directories are dot-prefixed on purpose: the catalogue, `grep` and
`search` all skip hidden entries, so an archived revision never comes back
beside the live file and a PDF never comes back beside the Markdown made from
it.

## Limits

- `grep` matches: 1–500, default 200. The response flags `truncated`.
- File names: a slug of the title, up to 80 characters, CJK kept as-is; a
  collision appends `-2`, `-3`, ….
- Catalogue size: no hard limit, but the design assumes a catalogue that fits
  in an agent's context — comfortable into the hundreds of files.
- Upload: one file per call, with a size ceiling; a refusal names the limit, and
  a failed conversion leaves neither a Markdown file nor a `.raw/` original.
