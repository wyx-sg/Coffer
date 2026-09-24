---
title: What is Coffer?
description: Coffer is a local daemon and vault that every AI coding agent on your machine connects to, so MCP servers, skills, knowledge, memory and model providers are set up once and shared.
---

# What is Coffer?

Coffer is a local-first vault for AI coding agents. It is one daemon on your machine that Claude Code and Codex both connect to, so you set up MCP servers, skills, knowledge, memory and model providers once instead of once per agent. This page is for anyone deciding whether Coffer fits how they work. It covers the problem Coffer solves, what it manages, where you use it, and what it is not.

## The problem

Each AI coding agent keeps its own copy of everything:

- **MCP servers.** Claude Code reads them from `~/.claude.json`, and Codex from `~/.codex/config.toml`. You add a server to one agent, forget the other, and the two lists drift apart.
- **Skills.** Each agent has its own `skills/` directory. A skill you improve in one directory stays out of date in the other.
- **Memory.** Claude Code writes notes about your projects to its own memory, and so does Codex. Neither can read the other's, so you teach each agent the same thing again.
- **Keys and providers.** Moving to a different model gateway means editing each agent's config by hand, with the API key pasted into several files.

All of this lives in files the agents own and nothing connects. The more agents you use, the more copies there are.

## What Coffer is

Coffer is a **daemon plus a vault**:

- **`coffer-daemon`** is a long-running process that listens on `127.0.0.1` (port 8000 by default). It holds all of Coffer's state and serves the MCP endpoint, the REST API and the web UI.
- **The vault** is the directory `~/.coffer`. It contains a SQLite database for configuration, plain-file trees for skills, knowledge and memory, and an encrypted credential store.
- **`coffer-mcp-shim`** is a small stdio program that each agent starts as an ordinary MCP server. It finds the running daemon, starting one if none is running, and forwards the session to it.

When you run `coffer agent mcp install claude-code`, Coffer writes one `coffer` entry into Claude Code's MCP config. From then on, Claude Code reaches every MCP server you register in Coffer through that one entry.

## What it manages

Everything Coffer manages is a **resource** of one of seven **kinds**. Every resource has an immutable id, a name, an on/off switch and an audit trail.

| Kind | What it is | Guide |
| --- | --- | --- |
| `mcp_server` | An upstream MCP server (stdio or HTTP) that Coffer runs and re-exposes to every agent | [MCP servers](/guides/mcp-servers) |
| `agent` | A registered local coding agent: Claude Code or Codex | [Agents](/guides/agents) |
| `skill` | An [AgentSkills](https://agentskills.io) folder, delivered into agents' `skills/` directories | [Skills](/guides/skills) |
| `knowledge` | A collection: a folder of Markdown documents under `~/.coffer/knowledge/` | [Knowledge](/guides/knowledge) |
| `memory` | A partition of notes that Coffer distils from the agents' own memory, one per repository plus `global` | [Memory](/guides/memory) |
| `channel` | A Telegram or SeaTalk bot you use to chat with your agents from your phone | [Channels](/guides/channels) |
| `provider` | A model-provider profile (protocol, base URL, key) that Coffer writes into each agent's config | [Model providers](/guides/providers) |

Coffer also provides some capabilities that are not resource kinds: an encrypted [credential store](/guides/credentials), a web [Chat](/guides/chat) page, an [activity and audit](/guides/activity) record, and [vault sync](/guides/vault-sync) with a git remote you own.

## Where you use it

Every surface talks to the same daemon, so a change made in one shows up in all the others.

| Surface | What it is for |
| --- | --- |
| **CLI** (`coffer …`) | Scripting and terminal work. Any command that needs the daemon starts it if it is not already running. See the [CLI reference](/reference/cli). |
| **Web UI** | Browsing and editing everything. The daemon serves it at its own address, and `coffer open` opens it with you already signed in. See [Web UI](/guides/web-ui). |
| **Desktop app** | The same UI in a native macOS window, with a Dock icon and a menu-bar icon. It starts the daemon for you. See [Desktop app](/guides/desktop-app). |
| **MCP endpoint** | Where agents connect, through `coffer-mcp-shim`. Agents see upstream tools plus Coffer's own `coffer__*` tools. See [Connect a client](/guides/connect-a-client). |
| **Channels** | Telegram and SeaTalk bots that let you drive your agents and receive notifications from your phone. See [Channels](/guides/channels). |

## What Coffer is not

- **Not a cloud service.** Coffer has no hosted backend and no account. The API binds to loopback only. Cloud services appear only as the model providers and MCP servers you choose to use. If you sync a vault between your machines, it goes through a git repository you own, and each machine keeps a complete copy.
- **Not an agent.** Coffer does not act as an assistant you chat with. Its Chat page and channels drive *your* agents (Claude Code or Codex). Coffer's own model runs only internal background jobs: knowledge curation, memory distillation, sync conflict resolution and voice transcription.
- **Not an orchestrator.** Coffer does not plan work or pass tasks from one agent to another. It is the shared layer beneath your agents: the tools, files and settings they all use.
- **Not a replacement for an agent's own configuration.** An agent's files remain the source of truth. Coffer writes only the documented entries it manages, atomically and with a `.bak` backup, and reads the rest when it needs them.

## Supported platforms and agents

| | Supported |
| --- | --- |
| Agents | Claude Code (`claude_code`) and Codex (`codex`) |
| Prebuilt binaries and desktop app | macOS on Apple silicon (arm64) |
| From source | Python 3.12 or later. The release builds and the login service target macOS. |
| MCP clients | Any client that can run a stdio MCP server can use `coffer-mcp-shim`. Only Claude Code and Codex get one-step install, skill delivery and provider switching. |

::: info Experimental features
Three capabilities are experimental and can be switched on or off on each machine: **Sync**, **Knowledge** and **Memory**. A release build (the `stable` channel) starts with them off. A build from source (the `dev` channel) starts with them on. You can switch them under **Settings → General** or with `coffer daemon features enable <key>`. See [Experimental features](/guides/experimental-features).
:::

## Next steps

- [Why Coffer](/start/why-coffer): the design decisions behind Coffer and what they mean for you.
- [Install](/start/install): every way to install Coffer.
- [Quickstart](/start/quickstart): connect Claude Code, register an MCP server and deliver a skill in about 15 minutes.
- [Core concepts](/start/concepts): the terms the rest of the docs use.
