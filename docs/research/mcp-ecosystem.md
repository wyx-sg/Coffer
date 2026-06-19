# Competitive Research — MCP Gateways, Aggregators & Registries

> English: this file · 中文版: [mcp-ecosystem.zh.md](./mcp-ecosystem.zh.md)
>
> Internal competitive-research report for Coffer's MCP gateway (spec 001).
> **Date:** 2026-06-16. **Method:** deep-research harness (24/25 claims
> 3-vote confirmed; the two headline findings below survived full adversarial
> verification).

## 1. Landscape at a glance

The MCP infrastructure market cleanly splits into **two layers** that are often
conflated:

| Layer                              | What it is                                                               | Examples                                                                            |
| ---------------------------------- | ------------------------------------------------------------------------ | ----------------------------------------------------------------------------------- |
| **Registry / catalog** (metadata)  | A catalog of _server metadata_, not code; you discover & install from it | Official MCP Registry, Smithery, Glama, PulseMCP, Composio, Docker MCP Catalog      |
| **Gateway / aggregator** (runtime) | A running proxy that puts many upstream servers behind one endpoint      | IBM ContextForge, MetaMCP, ToolHive vMCP, Docker MCP Gateway, MCPJungle, **Coffer** |

**The registry layer.** The **official MCP Registry** (Anthropic + Linux
Foundation, in preview through 2026) is an open, **unauthenticated read-only REST
API serving server metadata** (pointers to packages, not code). Aggregators
scrape it roughly hourly; downstream subregistries reimplement its OpenAPI spec
and inject ratings, download counts, and security scans. Host apps consume the
_downstream marketplaces_ (Smithery, Glama, PulseMCP, Composio, Docker MCP
Catalog), not the root registry. **It is explicitly not a gateway.** [confirmed
3-0]

**The gateway layer.** Five gateways put many upstreams behind one endpoint **and
let different clients see different curated subsets of tools.** Coffer is one of
them — strong on namespacing and secrets, and the only one shipping _both_ a
tool-search tool and an agentic answer tool. **Its distinguishing weakness: it
hands the whole gateway to every agent at once; the other four let each client
get its own curated tool set.** [confirmed 3-0]

### The gateways

- **IBM ContextForge** (`IBM/mcp-context-forge`, OSS) — composes curated subsets
  of upstream tools into named **"virtual servers,"** each exposed to a different
  client; full OAuth/auth story (Red Hat-documented). Self-hosted.
- **MetaMCP** (`metatool-ai/metamcp`, OSS) — groups servers into **"namespaces"**
  exposed as per-endpoint aggregates, with middleware for filtering. Self-hosted.
- **ToolHive vMCP** (`stacklok/toolhive`) — a "virtual MCP" gateway that
  aggregates backends with container isolation and scoping (vMCP GA 2025-12-11;
  production path is K8s-oriented). _Note:_ the precise mechanism of vMCP's
  per-instance tool filtering did not survive verification in this run — describe
  it as "aggregation + scoping" without over-specifying internals.
- **Docker MCP Toolkit / Gateway + Catalog** — runs MCP servers as Docker
  containers; **custom catalogs and "profiles"** scope which servers a client
  sees; secrets + security built in.
- **MCPJungle** (`mcpjungle/MCPJungle`, OSS) — self-hosted registry+gateway with
  **"tool groups"** for per-client scoping.

### Tool-overload mitigation — two strategies

The field fights tool overload **two ways**, and the leaders do both:

1. **Static per-client curation** — virtual servers (ContextForge), namespaces
   (MetaMCP), tool groups (MCPJungle), profiles (Docker). The client only ever
   sees the subset you assigned it.
2. **Runtime tool search** — Anthropic itself brought **MCP tool search to Claude
   Code** (load tool definitions on demand). [tessl.io]

**Coffer does strategy 2 (`search_tools` + `ask`) but not strategy 1.**

## 2. Capability comparison

| Capability                    | ContextForge    | MetaMCP    | ToolHive vMCP     | Docker MCP   | MCPJungle   | **Coffer**                        |
| ----------------------------- | --------------- | ---------- | ----------------- | ------------ | ----------- | --------------------------------- |
| Aggregate behind one endpoint | ✅              | ✅         | ✅                | ✅           | ✅          | ✅                                |
| Namespacing                   | virtual servers | namespaces | vMCP              | catalog      | tool groups | **`server__tool`**                |
| **Per-client curated subset** | ✅              | ✅         | ✅                | ✅ profiles  | ✅          | **❌ whole gateway per agent**    |
| Runtime tool-search           | —               | —          | —                 | —            | —           | **✅ search_tools**               |
| Agentic answer tool           | —               | —          | —                 | —            | —           | **✅ ask**                        |
| Secrets handling              | OAuth/secrets   | env        | keyring/1Password | secrets      | —           | **✅ refs + ciphertext at rest**  |
| Upstream isolation            | —               | —          | ✅ container      | ✅ container | —           | **❌ subprocess**                 |
| Transport                     | stdio/HTTP      | stdio/HTTP | stdio/HTTP        | stdio/HTTP   | stdio/HTTP  | **stdio (shim) + HTTP upstreams** |
| Local-first single-user       | team/server     | server     | team/K8s          | desktop+     | server      | **✅ strict**                     |
| OSS                           | ✅              | ✅         | ✅                | partial      | ✅          | ✅                                |

## 3. How Coffer compares

**Where Coffer is competitive or ahead.**

1. **Namespacing + secrets are solid.** `server__tool` prefixing and the
   refs-in-config / ciphertext-at-rest / materialize-at-spawn model are at parity
   with the best of the field.
2. **It is the only gateway shipping runtime tool-search _and_ an agentic answer
   tool.** `search_tools` (BM25 + optional embedding) and `ask` over
   knowledge/memory put Coffer on the same strategy Anthropic chose for Claude
   Code — and `ask` (retrieve-and-synthesize) goes a step further than any
   surveyed gateway.
3. **Strict single-user local-first** is distinctive; most gateways are
   server/team/K8s-oriented.

**Where Coffer lags — the headline gap.**

1. **No per-client curated subset.** This is the one verified, unanimous finding:
   ContextForge (virtual servers), MetaMCP (namespaces), MCPJungle (tool groups),
   and Docker (profiles) all let _each client see a different scoped subset_ of
   servers/tools. Coffer injects the **whole gateway into every agent**. This is
   both a UX gap (an agent that needs one tool gets all of them — which is _why_
   `search_tools` exists, partly papering over a self-inflicted overload) and a
   security gap (no way to withhold a sensitive server from a given agent).
2. **No upstream isolation.** ToolHive and Docker run each server in a container;
   Coffer spawns bare subprocesses.
3. **No registry/discovery.** Coffer has no catalog; the field has a rich registry
   layer (official Registry + Smithery/Glama/PulseMCP).

## 4. Key takeaways for Coffer

1. **Add per-client / per-agent scoping — the #1 borrow.** A "profile" or
   "virtual server" concept (curated subset of servers/tools per agent) is the
   single most validated idea in this space; every other gateway has it and
   Coffer does not. It fixes both the tool-overload root cause and the inability
   to withhold a sensitive server from an agent.
2. **Keep the tool-search + `ask` advantage** — it is genuinely differentiated;
   pair it _with_ curation rather than as a substitute for it.
3. **Consume the official MCP Registry** for discovery/install instead of
   requiring hand-entered configs — it is an open, unauthenticated metadata API
   built for exactly this.
4. **Consider opt-in upstream isolation** (container/sandbox) to match
   ToolHive/Docker for untrusted servers.

## 5. Sources

Gateways (primary):

- github.com/IBM/mcp-context-forge · ibm.github.io/mcp-context-forge/manage/oauth/
- github.com/metatool-ai/metamcp · docs.metamcp.com/en/concepts/namespaces
- github.com/stacklok/toolhive · stacklok.com/blog (Introducing Virtual MCP Server)
- docs.docker.com/ai/mcp-catalog-and-toolkit · docker.com/blog (Docker MCP Gateway / custom catalogs & profiles)
- github.com/mcpjungle/MCPJungle

Registry (primary):

- blog.modelcontextprotocol.io/posts/2025-09-08-mcp-registry-preview/
- modelcontextprotocol.io/registry/registry-aggregators · github.com/modelcontextprotocol/registry

Tool overload / commentary:

- tessl.io/blog/anthropic-brings-mcp-tool-search-to-claude-code/
- pulsemcp.com/posts/virtual-mcp-servers-and-gateways
- heyitworks.tech/blog/mcp-aggregation-gateway-proxy-tools-q1-2026 · truefoundry.com/blog/best-mcp-registries
- developers.redhat.com/articles/2025/12/12 (advanced auth for MCP gateway)

## Verification update (2026-06-19)

> Re-verification pass: claims hold except one that was overtaken by shipped
> code — the "no per-agent scoping" LOCAL headline finding flipped (PR #108 /
> ADR-026, merged 2026-06-18) and moves to ✏️ Corrected below; the
> `search_tools`/`ask` LOCAL finding still holds. WEB claims confirmed with two
> source upgrades and one scoping correction.

### ✅ Confirmed

- **Coffer ships both `search_tools` and `ask`.** `search_tools` is the built-in
  meta-tool (`tool_search_descriptor()` appended in `append_builtin_tools()`,
  dispatched by `dispatch_tool_search()` — BM25 default, semantic when an
  embedder is provided, per ADR-024); `ask` is a `BuiltinTool` (exposed as
  `coffer__ask`) built by `make_ask_tool()` — a bounded ReAct
  retrieve-and-synthesize loop over knowledge base + memory (read-only retrieval
  only). Both surface through the same gateway.
  `repo:backend/coffer/application/mcp/gateway_builtin.py:144-201`,
  `repo:backend/coffer/infrastructure/chat/agentic_rag.py:53-165`,
  `repo:backend/coffer/surfaces/http/wiring.py:253-293`
- **ToolHive vMCP per-instance tool filtering** (the report flagged the exact
  mechanism as unverified) — now confirmed from primary Stacklok docs: each
  `VirtualMCPServer` references an `MCPGroup` and defines its own aggregation, so
  distinct vMCP instances over the same backends expose different curated
  subsets. Keys: `aggregation.tools[].filter` (per-backend allowlist),
  `aggregation.tools[].excludeAll`, `aggregation.excludeAllTools` (global hide),
  `aggregation.tools[].overrides` (rename/redescribe). Filtered tools drop from
  `tools/list` but stay in the internal routing table for composite workflows.
  https://docs.stacklok.com/toolhive/guides-vmcp/tool-aggregation
- **Official MCP Registry still in preview as of 2026-06.** The Sept 2025 launch
  post frames it as a preview ahead of GA (possible breaking changes / data
  resets), an open read-only REST catalog of server metadata with an OpenAPI
  spec (~9,652 records as of 2026-05-24).
  https://blog.modelcontextprotocol.io/posts/2025-09-08-mcp-registry-preview/

### ✏️ Corrected

- **"No per-client/per-agent scoping" is now stale — Coffer shipped it.** This
  report's headline differentiator ("the lone whole-gateway-per-agent; the only
  gateway with no per-client scoping," §1/§2 table/§3/§4) was overtaken by
  **PR #108 / ADR-026** (`docs/decisions/ADR-026-per-agent-mcp-scoping.md`),
  merged **2026-06-18**. Coffer now supports **per-agent MCP server scoping**
  with two modes: `auto` (default — every enabled server, fully backward
  compatible) and `selected` (an explicit per-agent allowlist). Agent identity
  travels with the session: the install writer stamps `--agent <name>` into the
  agent's `coffer` MCP entry, the shim forwards it as an **`X-Coffer-Agent`**
  request header, and the gateway binds the session to that agent and enforces
  the effective scope (enabled ∩ allowlist) at `tools/list` /
  `resources/list` / `prompts/list`, in `coffer__search_tools` ranking, **and**
  on direct `tools/call` / `resources/read` / `prompts/get` (the call path is
  the real boundary, not list-time hiding). A session with no identity (e.g. the
  in-process built-in agent) stays unscoped. The agent gateway-MCP UI is now an
  **editable scope picker** (auto/selected radio + a per-server allowlist
  checkbox). So this report's headline "only gateway with no per-client scoping"
  finding should be read as **historical** — a gap Coffer has since **closed**;
  it no longer differentiates Coffer from ContextForge / MetaMCP / MCPJungle /
  Docker.
  `repo:backend/coffer/domain/agent/mcp_install.py:44-91`,
  `repo:backend/coffer/surfaces/shim/main.py:145-150`,
  `repo:backend/coffer/surfaces/http/mcp/protocol_routes.py:150,247`,
  `repo:backend/coffer/application/agent/scope_service.py:33-96`,
  `repo:backend/coffer/application/mcp/gateway.py:165-222`,
  `repo:frontend/src/components/agents/AgentGatewayMcpSection.tsx`,
  `repo:docs/decisions/ADR-026-per-agent-mcp-scoping.md`
- **"Only gateway with runtime tool-search" overstated for the broader field.**
  Old: the table marks runtime tool-search as a Coffer-unique `—` across all five
  rivals. Corrected: tool-search / progressive disclosure is not unique even
  beyond the surveyed five — AIRIS ships 7 meta-tools (find/exec/schema/suggest/
  route…), MarimerLLC/mcp-aggregator advertises "lazy tool discovery", MetaMCP
  markets "Elasticsearch for MCP tool selection", and MCPJungle/ContextForge have
  discovery/progressive-disclosure features. What is genuinely distinctive is the
  _combination_: a runtime tool-search tool **plus** an agentic retrieve-and-
  synthesize `ask` (RAG-style) answer tool over a knowledge/memory vault — no
  surveyed gateway ships a RAG answer tool. Reword §1/§3 from "only gateway with
  tool-search" to "distinctive in pairing tool-search with an agentic ask/RAG
  answer tool."
  https://www.heyitworks.tech/blog/mcp-aggregation-gateway-proxy-tools-q1-2026 ·
  https://github.com/MarimerLLC/mcp-aggregator
- **Claude Code MCP tool-search now has a primary source.** Old: cited only the
  tessl.io commentary blog. Corrected: official Claude Code docs section "Scale
  with MCP Tool Search" states tool search is enabled by default, MCP tools are
  deferred rather than loaded upfront, and Claude discovers relevant ones on
  demand (`ENABLE_TOOL_SEARCH`: unset/true/auto/false; `auto` = load upfront if
  within 10% of context window). Shipped in Claude Code 2.1.7 on 2026-01-14.
  https://code.claude.com/docs/en/mcp (section "Scale with MCP Tool Search")
- **"In preview through 2026" is an interpretation, not an official statement.**
  The launch post gives no GA timeline and does not literally say
  "unauthenticated" (the API is open/read-only). The phrasing is consistent with
  current state but should be marked as inference, not a quoted commitment.
  https://blog.modelcontextprotocol.io/posts/2025-09-08-mcp-registry-preview/

### ➕ Coverage added

- **IBM ContextForge** — confirmed per-client curated subsets via named "virtual
  servers" over a unified endpoint; OSS registry+proxy federating
  MCP/A2A/REST/gRPC with 40+ plugins, guardrails, full OAuth; supports
  progressive-disclosure/discovery, so runtime tool-search is not Coffer-unique.
  https://github.com/IBM/mcp-context-forge
- **MetaMCP** — confirmed three-level Servers → Namespaces → Endpoints hierarchy;
  namespaces are the per-endpoint curated aggregate, with description overrides
  and middleware filtering; marketed as "Elasticsearch for MCP tool selection."
  https://github.com/metatool-ai/metamcp
- **MCPJungle** — confirmed self-hosted registry+gateway with "Tool Groups"
  supporting include/exclude and per-client allowlisting (per-client curated
  subsets), matching the report.
  https://www.heyitworks.tech/blog/mcp-aggregation-gateway-proxy-tools-q1-2026
- **Docker MCP Toolkit/Gateway + Catalog** — runs MCP servers as containers;
  custom catalogs and "profiles" scope which servers a client sees, with built-in
  secrets/security (per-client subset = profiles). Characterized from the
  report's cited Docker sources; not independently re-fetched this pass.
  https://docs.docker.com/ai/mcp-catalog-and-toolkit
- **ToolHive vMCP (Stacklok)** — confirmed per-instance curated subsets: each
  `VirtualMCPServer` over an `MCPGroup` applies its own
  `aggregation.tools[].filter` allowlists / `excludeAll(Tools)` / `overrides`;
  container-isolated backends; vMCP introduced Dec 2025 (Stacklok docs give no
  explicit GA date — see the correction in `local-first-control-plane.md`) with
  a K8s-oriented production path.
  https://docs.stacklok.com/toolhive/guides-vmcp/tool-aggregation
