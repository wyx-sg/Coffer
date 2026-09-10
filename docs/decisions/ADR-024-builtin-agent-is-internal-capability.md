# ADR-024 — The Built-in Agent Is an Internal Capability, Not a Chat Persona

> 中文版: [ADR-024-builtin-agent-is-internal-capability.zh.md](./ADR-024-builtin-agent-is-internal-capability.zh.md)

- **Status:** Accepted
- **Date:** 2026-06-14
- **Deciders:** Yuxing Wu
- **Spec:** [008-agent-chat](../../specs/008-agent-chat/spec.md) and [004-agent-registry](../../specs/004-agent-registry/spec.md) (repositioning + capability move — no new spec number; both `spec.md` files are updated before implementation)
- **Supersedes:** the "converse with the vault through the `builtin` agent" half of [ADR-021](./ADR-021-chat-as-vault-console.md); **amends** [ADR-018](./ADR-018-tool-retrieval-for-overload.md) (search-tools ranking)
- **Related:** [007-memory](../../specs/007-memory/spec.md) (the Knowledge Layer spec), [ADR-012](./ADR-012-files-as-truth-sqlite-retrieval.md)

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
- **Memory organization and store merge** (spec 007) — use a one-shot LLM
  completion (`LangchainLlmCompletion`) against _any_ configured model, not the
  chat loop.
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
- ADR-021's **second** job survives unchanged: Chat remains the seat to
  **observe** channel/IM-driven conversations, over the same
  `ConversationPort` / `TurnPort` seams. "Chat" names the set
  of conversations — whoever drove them — so the name still fits.

  _Superseded 2026-09-10:_ the observation seat was never used and the Chat
  page is removed with spec 008. The `ConversationPort` / `TurnPort` seams
  named here survive as spec 009 FR-043…FR-055; only the surface is gone. The
  first two bullets — managed agents only, no `builtin` in the registry — still
  hold, and are now what the agent-provider listing returns.

### 2. The "built-in agent" concept leaves the UI

- The `/agents` list drops the built-in-agent card; `/agents` is purely managed
  agents.
- The `/agents/builtin` detail page is removed. Its one still-meaningful piece —
  the local model configuration — moves to **Settings → Models**, reframed from
  "models used by Coffer Assistant" to **"Coffer's internal model"** that powers
  retrieval and memory reorganization.

### 3. The local model becomes the engine for internal capabilities

The LLM machinery is **kept but repurposed**, never user-facing:

- **Keep** the model factory (`langchain_models.py`) and the one-shot completion
  (`llm_completion.py`) — memory organization and store merge already depend on
  them.
- **Remove** the chat-facing pieces: the `builtin` chat provider, its registry
  entry, and the chat-event mapping.
- **Keep** the ReAct loop as an internal-only engine (memory reorganization,
  spec 007), never exposed as a chat agent.

One capability is delivered in this change:

**`coffer__search_tools` gains semantic ranking (amends ADR-018).** The
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

### Invariants

- **No user-facing built-in persona.** The local model is reachable only as
  `coffer__*` tools (and internal flows like memory organization), never as a
  chat agent or a thing the UI presents as an assistant.
- **Additive, auditable tools.** The upgraded `coffer__search_tools` is
  advertised in `tools/list` like any `coffer__` built-in, logged in the
  invocation log (who/when/how-long/outcome, no args/results), and degrades
  gracefully (it falls back to BM25 when no embedder is configured, never a
  crash).
- **Seam parity preserved.** Removing the `builtin` chat provider does
  not touch the `ConversationPort` / `TurnPort` machinery that
  channels and managed-agent chat share.

## Alternatives considered

### A — Keep the built-in chat persona (status quo / ADR-021)

**Rejected.** Off-mission (Coffer is a vault, not an actor), redundant with
"Claude Code + Coffer MCP," no durable usage, and re-opens daily-driver creep.

### B — Remove the built-in agent _and_ delete all LLM machinery now

**Rejected.** Memory organization and store merge already depend on the model
factory + one-shot completion, and memory reorganization (spec 007) is a real
internal consumer of the ReAct substrate. Deleting it would orphan both. We
delete only the chat-facing shell.

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
- ADR-021 is marked **partially superseded**: its channel-observe job
  stands; its "converse with the vault through the builtin agent" job is removed.
- ADR-018 is **amended**: `coffer__search_tools` gains a semantic ranking path
  with BM25 fallback.
- UI: `/chat` reverts to "Chat"; the `/agents/builtin` route and the built-in
  card are removed; Settings → Models is reframed as Coffer's internal model.
- CLI: the `coffer chat` command (the built-in agent's terminal chat) is removed;
  `coffer model` and the rest of the CLI are unchanged.
- LangGraph/LangChain stay as **internal** dependencies (memory reorganization
  + store merge); the chat-event mapping and `builtin` chat provider are
  deleted.
- No new persisted state beyond what Settings → Models already stores; no
  migration.

## Revision history

- **2026-09-09** — Transcript distillation removed. It was one of the two
  internal consumers this ADR cited to justify keeping the LLM machinery after
  the chat persona left; the surviving consumers named above (memory
  organization, store merge, and the ReAct reorganization engine) carry that
  justification on their own, so **the decision is unchanged** — only the
  examples are.
- **2026-09-09** — `coffer__ask` removed. The agentic-RAG capability this ADR
  delivered as capability (b) is gone: the ReAct loop survives only as the
  internal memory-reorganization engine it also describes. The callers of
  `coffer__ask` are Claude Code and Codex, which are already strong ReAct
  agents; having Coffer's small internal model run a bounded 16-step retrieval
  loop on their behalf inverts the responsibility, and does it with a weaker
  model than the one that asked. Usage bore that out — four calls in thirty
  days, one of them a failure. The retrieval tools the loop wrapped remain
  directly callable, so nothing is lost but the wrapper.
