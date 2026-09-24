# MCP gateways and aggregators: how other products do it

**Feature**: put many upstream MCP servers behind one endpoint, give each client a curated view of their tools, keep the tool list small enough for the model to use, and keep upstream tool definitions and credentials trustworthy · **Coffer spec**: [mcp-gateway](../../openspec/specs/mcp-gateway/spec.md) · **Related ADRs**: [per-agent-resource-scope](../decisions/per-agent-resource-scope.md), [tool-overload-tier-the-list-search-the-rest](../decisions/tool-overload-tier-the-list-search-the-rest.md), [stdio-shim-bridge](../decisions/stdio-shim-bridge.md), [credential-references](../decisions/credential-references.md), [envelope-encrypted-credential-store](../decisions/envelope-encrypted-credential-store.md)
**Researched**: 2026-09 · **Method**: web research, primary sources (project READMEs and official docs, checked 2026-09-24)

## Scope and selection

This note covers the runtime layer: processes that proxy MCP traffic. It also
covers how the two agents most relevant here, Claude Code and Codex, consume MCP
servers themselves, because their client-side filters and tool search decide
what a gateway needs to do. Registries (catalogs of server metadata) come in
only where a gateway consumes one.

Products were picked by adoption (GitHub stars as of 2026-09) and by how
different their mechanisms are:

| Project | Stars | License | Shape |
| --- | --- | --- | --- |
| [agentgateway](https://github.com/agentgateway/agentgateway) | ~5.0k | Apache-2.0 | Rust data-plane proxy (Linux Foundation) |
| [IBM ContextForge](https://github.com/IBM/mcp-context-forge) | ~4.5k | Apache-2.0 | Python registry + gateway with virtual servers |
| [sparfenyuk/mcp-proxy](https://github.com/sparfenyuk/mcp-proxy) | ~2.8k | MIT | Transport bridge, named servers |
| [MetaMCP](https://github.com/metatool-ai/metamcp) | ~2.7k | MIT | Servers → namespaces → endpoints |
| [ToolHive](https://github.com/stacklok/toolhive) | ~2.2k | Apache-2.0 | Container-per-server runtime + vMCP gateway |
| [Docker MCP Gateway](https://github.com/docker/mcp-gateway) | ~1.6k | MIT | Container-per-server, profiles, dynamic tools |
| [MCPJungle](https://github.com/mcpjungle/MCPJungle) | ~1.3k | MPL-2.0 | Self-hosted registry + gateway, tool groups |
| [mcpm](https://github.com/pathintegral-institute/mcpm.sh) | ~1.0k | MIT | Config manager with profiles (no always-on router) |
| [Microsoft MCP Gateway](https://github.com/microsoft/mcp-gateway) | ~0.85k | MIT | Kubernetes control/data plane, session affinity |
| [1MCP](https://github.com/1mcp-app/agent) | ~0.5k | Apache-2.0 | Local aggregator daemon, tag filters |
| [Higress](https://github.com/higress-group/higress) + [Nacos MCP Router](https://github.com/nacos-group/nacos-mcp-router) | ~9.5k (Higress) | Apache-2.0 | Chinese ecosystem: API gateway hosting MCP; registry-backed router |

The [official MCP Registry](https://github.com/modelcontextprotocol/registry)
(~7.3k stars) is covered briefly as a source for gateways. It is not a gateway.

## Per-product mechanisms

### IBM ContextForge

- **Model.** Upstreams ("gateways") are registered with `POST /gateways`. The
  gateway discovers their tools into one catalog at `/tools`, alongside REST
  APIs wrapped as tools. A **virtual server** is a named bundle created from
  catalog IDs (`associatedTools`, and likewise resources and prompts). Clients
  connect to `/servers/{UUID}/mcp` over streamable HTTP, so each client gets its
  own URL and its own tool subset.
  ([README](https://github.com/IBM/mcp-context-forge))
- **Naming.** Federated tool names are slugged as `<gateway-slug><sep><tool>`,
  where `GATEWAY_TOOL_NAME_SEPARATOR` can be `-` (the default), `--`, `_` or `.`.
  ([configuration](https://ibm.github.io/mcp-context-forge/manage/configuration/))
- **Credentials.** Upstream auth headers are stored AES-encrypted, with the key
  derived from `AUTH_ENCRYPTION_SECRET`. The default value, `my-test-salt`, must
  be changed before production use. The gateway also supports user-scoped
  OAuth tokens to upstreams and an `X-Upstream-Authorization` passthrough header.
  Clients authenticate to the gateway with JWT bearer tokens signed with
  `JWT_SECRET_KEY`, and SSO is available.
- **Transports.** `mcpgateway.translate` wraps a stdio command and exposes it
  as SSE or streamable HTTP (`--stdio "…" --expose-sse`), so stdio servers
  become HTTP upstreams.
- **Health and storage.** The gateway polls every `HEALTH_CHECK_INTERVAL`
  (60 s) and deactivates a peer after `UNHEALTHY_THRESHOLD` (3) failures.
  Storage is SQLite by default and Postgres in production, with Redis for
  caching and multi-instance federation. A plugin framework (off by default,
  `PLUGINS_ENABLED`) provides guardrails, and tracing goes out over OTLP.

### MetaMCP

- **Three levels.** An **MCP server** is a launch config (stdio command, SSE or
  HTTP URL). A **namespace** groups servers, and inside it you can switch whole
  servers or single tools on and off, apply **overrides** (display name, title,
  description, annotations as JSON) and attach **middleware**. An **endpoint**
  publishes one namespace at `/metamcp/<ENDPOINT_NAME>/mcp` (streamable HTTP),
  `…/sse`, or as an OpenAPI surface for non-MCP clients such as Open WebUI.
  ([README](https://github.com/metatool-ai/metamcp))
- **Middleware.** The built-in example is "filter inactive tools". The
  request/response pipeline is the extension point for filtering, not a static
  list.
- **Cold start.** MetaMCP **pre-allocates idle sessions** for each stdio server,
  so the first call does not pay for spawn and initialize. Its docs describe how
  those sessions are invalidated when the config changes.
- **Secrets.** Env values can be raw, `${ENV_VAR}` references resolved from the
  container environment at runtime, or auto-matched. There is no dedicated
  secret store.
- **Auth.** API keys (`sk_mt_…`, sent as a header or query parameter, header
  only for SSE), OAuth per the 2025-06-18 MCP spec, and OIDC. State lives in
  Postgres. Tool search ("Elasticsearch for MCP tool selection") appears on the
  roadmap, not as a shipped feature.

### ToolHive and vMCP (Stacklok)

- **Isolation first.** `thv run` starts every MCP server in its own container.
  **Network isolation is on by default** (since v0.30.1): the server sits on a
  per-server internal network (`toolhive-<name>-internal`), and an egress proxy,
  a DNS container and (for HTTP transports) an ingress proxy bridge it to
  `toolhive-external`. Permission profiles are JSON with `read` and `write`
  paths and `network.outbound.{allow_host, allow_port, insecure_allow_all}`.
  Enforcement works by injecting `HTTP_PROXY`/`HTTPS_PROXY` and supports only
  HTTP and HTTPS, so raw TCP (databases) needs `--isolate-network=false`.
  ([network isolation](https://docs.stacklok.com/toolhive/guides-cli/network-isolation))
- **Aggregation.** In the Kubernetes operator, each `MCPServer` joins an
  `MCPGroup` (`spec.groupRef.name`), and a `VirtualMCPServer` aggregates one
  group. Name conflicts are resolved by `prefix` (the default,
  `prefixFormat: '{workload}_'`, which gives `github_create_issue`), by
  `priority` (a `priorityOrder` list that silently drops duplicates), or
  `manual` (explicit renames). Per-workload `filter` allowlists, `excludeAll`,
  the global `excludeAllTools`, and `overrides` (name, description, annotations)
  shape the view. `defaultToolVisibility: deny` makes every backend opt-in.
  ([tool aggregation](https://docs.stacklok.com/toolhive/guides-vmcp/tool-aggregation))
- **Composite tools.** Multi-step workflows are exposed as single tools and can
  call hidden backend tools as `<WORKLOAD_ID>.<TOOL_NAME>`.
- **Optimizer (tool search).** When enabled, the client sees only two meta-tools,
  `find_tool` and `call_tool`. Search is a hybrid of SQLite full-text search and
  embeddings (TEI with `BAAI/bge-small-en-v1.5` by default, or an
  OpenAI-compatible endpoint), weighted by `hybridSearchSemanticRatio` (0.5), and
  returns `maxToolsToReturn` results (8 by default, range 1 to 50) subject to a
  `semanticDistanceThreshold`.
  ([optimizer](https://docs.stacklok.com/toolhive/guides-vmcp/optimizer))
- **Secrets.** An encrypted store backed by the OS keyring, a read-only
  1Password provider, or env. The local CLI and desktop UI are single-user; vMCP
  and its CRDs target Kubernetes.

### Docker MCP Gateway (MCP Toolkit)

- **Runtime.** `docker mcp gateway run [--profile <name>] [--transport
  stdio|streaming|sse] [--port N]`. Each server is a container image from a
  **catalog**. The default catalog is the OCI image `mcp/docker-mcp-catalog`,
  and custom catalogs are pushed and pulled with `docker mcp catalog push/pull
  <oci-ref>`. A server's container is **started on first use** when a tool call
  routes to it, with restricted privileges, network and resources.
  ([gateway docs](https://docs.docker.com/ai/mcp-catalog-and-toolkit/mcp-gateway/),
  [README](https://github.com/docker/mcp-gateway))
- **Profiles.** `docker mcp profile create --name … --server …` defines which
  servers a client sees. Profiles export to and import from YAML.
  `docker mcp client connect <client> --profile <id>` writes the gateway entry
  into a named client's config. Tool-level allowlists:
  `docker mcp profile tools <id> --enable <server>.<tool>` /
  `--disable-all <server>`.
- **Secrets.** Stored in Docker Desktop's secret store (`docker mcp secret …`)
  rather than env vars, injected at call time, with an OAuth helper
  (`docker mcp oauth …`).
- **Dynamic MCP.** When enabled, the agent gets management tools: `mcp-find`
  (search the catalog), `mcp-add` / `mcp-remove` (change the session's
  servers), `mcp-config-set`, `mcp-exec` (call a tool by name), and `code-mode`
  (agent-written JavaScript that composes tools in a sandbox). Additions are
  **session-scoped and not persisted** to the profile, and
  `docker mcp feature disable dynamic-tools` turns the feature off.
  ([dynamic MCP](https://docs.docker.com/ai/mcp-catalog-and-toolkit/dynamic-mcp/))

### MCPJungle

- **Registration.** `mcpjungle register --name … --url …` or a JSON file.
  `${VAR}` placeholders are resolved by the CLI before the config is sent.
  Tools are canonically named `<server>__<tool>` (for example
  `github__git_commit`), and that name is used everywhere, including for
  enabling and disabling (`mcpjungle disable tool context7__get-library-docs`).
  ([README](https://github.com/mcpjungle/MCPJungle))
- **Tool groups.** A group is defined by `included_tools`, `included_servers`
  and `excluded_tools` (applied last), and is served at its own endpoint
  `/v0/groups/{name}/mcp`. Prompts are not supported in groups.
- **Two modes.** In development mode (the default), every client sees
  everything. **Enterprise mode** (`--enterprise`) requires an admin, and every
  client is a named principal created with an allowlist
  (`mcpjungle create mcp-client cursor-local --allow "calculator, github"`)
  that receives a bearer token. A client with no `--allow` sees nothing.
- **stdio lifecycle.** Stateless by default: a **new process per tool call**.
  `"session_mode": "stateful"` keeps the connection until
  `SESSION_IDLE_TIMEOUT_SEC` (default −1, meaning never). Storage is SQLite
  (`mcpjungle.db`) or Postgres, with OpenTelemetry metrics at `/metrics`.

### 1MCP

- **Local daemon.** `1mcp mcp add <name> -- <cmd>` then `1mcp serve`, which
  serves streamable HTTP on `127.0.0.1:3050`. Clients identify themselves in the
  URL (`/mcp?app=cursor`).
  ([README](https://github.com/1mcp-app/agent))
- **Tag filters instead of groups.** Each server in `mcp.json` has a `tags`
  array. A client narrows its view per connection with `?tags=web,api` (OR) or
  `?tag-filter=` boolean expressions (`+`/`and`, `,`/`or`, `-`/`!`/`not`, with
  parentheses). The subset is chosen in the client's URL, so it needs no
  server-side object and no restart.
  ([server filtering](https://docs.1mcp.app/guide/advanced/server-filtering))
- **Template servers** are instantiated per client or per session from
  connection context. An opt-in **lazy-loading** mode shrinks the initial schema
  payload. A CLI discovery path (`1mcp instructions` → `1mcp inspect <server>`
  → `1mcp run <server>/<tool>`) lets an agent explore tools through a shell
  instead of the tool list.

### mcpm

- **Config manager, not a router.** Servers are installed once into a global
  store. **Profiles are tags** on those servers, and `mcpm client edit <client>`
  writes the chosen servers straight into each client's own config file (Claude
  Desktop, Cursor, Windsurf, VS Code, Cline, Continue, Goose, 5ire, Roo Code,
  OpenCode). v2 dropped v1's always-on router daemon. A profile can still be
  served on demand (`mcpm profile run <p> [--http]`) or shared through a tunnel
  (`mcpm share`). ([README](https://github.com/pathintegral-institute/mcpm.sh))
- The lesson from the redesign: fanning config out into each client's native
  file avoids a single point of failure, but gives up central logging, a single
  auth point and tool search.

### agentgateway

- A Rust data-plane proxy for MCP, A2A and LLM traffic. It multiplexes several
  MCP targets (stdio, SSE, streamable HTTP, OpenAPI converted to tools) behind
  one listener, authenticates with JWT, API keys or OAuth, and authorizes
  **per tool with CEL policy expressions** (RBAC). It adds rate limiting, TLS and
  OTel. It is configured with flat YAML, or through a Kubernetes controller
  implementing the Gateway API.
  ([README](https://github.com/agentgateway/agentgateway))
- The difference: access control is a **policy evaluated per request**
  (identity claims × tool name), not a precomputed list per client.

### Microsoft MCP Gateway

- Split into a **control plane** (`POST/GET/PUT/DELETE /adapters` deploys MCP
  servers as pods, `POST /tools` registers tool definitions) and a **data
  plane** (`/adapters/{name}/mcp` for one server, `/mcp` through a "tool gateway
  router" that routes by tool name). Every request carrying the same
  `session_id` is pinned to the same pod (StatefulSets plus headless services),
  and a distributed session store lets gateway replicas stay stateless. Auth is
  Entra ID with app roles. ([README](https://github.com/microsoft/mcp-gateway))

### sparfenyuk/mcp-proxy

- A pure transport bridge. It runs as stdio→remote (lets a stdio-only client
  reach an SSE or streamable HTTP server, with `--headers` and OAuth2
  client-credentials flags) or as remote→stdio (serves local stdio servers over
  HTTP). `--named-server NAME 'cmd'` or `--named-server-config` hosts several at
  `/servers/<name>/sse`. There is no merged tool list and no filtering.
  `--pass-environment`, `--allow-origin` and `--stateless` are the main knobs.
  ([README](https://github.com/sparfenyuk/mcp-proxy))
- It shows how common the plain "stdio ↔ HTTP shim" piece is. Many
  deployments need only that.

### Higress and Nacos MCP Router (Chinese ecosystem)

- **Higress** (Alibaba's AI/API gateway) hosts MCP servers as an `mcp-server`
  Wasm plugin. A server is **declarative YAML**: `server.name`, then `tools[]`,
  each with `requestTemplate` (method, URL, body mapping) and
  `responseTemplate`. Any REST API becomes an MCP server without code, and
  [openapi-to-mcpserver](https://github.com/higress-group/openapi-to-mcpserver)
  generates these configs from OpenAPI specs. SSE sessions need Redis
  (`mcpServer.redis`), and database MCP servers are declared by DSN.
  ([quick start](https://higress.ai/en/docs/ai/mcp-quick-start/))
- **Nacos MCP Router** exposes three tools to the agent: `search_mcp_server`
  (find servers in the Nacos registry by task description), `add_mcp_server`
  (install or connect one, stdio or SSE, and return its tools) and `use_tool`
  (proxy a call to a tool on that server). In "proxy" mode it instead converts
  stdio/SSE servers into streamable HTTP.
  ([Nacos docs](https://nacos.io/en/docs/latest/ecology/use-nacos-mcp-router/),
  [repo](https://github.com/nacos-group/nacos-mcp-router))
- This is the same find → add → call pattern as Docker's dynamic MCP, built
  independently on a service registry.

## The agents' own mechanisms

### Claude Code

- **Scopes.** Servers come from local scope (`~/.claude.json`, per project path),
  project scope (`.mcp.json`, checked in) and user scope (`~/.claude.json`),
  plus plugins, claude.ai connectors and managed config. `.mcp.json` expands
  `${VAR}` and `${VAR:-default}` in `command`, `args`, `env`, `url` and
  `headers`, but credential-looking variables (`*TOKEN`, `*KEY`, `*SECRET`,
  `ANTHROPIC_API_KEY`, …) read as empty in remote `url` and `headers`.
  `headersHelper` runs a command that prints JSON headers.
  ([docs](https://code.claude.com/docs/en/mcp))
- **Naming and policy.** Tools appear as `mcp__<server>__<tool>`, and plugin
  servers as `mcp__plugin_<plugin>_<server>__<tool>`. These names are what
  permission rules, skill `allowed-tools` and hook matchers use.
  `allowedMcpServers` / `deniedMcpServers` in managed settings match by
  `serverName` or `serverUrl` pattern.
- **Tool search on by default.** MCP tools are deferred, and the model loads
  them on demand through a `ToolSearch` tool. It is off when
  `ENABLE_TOOL_SEARCH=false` or when a custom `ANTHROPIC_BASE_URL` is set. A
  server still connecting is awaited inside the search call.
- **Limits.** `MAX_MCP_OUTPUT_TOKENS` (25,000 by default; warns at 10,000). A
  per-tool `_meta["anthropic/maxResultSizeChars"]` up to 500,000. Per-server
  `timeout`, plus idle timeouts of 5 min for HTTP and 30 min for stdio. Calls
  running longer than 2 minutes move to a background task. On a `list_changed`
  notification the server's tools are refreshed, and the last good list is kept
  if the refresh fails.
- **API-level primitive.** On the Messages API, tools carry
  `defer_loading: true`, and a `tool_search_tool_regex_20251119` or
  `tool_search_tool_bm25_20251119` tool returns `tool_reference` blocks that the
  API expands into full definitions. It returns 5 results by default, and a
  request can defer up to 10,000 tools. A **custom search tool** (for example
  one using embeddings) can return `tool_reference` blocks itself. Anthropic
  advises keeping the 3–5 most-used tools non-deferred and prefixing tool names
  by service so one query matches a group.
  ([tool search tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool))

### Codex

- **Config.** `[mcp_servers.<name>]` in `config.toml`. For stdio: `command`,
  `args`, `env`, `env_vars` (an allowlist of variables to forward), `cwd`. For
  HTTP: `url`, `bearer_token_env_var`, `http_headers`, `env_http_headers` (header
  name → env var name), `http_headers_helper`, and `auth` (`oauth` or `chatgpt`).
  ([docs](https://learn.chatgpt.com/docs/extend/mcp?surface=cli))
- **Client-side curation.** `enabled_tools` (allowlist) and then
  `disabled_tools` (denylist) per server. `enabled` switches a server off
  without deleting it. `required` fails startup if the server cannot initialize.
  `default_tools_approval_mode` (`auto` / `prompt` / `writes` / `approve`) sets
  the approval policy. `startup_timeout_sec` defaults to 10 s and
  `tool_timeout_sec` to 60 s.
- **OAuth.** `codex mcp login <name>` supports both Client ID Metadata
  Documents and dynamic client registration.

### Official MCP Registry (source, not runtime)

- Stores `server.json` metadata that points to packages (npm, PyPI, OCI, …) or
  remote URLs, never code. Namespaces are verified: `io.github.<user>/` through
  GitHub OAuth or OIDC, and custom domains through DNS or HTTP challenges.
  Publishing uses `mcp-publisher`. The v0.1 API has been frozen since October
  2025, and the registry is still marked preview. Downstream subregistries
  mirror the API and add ratings and scans.
  ([repo](https://github.com/modelcontextprotocol/registry),
  [launch post](https://blog.modelcontextprotocol.io/posts/2025-09-08-mcp-registry-preview/))

## Tool-definition integrity

A gateway forwards tool definitions (names, descriptions, input schemas) that
upstream servers write. The model reads those definitions in full, while the
user usually sees a one-line summary. This section covers how the field deals
with definitions that are malicious or that change after the user approved them.

### The threats (Invariant Labs research)

Invariant Labs'
[tool poisoning notice](https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks)
(2025-04-01) named three attacks:

- **Tool poisoning.** Hidden instructions sit in a tool's description, and the
  model sees them but the user does not. The demonstration was an innocent-looking
  `add` tool whose description said, inside `<IMPORTANT>` tags, to read
  `~/.cursor/mcp.json` and the user's SSH private key and pass them in a
  `sidenote` argument. In Cursor the agent did so, and explained the call to the
  user as arithmetic.
- **Rug pull.** A server changes a tool's description *after* the user approved
  it. A one-time approval then covers text the user never saw.
- **Shadowing.** One server's description changes how the model uses *another*
  server's tool. In the demonstration, a malicious server's `add` description
  said every email must go to the attacker's address, which redirected a trusted
  `send_email` tool. Nothing from the malicious server shows up in the call log.

Invariant's recommended mitigations: show the user the full model-visible text,
pin definitions with checksums, and enforce data-flow boundaries between servers.
The [ETDI paper](https://arxiv.org/abs/2506.01333) (arXiv 2506.01333) blames
these attacks on MCP having no authenticity or integrity markers on tool
definitions. It proposes signed, immutable, versioned definitions: a changed
definition requires a new version and a new signature, and a client asks the
user to approve again before accepting new permissions.

### mcp-scan, now Snyk Agent Scan

- **Origin.** Invariant Labs released
  [mcp-scan](https://invariantlabs.ai/blog/introducing-mcp-scan) on 2025-04-11.
  It read the agents' MCP config files, connected to each server, fetched its
  tool descriptions and sent names and descriptions to Invariant's API for
  classification. Its **Tool Pinning** hashed each tool's definition on first
  scan and flagged any later difference as a possible rug pull. v0.1.4.6 added
  tool whitelisting. v0.2.1 added a **`proxy` mode** that sat in the live MCP
  traffic and applied
  [guardrail rules](https://explorer.invariantlabs.ai/docs/mcp-scan/guardrails/)
  to calls ([CHANGELOG](https://github.com/snyk/agent-scan/blob/main/CHANGELOG.md)).
  Snyk
  [acquired Invariant Labs](https://snyk.io/news/snyk-acquires-invariant-labs-to-accelerate-agentic-ai-security-innovation/)
  in June 2025.
- **Now (v0.6.x, [snyk/agent-scan](https://github.com/snyk/agent-scan), ~3.1k
  stars, v0.6.4 released 2026-09-21).** Renamed to agent-scan in 0.4.3, it now
  scans skills and plugins as well as MCP servers, across Claude Code, Cursor,
  Codex, VS Code, Copilot, OpenCode and others. The
  [CLI reference](https://github.com/snyk/agent-scan/blob/main/docs/cli-reference.md)
  lists `scan`, `inspect`, `evo` and `guard`. Neither the CLI nor the docs
  mention `proxy`, whitelisting or local hash comparison any more, and the
  source tree has no proxy module. Analysis requires a Snyk API token and uploads
  server configs, tool names and descriptions, and skill content to Snyk's API.
  Since 0.5.9, stdio servers are not launched by default. v0.6 replaced issue
  codes with scored risks, for example `prompt_injection_tool_desc`,
  `untrusted_content`, `private_data` and `destructive_capabilities`
  ([risks](https://github.com/snyk/agent-scan/blob/main/docs/risks.md)). The v0.5
  codes include E002 "cross-server tool reference (tool shadowing)" and "toxic
  flows": an agent that holds untrusted input, private data and an outbound
  channel at the same time
  ([issue codes](https://github.com/snyk/agent-scan/blob/main/docs/issue-codes.md)).
- **Runtime enforcement moved into agent hooks.**
  `snyk-agent-scan guard install {claude,cursor,codex,github-copilot,all}`
  installs "Agent Guard" hooks into each agent's own hook config. A session-start
  hook reports the MCP servers it finds to Snyk, and the installer detects
  unauthorized edits to its hook script. The runtime check now happens at the
  agent's hook points, not in a proxy in front of the servers.

### Lasso MCP Gateway

- [lasso-security/mcp-gateway](https://github.com/lasso-security/mcp-gateway)
  (~0.4k stars, last pushed 2026-01) wraps the stdio servers listed in an
  existing `mcp.json` and exposes just two tools, `get_metadata` and `run_tool`.
  Every call and result passes through **plugins**: `basic` (masks tokens and
  keys: GitHub, AWS, JWT, Hugging Face), `presidio` (Microsoft Presidio PII
  detection), `lasso` (hosted guardrails for prompt injection and custom
  policies) and `xetrack` (SQLite call tracing).
- **`--scan` checks servers before loading them.** It scores each server's
  reputation from Smithery, npm and GitHub, and scans its tool descriptions for
  hidden instructions. Servers scoring below 30 are blocked, and the verdict is
  written back into the config as `"blocked": "passed" | "blocked" | "skipped"`.
  Filtering happens on content at call time, not by comparing definitions over
  time.

### Prompt Security (SentinelOne)

- A commercial MCP gateway that sits between AI apps and MCP servers and
  inspects every call, prompt template and response. Each server gets a dynamic
  risk score, and policy can allow, block, filter or redact per user, agent and
  action type
  ([SentinelOne](https://www.sentinelone.com/blog/prompt-security-for-agentic-ai/)).
  SentinelOne
  [completed the acquisition](https://investors.sentinelone.com/press-releases/news-details/2025/SentinelOne-to-Acquire-Prompt-Security-to-Advance-GenAI-Security-and-Agent-Security-Strategy/default.aspx)
  in 2025. Implementation details are not public.

### Docker MCP Gateway's integrity controls

According to Docker's
[security model](https://github.com/docker/mcp-gateway/blob/main/docs/security.md):

- **Signed images.** Signature verification is on by default for images in the
  Docker Hub `mcp/` namespace. Those images must be referenced by digest and are
  verified before pull or run, and `--verify-signatures=false` is the explicit
  opt-out. Third-party images are not verified. Here the *server code* is pinned
  (digest plus signature), not the tool text it emits.
- **Secrets scanning.** `--block-secrets` is on by default and scans tool-call
  arguments and text responses for secret-like values, before and after
  execution. `--log-calls` (also on by default) records the tool name and the
  shape of the arguments, never their values.
- **Containment.** Containers do not inherit the host environment and run with
  `no-new-privileges` and CPU/memory limits. Host bind mounts are read-only
  unless a path is on an allowlist. Network isolation is opt-in (per-server
  `disableNetwork` / `allowHosts`, or `--block-network`). Remote URLs must be
  public HTTPS, with loopback, private and metadata-service ranges rejected.
- **Collisions.** The gateway rejects exposed tool names that collide with
  reserved gateway tools or with another enabled server's tools, and does the
  same for prompts and resource URIs. The same checks apply on dynamic
  registration and reload, so a server added mid-session cannot shadow an
  existing tool name.

### What happens on `list_changed`

MCP lets a server send `notifications/tools/list_changed` at any time. That
notification is exactly where a rug pull arrives.

- **ToolHive vMCP** subscribes to `tools`, `resources` and `prompts`
  `list_changed` on persistent backend connections. It clears the cached
  aggregation and re-runs aggregation (filters, overrides, conflict resolution)
  for each affected session, coalescing bursts into one resync per session and
  capability kind. Tool additions *and* removals propagate; for resources and
  prompts, only additions propagate so far
  ([serve_list_changed.go](https://github.com/stacklok/toolhive/blob/main/pkg/vmcp/server/serve_list_changed.go)).
- **ContextForge** routes every pooled session's notifications to one
  `NotificationService`, which **debounces** `list_changed` (5 s by default) to
  stop "refresh storms" and then refreshes that gateway's stored catalog
  ([decision record](https://github.com/IBM/mcp-context-forge/blob/main/docs/docs/architecture/adr/034-centralized-notification-service.md)).
- **Docker** re-applies its collision checks on reload before new capabilities
  become visible.
- **Claude Code** refreshes a server's tools when notified and keeps the last
  good list if the refresh fails.

None of these gateways compares the new definitions with previously approved
ones or asks for re-approval: a changed description is accepted as-is. Pinning
by hash (early mcp-scan) and signed, versioned definitions (ETDI) are the only
designs found that treat a definition change as an event needing approval.

## Gateway-to-upstream authorization

A gateway is an MCP client to each upstream and an MCP server to its own
clients. The
[MCP authorization spec (2025-11-25)](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization)
sets the rules for each direction:

- **Scope.** Authorization is optional. HTTP transports SHOULD follow the spec,
  while stdio servers SHOULD NOT and instead get credentials from the
  environment.
- **OAuth 2.1 roles.** The MCP server is a resource server. It MUST publish
  Protected Resource Metadata (RFC 9728), either through `resource_metadata` in
  the `WWW-Authenticate` header of a 401 or at
  `/.well-known/oauth-protected-resource[/<path>]`. The client finds the
  authorization server through RFC 8414 or OIDC discovery, trying the well-known
  paths in the order the spec lists.
- **Client registration.** In order of preference: pre-registered credentials,
  then **Client ID Metadata Documents** (the `client_id` is an HTTPS URL that
  serves the client's metadata, usable when `client_id_metadata_document_supported`
  is set), then Dynamic Client Registration (kept for backward compatibility),
  then asking the user.
- **PKCE is mandatory**, with `S256`. A client MUST refuse to proceed if the
  authorization server's metadata lacks `code_challenge_methods_supported`.
- **Resource indicators (RFC 8707).** The client MUST send
  `resource=<canonical server URI>` in both the authorization and the token
  request, whether or not the authorization server supports it. The server MUST
  check that each token was issued for it (its audience).
- **No token passthrough.** A server "MUST NOT accept or transit any other
  tokens". When it calls upstream APIs, it uses a separate token obtained as an
  OAuth client of that upstream, and MUST NOT forward the token it received. For
  a gateway this means one token per upstream, bound to that upstream's URI,
  never the client's inbound token.
- **Confused deputy.** A proxy that uses a static client ID with a third-party
  authorization server MUST get the user's consent for each dynamically
  registered client before forwarding.
- **Scopes and tokens.** Clients request the scopes named in the
  `WWW-Authenticate` challenge, or else `scopes_supported`. On a 403 with
  `insufficient_scope` they step up with a new authorization, retrying only a
  limited number of times. Tokens go in the `Authorization` header on every
  request, never in the query string. Refresh tokens for public clients MUST be
  rotated.

Where the surveyed products stand: Claude Code (`claude mcp login`,
`--client-id`, `--callback-port`, `oauth.scopes`) and Codex (`codex mcp login`,
CIMD and dynamic registration) do the client side themselves. ContextForge
stores per-user OAuth tokens to upstreams but also offers an
`X-Upstream-Authorization` passthrough header, which the no-passthrough rule
exists to prevent unless the header carries a token issued for that upstream.
MetaMCP supports spec-compliant OAuth for its own endpoints. Docker keeps
upstream OAuth tokens in its secret store (`docker mcp oauth …`).

## Summary comparison

| | Per-client subset | Unit of subset | Naming on collision | Tool search | Upstream isolation | Secret handling |
| --- | --- | --- | --- | --- | --- | --- |
| ContextForge | yes | virtual server (URL per bundle) | `slug<sep>tool`, sep configurable | discovery API; no meta-tool | none (wraps stdio) | AES-encrypted headers, OAuth |
| MetaMCP | yes | namespace → endpoint URL | per-tool overrides | roadmap | none | `${ENV}` refs |
| ToolHive vMCP | yes | VirtualMCPServer over MCPGroup | prefix / priority / manual | `find_tool` + `call_tool`, hybrid | container + egress proxy | keyring, 1Password |
| Docker | yes | profile (+ per-tool enable) | `server.tool` | `mcp-find` (catalog, not tools) | container, lazy start | Docker Desktop secrets |
| MCPJungle | yes | tool group URL; client allowlist + token | `server__tool` | none | none; process per call by default | `${VAR}` at register time |
| 1MCP | yes | tag expression in client URL | `server/tool` (CLI) | CLI inspect path, lazy mode | none | not documented |
| mcpm | yes | profile written into each client's file | client-native | none | none | client-native |
| agentgateway | yes | CEL policy per request | prefix per target | none | none | JWT / OAuth at the edge |
| Nacos Router | n/a | registry search | per-server | `search_mcp_server` | none | registry-managed |
| Claude Code (client) | n/a | managed allow/deny lists | `mcp__server__tool` | built-in, on by default | none | env expansion, helpers, OAuth |
| Codex (client) | n/a | `enabled_tools` / `disabled_tools` | per-server | none | none | env-var indirection, OAuth |

## Patterns and trade-offs

- **Everyone curates per client. The split is where the subset is defined.**
  There are four places: a server-side object with its own URL (ContextForge
  virtual servers, MetaMCP endpoints, MCPJungle groups, Docker profiles), a
  selector in the client's URL (1MCP tags), a per-request policy (agentgateway
  CEL), or the client's own config file (mcpm, Codex `enabled_tools`). A URL per
  subset is easy to reason about and to paste into a client. Policy scales to
  many identities but is harder to inspect. Writing into client files needs no
  daemon but spreads state across files the tool does not own.
- **Listing is not enforcing.** The products that treat access as security
  (MCPJungle enterprise mode, agentgateway, Microsoft's gateway) bind the
  subset to an authenticated principal and check it on the call. The ones that
  treat it as context hygiene (1MCP tags, MetaMCP middleware) only shape the
  list.
- **Two answers to tool overload, and the field now uses both.** Static
  curation shrinks the list ahead of time. Runtime search hides the list behind
  a meta-tool: ToolHive's `find_tool`/`call_tool`, Anthropic's `defer_loading`
  + tool search, Docker's and Nacos's find-then-add. The model provider has
  moved search into the client (Claude Code defers MCP tools by default), which
  changes what a gateway-side search is for: it helps clients that lack native
  search, and it can rank with information the client lacks (usage, which
  server, descriptions the gateway rewrote).
- **Search result shapes differ.** "Find a tool, then call it through a proxy
  meta-tool" (ToolHive, Nacos `use_tool`, Docker `mcp-exec`) works with any
  client but hides the real tool name from the client's permission system.
  "Return a reference the client expands" (Anthropic `tool_reference`) keeps the
  real name callable but needs client or API support.
- **Name collisions: prefixing wins.** Double underscore (`server__tool`:
  MCPJungle, Claude Code) and a single separator (ToolHive `{workload}_`,
  ContextForge `-`) dominate. ToolHive's `priority` strategy shows the danger
  of silent dropping. Anthropic's advice to prefix by service also makes
  regex/BM25 search match whole groups.
- **stdio lifecycle is a real design axis.** The options: a process per call
  (MCPJungle stateless: isolated, slow, loses server state), a warm pool
  (MetaMCP pre-allocated idle sessions), lazy start on first call (Docker), or
  one long-lived process (most others). Stateful servers (browsers, DB
  sessions) break under per-call spawning.
- **Isolation splits along deployment lines.** Container-based products (ToolHive,
  Docker) sandbox by default and filter egress. Everything else runs upstreams
  as plain processes. ToolHive's proxy-variable enforcement covers HTTP(S) only,
  so strict isolation and DB-talking servers conflict.
- **Secrets: indirection everywhere, encryption at rest in few places.**
  `${VAR}` or env-var-name indirection is universal (MetaMCP, MCPJungle, Codex
  `env_http_headers`, Claude Code). Encrypted storage is rarer (ContextForge
  AES with a default key that must be changed, ToolHive keyring, Docker Desktop
  secrets). Claude Code blanks credential-looking variables in remote URLs and
  headers to prevent exfiltration through config.
- **Integrity checks moved away from pinning.** The one pinning tool
  (mcp-scan) dropped local hashing and its proxy, and became a cloud-analysed
  scanner plus agent hooks. Gateways answer `list_changed` by refreshing, not by
  asking the user again. Docker pins the server *image* (digest plus signature),
  and the other products that check content (Lasso, Prompt Security, Docker
  `--block-secrets`) filter at call time. Nobody currently guards the gap
  between "the definition the user approved" and "the definition now being
  served".
- **The authorization spec makes the gateway an OAuth client of every upstream.**
  Resource indicators and the no-passthrough rule mean one audience-bound token
  per upstream, held by the gateway. Header passthrough options (ContextForge)
  are the part of the field that conflicts with that rule.
- **Team gateways vs local daemons.** ContextForge, MetaMCP, Microsoft and
  agentgateway assume Postgres, Redis or Kubernetes and multiple users. 1MCP,
  mcpm and the ToolHive CLI are local and single-user. vMCP's advanced
  aggregation lives only in the Kubernetes operator.

## Worth borrowing / worth avoiding

**Worth borrowing**

- **Default-deny for new upstreams** (ToolHive `defaultToolVisibility: deny`,
  MCPJungle "no `--allow` means nothing"). A newly registered server should not
  silently reach every client.
- **Per-tool overrides of description and annotations** (MetaMCP, vMCP).
  Rewriting a vague upstream description is the cheapest way to improve both
  model selection and search recall. Annotation overrides (`readOnlyHint`,
  `destructiveHint`) can feed approval policies.
- **Composite tools that may call hidden tools** (vMCP). Expose one safe
  workflow tool while its raw building blocks stay off the list.
- **A tunable hybrid search** (vMCP): keyword FTS plus embeddings, a ratio knob,
  a result cap and a distance threshold, with the default cap in single digits.
- **Returning references rather than proxying calls**, where the client
  supports it (Anthropic `tool_reference`). The real tool name stays visible to
  permissions, hooks and audit.
- **Session-scoped dynamic additions** (Docker). An agent can pull in a server
  for one task without changing the durable configuration.
- **Blanking credential-shaped variables in remote URLs** (Claude Code). A
  simple guard against config-driven exfiltration.
- **Lazy start plus health-based deactivation** (Docker on-demand containers;
  ContextForge `UNHEALTHY_THRESHOLD`). Idle upstreams cost nothing, and a
  flapping one leaves the list instead of timing out every call.
- **Declarative REST-to-MCP templates** (Higress `requestTemplate` /
  `responseTemplate`, openapi-to-mcpserver). Many internal "servers" are thin
  HTTP wrappers that need no process at all.

- **Pin at the gateway, where every definition passes anyway.** Hash each
  tool's name, description and schema when the user enables the server, compare
  on every `tools/list` and `list_changed`, and hold changed tools back until
  someone approves the new text (mcp-scan's idea, applied in-line as ETDI
  suggests).
- **Show the model-visible text.** Invariant's first mitigation: let the user
  see the full description the model gets, not a summary.
- **Coalesce `list_changed` handling** (ToolHive's one resync per session and
  capability kind, ContextForge's 5 s debounce), so a noisy upstream cannot
  trigger a storm of refreshes.
- **Apply collision checks on every reload path** (Docker), so a server added
  mid-session cannot take over an existing tool name.
- **Scan for secrets on both sides of the call** (Docker `--block-secrets`,
  Lasso `basic`) and log only the shape of the arguments.
- **Follow the authorization spec for upstreams:** PKCE with S256, `resource`
  on every authorization and token request, one token per upstream, and
  refresh-token rotation.

**Worth avoiding**

- **Treating a refresh as trust.** Accepting whatever `list_changed` delivers
  lets a server rug-pull in the middle of a session.
- **Sending tool definitions to a third-party service by default** (Snyk Agent
  Scan requires uploading them). Local checks should work without the network.
- **Forwarding the client's token upstream.** The spec forbids it, and it turns
  the gateway into a confused deputy.

- **Silent de-duplication** (vMCP `priority`): dropping a colliding tool with no
  signal causes baffling "tool not found" behaviour. Prefer prefixing plus
  explicit renames.
- **Shipping a working default encryption key** (ContextForge `my-test-salt`):
  generate a key on first run, or refuse to start without one.
- **Treating list filtering as access control.** If the call path does not
  re-check the subset, a client that knows the name can still call the tool.
- **A process per call for stateful servers** (MCPJungle's default). It breaks
  servers that keep sessions and multiplies spawn latency.
- **Proxy meta-tools as the only way to call** (`call_tool`, `use_tool`,
  `mcp-exec`). The client's permission rules, hooks and transcripts only ever
  see the meta-tool name.
- **Isolation that fails silently.** ToolHive's proxy-variable egress control
  breaks raw-socket servers without any error. Isolation should say what it
  blocked.
