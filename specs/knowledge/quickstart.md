# Quickstart — Memory (Shared Agent Memory)

> 中文版: [quickstart.zh.md](./quickstart.zh.md)

> **Historical — 2026-09-10.** The Knowledge Base and Memory specs merged into
> one **Knowledge Layer** on this date. [`spec.md`](./spec.md) is the
> authority for the merged model — one `knowledge` kind, three scopes, one
> storage root `~/.coffer/knowledge/<scope>/`, eight `coffer__*` tools. This
> document records the design as it stood before that merge; where it says
> "memory face", "`memory` kind", `~/.coffer/memory/` or `/api/v1/memory_stores`,
> read the merged equivalents in `spec.md`. The commands and tool names below
> have been updated to the merged surface, so they are runnable as written. The
> folder name `specs/knowledge/` is likewise historical: it is the spec id every
> inbound link and the acceptance audit key on.

Memory is the **memory face** of Coffer's unified knowledge substrate. Facts are markdown files (the source of truth) shared across every agent — read and written **only over MCP** (Coffer keeps its own canonical format and does not touch agents' native memory files). No LLM runs at write time; the agent writes a clean fact.

## Through an MCP client (the primary surface)

Eight built-in tools appear (no store reference needed — scope is resolved from the agent's working directory):

- `coffer__search(query, scope?, top_k?)` — ranked search over a scope's written entries AND its ingested documents at once.
- `coffer__grep(pattern, scope?, max_matches?)` — literal/regex match over every Markdown file in a scope.
- `coffer__read(id, scope?)` — read one item (entry or document) in full.
- `coffer__list(scope?, all?, limit?)` — browse one scope's contents, or `all=true` for the catalogue of every scope.
- `coffer__write(text, title?, description?, filename?, id?, scope?)` — record an entry, store a document (`filename`), or rewrite an existing item (`id`).
- `coffer__delete(id, scope?)` — delete one entry or document.
- `coffer__set_handoff(body)` — save the current working state for this project + branch.
- `coffer__resume()` — return the saved working-state handoff for this project + branch.

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

### Merging duplicate project scopes (AI-assisted)

Multi-machine sync can leave two `project-<ulid>` scopes for the SAME project
(no origin remote, a pre-portable-identity scope, a renamed remote). Scan for
them, then merge the confirmed pair — additive, nothing is ever lost, and the
merged-away identity keeps resolving to the survivor (FR-056–059):

```bash
coffer knowledge merge-scan               # deterministic + internal-engine proposals
coffer knowledge merge project-01H… project-01J…          # source → target
coffer knowledge merge project-01H… project-01J… --no-organize   # skip the post-merge reorg
```

The web-UI equivalent is **Memory → Find duplicates (AI)**. Without an
internal engine (Settings → LLM connections) the scan still reports pairs it
can prove by matching git remotes.

## Web UI

1. Sidebar → **Memory**. The page shows a table of all memory stores (the global store plus one per project — auto-provisioned, so there is no "New store" action).
2. Click a store row to open its per-store detail page.
3. The entry list is the main view, with a recall box at the top. There is no mode selector — retrieval mode is an internal engine detail (ADR retrieval-mode-is-internal).
4. Click a fact to expand a **read-only** render (the UI does not edit fact content in-app). Each fact and its containing folder offer **open in external editor** and **reveal in file manager** (real OS actions, performed by the local daemon); which editor opens is the global preferred-editor preference (see spec ui-shell). Correct a fact by opening it in your own editor — the next recall picks up the change via lazy reindex-on-read.
5. The header shows fact count and on-disk size; a kebab-menu offers "Clear scope". To add or delete facts, use `coffer knowledge remember` / `coffer knowledge forget` (or the REST API).

Every write — agent (MCP), CLI, or REST — reindexes and audits; the web UI itself is a read-only viewer. There is no derived `MEMORY.md`: the markdown files under `knowledge/` are the source of truth (ADR files-as-truth-sqlite-retrieval).

## Optional: vector recall

Default retrieval is keyword + grep — zero config, offline, language-agnostic. The embedding provider is **installation-wide**, not per scope: set it once in the web UI (**Model providers → Embedding**, i.e. `PUT /api/v1/embedding/config`); there is no CLI for it. A scope then opts in by listing `vector` in its retrieval modes:

```bash
coffer credentials set embed-key      # the key the embedding config refers to
coffer knowledge configure project-01J… --enable-vector
```

`coffer knowledge configure <name>` PATCHes the scope's config; the other knobs are `--max-entry-chars`, `--chunk-size`, `--chunk-overlap`, and `--auto-update-sources/--no-auto-update-sources`. Enabling vector re-indexes the scope's existing content. A new named collection can be born vector-enabled: `coffer knowledge create <name> --enable-vector`.

For bilingual content, a local provider (`fastembed` with `bge-m3`) or a cloud model that embeds Chinese well is recommended. The embedding model is mutable — changing it re-embeds every scope that lists a vector mode. With no embedding config, a vector-enabled scope falls back to keyword internally, with no per-query flag.

## Where files live

```
~/.coffer/
├── coffer.db                              # SQLite — rebuildable index (documents, chunks, FTS5, vec, audit)
└── memory/
    ├── global/
    │   └── prefers-tabs.md                # per-fact file = truth
    └── projects/<project-ulid>/
        └── deploy-via-make-release.md
```

The markdown files are the source of truth; `coffer.db` can be rebuilt from them at any time.

## Limits

- Entry text: 1–8192 chars (configurable per scope up to 32 768, via `--max-entry-chars`).
- Search `top_k`: 1–20 (default 5).
- Scope: `global`, a `project-<ulid>` scope, or a named collection — omitted on a tool call, it resolves from the agent's cwd (falling back to `global` outside a project).
