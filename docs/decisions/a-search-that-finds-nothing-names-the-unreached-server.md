# A Search That Finds Nothing Names the Server the Agent Is Not Reached By

**Status**: Accepted
**Date**: 2026-11-13
**Deciders**: Yuxing Wu
**Related**: [Per-Agent Resource Scope](per-agent-resource-scope.md), [Tool Overload: Tier the List, Search the Rest](tool-overload-tier-the-list-search-the-rest.md), spec mcp-gateway "Gate server exposure by scope per session", "Tell live sessions when their tool list changes" (this change)

## Context

An agent searches Coffer's catalogue with `coffer__search_tools`. The search covers only the servers the agent is reached by. A Grafana server reached only by Codex gave Claude Code an empty result (`{"tools": [], "total_searched": 10}`), so the agent concluded Coffer had no Grafana capability. The coffer-guide says a call refused for scope "comes back with the reason", but the search path gave no reason at all.

The question: when a search finds nothing, what does Coffer say about servers the agent cannot see?

## Options

1. **Say nothing (the old behaviour).** The agent cannot tell "no such tool" from "not reached", and guesses wrong. Cost: silent failure, which is the bug.
2. **A generic note: "a server matches but is not in reach for you."** It leaks no names, so nothing about another agent's setup is revealed. But the agent cannot act on it, because it cannot name what to ask the developer for.
3. **Name the matching servers and give the command that reaches them** (`coffer mcp reach <server> --agent <agent>`). The agent can report exactly what to ask for, and the developer runs one command. Cost: an agent learns that a server exists when it was not reached by it. The matching is by name only, and only when the search has no results, so a server nobody asked about is never listed.
4. **List every unreached server on every search.** Noisy, reveals names on every query, and most results are not relevant.

Research: this change did not survey other MCP clients or gateways. The comparison rests on Coffer's own code and the agents' needs, and a survey of comparable products should be added before the option is reused elsewhere.

## Decision

Option 3. When a search returns no tools, the result carries a `note` that names the unreached servers whose names share a word with the query, and gives the reach command. Searches with results are unchanged. Names are never listed otherwise.

## Consequences

- An agent stops guessing "Coffer has no Grafana".
- The developer's reach is the only gate, unchanged. Coffer grants nothing new: the note only names servers, never their tools.
- Matching is by server name, so a server found only by its description is not hinted. Accepted: the common case is a server named after the thing the agent wants.
