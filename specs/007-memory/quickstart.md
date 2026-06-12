# Quickstart — Memory (Shared Agent Memory)

> 中文版: [quickstart.zh.md](./quickstart.zh.md)

Memory is the **memory face** of Coffer's unified knowledge substrate. Facts are markdown files (the source of truth) shared across every agent — read/written over MCP and projected into each agent's native location. No LLM runs at write time; the agent writes a clean fact.

## Through an MCP client (the primary surface)

Five built-in tools appear (no store reference needed — scope is resolved from the agent's working directory):

- `coffer__recall(query, scope?, mode?, top_k?)` — search project + global memory (default: both; `mode` is `grep` | `keyword` | `vector`).
- `coffer__remember(text, scope?, type?)` — save a fact (default `scope=project`).
- `coffer__update_memory(id, text)` — edit a fact.
- `coffer__forget(id)` — delete a fact.
- `coffer__list_memory(scope?)` — browse.

```text
# Inside a git project, the agent saves a project fact:
coffer__remember("This repo deploys via `make release`, never git push --tags.",
                 scope="project", type="project")

# A personal preference, available everywhere:
coffer__remember("Prefers tabs over spaces.", scope="global", type="user")

# Later — possibly a different agent — recalls across both scopes:
coffer__recall("how do we deploy?")
```

`recall` lazily reindexes the fact directory on every call, so edits made by another agent (or by Claude through its symlink) are visible immediately.

## Native projection (one memory, every agent)

The canonical files are projected into each agent's native location, so you keep using each agent's own memory UX:

| Agent       | Project layer                                                   | Global layer                            |
| ----------- | --------------------------------------------------------------- | --------------------------------------- |
| Claude Code | directory **symlink** → `~/.claude/projects/<slug>/memory/`     | rendered block in `~/.claude/CLAUDE.md` |
| Codex       | rendered block in `<project>/AGENTS.md` (native `memories` off) | rendered block in `~/.codex/AGENTS.md`  |

For Claude, keep auto-memory **on** — the symlinked dir _is_ the canonical store, so Claude's own edits become canonical. For Codex, Coffer renders a managed block:

```
<!-- coffer:memory:start (managed, do not edit) -->
# Memory

- deploy-via-make-release — This repo deploys via make release.
<!-- coffer:memory:end -->
```

Content outside the markers is never touched; re-rendering is idempotent. If Claude's memory dir already has real files when you bind a project, Coffer **merges** them into the canonical store first, then replaces the dir with a symlink — nothing is overwritten.

### Taking over existing native memory

Claude Code may have written memory natively long before Coffer was installed (one `~/.claude/projects/<slug>/memory/` dir per project). The agent **Memory** tab discovers these (`GET /api/v1/agents/{name}/native-memory`) and, with one **Take over** click, imports them all (`POST /api/v1/agents/{name}/native-memory/import`):

- each project's `<slug>` is decoded back to a real project root by walking the filesystem (the slug encoding is lossy, so an undecodable slug is reported and left untouched — never guessed);
- the original `memory/` dir is copied to `memory.bak-<timestamp>` beside it before anything is touched;
- the project's canonical store is provisioned (keyed by git-root, matching how a later `remember` from that repo resolves) and a SYMLINK projection is established (the merge-first step above moves the existing facts in).

The result lists each project's outcome (`imported` / `skipped_undecodable` / `error`) with its store name and backup path. Re-running is idempotent — already-managed (symlinked) dirs are skipped.

Adding a new agent is one `AgentMemoryAdapter`; the memory substrate is untouched.

## CLI

The CLI addresses stores by NAME as a positional argument — `global` or `project-<ulid>` (stores are auto-provisioned; `coffer memory list` shows what exists). There are no `--scope` flags.

```bash
# See the stores (one global + one per project), then inspect one.
coffer memory list
coffer memory describe global

# Add a fact to a store (actor=user).
coffer memory add project-01J… "API base path is /api/v2."
coffer memory add global "Prefers tabs over spaces."

# List facts / get one.
coffer memory facts project-01J…
coffer memory facts global --json
coffer memory get global <fact-id>

# Recall from a store.
coffer memory recall project-01J… "deployment"
coffer memory recall project-01J… "deployment" --mode keyword --top-k 3 --json
coffer memory recall global "部署流程" --mode grep        # exact/regex over the fact files — great for CJK

# Edit, delete, clear a store (store preserved).
coffer memory edit global <fact-id> "API base path is /api/v3."
coffer memory delete global <fact-id>
coffer memory clear project-01J… --yes

# Projections (establish / list / remove a native binding).
coffer memory bind project-01J… my-claude --project-root /abs/path/to/repo
coffer memory projections project-01J…
coffer memory unbind project-01J… my-claude
```

`--json` works on every read command. `--mode` is `grep` | `keyword` | `vector` (default `keyword`). `grep` recall is real — ripgrep over the fact files, no index, no tokenizer, so it works where FTS5 cannot (e.g. CJK). `vector` falls back to `keyword` (flagged) if no embedding provider is configured.

## Desktop

1. Sidebar → **Memory**. The page shows a table of all memory stores (the global store plus one per project — auto-provisioned, so there is no "New store" action).
2. Click a store row to open its per-store detail page.
3. The fact list is the main view, with a recall box at the top (mode selector defaults to keyword).
4. Click a fact to expand / edit-in-place / delete; **Add fact** writes a new markdown file (actor=user).
5. The header shows fact count and on-disk size; a kebab-menu offers "Clear scope".

Every user write regenerates `MEMORY.md`, reindexes, re-projects to bound agents, and audits.

## Optional: vector recall

Default retrieval is keyword + grep — zero config, offline, language-agnostic. To enable vector recall, configure an embedding provider on the store:

```bash
coffer credentials set embed-key
coffer memory configure project-01J… \
    --enable-vector \
    --provider openai \
    --model text-embedding-3-small \
    --dimensions 1536 \
    --credential-ref embed-key
```

`coffer memory configure <name>` PATCHes the store's config; the other knobs are `--base-url`, `--default-mode`, and `--max-fact-chars`. Enabling vector re-embeds the store's existing facts.

For bilingual content, a local provider (`fastembed` with `bge-m3`) or a cloud model that embeds Chinese well is recommended. The embedding model is mutable — changing it re-embeds the store. If vector is requested but unconfigured, recall returns keyword results and flags the fallback.

## Where files live

```
~/.coffer/
├── coffer.db                              # SQLite — rebuildable index (documents, chunks, FTS5, vec, audit)
└── memory/
    ├── global/
    │   ├── MEMORY.md                      # regenerated index
    │   └── prefers-tabs.md                # per-fact file = truth
    └── projects/<project-ulid>/
        ├── MEMORY.md
        └── deploy-via-make-release.md
```

The markdown files are the source of truth; `coffer.db` can be rebuilt from them at any time.

## Limits

- Fact text: 1–8192 chars (configurable per store up to 32 768).
- Recall `top_k`: 1–20 (default 5).
- Scopes: `global`, `project`, or `both` (recall default).
