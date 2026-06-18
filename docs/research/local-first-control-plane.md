# Competitive Research — Local-First AI-Agent / MCP Control Planes

> English: this file · 中文版: [local-first-control-plane.zh.md](./local-first-control-plane.zh.md)
>
> Internal competitive-research report on Coffer's overall positioning as a
> local-first vault. **Date:** 2026-06-16. **Method:** deep-research harness
> (this run's verification mostly succeeded — several claims 3-0 confirmed).

## 1. Landscape at a glance

A real category of "local control plane for AI agents" exists in 2026, but it is
**overwhelmingly MCP-centric**: almost every tool solves _per-client MCP config
sprawl_ — how MCP servers are installed, run, proxied, and authenticated — not
"a single vault for ALL of an agent's assets." They split on three axes:

| Axis                               | Behaviour                                   | Examples                                                 |
| ---------------------------------- | ------------------------------------------- | -------------------------------------------------------- |
| **Pure config managers**           | Centralize config; **no running gateway**   | mcpm v2                                                  |
| **Aggregating daemons / gateways** | One local endpoint in front of many servers | 1MCP, Station, ToolHive (vMCP), unrelated-ai/mcp-gateway |
| **Narrow auth shims**              | Front a single server; refuse to aggregate  | mcp-auth-proxy                                           |

**Local-first is a spectrum, and the market is drifting toward team/cloud:**
ToolHive, 1MCP, unrelated-ai are genuinely self-hostable OSS; **Station** nudges
toward its CloudShip backend; **Plugged.in**'s proxy is backend-dependent (needs
a separate plugged.in App + API key); **Toolbase** _deprecated its OSS Electron
desktop_ in favour of a hosted Cloudflare-containers web product.

### The players

- **ToolHive** (`stacklok/toolhive`, OSS) — the most complete, enterprise-grade
  local-first MCP control plane, positioned explicitly as the anti-SaaS option
  for compliance. **Runs every MCP server in an isolated Docker/Podman
  container** sourced from a vetted registry / any container / package managers
  (`uvx://`, `npx://`, `go://`), fronted by a **vMCP gateway that aggregates
  upstreams behind one endpoint**, with built-in secrets management (encrypted
  OS-keyring, 1Password read-only, env), enterprise OAuth, and network-access
  filtering. _Caveat:_ production vMCP runs chiefly via a Kubernetes Operator
  (team/cluster scope); MCPRemoteProxy + its vMCP auth are still in development;
  network isolation is HTTP/HTTPS-only. vMCP GA'd 2025-12-11. [confidence high —
  github.com/stacklok/toolhive; docs.stacklok.com]
- **mcpm** (`pathintegral-institute/mcpm.sh`, MIT CLI) — the canonical **pure
  config manager**: installs MCP servers once into a global workspace, organizes
  them with **virtual-tag "profiles"**, and syncs enable/disable/import across
  10+ named clients (Claude Desktop, Cursor, Windsurf, VS Code, Cline, Continue,
  Goose, 5ire, Roo, OpenCode). v2 **deliberately removed v1's "Router" daemon** —
  it centralizes configuration, not a running gateway. Actively maintained
  (v2.15.0, 2026-05-22). [confidence high]
- **1MCP** (`1mcp-app/agent`, Apache-2.0) — a clean local-first self-hosted
  **aggregator daemon**: `1mcp serve` consolidates many MCP servers into one
  runtime (stdio proxy + optional direct streamable-HTTP) to kill per-client
  wiring/auth/filtering sprawl. npm-installed, Docker-self-hostable, not cloud.
  **Documents no built-in secrets vault / envelope encryption** for upstream
  credentials (OAuth only gates access _to_ 1MCP). [confidence high]
- **Station** (`cloudshipai/station`) — self-hosted multi-port daemon that nudges
  toward the CloudShip backend.
- **Plugged.in** — proxy that depends on a separate hosted app + API key.
- **Toolbase** — deprecated its OSS desktop for a hosted web product.
- **mcp-auth-proxy** — a single-server OAuth/auth shim that explicitly refuses
  to aggregate.

## 2. Capability comparison

| Capability                         | ToolHive                 | mcpm             | 1MCP          | Station     | **Coffer**                                         |
| ---------------------------------- | ------------------------ | ---------------- | ------------- | ----------- | -------------------------------------------------- |
| Scope of assets managed            | MCP only                 | MCP only         | MCP only      | MCP only    | **MCP + agents + skills + KB + memory + channels** |
| Aggregating gateway                | ✅ vMCP                  | ❌ (config only) | ✅            | ✅          | ✅                                                 |
| Per-client / profile scoping       | ✅ vMCP virtual servers  | ✅ profiles      | partial       | ✅          | **❌ all-or-nothing per agent**                    |
| Upstream isolation/sandbox         | ✅ container per server  | ❌               | ❌            | partial     | **❌ bare subprocess**                             |
| Secrets management                 | ✅ keyring/1Password/env | ❌               | ❌            | partial     | **✅ envelope-encrypted store**                    |
| Files-as-truth + rebuildable index | ❌                       | n/a              | ❌            | ❌          | **✅**                                             |
| Vetted server registry / discovery | ✅                       | partial          | ❌            | ❌          | **❌**                                             |
| Single-user local-first framing    | team/K8s drift           | ✅               | ✅            | cloud drift | **✅ strict 127.0.0.1 single-user**                |
| Clients/agents covered             | many                     | 10+              | many          | many        | **2 enabled (4 hidden)**                           |
| OSS                                | ✅                       | ✅ MIT           | ✅ Apache-2.0 | partial     | ✅ MIT                                             |

## 3. How Coffer compares

**Where Coffer is genuinely unique.**

1. **Scope.** Coffer is the _only_ tool framing itself as a vault for **all**
   agent assets — MCP servers, agents, skills, knowledge, memory, channels — as
   one resource kind with shared identity/lifecycle/audit. Every competitor is
   MCP-only. This breadth is the moat.
2. **Files-as-truth + rebuildable index.** No competitor models its state as
   markdown-on-disk with a throwaway SQLite index. This is a durability and
   backup story none of them tell.
3. **Strict single-user local-first.** As the field drifts to team/cloud
   (ToolHive→K8s, Station→CloudShip, Toolbase→hosted, Plugged.in→backend),
   Coffer's 127.0.0.1 single-user vault is a deliberate, increasingly distinctive
   niche.

**Where Coffer overlaps / lags — and should borrow.**

1. **Upstream isolation (biggest security gap).** ToolHive runs **each MCP server
   in its own container**. Coffer spawns upstreams as bare subprocesses with no
   sandbox. For a tool that calls itself a "vault," running untrusted MCP servers
   unsandboxed is the sharpest gap. Borrow container/sandbox isolation (or at
   least opt-in).
2. **Per-client / profile scoping (fixes a known Coffer limitation).** mcpm
   _profiles_ and ToolHive _vMCP virtual servers_ both let you expose a _subset_
   of servers per client. This is exactly the cure for Coffer's all-or-nothing
   "whole gateway injected per agent." Adopt a profile/virtual-server concept so
   agent A can get GitHub while agent B does not.
3. **Network-egress filtering.** ToolHive filters each server's network access;
   Coffer guards only its own outbound (SSRF), not the upstreams it spawns.
4. **Vetted-server registry / discovery.** ToolHive ships a vetted registry;
   Coffer has none (same gap as the MCP-ecosystem report).
5. **Secrets-provider plugins.** ToolHive integrates 1Password; Coffer's store is
   self-contained — a 1Password/keyring provider plugin would be cheap parity.

## 4. Key takeaways for Coffer

1. **The "vault for ALL assets, single-user, local-first" positioning is unique
   and defensible** — no competitor goes beyond MCP. Make breadth the headline;
   it is the moat.
2. **Highest-leverage borrow: upstream sandboxing** (ToolHive container-per-server).
   Running untrusted MCP servers unsandboxed undercuts the "vault" promise.
3. **Second borrow: profiles / virtual servers** for per-agent scoping — the
   direct, proven cure for Coffer's all-or-nothing gateway injection.
4. **The team/cloud segment is wide open** because Coffer is deliberately
   single-user; that is a strategic choice to make consciously, not by default.
5. **Table-stakes parity:** a vetted-server registry + secrets-provider plugins
   (1Password) to match ToolHive/mcpm.

## 5. Sources

Primary (project repos/docs):

- github.com/stacklok/toolhive · docs.stacklok.com/toolhive _(confirmed: isolation, vMCP, secrets)_
- github.com/pathintegral-institute/mcpm.sh _(confirmed: profiles, v2 router removal)_
- github.com/1mcp-app/agent · docs.1mcp.app _(confirmed: aggregator, no secrets vault)_
- github.com/cloudshipai/station
- plugged.in (docs) · gettoolbase.ai (deprecation notice)
- mcp-auth-proxy (project README) · unrelated-ai/mcp-gateway

## Verification update (2026-06-19)

> Re-verification pass against the repo and primary vendor sources. Two of the
> three LOCAL claims about Coffer's MCP handling still hold (bare unsandboxed
> subprocess upstreams; SSRF guard covers only Coffer's own outbound). The
> "all-or-nothing per agent" claim has since flipped: per-agent MCP server
> scoping shipped in PR #108 / ADR-026 (2026-06-18) — moved to ✏️ Corrected
> below. The vMCP "GA'd 2025-12-11" date remains corrected (primary Stacklok docs
> do not substantiate it).

### ✅ Confirmed

- **Bare, unsandboxed subprocess upstreams.** Each stdio upstream is spawned via
  `mcp.client.stdio.stdio_client(StdioServerParameters(command, args, env, cwd))`
  as a direct child process. The only hardening is env scoping (CODE-027 minimal
  allowlist) plus PID-tracking / orphan-reaping — no Docker/Podman/seccomp/
  namespace/firejail/bubblewrap/chroot anywhere in `backend/coffer`. The single
  `sandbox` string in the codebase is `"sandbox": "danger-full-access"` in the
  Codex CLI agent provider (which _disables_ sandboxing — unrelated to MCP
  spawning). `repo:backend/coffer/infrastructure/mcp/subprocess.py`
- **SSRF guard covers only Coffer's own outbound, not spawned upstreams.**
  `ssrf_guard.py` (`check_url` / `is_blocked_host`) is imported by exactly two
  callers — `skill/source_fetcher.py` (git-URL validation for skill fetching) and
  `providers/provider_introspector.py` (provider URL introspection). Neither the
  MCP subprocess path nor the gateway applies it; spawned upstreams have
  unrestricted egress. `repo:backend/coffer/infrastructure/skill/ssrf_guard.py`
- **ToolHive MCPRemoteProxy still in development.** Confirmed verbatim:
  "MCPRemoteProxy support in vMCP is currently in development. vMCP can discover
  MCPRemoteProxy backends, but authentication between vMCP and MCPRemoteProxy is
  not yet fully implemented." https://docs.stacklok.com/toolhive/concepts/vmcp
- **mcpm v2.15.0, 2026-05-22.** Latest on PyPI is 2.15.0, released 2026-05-22
  (prior: 2.14.0 on 2026-03-27, 2.13.0 on 2026-01-15). https://pypi.org/project/mcpm/
- **1MCP documents no built-in secrets vault / envelope encryption.** The README
  frames auth as gating access _to_ the aggregator and shows no built-in secrets
  vault or envelope encryption for upstream credentials. (Negative finding —
  absence of a documented feature, not an explicit vendor denial.)
  https://github.com/1mcp-app/agent

### ✏️ Corrected

- **"All-or-nothing per agent" → resolved: per-agent MCP server scoping shipped.**
  The original ✅ bullet (and the §2 capability table, §3.2 and §4.3 "borrow"
  recommendations) called Coffer's gateway injection all-or-nothing — every
  gateway-installed agent saw the full set of enabled servers, with no
  subset/profile mechanism. That limitation is now **closed**: per-agent MCP
  server scoping shipped in **PR #108 / ADR-026** (2026-06-18). Each agent
  carries a scope **mode** — `auto` (default; every enabled server, new servers
  auto-included) or `selected` (an explicit server allowlist). The installed
  `coffer` entry stamps the agent's identity via `--agent <name>` (forwarded as
  an `X-Coffer-Agent` header), and the gateway enforces the **effective scope**
  (enabled ∩ allowlist) at `tools/list` / `resources/list` / `prompts/list`,
  `coffer__search_tools` ranking, **and** the direct `tools/call` /
  `resources/read` / `prompts/get` call path — so an out-of-scope tool cannot be
  listed, ranked, or called. The "all-or-nothing" gap is resolved; the
  competitive gap noted in §3.2 / §4.3 (mcpm profiles, ToolHive vMCP virtual
  servers) is now matched. `repo:docs/decisions/ADR-026-per-agent-mcp-scoping.md`
  · `repo:backend/coffer/application/agent/scope_service.py` ·
  `repo:backend/coffer/application/mcp/gateway.py`
  (`_effective_mcp_servers` / `authorize_server`). _Unchanged:_ the sandboxing
  gap above — upstreams are still bare subprocesses with no container isolation —
  remains, and scoping does not address it.
- **vMCP "GA'd 2025-12-11" → introduced 2025-12-08; no explicit GA date
  documented.** The MCPRemoteProxy "still in development" half holds, but the GA
  date is unsupported: the introduction announcement is dated 2025-12-08 and no
  primary Stacklok doc carries an explicit GA-on-Dec-11 statement.
  https://docs.stacklok.com/toolhive/concepts/vmcp

### ➕ Coverage added

- **Station** (`cloudshipai/station`) — open-source agent runtime that runs on
  your own infra but is explicitly built to connect _up_ to the CloudShip
  Platform (cloud) for centralized management, OAuth, analytics, and leadership
  reporting; confirms the "nudges toward CloudShip backend" framing.
  https://www.cloudshipai.com/station
- **Toolbase** (gettoolbase.ai) — the OSS desktop app is deprecated; users are
  pushed to the web product (old desktop preserved at `old.gettoolbase.ai`), with
  the platform now web/Cloudflare-hosted; confirms "deprecated its OSS desktop for
  a hosted web product." https://gettoolbase.ai/
- **Plugged.in** (`VeriTeknik/pluggedin-mcp-proxy`) — the proxy requires an API
  key from the hosted plugged.in App and fetches all tool/prompt/resource config
  from that backend; it is backend-dependent, not standalone-local; confirms
  "proxy depends on a separate hosted app + API key."
  https://github.com/VeriTeknik/pluggedin-mcp-proxy
