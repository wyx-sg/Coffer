# ADR-011: Memory Engine — mem0 Behind an Application Port

**Status**: Superseded by [ADR-012](ADR-012-files-as-truth-sqlite-retrieval.md), [ADR-013](ADR-013-agent-native-shared-memory.md)
**Date**: 2026-05-29
**Deciders**: Yuxing Wu
**Related**: spec `007-memory` (redesigned), [ADR-002](ADR-002-code-layout-layer-first.md), [ADR-007](ADR-007-everything-is-a-resource-kind.md), [ADR-010](ADR-010-llamaindex-rag-engine.md)

> **Superseded (2026-06-09) by [ADR-012](ADR-012-files-as-truth-sqlite-retrieval.md)
> and [ADR-013](ADR-013-agent-native-shared-memory.md).** The KB/memory redesign
> drops mem0 (no LLM at write time; the agent writes clean facts itself) in favour
> of per-fact markdown as truth indexed by SQLite FTS5 + sqlite-vec (ADR-012), and
> makes memory a single canonical store shared across agents via MCP + native
> projection (ADR-013). The content below is retained for historical context only.

## Context

Spec `007-memory` adds the `memory` resource kind. Each memory store is
a `Resource` (kind `memory`) holding short, derived facts written by
either the coding agent (via Coffer's MCP gateway) or the user, and
surfaced back to the agent through built-in `coffer__*` tools. Distinct
from `knowledge_base` (spec 006): KBs hold user-uploaded documents,
memories hold short derived facts (≤ 8 KB).

Long-term agent memory is a non-trivial moving part. It typically owns
a fact-extraction LLM call at write time, an embedding pass, a vector
index for recall, a dedup / merge policy, and a per-actor scoping
scheme. Coffer's competing pressures (the same two ADR-010 captured)
recur here:

1. **Local-first + small dependency footprint.** No outbound API calls
   in the default install; nothing that demands a separate server
   process; nothing that forces a cloud provider.
2. **Resume-signal mainstream.** The choice should be a name a reader
   recognises, not a fringe library that adds learning burden.

Memory has an extra constraint the RAG engine did not: **it needs an
LLM at write time**. The framework cannot be evaluated in isolation
from the LLM-provider story.

## Decision

**Use `mem0ai` as the memory engine, confined to a single
infrastructure adapter behind a small kind-owned port (`MemoryStore`).
LLM provider choice is user-configured per memory store; the default
is `none` (read-only).**

Concrete shape:

- The port lives in `coffer.domain.memory.store` and expresses
  _Coffer's_ needs: `open(store_name, config)`, `add(store_name, text,
actor) -> MemoryRecord`, `get`, `list`, `update`, `delete`, `clear`,
  `search(store_name, query, top_k) -> Sequence[MemoryHit]`, `drop`,
  `close`. The Protocol does not leak any mem0 type.
- The real adapter is `coffer.infrastructure.memory.mem0_store`. It is
  the _only_ module in the entire codebase allowed to `import mem0`
  (any submodule).
- A `FakeMemoryStore` lives in tests; the entire `application/` and
  `domain/` test surface uses the fake.
- A new importlinter contract (Contract 8 in `backend/pyproject.toml`)
  enforces the confinement: `coffer.application.*` and
  `coffer.domain.*` MUST NOT import `mem0*`. CI fails if anyone breaks
  it.
- mem0's per-call `user_id` is mapped to the memory store's name (single
  Coffer user, multi-store scoping).
- `MemoryStoreConfig.llm_provider` defaults to `"none"` so a fresh
  install does not write to any cloud or local LLM; users opt in to
  `"ollama"` (local) or `"openai"` (cloud) per store. The
  provider / model / endpoint / credential ref are **immutable**
  post-create — switching requires a new store (consistency of stored
  facts, mirroring the embedding-model rule on KBs).

## Consequences

**Positive**

- Coffer ships a mainstream memory stack with no in-house extractor /
  retriever / dedup glue to maintain.
- A future bump (or swap to LangMem / Letta / a hand-rolled solution)
  rewrites _one_ file. Contract 8 guarantees no creeping coupling.
- Engine-down does not take the daemon down: if mem0 or its embedding
  model fails to load, the daemon still starts; only memory write/read
  endpoints return 503 (FR-012).
- The `none`-default LLM provider preserves local-first: a fresh
  install never makes outbound calls unless the user explicitly
  configures one (FR-013 / FR-014).

**Negative**

- mem0's API has shifted across versions through 2024. Each future bump
  may touch the adapter file. Mitigated by (a) the adapter being one
  file, (b) the port being our shape, (c) integration tests under
  `pytest.importorskip("mem0")` catching breakage at CI time.
- mem0 transitively pulls in optional LLM-client packages (OpenAI
  client by default). We accept this in exchange for the framework's
  fact-extraction and dedup logic.
- The "LLM at write time" requirement is real user friction. Documented
  in `quickstart.md`; `--llm-provider ollama` is offered as the
  recommended zero-cost local default.
- `llm_provider` immutability means users must re-create a store to
  switch providers; export-import is not implemented in this spec.
  Documented in `spec.md` FR-001 and `quickstart.md`.

## Alternatives Considered

Six candidates were evaluated in
[`specs/007-memory/research.md` §1](../../specs/007-memory/research.md).
Summary of the rejections:

**LangMem** — Official LangChain memory library; a great fit if
everything is already LangChain. Rejected because it would lock Coffer
into the LangChain ecosystem prematurely (the agent runtime choice is
still open), and its standalone usage outside LangChain is
significantly less common than mem0.

**Letta (formerly MemGPT)** — Strong research credibility, but Letta
is a full agent framework, not just memory. Adopting it would
pre-decide the future agent runtime choice and collide with the
LangGraph direction we are leaning toward.

**Zep (self-host)** — Production-grade with a UI of its own. Rejected
because it requires Postgres and a separate server process — far too
heavy an operational surface for a local-first single-user desktop
app.

**LangGraph checkpointer** — Same ecosystem as the likely future
agent runtime. Rejected because it is designed for in-conversation
state (checkpoint a graph's traversal), not durable cross-session
fact memory.

**Custom (vector DB + facts schema)** — Maximum control; ~300 LOC of
in-house orchestration (extractor prompts, dedup, retriever, persistence).
Rejected for the same reason as the LanceDB option in ADR-010: the
savings in dependency size do not justify re-implementing what mem0
already does, and our team-of-one cannot maintain bespoke memory logic
on top of every other Coffer concern.

**No engine (skip the feature)** — Considered explicitly: ship Coffer
without a memory feature and let agents rely on in-context recall.
Rejected because cross-session recall is the entire user value of the
`memory` resource kind; without it the feature offers nothing over what
an agent already does in-context (spec.md User Story 1 "Why this
priority").

## Lock-in mitigation summary

The confinement contract (importlinter Contract 8), the kind-owned port,
the test pyramid that runs entirely against the fake, and the
single-file adapter together constitute the mitigation. The cost of
swapping engines is bounded to one file's rewrite plus updating the
`mem0ai` dependency line in `pyproject.toml`. No application or domain
code changes. The `llm_provider` enum is also kept narrow on purpose
(`none` / `ollama` / `openai`); adding `anthropic` or any new provider
is a deliberate follow-up touching the adapter and the schema in lock
step.
