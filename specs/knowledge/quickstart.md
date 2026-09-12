# Quickstart — Knowledge Layer

> 中文版: [quickstart.zh.md](./quickstart.zh.md)

Knowledge is a directory of Markdown files under
`~/.coffer/knowledge/<collection>/`. An agent finds what it needs by reading a
generated catalogue and grepping, the way it navigates a codebase; you find it
by opening a folder. There is no index, so what one of you writes the other
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

Five built-in tools. No scope argument, no mode, no `top_k`: a call spans every
collection the agent is authorized for.

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

There is **no `coffer__search`**: with no ranked index behind it, it would be a
second name for `grep`.

The motion is catalogue-then-grep — descend to choose *which file*, grep to find
*which line*:

```text
coffer__list()                              # → shopee (48 files), coffer (4 files)
coffer__list(path="shopee")                 # → account/, gateway-routing.md, …
coffer__list(path="shopee/account")         # → titles + descriptions
coffer__read(path="shopee/account/session-ownership.md")

coffer__grep(pattern="account.session")     # when you know the literal string
coffer__grep(pattern="部署流程", collection="shopee")

coffer__write(title="Release process",
              description="How this repo cuts a release, and what not to do.",
              body="Deploys via `make release`, never `git push --tags`.",
              directory="coffer")
```

Agents learn the layer exists from the `coffer-knowledge` skill Coffer delivers
through its normal skill channel — no hook, no session injection, nothing
written into an agent's own memory files.

## CLI

Eight commands, all thin HTTP shells over the daemon. Paths are relative to the
knowledge root.

```bash
# Browse.
coffer knowledge collections                       # every collection
coffer knowledge ls shopee                         # one level: folders + files
coffer knowledge ls shopee/account --json
coffer knowledge read shopee/account/session-ownership.md

# Search the files themselves. There is no index; this is the search.
coffer knowledge grep "account.session"
coffer knowledge grep "部署流程" --in shopee        # great for CJK — no tokenizer
coffer knowledge grep "make release" --json

# Write. Exactly one of --in (create here) or --path (replace this).
coffer knowledge write -t "Release process" \
  -d "How this repo cuts a release, and what not to do." \
  -b "Deploys via \`make release\`, never \`git push --tags\`." \
  --in coffer
coffer knowledge write -t "Release process" -d "…" -b "…" --path coffer/release-process.md

# Delete one file.
coffer knowledge delete coffer/release-process.md
```

`--json` works on `collections`, `ls`, `read` and `grep`.

## Curate in your own tools

The filesystem is the ingestion surface. Drop a Markdown file into a collection
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

There is no upload endpoint and no format conversion. A PDF is not knowledge
until someone turns it into Markdown.

## Tidy

A bounded agentic pass over one collection: it merges duplicates and rewrites
them into coherent documents, copying every prior revision into the hidden
`.history/` first. With no internal model configured (Settings → LLM
connections) it is a clean no-op.

```bash
coffer knowledge organize shopee
```

The web-UI equivalent is the **Tidy** button. A background worker can also run
the pass on an interval, but it is **off by default** and installation-wide —
turn it on deliberately in Settings → Engine, because it rewrites files you and
your agents manage together with no diff to approve. Each pass is recorded in
Coffer's audit log.

## Web UI

1. Sidebar → **Knowledge**. One tree, no tabs: the collections, then whatever
   you nested inside them.
2. Click a file to see it rendered **read-only**. The UI has no editor; the
   file and its containing folder each offer **open in external editor** and
   **reveal in file manager** (real OS actions performed by the local daemon;
   which editor opens is the global preferred-editor preference, spec
   ui-shell). Your edit takes effect immediately — there is nothing to
   reconcile.

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
    │   └── .history/               # revisions the tidy pass replaced (hidden)
    └── coffer/
        ├── README.md
        └── release-process.md
```

`.history/` is dot-prefixed on purpose: ripgrep skips hidden entries, so an
archived revision never comes back beside the live file.

## Limits

- `grep` matches: 1–500, default 200. The response flags `truncated`.
- File names: a slug of the title, up to 80 characters, CJK kept as-is; a
  collision appends `-2`, `-3`, ….
- Catalogue size: no hard limit, but the design assumes a catalogue that fits
  in an agent's context — comfortable into the hundreds of files.
