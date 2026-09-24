# Tool Overload: List a Usage-Ranked Slice, Search the Rest

**Status**: Accepted
**Date**: 2026-09-09
**Deciders**: Yuxing Wu
**Related**: [Capability State Model](capability-state-model.md), [Per-Agent Resource Scope](per-agent-resource-scope.md), [Coffer's Own Model Is an Internal Engine](coffer-model-is-an-internal-engine.md), [Coffer Ships Its Own Skill](coffer-ships-its-own-skill.md), [Eval Capture and Regression Gate](eval-capture-and-regression-gate.md), [Session Subprocess Model](session-subprocess-model.md), spec mcp-gateway "Forward tools, resources and prompts", spec mcp-gateway "Toggle individual capabilities", spec mcp-gateway "Gate server exposure by scope per session", spec mcp-gateway "Record invocations without content", research note [MCP gateways](../research/mcp-gateways.md), PR #76, PR #310

## Context

Coffer merges every registered MCP server's tools into one namespaced catalogue
and serves it to Claude Code and Codex through a single MCP endpoint. That is
the point of the gateway, and it has a failure mode that grows with use.

Published evidence puts the cliff at roughly 30–50 tools:

- Anthropic's Tool Search Tool documentation names the same range and reports
  tool-selection accuracy rising from 49% to 74% (Opus 4) and from 79.5% to
  88.1% (Opus 4.5) when the model searches the catalogue instead of receiving
  all of it, with about 85% fewer tokens spent on tool definitions.
- RAG-MCP (arXiv:2505.03275) reports 43% selection accuracy with retrieval
  versus 13.6% with every tool in the prompt, at about half the prompt tokens.
- GitHub Copilot cut its default tool set from 40 to 13 and found an
  embedding-based selector beat an LLM-based one at picking tools (94.5% vs
  87.5%).

Measured on this vault when the gateway still listed everything:

| Signal | Value |
| --- | --- |
| Upstream tools across registered servers | 316 |
| Upstream tools reaching one live Claude Code session | ~125 |
| Distinct tools ever invoked | 44 |
| `mcp.gateway.list_tools.upstream_failed` events in one log rotation | 180 |

Three things went wrong at that size:

- **The client's own deferral was indiscriminate.** Given ~125 tools from one
  server, Claude Code moved the whole `mcp__coffer__*` namespace behind its own
  tool-search indirection, including `coffer__search_tools`, the tool Coffer had
  added to solve the problem. The client has no usage signal to defer on;
  Coffer has one, in its invocation log.
- **Nothing told the agent what Coffer was.** The `initialize` reply carried no
  MCP `instructions`, so no agent was ever told to search first.
- **A slow server vanished for the session.** A server that missed the
  per-server discovery timeout was dropped from `tools/list`. The client cached
  that list, and the `list_changed` that would fix it could only come from the
  server that never connected.

## Options Considered

### Option A — List a usage-ranked slice; keep everything callable and searchable (chosen)

**Listing.** `tools/list` returns Coffer's own `coffer__*` tools plus at most
50 upstream tools (`select_listed_tools` in `domain/mcp/tool_tiering.py`, a
pure function). The builtins never count against the budget. At or under the
budget, every upstream tool is listed. Over it, upstream tools are ranked by
invocation count over the last 90 days, with catalogue order breaking ties.
Each server's best-ranked tool is reserved first, so no enabled server
disappears; the remaining slots are filled in pure rank order. With every
experimental feature on, there are four builtins (`write`, `recall`,
`diagnose`, `search_tools`), so a session lists at most about 54 tools.

**Hidden is not disabled.** `tools/call` gates on the capability preference
(`check_capability_enabled` in `application/mcp/gateway_handlers.py`) and on
the session's scope, never on list membership. An unlisted tool routes exactly
as before.

**Search reaches the rest.** `coffer__search_tools(query, top_k=5, max 20)`
ranks the full upstream catalogue with a BM25-lite scorer
(`domain/mcp/tool_search.py`): name tokens weigh 3.0 against 1.0 for
description tokens, and the doubled server namespace
(`jira__jira_get_issue`) is collapsed to one token so it does not crowd out
the intent words. Coffer's own tools are excluded from results. It returns
real `{name, description, inputSchema, score}` entries that the agent then
calls by name, the shape of Anthropic's "custom tool search" pattern. There is
no LLM, no embedding and no network call.

**The contract reaches the agent.** `initialize` returns `instructions`
capped at 800 characters (`application/mcp/gateway_instructions.py`). The text
says what Coffer is, names each builtin currently in the tool list
(`NAMED_TOOLS`, held against the registered tools by a contract test), adds the
"some tools are unlisted, search for them" sentence only when something is
hidden, and points at the `coffer-guide` skill for everything else.

**Degradation recovers.** Discovery fans out in parallel with a 5-second budget
per server (`PER_SERVER_LIST_TIMEOUT`). A server that misses it is recorded by
`DegradedTracker` (`application/mcp/gateway_recovery.py`), retried at 2, 8 and
30 seconds, and on recovery the gateway invalidates its cache and sends
`notifications/tools/list_changed` so the client re-lists.

**Fail open.** `COFFER_TOOL_TIERING=off` lists everything. So does any failure
of the usage query (`application/mcp/gateway_tiering.py`). `COFFER_TOOL_TIERING_BUDGET`
and `COFFER_TOOL_TIERING_WINDOW_DAYS` tune the policy. Only the exact value
`off` disables tiering, and a malformed number falls back to the default
(`application/mcp/tiering_config.py`). These are operator knobs with no
database row and no UI.

Pros: the default install stops overloading the client with no configuration;
the tools a user calls every day stay one call away; the escape hatch is pinned
into the list by construction; a new vault with few tools sees everything.
Cons: `tools/list` is no longer a pure reflection of upstream, which adds one
layer to "why can't the agent see tool X"; usage is self-reinforcing, so a new
tool on a busy server is discoverable only through search until it is used;
the listing path gains one indexed aggregate over `mcp_invocations`. It wins
because it uses the one signal Coffer has and the client lacks, and no tool
becomes unreachable.

### Option B — List everything; leave deferral to the client (the design this replaced)

The first design (PR #76): `coffer__search_tools` was added and advertised, but
the full catalogue was still listed. Deferral was left to clients with native
tool search.

Pros: `tools/list` mirrors upstream exactly; no policy, no state. Cons:
measured and failed. The client folded Coffer's whole namespace, search tool
included, behind its own indirection, and it has no usage signal to do better.

### Option C — An LLM router that selects and invokes

One tool, `coffer_use(intent)`: a model picks the upstream tool and calls it.

Pros: the agent sees a single tool. Cons: a second model call on every tool
use doubles latency and cost; a router with little context selects worse than
the main agent (Copilot's 94.5% vs 87.5%); the hop is opaque to the agent and
to the invocation log, which records no content; and it breaks the agent's own
reasoning loop. It loses on every axis that matters for a local, auditable
gateway ([Coffer's Own Model Is an Internal Engine](coffer-model-is-an-internal-engine.md)).

### Option D — Hide every upstream tool behind search

List only the builtins and force every call through `coffer__search_tools`.

Pros: minimal context; one uniform discovery path. Cons: every routine call —
the 44 tools this vault actually uses — pays a search round-trip first, and an
agent that ignores the instructions sees no upstream tools at all. It loses on
the common case.

### Option E — Manual allowlists

The user curates a tool subset per agent or per profile. This is the approach
of ContextForge virtual servers, MetaMCP namespaces, MCPJungle tool groups and
Docker MCP profiles.

Pros: exact control. Cons: it does nothing until configured, and the
unconfigured default is where the overload happens. An earlier per-agent MCP
scoping design was built and reverted as over-complex. Server-level scope
([Per-Agent Resource Scope](per-agent-resource-scope.md)) and per-tool
enable/disable ([Capability State Model](capability-state-model.md)) remain
and compose with tiering: scope decides which servers a session sees, the
preference decides what may be called, and tiering decides which of the rest
are listed.

### Option F — A longer discovery timeout

Raise the 5-second per-server budget so slow servers make the first list.

Pros: trivial. Cons: the budget exists so one dead upstream cannot stall the
aggregate list for every session. The defect was that a miss could not be
recovered, not that the threshold was too low. Recovery with `list_changed`
fixes the cause.

## Decision

The gateway lists Coffer's own tools plus a budgeted, usage-ranked slice of
the upstream catalogue: 50 tools, a 90-day window, each server's best tool
reserved first, then pure rank order. Every enabled, in-scope tool stays
callable. `coffer__search_tools` ranks the full catalogue lexically and returns
real schemas. `initialize` tells the agent this in at most 800 characters.
Degraded servers are retried and announced with `list_changed`. The policy fails
open, and is tuned only by environment variables.

Rules a change must keep:

- The call gate never reads list membership.
- The tiering policy stays a pure function over the catalogue and usage counts,
  deterministic for an unchanged catalogue.
- `coffer__search_tools` stays model-free, and its results stay upstream-only.
- The instructions name only tools present in the session's list.

## Consequences

- The upstream slice a session lists drops from ~125 to at most 50, inside the
  30–50 accuracy band, with at most four builtins on top. Whether that clears a given client's own
  deferral threshold is the client's business.
- The `tool_search` eval suite (recall@3 over the ranker, deterministic)
  gates ranker changes in CI ([Eval Capture and Regression Gate](eval-capture-and-regression-gate.md)).
- The split between listed and hidden tools is not shown on a management page.
  It is visible to the agent through the instructions, and to an operator by
  comparing `tools/list` with the capability view.
- Search is lexical, so a query that shares no word with a tool's name or
  description will not find it. An embedding ranking path was added, never wired
  to a real embedder, and removed with every other use of embeddings in Coffer. The eval suite is where a recall gap
  would show up first.
