# Research — 007 Memory (Shared Agent Memory)

> 中文版: [research.zh.md](./research.zh.md)

## 1. Why drop mem0 (and the per-agent silo model)

**Question**: Should memory keep using mem0 (LLM-at-write fact extraction + vector store)?

**Decision**: **No.** Three problems drove the redesign:

1. **LLM-at-write is friction** when the consumer is already an LLM that can decide what to remember and write a clean fact itself. mem0's default `llm_provider="none"` made `add_memory` return 503 — the feature was unusable out of the box.
2. **KB and memory were near-duplicate code** yet are two points on one spectrum ("markdown the agent retrieves"). They now share one substrate.
3. **Memory was a private per-agent silo that diverges** — the same project fact ends up copied and drifting across Claude's memory dir, Codex's memories, etc.

**Replacement**: memory = a **single shared source of truth across agents**, agent-native where the format matches. mem0 / chroma / LlamaIndex are removed entirely.

## 2. Canonical format — per-fact markdown + `MEMORY.md`

**Question**: What is the on-disk truth?

**Decision**: Per-fact markdown files with YAML frontmatter (`name`, `description`, `metadata.type`, `metadata.actor`, `origin_session_id`) + a markdown body, plus a `MEMORY.md` index (`- [name](file.md) — description`). This is **Claude Code's auto-memory format**, adopted as canonical so Claude projection is a native directory symlink. Files are the source of truth; SQLite is a rebuildable index. `MEMORY.md` is a Coffer-regenerated derived index — any writer triggers idempotent regeneration, so Claude's own `MEMORY.md` writes are harmlessly overwritten.

## 3. Two-layer scope

**Question**: How do personal facts and repo facts stay separated?

**Decision**: Two scopes.

- **Global** — `project_id = WORKSPACE_GLOBAL_PROJECT_ID` (the existing sentinel `00000000000000000000000000`; reused, not re-minted). One store under `~/.coffer/memory/global/`.
- **Per-project** — `project_id = <project ULID>`. One store per project under `~/.coffer/memory/projects/<ulid>/`.

`remember(scope=project)` → the project store; `scope=global` → the sentinel store; `recall` default → both.

## 4. Scope resolution from the agent's cwd

**Question**: How does the daemon know which project a session is in?

**Decision**: The coffer-mcp-shim starts in the agent's cwd and **reports cwd at session handshake**. The daemon computes the git-root (same basis as Claude's project slug) and resolves — lazily provisioning if absent — the per-project memory store. If cwd is not inside a git project, `scope=project` is rejected (`ScopeUnresolved`) and `scope=global` still works. **To verify in implementation**: MCP server cwd propagation on Claude Code and Codex (design open item #1).

## 5. Sharing mechanism — hybrid (MCP + native projection)

**Question**: How is the single store actually shared into each agent?

**Decision**: Hybrid.

- **MCP for all agents** — every agent reads/writes via Coffer gateway tools.
- **Native projection** — an `AgentMemoryAdapter` (living with the agent driver, not the memory kind) lands canonical content into native locations:
  - **Claude Code** = directory **SYMLINK** of the canonical project memory dir into `~/.claude/projects/<slug>/memory/` (native, bidirectional; keep auto-memory ON — it _is_ canonical).
  - **Codex** = **RENDER** a marker-fenced managed block (`<!-- coffer:memory:start -->…<!-- coffer:memory:end -->`) into `<project>/AGENTS.md` (project layer) and `~/.codex/AGENTS.md` (global layer); disable Codex native `memories` so no second copy accumulates.

The projection engine dispatches on `projection_mode` (`SYMLINK` | `RENDER` | `NONE`). **Adding a new agent = one adapter, no core change.** The adapter performs all native-file mutations; the memory substrate only provides canonical files + rendered markdown, keeping memory agent-agnostic and the L1 config boundary clean.

**Migration on first projection**: if Claude's memory dir already holds real files, merge them into canonical first, then replace with a symlink — never silently overwrite. Managed-block re-render is idempotent.

## 6. Retrieval — shared engine, lazy reindex-on-read

**Question**: How is recall implemented and kept fresh?

**Decision**: The same retrieval engine as the KB: `grep` (ripgrep over files), `keyword` (SQLite FTS5 + BM25, the zero-config default), `vector` (sqlite-vec + a configurable embedding provider, opt-in). When `vector` is requested but embedding is unconfigured, fall back to `keyword` and flag it in the response — never block.

Memory uses **lazy reindex-on-read**: `recall` first scans the small fact dir for deltas (by `content_sha256`) and reconciles the index before searching. This makes Claude's symlink edits and any direct-disk edits instantly visible to all agents with **no filesystem watcher**. (KB, by contrast, reindexes on Coffer-mediated edits + explicit `coffer kb reindex` + an optional off-by-default watcher.)

The **store-list** `fact_count` (KB14, see 006 research §12) reads the indexed `count_documents`, not a `scan_store_dir` of the fact files — any index-vs-disk staleness closes on the next recall/reconcile above. The per-store `/metrics` detail endpoint still scans + walks the disk for `disk_bytes`.

## 7. Embedding configuration

**Question**: How is vector recall configured?

**Decision**: DevPilot-style OpenAI-compatible provider abstraction (one `AsyncOpenAI` client with swappable `base_url`): `embedding_provider`, `embedding_model`, `embedding_base_url`, `embedding_credential_ref` (keychain ref, never plaintext). Providers: OpenAI / OpenRouter / Voyage / Jina / Gemini / Azure / DashScope and local Ollama / LM Studio — all via `.embeddings.create`; plus an optional in-process `local` provider (fastembed) for zero-server offline embeddings. Default retrieval is `keyword`+`grep` (zero config, offline, language-agnostic); vector is opt-in. For bilingual content recommend local `bge-m3` or a cloud provider (English-only small models embed Chinese poorly). The embedding model is **mutable** — changing it re-embeds the store (files are truth).

## 8. Built-in MCP tools

Five memory tools, namespaced under `coffer__`, agent-centric and frictionless:

- `coffer__recall(query, scope?, mode?, top_k?)` → `[{id, text, score, source, time}, …]` (default both scopes; `mode` ∈ `grep` | `keyword` | `vector`).
- `coffer__remember(text, scope?, type?)` → `{id, …}` (default `scope=project`).
- `coffer__set_handoff(body)` → `{status, branch, scope}` (working state, per project + branch).
- `coffer__resume()` → `{found, branch?, body?, updated_at?, note?}`.
- `coffer__list_memory(scope?)` → facts for browse.

Invocations are recorded in `mcp_invocations` the same way KB and upstream tools are: tool name + who/when/duration/outcome only — no arguments or returned content (existing privacy stance).

## 9. Prior art & novelty

- **Managed-block injection** into agent config files is established: **Next.js** ships `<!-- BEGIN:nextjs-agent-rules -->` into `AGENTS.md`; **claude-mem** uses `<claude-mem-context>` in `CLAUDE.md`.
- **Multi-agent native projection of accumulated memory is novel** — every canonical-memory system (mem0/OpenMemory, Letta, Zep, Cognee, MCP memory server, MemPalace) is MCP-centric; the only native-file projectors (claude-mem, agentmemory) are Claude-only single-target. Coffer's fan-out to multiple agents' native locations is unclaimed in OSS as of mid-2026.

## 10. What we are NOT doing in this spec

- Reranking / HyDE / multi-query / LLM synthesis on recall (the agent synthesizes).
- Bidirectional parsing of a proprietary agent memory format back into canonical (industry-unsolved; avoided by symlink-where-compatible + MCP elsewhere).
- Multi-machine sync (constitutional).
- Filesystem watcher on by default.
- Memory categories beyond a free-form `metadata.type`.

## 11. Open items to verify in implementation

1. MCP shim cwd propagation on Claude Code and Codex (§4).
2. sqlite-vec packaging/loading on macOS arm64 and Linux (vector is opt-in; keyword+grep needs no native ext).
3. Local embedding model benchmarks for Chinese/multilingual (default stays keyword+grep).
