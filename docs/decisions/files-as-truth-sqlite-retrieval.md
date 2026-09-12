# Retrieval Stack — Markdown Files as Truth, SQLite FTS5 + sqlite-vec, Configurable Embeddings

> 中文版: [files-as-truth-sqlite-retrieval.zh.md](./files-as-truth-sqlite-retrieval.zh.md)

**Status**: Accepted
**Date**: 2026-06-09 (revised 2026-09-11; see Revision history)
**Deciders**: Yuxing Wu
**Supersedes**: the LlamaIndex RAG engine decision and the mem0 memory engine decision — both ADRs since removed as dead docs
**Related**: spec `knowledge` (the Knowledge Layer spec), [Layer-First Code Layout](code-layout-layer-first.md), [Everything Is a Resource Kind](everything-is-a-resource-kind.md), [One Shared Knowledge Store](agent-native-shared-memory.md)

## Context

The first cut of `knowledge_base` (on a LlamaIndex RAG engine) and `memory` (on
the mem0 memory engine) shipped as two near-symmetric "stores you query over
MCP", each with its own heavyweight engine:

- **KB** routed between a hand-rolled keyword backend and a LlamaIndex semantic
  backend through a `DispatchingKnowledgeBaseStore`. LlamaIndex persisted its
  own on-disk index alongside the raw documents.
- **Memory** used `mem0ai`, which requires an LLM at write time (mem0
  fact-extraction). The default `llm_provider="none"` made `add_memory` return
  503, and text was dual-written to both SQLite and chroma.

Three structural problems surfaced once both kinds were in use:

1. **Dual source of truth.** mem0/chroma stored fact text in chroma _and_ in
   SQLite; LlamaIndex stored a derived index that could silently diverge from
   the raw documents. There was no single authoritative copy to back up,
   diff, or rebuild from.
2. **Engine sprawl.** Two RAG/memory frameworks (LlamaIndex, mem0), a vector DB
   (chroma), a hand-rolled keyword store, and a dispatcher — four heavy moving
   parts plus glue — for what is, conceptually, "retrieve over markdown."
3. **LLM-at-write-time for memory is friction** when the consumer is already an
   LLM that can decide what to remember and write a clean fact itself.

The retired LlamaIndex decision explicitly parked `sqlite-vec + FTS5` ("revisit
when scale or zero-dependency policy demands it") and the mem0 one mirrored that
reasoning. This redesign revisits exactly that: the configurable-embedding
requirement and the files-as-truth requirement together change the calculus.

## Decision

**Drop LlamaIndex, mem0, chroma, the hand-rolled keyword store, and the
dispatcher. Make markdown files on disk the sole source of truth, and keep all
derived index/metadata in `coffer.db` via SQLite FTS5 (keyword/BM25) and
sqlite-vec (vector). Embeddings come from an OpenAI-compatible, user-configurable
provider. Any-format ingestion goes through a pluggable `MarkdownConverter`
port (MarkItDown default).**

Concrete shape:

- **Files are truth, SQLite is a rebuildable index.** KB documents live as
  normalized `docs/<doc-id>.md` (plus `raw/<doc-id>.<ext>` provenance); memory
  facts live as per-fact `<slug>.md` + a regenerated `MEMORY.md`. Anything in
  SQLite (`documents`, `chunks`, `documents_fts`, `vec_chunks`) is reconstructable
  by `coffer reindex` from the files. This kills the dual-source-of-truth bug at
  the root.
- **Three retrieval modes**, all over the same files/index:
  - `grep` — ripgrep over `docs/` (raw files, zero index, language-agnostic).
  - `keyword` — SQLite FTS5 `MATCH … ORDER BY bm25()`. A regular FTS5 table
    stores the chunk text once inside its index (still rebuildable from the
    markdown files, which remain the source of truth).
  - `vector` — sqlite-vec KNN over chunk embeddings.
  - `hybrid` — reciprocal rank fusion of `keyword`+`vector` (`K = 60`, deduped
    by `(document_id, position)`), so exact/CJK/identifier hits and paraphrase
    hits reinforce each other. **Delivered**: enabling `vector` auto-enables
    `hybrid` and makes it the default mode. Default retrieval is
    `keyword`+`grep` (zero config, offline). Vector is opt-in; if
    vector or hybrid is requested but embeddings are unconfigured, retrieval
    falls back to keyword and flags it — it never blocks.
- **Configurable, OpenAI-compatible embeddings** (DevPilot-style: one
  `AsyncOpenAI` client with a swappable `base_url`). Per-corpus config:
  `embedding_provider`, `embedding_model`, `embedding_base_url`,
  `embedding_credential_ref` (keychain ref, never plaintext). Works against
  OpenAI / OpenRouter / Voyage / Jina / Gemini / Azure / DashScope and
  local Ollama / LM Studio through the same `.embeddings.create` call, plus an
  optional in-process `local` provider (fastembed) for zero-server offline
  embeddings. The embedding model is **mutable** — changing it re-embeds the
  corpus (files = truth), so there is no immutability lock. *Superseded in
  shape, not in substance:* the config is now one installation-wide setting
  that NAMES an LLM connection plus one of its `embedding`-modality models
  (spec knowledge FR-077), so the endpoint and key are typed once on the
  Connections page instead of restated per corpus.
- **Pluggable `MarkdownConverter` port** (`can_handle(format)` +
  `convert(bytes) -> (markdown, metadata)`), confined to infrastructure,
  dispatched by format. Default engine is **MarkItDown** (broad coverage,
  LLM-oriented, MIT); Docling / pandoc can be attached per format. Because
  `raw/` is retained, markdown can be regenerated with a better converter later.
- **One store, two faces.** A single `knowledge` retrieval engine backs both the
  KB face (any-format → markdown, agent-read-only) and the memory face (per-fact
  markdown, shared across agents). The import-confinement contract that the
  retired LlamaIndex decision applied to `llama_index*`, and the mem0 one to
  `mem0*`, is re-pointed at the new third-party libs (sqlite-vec loader, the
  converter libs, the OpenAI client) so `application/` and `domain/` never
  import them directly.

## Consequences

**Positive**

- **One source of truth.** Markdown files are authoritative; SQLite is fully
  rebuildable. Backup is one directory tree; corruption recovery is `reindex`;
  a user can diff/grep/edit memory and KB content with ordinary tools.
- **One store, fewer deps.** Everything lives in `coffer.db` (FTS5 + sqlite-vec);
  chroma, LlamaIndex's persist layer, and mem0's vector path all leave the
  lockfile. The keyword path becomes BM25 instead of a hand-rolled
  term-frequency JSON scan, and the dispatcher disappears.
- **No LLM required to write memory.** The agent writes a clean fact directly;
  the default install makes zero outbound calls. Embeddings (and thus any
  outbound call) are strictly opt-in per corpus.
- **Configurable embeddings without a framework.** A thin OpenAI-compatible
  client covers every mainstream provider and local server, which is the exact
  flexibility LlamaIndex's embedding adapters were being used for — minus the
  framework.
- **Cheap mutability.** Because files are truth, changing chunk params or the
  embedding model is a re-chunk/re-embed, not a store rebuild from a lossy
  index. This fixes the mem0 engine's "config is immutable post-create" friction.

**Negative**

- **More in-house orchestration than the retired LlamaIndex and mem0 decisions
  accepted.** We now own the chunker, the FTS5/vec glue, the retrieval fusion,
  and the converter dispatch — the very ~200–300 LOC those decisions paid
  LlamaIndex/mem0 to avoid. We accept this: the surface is small, the concepts
  are ours, and there is no framework churn to track.
- **sqlite-vec is a native extension.** It must load on macOS arm64 and Linux
  in the PyInstaller bundle ([PyInstaller Distribution](distribution-pyinstaller.md));
  packaging/loading is an open verification item.
- **Converter quality is now our problem.** MarkItDown's PDF/Docx fidelity, OCR,
  and the MarkItDown-vs-Docling choice are ours to validate per format. The
  `raw/` retention + re-convertibility is the mitigation.
- **Less "resume-signal mainstream".** The retired LlamaIndex and mem0 decisions
  valued legibility via well-known frameworks. SQLite FTS5 + sqlite-vec is
  arguably _more_ legible to a reader (it is just SQLite), but loses the "I used
  LlamaIndex/mem0" signal. We judge the architectural win to dominate.

## Alternatives Considered

**Keep LlamaIndex for KB.** The strongest reason to keep it was its
embedding adapters and loaders. But the configurable-embedding need is met more
directly by a thin OpenAI-compatible client (one `base_url` swap reaches every
provider), and LlamaIndex's persisted index actively fights files-as-truth: it
wants to own a derived store that can diverge from the markdown. Rejected
because the single-source-of-truth requirement is incompatible with a framework
that insists on owning the index, and the one thing we wanted from it
(embeddings) is a 50-line client.

**Keep mem0 for memory.** mem0's value is fact-extraction + dedup at
write time, which presupposes an LLM call we explicitly want to remove: the
agent _is_ the LLM and writes the fact itself. mem0 also dual-writes to chroma,
the exact bug being eliminated. Rejected — the framework's core feature is the
friction we are removing.

**Keep chroma as the vector store, FTS5 for keyword.** Workable, but it keeps a
second datastore (and a second source of truth for vectors) alongside SQLite.
sqlite-vec puts vectors in the same `coffer.db` as FTS5, the documents table,
and the audit log — one file to back up, one writer, one rebuild path. Rejected
for store uniformity: a second embedded DB earns nothing once vectors are
rebuildable from files.

**Hand-rolled keyword store (the current KB keyword backend) kept as-is.** It is
a term-frequency JSON scan — slower, no BM25, and a bespoke ranker to maintain.
FTS5 is built into SQLite, gives `bm25()` for free, and removes code. Rejected;
there is no reason to keep a worse re-implementation of what SQLite ships.

**Files-as-truth with no SQLite index (grep only).** Tempting for zero
infrastructure, and grep remains a first-class mode. But keyword ranking (BM25)
and vector recall need an index, and rebuilding one from files on every query
does not scale. Rejected as the _sole_ mode; retained as one of three.

## Lock-in mitigation summary

The same confinement discipline as the retired LlamaIndex and mem0 decisions
applies, re-pointed: the `MarkdownConverter` port and the OpenAI-compatible
embedding client are the only
infrastructure seams that touch third-party libs, behind kind-owned ports with
fakes in tests and importlinter contracts keeping `application/` and `domain/`
clean. Swapping the converter, the embedding provider, or even the vector
extension is a one-adapter change. Crucially, because **files are the source of
truth**, the deepest possible lock-in — a proprietary index format you cannot
leave — is gone: any engine can be rebuilt from the markdown.

## Revision history

- **2026-06-09** — Initial decision: markdown files are the sole source of
  truth; SQLite FTS5 + sqlite-vec hold a fully rebuildable index; embeddings
  come from a configurable OpenAI-compatible provider; ingestion goes through a
  pluggable `MarkdownConverter` port. One substrate wearing **two faces** — a
  `knowledge_base` kind and a `memory` kind.
- **2026-09-10** — **The two faces became one.** `memory` and `knowledge_base`
  merged into a single resource kind, `knowledge`. Nothing in the substrate
  moved, because there was never anything to move: `documents`, `chunks`,
  `documents_fts` and `vec_chunks` were shared from the day this ADR landed, and
  `infrastructure/knowledge/paths.py` already owned both on-disk layouts. Only
  the facade was two — two sets of MCP tools, two REST routers, two CLI groups,
  two pages — and it made the caller guess which face a fact belonged to before
  it could search for it. The merge is therefore not a change of position but
  the position being followed through. What it revises above:
  - **Storage root and lanes.** One root, `~/.coffer/knowledge/<scope>/`, with
    lanes `knowledge/` (entries an agent wrote), `inbox/` (ingested documents),
    `rules/`, `handoff/`, `superseded/`, and a hidden `.raw/` holding ingested
    originals. So the `docs/<doc-id>.md` + `raw/<doc-id>.<ext>` pair named in
    the Decision above is now `<scope>/inbox/<doc-id>.md` +
    `<scope>/.raw/<doc-id>.<ext>`, and the per-fact memory markdown is an entry
    under `<scope>/knowledge/`. Provenance retention and re-convertibility are
    unchanged; `.raw/` is hidden only so that ripgrep stops returning two hits
    per ingested document — the converted Markdown and the original it came
    from.
  - **Scope replaces store name.** Scope is read from the resource name:
    `global` and `project-<ULID>` (resolved from the cwd's git root) both
    auto-provision on first use; any other name is a collection the user
    created deliberately and never auto-provisions, because silently minting a
    scope from a typo is worse than an error.
  - **A stored lane discriminator.** `documents.lane` (`knowledge` | `inbox`,
    migration `0053`) records which writer owns a row, because the two lanes'
    paths genuinely overlap under one root. Counts are lane-scoped; **retrieval
    deliberately spans both lanes** — one index, one query — which is the whole
    point of the merge.
  - **Per-corpus embedding config is gone.** The per-scope `KnowledgeConfig`
    carries no embedding fields at all; by the time of the merge neither old
    config's fields were read. Embedding resolves through the
    installation-wide config, and a scope opts into vector search purely by
    listing the retrieval mode. The mutability argument above is unaffected —
    files are still truth, so re-embedding is still a re-derivation.
- **2026-09-10, on clearing the index.** Migration `0051` merged the two kinds
  and **cleared the derived index**. That is this ADR's own position in action,
  not an exception to it. `memory:global` and `knowledge_base:global` both
  existed and `resources` is keyed by `(kind, name)`, so converting both would
  have collided on `knowledge:global`, and any automatic rename would have been
  a guess. It cost little: every `documents` row was `kind='memory'` — a
  memory-side index over the journal lane that a previous change removed — so
  the index already pointed at files that no longer exist, and the
  knowledge-base face had never held a single document. **Files are truth,
  SQLite is a rebuildable index**: clearing an index that files can rebuild
  loses nothing authoritative, because the index was never the system of
  record. Re-accumulation is by explicit `coffer__write` and file ingestion.
- **2026-09-11** — **Two lanes.** The scope's storage lanes collapse to the two
  kinds of material a person actually distinguishes: what someone wrote, and
  what someone uploaded. Nothing about files-as-truth moves; what moves is how
  many boxes the files are sorted into. What it revises above:
  - **Lane layout.** A scope is `~/.coffer/knowledge/<scope>/` with `notes/`
    (what an agent or the user wrote — `coffer__write` lands directly there) and
    `docs/` (uploaded documents, normalized to markdown), plus a hidden
    `.history/` and the hidden `.raw/` holding the uploaded originals. So
    the `docs/<doc-id>.md` + original pair named in the Decision above is once
    again literally `<scope>/docs/<doc-id>.md` + `<scope>/.raw/<doc-id>.<ext>`,
    and the per-fact markdown is a note under `<scope>/notes/`. The lanes the
    2026-09-10 entry listed — `knowledge/` with its `knowledge/inbox/` gradient,
    `rules/`, `handoff/`, `superseded/` — are all deleted, and so is the
    regenerated index file this ADR originally named `MEMORY.md` and latterly
    `knowledge/INDEX.md`: nothing regenerates an index file any more. What
    `superseded/` did is now done by `.history/`, which holds pre-rewrite
    copies rather than tombstones. `.history/` is dot-prefixed for the same
    reason `.raw/` is — ripgrep skips hidden entries, so `coffer__grep` never
    returns an archived revision alongside the live file.
  - **Lane discriminator values.** `documents.lane` becomes `notes` | `docs`.
    Counts stay lane-scoped and retrieval still spans both lanes. The migration
    is destructive by explicit decision — no holding pen — and leaves no
    load-time compatibility shim: the data is corrected in the database and the
    compatibility branch is removed in the same change. That is this ADR's own
    position again: files are truth, so an index the files can rebuild is never
    the thing being risked.
  - **A periodic tidy over `notes/`.** A bounded agentic pass merges duplicate
    notes and rewrites them into topic documents. Before any overwrite or merge
    it copies the prior revision into `.history/`, so an unattended
    rewrite is recoverable. It runs from a background worker shaped like the
    existing `RetentionWorker` — one catch-up pass on boot, then on an interval
    — no-ops when no internal model is configured, and can be triggered by hand.
    Each pass is recorded in Coffer's existing audit log; the per-scope
    `consolidation-log.md` is deleted and not replaced. The pass rewrites the
    files, which remain the record; the index is re-derived from them as always.
  - **Retrieval is untouched.** FTS5 + `bm25()`, sqlite-vec, the modes and their
    fusion, the installation-wide embedder and the `MarkdownConverter` port all
    stand exactly as decided. Dropping the vector-retrieval switch from the
    create-a-collection dialog removes a question put to the user, not the
    capability: a new collection still carries keyword + grep + vector.
