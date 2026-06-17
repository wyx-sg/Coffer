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
