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
  - title: Skills · Knowledge
    details: Keep one master skill library and deliver it into each agent; keep one knowledge store — ingested documents and the entries agents write — that every agent searches and contributes to.
  - title: Chat with any agent
    details: Talk to Coffer's built-in agent — or drive Claude Code and Codex — from a streamed chat in the web UI.
  - title: Reach agents anywhere
    details: Pair a Telegram or SeaTalk channel and chat with your agents from your phone. Moving to a new machine? Export the whole vault to a directory and import it there.
  - title: CLI · Web UI
    details: Drive the whole vault from a terminal, or from a local web UI the daemon serves itself — `coffer open` and you are in. Agents auto-discover the daemon — no port or token wiring.
---

## How it works

```mermaid
flowchart LR
  subgraph You["You"]
    UI["CLI · Web UI"]
    IM["Telegram · SeaTalk"]
  end
  A["AI agents<br/>Claude Code · Codex"] -->|MCP| D
  UI --> D
  IM --> D
  D["coffer-daemon<br/>the vault: MCP gateway · skills · knowledge · agents · chat"]
  D -->|namespaced tools| U["Upstream MCP servers"]
  D -->|chat| L["LLM providers"]
  D -->|export / import| G["A directory you carry"]
```

Coffer is a long-lived local daemon that holds your vault. The MCP gateway is one part of it: every AI agent connects through one auto-discovering endpoint and sees the same tools, skills, and knowledge — while secrets stay encrypted and nothing leaves your machine. Moving to another of your own machines is an explicit act: export the vault to a directory, carry it across, import it there.

## Quickstart

```bash
# Aggregate an upstream MCP server, then point Claude Code at Coffer.
coffer mcp add filesystem --stdio "npx -y @modelcontextprotocol/server-filesystem /tmp"
claude mcp add coffer coffer-mcp-shim

# Curate a knowledge collection and a shared skill — your agents pick them up automatically.
coffer knowledge create handbook
coffer skill import ./my-skill

# Reach your agents from your phone — pair a channel, then chat over IM.
coffer channel add work --type telegram --credential-ref telegram.token
coffer channel pairing-code work
```

[Read the full guide →](/guide/getting-started)
