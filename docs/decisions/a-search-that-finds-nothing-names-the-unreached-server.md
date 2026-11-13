# A Search Names the Server the Agent Is Not Reached By

**Status**: Accepted
**Date**: 2026-11-13
**Deciders**: Yuxing Wu
**Related**: [Per-Agent Resource Scope](per-agent-resource-scope.md), [Tool Overload: Tier the List, Search the Rest](tool-overload-tier-the-list-search-the-rest.md), spec mcp-gateway "Name the unreached server when a search asks for it", "Gate server exposure by scope per session"

## Context

An agent searches Coffer's catalogue with `coffer__search_tools`. The search covers only the servers the agent is reached by. A Grafana server reached only by Codex gave Claude Code an empty result (`{"tools": [], "total_searched": 10}`), so the agent concluded Coffer had no Grafana capability and told the developer so. The developer owns every server and every agent on the machine; the reach is their own setting, not a boundary between tenants.

The question: what does a search say about an enabled server the asking agent is not reached by?

## How comparable gateways answer

- **Zuplo MCP Gateway** (capability filtering): items off the allow-list are "silently dropped" from the list, a call gets JSON-RPC `-32601 Method not found`, and "the client never learns they exist". This is the multi-tenant answer: the hidden thing may belong to someone else.
- **LiteLLM MCP permissions**: `tools/list` returns "only the tools the entity has permissions to access". A refused call does name what was refused and whom to ask: "Tool 'delete_repo' is not allowed for your key/team on server 'issue_tracker'. Contact proxy admin for access." Listing is silent, refusal is explained.
- **Docker MCP Gateway** (Dynamic MCP): the agent gets `mcp-find` to search the whole catalogue, servers it does not have included, and `mcp-add` to add one to its session itself. Discovery is open and the agent widens its own access.

Sources: zuplo.com/docs/mcp-gateway/capability-filtering, docs.litellm.ai/docs/mcp_control, docs.docker.com/ai/mcp-catalog-and-toolkit/dynamic-mcp (read 2026-11-13).

## Options Considered

### Option A — Name the server, leave the change to the developer (chosen)

When a search finds nothing, the result carries a `note` naming the unreached servers whose names share a word with the query. When a search does find tools, the note appears only for a server a query word spells exactly (searching `grafana` while `grafana` is unreached and other tools merely mention it). The note says only the developer can change the reach and where: the Reach control or `coffer mcp reach`.

Pros: the agent reports the true state ("Grafana is in Coffer but not reached by me") instead of a false one. Only names leak, only for what was asked about, and to an agent on the developer's own machine. Cons: an agent learns that a server it was not given exists.

### Option B — Say nothing (Zuplo, and Coffer before this)

Right when the hidden server may be another tenant's. Coffer has one developer, and the cost was the incident above: a silent wrong answer.

### Option C — A note without names

"A server matches but is not in your reach." Leaks nothing, but the agent cannot say what to ask for, and the developer has to guess which server.

### Option D — Let the agent reach the server itself (Docker)

Fits a catalogue of servers nobody has chosen yet. In Coffer the reach is the developer's deliberate gate; an agent that can lift it has no gate.

### Option E — Search every server, mark the unreached results

Would also find an unreached server by its tools' descriptions. Costs a listing of servers this session never started, and shows tool definitions the developer withheld, not only a name.

## Decision

Option A. A search names an unreached server only when the query asks for it by name, and never returns its tools. Only the developer changes a reach.

## Consequences

- An agent stops answering "Coffer has no Grafana" when the server is one switch away.
- A server found only through its tools' descriptions is not hinted (Option E's cost was judged higher).
- `coffer mcp|skill|channel reach` and `coffer resource reach set` take `--agent` (repeatable, by name) and `--all`, like `coffer custom-tool group reach`, so the command the note points at can be typed without looking up uids. `--agent` writes the whole list, as the route does.
- Enforced in `application/mcp/gateway_tool_search.py`.
