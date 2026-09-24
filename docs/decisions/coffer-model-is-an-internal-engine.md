# Coffer's Own Model Is an Internal Engine, Not a Persona or a Tool

**Status**: Accepted
**Date**: 2026-09-09
**Deciders**: Yuxing Wu
**Related**: [Internal Engine Settings](internal-engine-settings.md), [Knowledge Curation](knowledge-curation.md), [Aggregate Agent Memory, Never Write It](aggregate-agent-memory-never-write-it.md), [Tool Overload: Tier the List, Search the Rest](tool-overload-tier-the-list-search-the-rest.md), [Chat Is a Single-Owner Live Mirror](chat-single-owner-live-mirror.md), spec internal-engine "Resolve the engine's connection and model together", spec internal-engine "Make every internal pass a clean no-op when nothing is configured", spec chat "Require every writer to name the agent", [principles](../../docs-site/architecture/principles.md) ("Not a model provider"), PR #57, PR #93, PR #315

## Context

Coffer is the vault an agent works inside of: it aggregates MCP servers, holds
knowledge and memory, and drives the user's own coding agents (Claude Code and
Codex) from the web chat and IM channels. The principles say it is not a model
provider — the models it calls are external.

Some of Coffer's own work still needs a language model, run on Coffer's behalf
rather than an agent's:

| Pass | What the model does | Code |
| --- | --- | --- |
| Memory distil | Rewrites the derived digest of the agents' aggregated memory | `application/memory/distil*.py`, one-shot `LangchainLlmCompletion` |
| Knowledge curation | Merges inbox material into a collection's documents and carries a person's edit through the rest | `infrastructure/llm/agentic_reorg.py` — a LangGraph ReAct loop with four internal write tools |
| Knowledge ingest | Writes the one-line description of an ingested document | `application/knowledge/ingest.py`, one-shot completion |
| Vault-sync conflicts | Resolves, inside the git working tree only, a conflict the converge round cannot settle mechanically | `AgenticConflictResolver`, wired in `surfaces/http/sync_wiring.py` |
| Voice transcription | Turns an inbound voice message into text for the turn | `infrastructure/llm/transcription.py`, on its own connection |

Every one of these is unattended or invisible: nobody converses with the model
while it runs, and each pass has a safe answer when no model is configured
(material becomes a document as it stands, a description falls back to the
document's opening prose, the digest is not rewritten, a conflicted converge
round stops for the user's own git tools, audio is handed to the agent as a
file). The code resolves the engine through one
seam, `application/engine/resolve.py`, which answers `None` rather than raising
when either half — a flagged connection or a chosen model — is missing.

Two shapes for this model were built and removed before the current one:

- **A built-in chat persona.** The first chat platform (PR #57) shipped a
  "Coffer Assistant" — a local Qwen model via Ollama in a LangGraph ReAct loop —
  registered as a third chat agent beside `claude_code` and `codex`, with its
  own `/agents/builtin` page and a `coffer chat` command. It had no durable
  usage against the agents' own UIs, it duplicated "Claude Code plus Coffer's
  MCP tools" with a much weaker model, and it made Coffer an actor rather than
  a substrate. PR #93 withdrew it; migration `20260923_0102` finally dropped the
  storage-level `server_default='builtin'` on `conversations.agent_key`, so a
  writer that forgets to name an agent is refused rather than routed to an
  agent that no longer exists.
- **A gateway tool, `coffer__ask`.** PR #93 re-exposed the ReAct loop to agents
  as an agentic-RAG tool that ran a bounded 16-step retrieval loop on the
  caller's behalf. Its callers were Claude Code and Codex — already strong
  ReAct agents — so it inverted the responsibility and did the reasoning with a
  weaker model than the one asking. It was called four times in thirty days,
  one of them a failure; PR #315 removed it.

## Options Considered

### Option A — An internal engine with no persona and no tool surface (chosen)

Keep the model machinery — `infrastructure/llm/langchain_models.py` (model
factory), `llm_completion.py` (one-shot completion), `agentic_reorg.py` (the
ReAct loop) — and use it only from inside Coffer's own passes, each reaching it
through a port (`application/engine_ports.py`). Nothing user-facing presents it
as an assistant; no gateway tool calls it; `coffer__search_tools` stays a pure
BM25 ranker. The model is configured once, in Settings → Coffer's model
(`/settings/engine`), and every pass is a clean no-op until it is.

Pros: each pass gets exactly the model capability it needs (a completion, or a
fenced loop with four tools) and nothing more; the no-op default means Coffer
works with no model at all; LangChain and LangGraph stay confined to
`infrastructure/llm` (import-linter Contract 9a), so the dependency is one
package deep. Cons: the operator configures a model separately from the agents
they already pay for, and a pass without one is quietly not done — the settings
page has to say so. It wins because every consumer is unattended background
work where a small, cheap, separately chosen model is the right tool, and none
of them benefits from a conversational surface.

### Option B — A built-in chat persona (the design removed in PR #93)

A Coffer-hosted model the user chats with, alongside the managed agents.

Pros: works with no external agent installed; a single place to "talk to the
vault". Cons: redundant with a managed agent that already has Coffer's tools
through the gateway; the persona is always the weakest model in the picker; it
needs its own chat adapter, event mapping, registry entry, detail page and CLI;
and it makes Coffer compete with the agents it exists to serve. It lost on
usage and on mission: nobody used it once Claude Code could reach the vault.

### Option C — Expose the engine to agents as a tool (`coffer__ask`, removed in PR #315)

The agent delegates a question to Coffer's model, which runs its own retrieval
loop and answers.

Pros: in principle saves the calling agent context by summarising for it. Cons:
the caller is the stronger reasoner, so delegating to a weaker one lowers answer
quality; a second model hop doubles latency and cost; the loop is opaque to the
caller and to the invocation log, which records no content. The evidence was
four calls in thirty days. The retrieval tools the loop wrapped remain directly
available, so removing the wrapper lost nothing.

### Option D — No internal model at all

Delete the LLM machinery; do every pass mechanically or not at all.

Pros: no model to configure, no LangChain dependency, no model cost. Cons: the
passes that need judgement have no mechanical equivalent — merging new material
into existing documents, rewriting a digest, describing a source, resolving a
text conflict — and transcription needs a speech model by definition. The
passes already degrade to their no-model answers, so Option A contains Option D
as its unconfigured state; deleting the engine would remove the configured
state without saving anything the no-op path does not already save.

### Option E — Borrow a managed agent for internal passes

Run each pass as a headless turn of the user's Claude Code or Codex.

Pros: no second model to configure; the strongest model on the machine does the
work. Cons: an agent turn is a full coding-agent session — tools, file access,
full permissions ([Managed Agents Run With Full Permissions](managed-agents-run-with-full-permissions.md)) —
where a pass needs a completion or a loop fenced to four write tools; it
consumes the user's agent quota on a timer they did not start; it ties every
unattended pass to an installed, logged-in agent CLI; and neither agent offers
a transcription endpoint. It loses on blast radius: curation's safety comes
from the fence ([Knowledge Curation](knowledge-curation.md)), and an agent turn
has none.

## Decision

Coffer's model is an internal engine. It has no chat persona, no agent-registry
entry and no gateway tool. It is reached only by Coffer's own passes — memory
distil, knowledge curation and ingest, vault-sync conflict resolution, and
speech transcription on its own connection — each through a port, each a clean
no-op when the engine is not configured. Rules a future change must respect:

- The chat surface and the channels drive managed agents only; no built-in
  agent may return to the registry, the picker or `/agents`.
- No `coffer__*` tool may call the engine. `coffer__search_tools` ranks
  lexically, without a model.
- LangChain and LangGraph are imported only under `infrastructure/llm`.
- Every consumer resolves the engine through `application/engine/resolve.py`
  and treats `None` as a normal answer, not an error.

## Consequences

- The chat and channel turn seam carries two agent types and nothing else;
  migration `20260923_0102` enforces that a conversation names its agent.
- The engine's configuration is its own settings surface
  ([Internal Engine Settings](internal-engine-settings.md)); an unconfigured
  engine is a supported, first-run state rather than a fault.
- Pass quality depends on the model the operator chooses, and Coffer cannot
  vouch for it. The fences — curation's four tools and write cap, distil
  writing only the derived tree — bound what a poor model can damage.
- Adding a new internal pass means adding a port consumer, not a user surface.
  Adding a user-facing model surface would reopen this decision.
