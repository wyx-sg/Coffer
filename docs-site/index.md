---
layout: home
hero:
  name: Coffer
  text: Local-first AI agent vault
  tagline: Manage all your MCP servers from one place. Configure once; every client sees the same tools.
  actions:
    - theme: brand
      text: Get started
      link: /guide/getting-started
    - theme: alt
      text: View on GitHub
      link: https://github.com/wyx-sg/Coffer
features:
  - title: Local-first
    details: All state lives on your machine — no cloud accounts, no vendor lock-in.
  - title: One unified surface
    details: Aggregate upstream MCP servers and re-expose them namespaced as &lt;server&gt;__&lt;tool&gt;.
  - title: Configure once
    details: Claude Code, Codex, and every other MCP client see exactly the same tools.
  - title: Agent registry
    details: Detect and register your local AI coding agents, edit their config files, and one-click install Coffer into Claude Code or Codex.
  - title: Auto-discovering shim
    details: coffer-mcp-shim finds (or spawns) the daemon — no port or token wiring.
  - title: CLI · Web · Desktop
    details: Drive the gateway from a terminal, a web UI, or the desktop app.
---

<div style="text-align:center; margin: 2.5rem 0 1rem;">
  <img src="/screenshots/resources.png" alt="Coffer — manage all your MCP servers from one place" style="border-radius:12px; box-shadow:0 10px 40px rgba(31,27,23,.14); max-width:100%; height:auto;" />
</div>

<div style="display:flex; gap:1rem; flex-wrap:wrap; justify-content:center; margin-bottom:1rem;">
  <img src="/screenshots/server-detail.png" alt="Per-server detail — health, transport, and discovered capabilities" style="border-radius:12px; box-shadow:0 10px 40px rgba(31,27,23,.14); flex:1 1 360px; min-width:0; max-width:49%; height:auto;" />
  <img src="/screenshots/observability.png" alt="Audit log — every lifecycle change to any resource or capability" style="border-radius:12px; box-shadow:0 10px 40px rgba(31,27,23,.14); flex:1 1 360px; min-width:0; max-width:49%; height:auto;" />
</div>

## How it works

```mermaid
flowchart LR
  C["MCP clients<br/>Claude Code · Codex"] --> S["coffer-mcp-shim<br/>auto-discovers daemon"]
  S --> D["coffer-daemon<br/>unified gateway"]
  D --> U["Upstream MCP servers"]
```

## Quickstart

```bash
coffer mcp add filesystem --stdio "npx -y @modelcontextprotocol/server-filesystem /tmp"
claude mcp add coffer coffer-mcp-shim
```

[Read the full guide →](/guide/getting-started)
