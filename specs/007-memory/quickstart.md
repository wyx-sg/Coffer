# Quickstart — Memory (Shared Agent Memory)

> 中文版: [quickstart.zh.md](./quickstart.zh.md)

Memory is the **memory face** of Coffer's unified knowledge substrate. Facts are markdown files (the source of truth) shared across every agent — read/written over MCP and projected into each agent's native location. No LLM runs at write time; the agent writes a clean fact.

## Through an MCP client (the primary surface)

Five built-in tools appear (no store reference needed — scope is resolved from the agent's working directory):

- `coffer__recall(query, scope?, top_k?)` — search project + global memory (default: both).
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
- [deploy-via-make-release](deploy-via-make-release.md) — This repo deploys via make release.
<!-- coffer:memory:end -->
```

Content outside the markers is never touched; re-rendering is idempotent. If Claude's memory dir already has real files when you bind a project, Coffer **merges** them into the canonical store first, then replaces the dir with a symlink — nothing is overwritten.

Adding a new agent is one `AgentMemoryAdapter`; the memory substrate is untouched.

## CLI

```bash
# Add a fact at a scope (actor=user). project = the current git project.
coffer memory add --scope project "API base path is /api/v2."
coffer memory add --scope global "Prefers tabs over spaces."

# List, recall.
coffer memory list --scope project
coffer memory list --scope global --json
coffer memory recall "deployment" --scope both
coffer memory recall "deployment" --mode keyword --top-k 3 --json

# Edit, forget, clear a scope (store preserved).
coffer memory edit <id> "API base path is /api/v3."
coffer memory forget <id>
coffer memory clear --scope project --yes

# Per-store metrics.
coffer memory describe --scope project
```

`--json` works on every read command. `--mode` is `grep` | `keyword` | `vector` (default `keyword`); `vector` falls back to `keyword` if no embedding provider is configured.

## Desktop

1. Sidebar → **Resources** → open the project (or **Global**) memory store.
2. Tabs switch between **Global** and **Project** scope.
3. The fact list is the main view, with a recall box at the top (mode selector defaults to keyword).
4. Click a fact to expand / edit-in-place / delete; **Add fact** writes a new markdown file (actor=user).
5. The header shows fact count and on-disk size; a kebab-menu offers "Clear scope".

Every user write regenerates `MEMORY.md`, reindexes, re-projects to bound agents, and audits.

## Optional: vector recall

Default retrieval is keyword + grep — zero config, offline, language-agnostic. To enable vector recall, configure an embedding provider on the store:

```bash
coffer keychain set embed-key sk-...
coffer memory configure --scope project \
    --enable-vector \
    --embedding-provider openai \
    --embedding-model text-embedding-3-small \
    --embedding-credential-ref embed-key
```

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
