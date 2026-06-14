# ADR-018: Tool Retrieval for Aggregation Overload

**Status**: Accepted
**Amended by**: [ADR-024](ADR-024-builtin-agent-is-internal-capability.md) (2026-06-14) — `coffer__search_tools` gains a semantic (embedding) ranking path with BM25 fallback, and Capability B is un-deferred for knowledge/memory as the `coffer__ask` built-in tool.
**Date**: 2026-06-14
**Deciders**: Yuxing Wu
**Related**: `.specify/memory/constitution.md`, [spec `001-mcp-gateway`](../../specs/001-mcp-gateway/spec.md), [ADR-007](ADR-007-everything-is-a-resource-kind.md), [ADR-012](ADR-012-files-as-truth-sqlite-retrieval.md)

## Context

Coffer is a local-first MCP aggregator: it merges many upstream MCP servers'
tools and re-exposes them to one coding agent (Claude Code / Codex) as a single
namespaced surface. That is the whole point of spec 001 — register once, use
everywhere. But the aggregation has a failure mode that grows with success:
once a user has registered many servers, the merged catalogue routinely exceeds
**150 tools**, and a coding agent's tool-selection accuracy degrades sharply once
the catalogue passes roughly **30–50 tools**.

The cost is twofold. First, **context**: dumping 150+ full tool schemas into
every request burns a large, fixed token budget before the agent has done any
work. Second, **accuracy**: the more near-duplicate, overlapping tools the model
must reason over, the more often it picks the wrong one or hallucinates a call.
Aggregation, the feature, becomes the thing that makes the agent worse.

The published evidence is consistent and strong (see Evidence below):

- Anthropic's **Tool Search Tool** documents the same 30–50-tool cliff and shows
  that letting the model _search_ the catalogue instead of being handed all of
  it lifts tool-selection accuracy **49% → 74%** (Opus 4) and **79.5% → 88.1%**
  (Opus 4.5), with roughly **85%** fewer tokens spent on tool definitions.
- **RAG-MCP** reports retrieval-based tool selection at **43%** accuracy versus
  **13.6%** when all tools are dumped — more than 3× — at about half the prompt
  tokens.
- **GitHub Copilot** trimmed its tool set from 40 to 13 and, critically, found
  that an embedding/retrieval-based selector beat an LLM-based selector at
  picking tools: **94.5% > 87.5%** — a retrieval index outperforms an LLM router
  at selection, while being cheaper and faster.

Coffer needs a way to keep aggregation a net win at scale: let the agent find the
few tools that match its current intent and call them directly, instead of
reasoning over the entire merged list.

## Decision

Add a single Coffer built-in MCP tool, **`coffer__search_tools`**, that is a
**retrieval primitive returning real upstream tool schemas to the main agent** —
not an LLM sub-agent that selects-and-invokes on the agent's behalf.

Contract:

```
coffer__search_tools(query: string [required], top_k?: int = 5, max 20)
  -> { tools: [{ name, description, inputSchema, score }], total_searched: N }
```

- **Ranks the live aggregated catalogue.** It scores the currently-aggregated
  upstream tools against the intent `query` and returns the top-k. The agent then
  calls the returned tools directly by their existing `<server>__<tool>` names;
  routing is unchanged from spec 001.
- **Returns real schemas, not an invocation.** The shape mirrors Anthropic's
  sanctioned "custom tool search implementation", which returns `tool_reference`
  blocks the API expands into real tool definitions. The main agent — already a
  top-tier model — keeps the select-and-call decision.
- **Pure, deterministic, local ranker.** A BM25-lite keyword ranker over each
  tool's name + description, with name tokens weighted higher. No LLM, no
  embeddings, no network — appropriate for a local-first, trust-centric vault
  and free to run inside the gateway.
- **Upstream-only results.** Coffer's own `coffer__` built-ins are excluded; only
  the upstream capabilities — the overload source — are ranked.
- **Additive.** `coffer__search_tools` is always advertised in `tools/list`
  alongside the other `coffer__` built-ins. Coffer continues to advertise the
  full upstream catalogue exactly as before; nothing is hidden server-side. Tool
  deferral, if any, stays the client's choice.

The invocation is recorded in the invocation log like any other gateway call
(who / when / how-long / outcome, no arguments or results — per spec 001).

## Consequences

- Aggregation stays a net win at scale: the agent can search past the 30–50-tool
  cliff and call the right tool with a fraction of the context cost.
- The call path stays **auditable and unchanged** — searched tools are the same
  real, namespaced tools the agent could already call, so routing, curation
  (enable/disable), and the invocation log all apply with no special-casing.
- A new local ranker is load-bearing for selection quality; it is covered by the
  `tool_search` eval suite (recall@k / MRR over the ranker — deterministic and
  local, part of the default `python -m evals.run`), so ranker changes can't
  silently regress.
- No persisted setting and no migration: keeping the gateway additive (rather
  than adding a server-side advertise/defer mode) avoids new state in
  `coffer.db`.
- The agent must _choose_ to call `coffer__search_tools` (or the client must use
  native tool-search). For an agent that ignores it, the full catalogue is still
  present — a graceful, additive fallback rather than a hard dependency.

## Alternatives Considered

- **An LLM router (`coffer_use(intent)` that selects _and_ invokes).** Rejected:
  it doubles cost and latency (a second model call wrapping every tool use); a
  context-starved router is weaker at selection than the main model — Copilot's
  own data shows retrieval **94.5% > 87.5%** LLM selection; it inserts an opaque,
  un-auditable hop into the call path; and it breaks the agent's own ReAct loop.
  Wrong for a local-first, trust-centric vault where the call path must stay
  legible.
- **Server-side defer-load / advertise-mode (hide upstream tools from
  `tools/list` until searched).** Rejected for now: deferral is properly the
  _client's_ choice — e.g. Claude Code's `tool_search_tool` with
  `defer_loading` — and a server-side mode would require a persisted setting plus
  a migration. Keeping Coffer additive avoids that. Revisit only for clients that
  lack native tool-search.
- **Static namespacing / manual curation alone.** Rejected as insufficient:
  prefixing and per-tool enable/disable (spec 001) already exist and help, but a
  curated set can still exceed the 30–50-tool cliff, and asking the user to hand-
  prune for every task does not scale. Retrieval is the per-request answer that
  curation cannot be.
- **Capability B — an agentic retrieval sub-agent**, and **Capability C — LLM
  memory curation of the catalogue.** Deferred. Their benchmark wins are measured
  against naive all-tools dumping, not against a capable agent handed a small,
  ranked result set. Coffer's consumer is already a top-tier agentic model and
  the local vault is small, so those wins don't transfer yet; revisit if the
  catalogue or the consumer changes.

## Evidence / References

- Anthropic — Tool Search Tool: <https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool>
- Anthropic — Advanced tool use (accuracy + token-reduction figures, custom tool search): <https://www.anthropic.com/engineering/advanced-tool-use>
- RAG-MCP: Mitigating Prompt Bloat in LLM Tool Selection via Retrieval-Augmented Generation — arXiv:2505.03275: <https://arxiv.org/abs/2505.03275>
- GitHub Copilot — How we're making GitHub Copilot smarter with fewer tools (40→13; embedding 94.5% > LLM 87.5%): <https://github.blog/ai-and-ml/github-copilot/how-were-making-github-copilot-smarter-with-fewer-tools/>
