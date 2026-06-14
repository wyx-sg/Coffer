# ADR-024 — The Built-in Agent Is an Internal Capability, Not a Chat Persona

> 中文版: [ADR-024-builtin-agent-is-internal-capability.zh.md](./ADR-024-builtin-agent-is-internal-capability.zh.md)

- **Status:** Accepted
- **Date:** 2026-06-14
- **Deciders:** Yuxing Wu
- **Spec:** [008-agent-chat](../../specs/008-agent-chat/spec.md) and [004-agent-registry](../../specs/004-agent-registry/spec.md) (repositioning + capability move — no new spec number; both `spec.md` files are updated before implementation)
- **Supersedes:** the "converse with the vault through the `builtin` agent" half of [ADR-021](./ADR-021-chat-as-vault-console.md); **amends** [ADR-018](./ADR-018-tool-retrieval-for-overload.md) (search-tools ranking) and un-defers its Capability B
- **Related:** [007-memory](../../specs/007-memory/spec.md), [006-knowledge-base](../../specs/006-knowledge-base/spec.md), [ADR-012](./ADR-012-files-as-truth-sqlite-retrieval.md), [ADR-020](./ADR-020-transcript-distillation.md)

## Context

Coffer shipped a `builtin` "Coffer Assistant" — a local LLM (Qwen via Ollama,
LangGraph ReAct loop) registered as one of three **chat** agents alongside
`claude_code` and `codex`. [ADR-021](./ADR-021-chat-as-vault-console.md)
repositioned the chat surface as the _Vault Console_ and made "converse with the
vault through the `builtin` agent" its first job.

That framing has not held up. The convergent direction — recorded while building
the channel bridge — is that **Coffer is a vault/substrate, not an actor**: the
constitution defines it as the place "any AI agent reads and contributes through
one safe interface." A user-facing chat persona is off that line. It is
redundant with "Claude Code + Coffer MCP," has no durable usage against the
agents' own UIs and IM, and quietly re-opens the daily-driver creep ADR-021
itself tried to close.

Meanwhile the `builtin` model's _only_ exclusive consumer is that chat persona.
An audit of what actually uses the local LLM machinery:

- **`coffer__search_tools`** (ADR-018) — a pure BM25-lite ranker. **No LLM.**
- **Transcript distillation** (ADR-020) — uses a one-shot LLM completion
  (`LangchainLlmCompletion`) against _any_ configured model, not the chat loop.
- **The `builtin` chat agent** — the only thing that needs the LangGraph ReAct
  loop, and the only thing that puts a model in front of the user as a persona.

So the question is not cosmetic ("rename the page") but structural: **the
built-in agent is an internal implementation detail, not a product concept.**
Its right shape is the one already named in the project's own direction notes —
an _auxiliary capability_ invoked through Coffer's MCP interface, "like the
embedding model in RAG: not something the user chats with, a sub-component the
main agent calls to do its job better."

## Decision

**Retire the built-in agent as a chat persona; recast it as internal Coffer
capabilities.** Three moves.

### 1. Chat is for managed agents only; the page is "Chat" again

- The chat surface talks **only** to Coffer-managed agents (`claude_code`,
  `codex`, and future managed agents). The `builtin` provider is removed from
  the chat agent registry and from the agent picker.
- The sidebar label reverts from _Vault Console_ / 金库控制台 to **Chat** / 聊天.
- ADR-021's **second** job survives unchanged: Chat remains the human-in-the-loop
  seat to **observe and approve** channel/IM-driven conversations, over the same
  `ConversationPort` / `TurnPort` / `submit_approval` seams. "Chat" names the set
  of conversations — whoever drove them — so the name still fits.

### 2. The "built-in agent" concept leaves the UI

- The `/agents` list drops the built-in-agent card; `/agents` is purely managed
  agents.
- The `/agents/builtin` detail page is removed. Its one still-meaningful piece —
  the local model configuration — moves to **Settings → Models**, reframed from
  "models used by Coffer Assistant" to **"Coffer's internal model"** that powers
  retrieval, agentic RAG, and distillation.

### 3. The local model becomes the engine for internal capabilities

The LLM machinery is **kept but repurposed**, never user-facing:

- **Keep** the model factory (`langchain_models.py`) and the one-shot completion
  (`llm_completion.py`) — distillation already depends on them, and so will (b).
- **Remove** the chat-facing pieces: the `builtin` chat provider, its registry
  entry, and the chat-event mapping.
- **Repurpose** the ReAct loop into an internal agentic-RAG engine behind a new
  built-in tool (b), reusing the existing in-process gateway session
  (`coffer-builtin-agent`) for knowledge/memory access.

Two capabilities are delivered in this change:

**(a) `coffer__search_tools` gains semantic ranking (amends ADR-018).** The
BM25-lite ranker has a real recall gap: it is purely lexical, so an intent like
"notify someone" misses a `send_message` tool, and cross-language queries miss
English tool names. ADR-018's _own cited evidence_ found the winning selector was
an **embedding** index (Copilot: embedding 94.5% > LLM 87.5%) — embeddings, not
keywords. So `coffer__search_tools` now ranks semantically **when an embedder is
configured, and falls back to the BM25-lite ranker when it is not** — the same
`vector → keyword` degradation the knowledge base already uses (ADR-012). This
keeps the zero-config, offline, deterministic path intact (and still guarded by
the `tool_search` eval), while fixing recall for users who have an embedder.
Note this does **not** reverse ADR-018's rejection of an _LLM router_ for tool
selection: the downstream agent still does the select-and-call; we only improve
which candidates it sees.

**(b) `coffer__ask` — agentic retrieval over the vault (un-defers ADR-018
Capability B).** A new built-in MCP tool that runs a bounded retrieve-and-
synthesize loop over the user's **knowledge base + memory** and returns a cited
answer. ADR-018 deferred Capability B _for tool selection_, where the downstream
frontier model already excels at picking from a ranked set. Knowledge/memory
synthesis is a different problem: multi-step retrieval + reading + summarizing
across documents is work the calling agent would otherwise do with many manual
`search_knowledge` / `read_document` round-trips. `coffer__ask` is the literal
form of the "embedding model in RAG" analogy — an internal sub-component the main
agent calls, never a chat partner.

### Invariants

- **No user-facing built-in persona.** The local model is reachable only as
  `coffer__*` tools (and internal flows like distillation), never as a chat
  agent or a thing the UI presents as an assistant.
- **Additive, auditable tools.** `coffer__ask` and the upgraded
  `coffer__search_tools` are advertised in `tools/list` like any `coffer__`
  built-in, logged in the invocation log (who/when/how-long/outcome, no
  args/results), and degrade gracefully (search falls back to BM25; an
  unconfigured model surfaces a clear error, never a crash).
- **Approval/seam parity preserved.** Removing the `builtin` chat provider does
  not touch the `ConversationPort` / `TurnPort` / approval machinery that
  channels and managed-agent chat share.

## Alternatives considered

### A — Keep the built-in chat persona (status quo / ADR-021)

**Rejected.** Off-mission (Coffer is a vault, not an actor), redundant with
"Claude Code + Coffer MCP," no durable usage, and re-opens daily-driver creep.

### B — Remove the built-in agent _and_ delete all LLM machinery now

**Rejected.** Distillation already depends on the model factory + one-shot
completion, and agentic RAG (b) gives the ReAct substrate a real internal
consumer. Deleting it would orphan distillation and force a from-scratch rebuild
for (b). We delete only the chat-facing shell.

### C — Keep `coffer__search_tools` BM25-only; do not add an embedder path

**Rejected.** The lexical recall gap is real and is exactly what ADR-018's cited
evidence says embeddings fix. The `vector → keyword` fallback keeps the
zero-config default, so adding the semantic path costs nothing for users without
an embedder.

### D — Keep `/agents/builtin` as a read-only "Coffer internals" observability page

**Rejected for now (YAGNI).** Surfacing what the internal model/tools do can be
a later, deliberate transparency feature; reusing an _agent detail_ page for it
keeps the very "built-in agent is a thing" framing this ADR removes.

## Consequences

- Spec 008 (`spec.md`, acceptance scenarios) and Spec 004 (agent registry) are
  updated: chat lists managed agents only; the built-in agent is no longer a
  registered chat agent.
- ADR-021 is marked **partially superseded**: its channel-observe/approve job
  stands; its "converse with the vault through the builtin agent" job is removed.
- ADR-018 is **amended**: `coffer__search_tools` gains a semantic ranking path
  with BM25 fallback; Capability B is un-deferred for knowledge/memory as
  `coffer__ask`.
- UI: `/chat` reverts to "Chat"; the `/agents/builtin` route and the built-in
  card are removed; Settings → Models is reframed as Coffer's internal model.
- CLI: the `coffer chat` command (the built-in agent's terminal chat) is removed;
  `coffer model` and the rest of the CLI are unchanged.
- LangGraph/LangChain stay as **internal** dependencies (distillation +
  `coffer__ask`); the chat-event mapping and `builtin` chat provider are deleted.
- No new persisted state beyond what Settings → Models already stores; no
  migration.
