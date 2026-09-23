# The Built-in Agent Is an Internal Capability, Not a Chat Persona

**Status**: Accepted
**Date**: 2026-06-14
**Deciders**: Yuxing Wu
**Spec**: [channels](../../openspec/specs/channels/spec.md) and [agent-registry](../../openspec/specs/agent-registry/spec.md) (repositioning + capability move — no new spec; both `spec.md` files are updated before implementation)
**Supersedes**: the "converse with the vault through the `builtin` agent" half of the since-removed ADR that repositioned Agent Chat as the Vault Console; **amends** [Tool Retrieval](./tool-retrieval-for-overload.md) (search-tools ranking)
**Related**: [knowledge](../../openspec/specs/knowledge/spec.md) (the Knowledge Layer spec), [Files as Truth](./files-as-truth-sqlite-retrieval.md)

## Context

Coffer shipped a `builtin` "Coffer Assistant" — a local LLM (Qwen via Ollama,
LangGraph ReAct loop) registered as one of three **chat** agents alongside
`claude_code` and `codex`. A since-removed ADR repositioned the chat surface as
the _Vault Console_ and made "converse with the vault through the `builtin`
agent" its first job.

That framing has not held up. The convergent direction — recorded while building
the channel bridge — is that **Coffer is a vault/substrate, not an actor**: the
principles define it as the place "any AI agent reads and contributes through
one safe interface." A user-facing chat persona is off that line. It is
redundant with "Claude Code + Coffer MCP," has no durable usage against the
agents' own UIs and IM, and quietly re-opens the daily-driver creep that
repositioning itself tried to close.

Meanwhile the `builtin` model's _only_ exclusive consumer is that chat persona.
An audit of what actually uses the local LLM machinery:

- **`coffer__search_tools`** (ADR tool-retrieval-for-overload) — a pure BM25-lite ranker. **No LLM.**
- **Memory organization and store merge** (spec knowledge) — use a one-shot LLM
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
- That repositioning's **second** job survives unchanged: Chat remains the seat to
  **observe** channel/IM-driven conversations, over the same
  `ConversationPort` / `TurnPort` seams. "Chat" names the set
  of conversations — whoever drove them — so the name still fits.

  _Amended 2026-09-10, then 2026-09-12:_ the page was removed on the 10th as
  unused and restored on the 12th, so the observation seat described here stands
  — widened, since the page also interrupts and continues what it watches
  ([Chat Is a Single-Owner Live Mirror](chat-single-owner-live-mirror.md)). The
  `ConversationPort` / `TurnPort` seams named here live in spec chat FR-001…spec chat FR-012, with the page itself at
  spec chat FR-029…spec chat FR-041. The first two bullets —
  managed agents only, no `builtin` in the registry — still hold, and are now
  what the agent-provider listing returns.

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
  spec knowledge), never exposed as a chat agent.

One capability is delivered in this change:

**`coffer__search_tools` stays lexical.** This decision once added an
embedding path to `coffer__search_tools`, falling back to the BM25-lite ranker
when no embedder was configured. That path was never wired to a real embedder
and was removed with every other use of embeddings in Coffer, so the tool ranks
with BM25-lite alone ([Tool Retrieval](./tool-retrieval-for-overload.md)). The
downstream agent still does the select-and-call; Coffer only chooses which
candidates it sees.

### Invariants

- **No user-facing built-in persona.** The local model is reachable only as
  `coffer__*` tools (and internal flows like memory organization), never as a
  chat agent or a thing the UI presents as an assistant.
- **Additive, auditable tools.** The upgraded `coffer__search_tools` is
  advertised in `tools/list` like any `coffer__` built-in, logged in the
  invocation log (who/when/how-long/outcome, no args/results).
- **Seam parity preserved.** Removing the `builtin` chat provider does
  not touch the `ConversationPort` / `TurnPort` machinery that
  channels and managed-agent chat share.

## Alternatives considered

### A — Keep the built-in chat persona (status quo / the Vault Console repositioning)

**Rejected.** Off-mission (Coffer is a vault, not an actor), redundant with
"Claude Code + Coffer MCP," no durable usage, and re-opens daily-driver creep.

### B — Remove the built-in agent _and_ delete all LLM machinery now

**Rejected.** Memory organization and store merge already depend on the model
factory + one-shot completion, and memory reorganization (spec knowledge) is a real
internal consumer of the ReAct substrate. Deleting it would orphan both. We
delete only the chat-facing shell.

### C — Keep `coffer__search_tools` BM25-only; do not add an embedder path

**Rejected.** The lexical recall gap is real and is exactly what Tool Retrieval's cited
evidence says embeddings fix. The `vector → keyword` fallback keeps the
zero-config default, so adding the semantic path costs nothing for users without
an embedder.

### D — Keep `/agents/builtin` as a read-only "Coffer internals" observability page

**Rejected for now (YAGNI).** Surfacing what the internal model/tools do can be
a later, deliberate transparency feature; reusing an _agent detail_ page for it
keeps the very "built-in agent is a thing" framing this ADR removes.

## Consequences

- The Agent Chat spec (`spec.md`, acceptance scenarios) and the Agent Registry spec are
  updated: chat lists managed agents only; the built-in agent is no longer a
  registered chat agent.
- The Vault Console repositioning is marked **partially superseded**: its channel-observe job
  stands; its "converse with the vault through the builtin agent" job is removed.
- Tool Retrieval is **amended**: `coffer__search_tools` gains a semantic ranking path
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

## Implementation notes — the engine's settings

The "local model" of move 3 is now [spec internal-engine](../../openspec/specs/internal-engine/spec.md):
one global settings row naming the model, each unattended pass's switch and
interval, the bound on one call and the speech-to-text model, while the
endpoint and key are borrowed from the connection flagged `internal_default`
([Provider Switching](provider-switching.md)). The choices behind its shape:

- **The model is not a field on the connection.** A connection answers "which
  gateway account"; which model runs on it is a property of each use (an
  agent's binding, a conversation, Coffer's own passes). The cost is that two
  independent settings can disagree, and a live vault did pair one provider with
  another's model. The repair is the drop rule: when the flag moves, the engine
  model is kept only if the new connection curates it, and dropped otherwise.
  Probing the new endpoint was rejected because a settings write must not
  depend on an endpoint being reachable. Re-flagging the connection that
  already holds the flag changes nothing.
- **A missing half resolves to `None`, not an error.** Coffer with no
  connection is its first-run state, and the most frequent caller — voice
  transcription, on every inbound message — would otherwise be the loudest
  error in the log. Both halves answer the same `None`, so no consumer encodes
  which one was missing.
- **Passes are switched per pass, not per collection or partition.** The
  question is what Coffer's one engine may do unattended; a per-target setting
  would multiply rows, surfaces and defaults.
- **One pass per write.** A body carrying all three passes would make every
  toggle a read-modify-write over state another machine may be changing through
  sync. `use_default_interval` exists because JSON cannot tell "use the
  default" from "not sent".
- **Defaults are reported, not stored.** An unchosen interval or bound is
  `NULL` in the row and reported beside the default that applies
  (`application/upkeep_schedule.py`), so raising a default later reaches every
  vault that never chose.
- **The schedule polls in slices instead of subscribing.** A settings change
  arrives as often through a converge round from another machine as from a
  local write, and only a wait that re-reads the interval each slice covers
  both.
- **The synced state area publishes a decision, not the row.** A singleton row
  has no "absent" state, so exporting it would make a fresh machine and a
  configured one delete and re-add the document forever. Publishing only a
  non-default choice gives the area a fixed point; deleting the document means
  "back to the defaults" everywhere.
- **The engine is kind-agnostic substrate.** `application/engine/` sits in the
  kind-agnostic-core import-linter contract; the provider kind declares
  `EngineNotifyPort` for the flag moving, and the composition root is the only
  place that sees both. `ResolvedConnection` is the provider kind's value
  object; the engine owns only the conjunction of a flagged connection and a
  chosen model.
- **Known defect.** The `internal_engine_model_set` audit event fires for every
  write to the row, not only for a model change; renaming it is a migration
  over the audit enum.
