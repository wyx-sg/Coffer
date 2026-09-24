---
layout: home
title: Coffer
description: Coffer is a local-first vault for AI coding agents. It gives Claude Code and Codex one MCP endpoint, one skill library, and shared knowledge, memory and model providers, all kept on your machine.

hero:
  name: Coffer
  text: A local vault for your AI coding agents
  tagline: Set up your MCP servers, skills, knowledge and model providers once, and every agent on your machine uses the same setup.
  actions:
    - theme: brand
      text: Get started
      link: /start/quickstart
    - theme: alt
      text: What is Coffer?
      link: /start/
    - theme: alt
      text: GitHub
      link: https://github.com/wyx-sg/Coffer

features:
  - title: One MCP endpoint for every agent
    details: Register an upstream MCP server once. Claude Code and Codex connect to Coffer's single endpoint and see its tools as server__tool, and you choose which tools each server exposes.
    link: /guides/mcp-servers
    linkText: MCP servers
  - title: One skill library, delivered
    details: Import a skill folder in the AgentSkills format once. Coffer links it into each agent's skills directory, keeps the links correct, and lets you choose which agents get it.
    link: /guides/skills
    linkText: Skills
  - title: Knowledge and memory, shared
    details: Keep Markdown knowledge that every agent reads with its own file tools. Coffer also reads each agent's own memory and turns it into notes that the other agents can use too.
    link: /guides/knowledge
    linkText: Knowledge
  - title: Switch model providers once
    details: Store a provider profile (a base URL and a key) and switch to it. Coffer writes the change into each agent's own config file.
    link: /guides/providers
    linkText: Model providers
  - title: Chat from a browser or your phone
    details: Drive Claude Code or Codex from the web Chat page, or pair a Telegram or SeaTalk bot and message your agents from anywhere.
    link: /guides/chat
    linkText: Chat
  - title: Local-first by design
    details: The daemon listens only on 127.0.0.1. Secrets are Fernet ciphertext under a master key you hold. To share a vault between your machines, sync it through a git remote you own.
    link: /start/why-coffer
    linkText: Why Coffer
---

## How it works

Coffer is a daemon that runs on your machine and holds your vault in `~/.coffer`. Agents reach it through a small stdio shim that Coffer writes into each agent's MCP config. You manage it from the CLI, the web UI, the desktop app or a chat channel. All of these talk to the same daemon.

```mermaid
flowchart LR
  subgraph agents["Your agents"]
    CC["Claude Code"]
    CX["Codex"]
  end
  subgraph surfaces["Your surfaces"]
    CLI["coffer CLI"]
    WEB["Web UI and desktop app"]
    IM["Telegram and SeaTalk"]
  end
  CC --> SHIM["coffer-mcp-shim"]
  CX --> SHIM
  SHIM -->|"MCP over loopback"| D["coffer-daemon"]
  CLI -->|"REST"| D
  WEB -->|"REST"| D
  IM --> D
  D <--> V[("~/.coffer vault")]
  D --> UP["Upstream MCP servers"]
  D --> PR["Model providers"]
  D -.->|"skill links, provider config"| agents
```

- **The gateway.** Each agent session gets its own set of upstream MCP servers. Coffer lists their tools under a `<server>__<tool>` prefix, next to its own `coffer__*` tools.
- **Delivery into agents.** Skills arrive as directory links in each agent's `skills/` folder. Provider switches are written into the agent's own config file. Coffer never copies an agent's files into its database.
- **The vault.** Configuration and state live in `~/.coffer/coffer.db` (SQLite). Skills, knowledge and memory are plain files in the same directory, and secrets are encrypted.

The [architecture overview](/architecture/) explains each part in depth.

## Install in one line

On a Mac with Apple silicon:

```sh
curl -fsSL --proto '=https' --tlsv1.2 https://wyx-sg.github.io/Coffer/install.sh | sh
```

This installs `coffer`, `coffer-daemon` and `coffer-mcp-shim` into `~/.coffer/bin` and adds that directory to your `PATH`. The [install guide](/start/install) also covers the desktop app, building from source, upgrading and uninstalling.

::: warning No tagged release yet
The installer downloads from a tagged GitHub release, and none is published yet, so for now [install from source](/start/install#from-source).
:::

## Where to next

- **[Getting started](/start/)**: what Coffer is, why it works the way it does, and a [15-minute quickstart](/start/quickstart).
- **[Guides](/guides/agents)**: step-by-step tasks for agents, MCP servers, skills, knowledge, memory, providers, chat, channels and sync.
- **[Architecture](/architecture/)**: how the daemon, the gateway, the resource framework and the vault fit together, and the reasons behind the design.
- **[Reference](/reference/cli)**: every CLI command, MCP tool, REST route, configuration key and error code.
- **[Contributing](/contributing/)**: how to set up a development environment and change Coffer through its specs.
