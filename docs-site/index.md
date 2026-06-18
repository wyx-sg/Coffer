---
layout: home
hero:
  name: Coffer
  text: Local-first AI agent vault
  tagline: One secure, shared interface for every AI agent on your machine. Configure your tools, skills, knowledge, and memory once — every agent sees the same vault. Nothing leaves your machine.
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
    details: Keep one master skill library and deliver it into each agent; curate knowledge bases your agents can search; share one memory across every agent.
  - title: Chat with any agent
    details: Talk to Coffer's built-in agent — or drive Claude Code and Codex — from a streamed chat, in the web or desktop app.
  - title: Reach agents anywhere
    details: Pair a Telegram or SeaTalk channel and chat with your agents from your phone. Multi-machine sync keeps every machine consistent over a git repo you own.
  - title: CLI · Web · Desktop
    details: Drive the whole vault from a terminal, a local web UI, or the desktop app. Agents auto-discover the daemon — no port or token wiring.
---

## How it works

```mermaid
flowchart LR
  subgraph You["You"]
    UI["CLI · Web · Desktop"]
    IM["Telegram · SeaTalk"]
  end
  A["AI agents<br/>Claude Code · Codex · Cursor"] -->|MCP| D
  UI --> D
  IM --> D
  D["coffer-daemon<br/>the vault: MCP gateway · skills · knowledge · memory · agents · chat"]
  D -->|namespaced tools| U["Upstream MCP servers"]
  D -->|chat| L["LLM providers"]
  D -->|sync| G["Your git remote"]
```

Coffer is a long-lived local daemon that holds your vault. The MCP gateway is one part of it: every AI agent connects through one auto-discovering endpoint and sees the same tools, skills, knowledge, and memory — while secrets stay encrypted and nothing leaves your machine unless you sync it to a git remote you own.

## Quickstart

```bash
# Aggregate an upstream MCP server, then point Claude Code at Coffer.
coffer mcp add filesystem --stdio "npx -y @modelcontextprotocol/server-filesystem /tmp"
claude mcp add coffer coffer-mcp-shim

# Curate a knowledge base and a shared skill — your agents pick them up automatically.
coffer kb create handbook
coffer skill import ./my-skill

# Chat with Coffer's built-in agent from the terminal.
coffer chat -m "what MCP servers and knowledge bases do I have?"
```

[Read the full guide →](/guide/getting-started)
