# Quickstart — Memory (Shared Agent Memory)

> 中文版: [quickstart.zh.md](./quickstart.zh.md)

> **Historical — 2026-09-10.** Spec knowledge (Knowledge Base) and spec knowledge (Memory)
> merged into one **Knowledge Layer** on this date. [`spec.md`](./spec.md) is the
> authority for the merged model — one `knowledge` kind, three scopes, one
> storage root `~/.coffer/knowledge/<scope>/`, six `coffer__*` tools. This
> document records the design as it stood before that merge; where it says
> "memory face", "`memory` kind", `~/.coffer/memory/` or `/api/v1/memory_stores`,
> read the merged equivalents in `spec.md`. The commands and tool names below
> have been updated to the merged surface, so they are runnable as written. The
> folder name `specs/knowledge/` is likewise historical: it is the spec id every
> inbound link and the acceptance audit key on.

Memory is the **memory face** of Coffer's unified knowledge substrate. Facts are markdown files (the source of truth) shared across every agent — read and written **only over MCP** (Coffer keeps its own canonical format and does not touch agents' native memory files). No LLM runs at write time; the agent writes a clean fact.

## Through an MCP client (the primary surface)

Six built-in tools appear (no store reference needed — scope is resolved from the agent's working directory):

- `coffer__search(query, scope?, top_k?)` — ranked search over a scope's notes AND its uploaded documents at once.
- `coffer__grep(pattern, scope?, max_matches?)` — literal/regex match over every Markdown file in a scope.
- `coffer__read(id, scope?)` — read one item (note or document) in full.
- `coffer__list(scope?, all?, limit?)` — browse one scope's contents, or `all=true` for the catalogue of every scope.
- `coffer__write(text, title?, description?, filename?, id?, scope?)` — record a note, store a document (`filename`), or rewrite an existing item (`id`).
- `coffer__delete(id, scope?)` — delete one note or document.

A write lands in the scope's `notes/` lane directly — there is no inbox to drain
and no handoff lane, so nothing has to be filed anywhere before it can be found.

```text
# Inside a git project, the agent records a project fact:
coffer__write(text="This repo deploys via `make release`, never git push --tags.",
              title="Release process")

# A personal preference, available everywhere:
coffer__write(text="Prefers tabs over spaces.", title="Indentation", scope="global")

# Later — possibly a different agent — searches:
coffer__search(query="how do we deploy?")
```

`search` lazily reindexes the scope directory on every call, so edits made by another agent (over MCP), by the user in the Coffer UI, or directly on disk are visible immediately.

## CLI

The CLI addresses scopes by NAME as a positional argument — `global`, `project-<ulid>`, or a named collection (`global` and per-project scopes are auto-provisioned; `coffer knowledge list` shows what exists). There are no `--scope` flags.

```bash
# See the scopes (one global + one per project + any named collections), then inspect one.
coffer knowledge list
coffer knowledge describe global

# Write an entry into a scope (actor=user).
coffer knowledge remember project-01J… "API base path is /api/v2."
coffer knowledge remember global "Prefers tabs over spaces."

# List entries / get one.
coffer knowledge entries project-01J…
coffer knowledge entries global --json
coffer knowledge get global <entry-id>

# Retrieve from a scope.
coffer knowledge recall project-01J… "deployment"
coffer knowledge recall project-01J… "deployment" --top-k 3 --json
coffer knowledge search project-01J… "deployment"     # passage search, documents included
coffer knowledge grep global "部署流程"                 # exact/regex over the Markdown files — great for CJK

# Edit, delete, clear a scope (scope preserved).
coffer knowledge edit-entry global <entry-id> "API base path is /api/v3."
coffer knowledge forget global <entry-id>
coffer knowledge clear project-01J… --yes
```

`--json` works on every read command above. There is no `--mode` flag: retrieval mode is an internal engine detail ([Retrieval Mode Is Internal](../../docs/decisions/retrieval-mode-is-internal.md)) — the engine resolves the scope's own strategy (`hybrid` when the scope lists vector, else `keyword`) and falls back to `keyword` internally, unflagged, when no embedding provider is configured. `coffer knowledge grep` is real — ripgrep over the Markdown files, no index, no tokenizer, so it works where FTS5 cannot (e.g. CJK).

### Tidying the notes lane

A scope's notes are tidied on a schedule: a background worker runs one catch-up
pass at daemon boot and then on an interval, merging duplicate notes and
rewriting them into topic documents. Before any overwrite or merge it copies the
prior revision into the hidden `.history/`, so an unattended rewrite is
always recoverable. With no internal model configured (Settings → LLM
connections) the pass is a no-op.

To run one by hand:

```bash
coffer knowledge organize project-01J…    # one tidy pass over that scope's notes/
```

The web-UI equivalent is the **Tidy** button in the scope's header. Each pass
records a row in Coffer's audit log — there is no per-scope changelog file.

## Web UI

1. Sidebar → **Memory**. The page shows a table of all scopes (the global scope plus one per project — auto-provisioned — and any named collections). The Notes column counts what has been written into each.
2. Click a row to open the scope's detail page.
3. The detail page has **two tabs, Documents and Notes**, with one filter box above the tree that matches filenames as you type — client-side, no button, no request. Server retrieval lives where it belongs: `coffer__search` for agents, `coffer knowledge recall` for the CLI.
4. Click an item to expand a **read-only** render (the UI does not edit note text in-app). Each file and its containing folder offer **open in external editor** and **reveal in file manager** (real OS actions, performed by the local daemon); which editor opens is the global preferred-editor preference (see spec ui-shell). Correct a note by opening it in your own editor — the next search picks up the change via lazy reindex-on-read.
5. The header keeps the title, the rename pencil and the project path. **Upload** and **Tidy** are the two buttons; Settings / Check sources / Reindex sit behind an overflow menu. A warning appears only when a document is degraded.

Every write — agent (MCP), CLI, or REST — reindexes and audits; the web UI writes only by uploading a document or running a tidy pass. There is no derived `MEMORY.md` and no `INDEX.md`: the markdown files under `notes/` and `docs/` are the source of truth (Files as Truth).

## Optional: vector recall

Default retrieval is keyword + grep — zero config, offline, language-agnostic. Embedding is configured **installation-wide**, not per scope: set it once in the web UI (**Settings → Engine → Embedding**, i.e. `PUT /api/v1/embedding/config`); there is no CLI for it. That card is two pickers — a model provider, then one of its `embedding`-type models — the same shape as the internal-engine card above it; there is no add-a-model form and no key field. The config **names a connection** — one of the LLM connections you already configured — plus a model on it; the protocol, base URL and API key are resolved from that connection, so the embedding settings hold no `base_url`, no `credential_ref` and no key of their own. A scope then opts in by listing `vector` in its retrieval modes:

```bash
# the connection already holds the key; add one on Model providers first
coffer knowledge configure project-01J… --enable-vector
```

Naming a connection that does not exist, an `anthropic` connection (no embedding API), a connection that curates models but none of modality `embedding`, or a model the connection does not curate is refused with a 422 that says which. A connection curating no models at all is unrestricted, so the model id you type is taken at its word. `POST /api/v1/embedding/test` takes `{connection, model}` and reports the vector dimension without persisting anything. With no connection named, the config is inactive and retrieval degrades to keyword/grep.

`coffer knowledge configure <name>` PATCHes the scope's config; the other knobs are `--max-entry-chars`, `--chunk-size`, `--chunk-overlap`, and `--auto-update-sources/--no-auto-update-sources`. Enabling vector re-indexes the scope's existing content. A new named collection is born vector-enabled and the create-collection dialog no longer asks: which index a scope carries is an implementation detail, not a question to put to the user at creation time.

For bilingual content, a local connection (Ollama with `bge-m3`) or a cloud model that embeds Chinese well is recommended. The embedding model is mutable — changing it re-embeds every scope that lists a vector mode. With no embedding config, a vector-enabled scope falls back to keyword internally, with no per-query flag.

## Where files live

```
~/.coffer/
├── coffer.db                                  # SQLite — rebuildable index (documents, chunks, FTS5, vec, audit)
└── memory/
    ├── global/
    │   ├── notes/                             # what someone wrote (coffer__write lands here)
    │   │   ├── prefers-tabs.md                # per-note file = truth
    │   │   └── .history/                      # pre-rewrite copies kept by the tidy pass (hidden)
    │   ├── docs/                              # uploaded documents, normalized to markdown
    │   └── .raw/                              # the uploaded originals (hidden)
    └── projects/<project-ulid>/
        ├── notes/deploy-via-make-release.md
        ├── docs/
        └── .raw/
```

Two lanes: `notes/` for anything a person or an agent wrote, `docs/` for anything uploaded. `.history/` and `.raw/` are hidden on purpose — ripgrep skips them, so `coffer__grep` never returns an archived revision or an original alongside the live file. The markdown files are the source of truth; `coffer.db` can be rebuilt from them at any time.

## Limits

- Entry text: 1–8192 chars (configurable per scope up to 32 768, via `--max-entry-chars`).
- Search `top_k`: 1–20 (default 5).
- Scope: `global`, a `project-<ulid>` scope, or a named collection — omitted on a tool call, it resolves from the agent's cwd (falling back to `global` outside a project).
