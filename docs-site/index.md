---
layout: home
hero:
  name: Coffer
  text: Local-first AI agent vault
  tagline: One secure, shared interface for every AI agent on your machine. Configure your tools, skills, and knowledge once — every agent sees the same vault. Nothing leaves your machine.
  actions:
    - theme: brand
      text: Get started
      link: /guide/getting-started
    - theme: alt
      text: View on GitHub
      link: https://github.com/wyx-sg/Coffer
features:
  - title: Local-first & encrypted
    details: All state lives on your machine — no cloud accounts, no vendor lock-in. Secrets are Fernet-encrypted at rest behind a master key you control.
  - title: One MCP endpoint
    details: Aggregate every upstream MCP server and re-expose their tools namespaced as &lt;server&gt;__&lt;tool&gt;. Claude Code, Codex, and any MCP client see exactly the same tools.
  - title: Skills · Knowledge · Memory
    details: Keep one master skill library and deliver it into each agent; keep one knowledge tree of Markdown files — ingested documents and the entries agents write — that every agent reads with its own tools and adds to through coffer__write; and see what your agents have already learned, aggregated out of their own memory.
  - title: Chat with any agent
    details: Drive Claude Code or Codex from a streamed chat in the web UI — your own agents, on your own machine, with the whole vault behind them.
  - title: Reach agents anywhere
    details: Pair a Telegram or SeaTalk channel and chat with your agents from your phone. Working across two machines? Point both at a git remote you own and the vault converges.
  - title: CLI · Web UI · Desktop app
    details: Drive the whole vault from a terminal, from a local web UI the daemon serves itself (`coffer open` and you are in), or from a native app with a Dock icon and a tray. Agents auto-discover the daemon — no port or token wiring.
---

## How it works

```mermaid
flowchart LR
  subgraph You["You"]
    UI["CLI · Web UI · Coffer.app"]
    IM["Telegram · SeaTalk"]
  end
  A["AI agents<br/>Claude Code · Codex"] -->|MCP| D
  UI --> D
  IM --> D
  D["coffer-daemon<br/>the vault: MCP gateway · skills · knowledge · memory · agents · chat"]
  D -->|namespaced tools| U["Upstream MCP servers"]
  D -->|chat| L["LLM providers"]
  D <-->|converge| G["A git remote you own"]
```

Coffer is a long-lived local daemon that holds your vault. The MCP gateway is one part of it: every AI agent connects through one auto-discovering endpoint and sees the same tools, skills, and knowledge — while secrets stay encrypted and nothing leaves your machine. Working across two of your own machines is opt-in: point both at a git remote you own, and the vault converges in both directions, with secrets travelling as ciphertext only.

## Quickstart

```bash
# Aggregate an upstream MCP server, then point Claude Code at Coffer.
coffer mcp add filesystem --stdio "npx -y @modelcontextprotocol/server-filesystem /tmp"
claude mcp add coffer coffer-mcp-shim

# Curate a knowledge collection and a shared skill — your agents pick them up automatically.
coffer knowledge create handbook
coffer skill import ./my-skill

# Reach your agents from your phone — pair a channel, then chat over IM.
coffer credentials set telegram.token
coffer channel register work --type telegram --bot-token-ref telegram.token
coffer channel pair work
```

[Read the full guide →](/guide/getting-started)
