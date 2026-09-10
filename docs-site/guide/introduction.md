# Introduction

Coffer is a local-first **AI agent vault** — one secure, shared interface for every AI agent on your machine.

Coffer is a daemon + CLI + a web UI the daemon serves itself. It started as a unified **MCP gateway** — aggregating upstream MCP servers and re-exposing them to MCP clients (Claude Code, Codex) through one namespaced surface — and grew into a vault that also manages your **skills**, shared **knowledge**, and registered **agents**, reachable over **channels** and carried to another machine by **export and import**. Configure once; every agent sees the same vault. All state lives on your machine — no cloud accounts, no vendor lock-in.

## Why Coffer?

Before Coffer, every AI client kept its own siloed configuration. Adding an MCP server, a skill, or something worth remembering meant updating Claude Code, Codex, and every future client separately — the same thing registered over and over, and a change in one place never propagated to the others.

Coffer is the single source of truth instead. Register a tool, deliver a skill, ingest a document, or write down a fact **once** in Coffer, and every agent that connects sees it. Secrets are encrypted at rest behind a master key you control, every action is audited, and nothing leaves your machine unless you sync it to a git remote you own.

### What Coffer manages

| Kind                                     | What it is                                                                                               |
| ---------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| [MCP servers](/guide/register-server)    | Aggregate upstream MCP servers; re-expose their tools namespaced through one endpoint.                   |
| [Agents](/guide/agents)                  | Detect and register Claude Code / Codex; edit their config, deliver skills, install Coffer's MCP server. |
| [Skills](/guide/skills)                  | One master skill library, delivered into the agents you choose.                                          |
| [Knowledge](/guide/knowledge)            | One store, shared by every agent: the entries they write and the documents you ingest, under one search. |
| [Model providers](/guide/web-ui)         | The vendor endpoints Coffer holds keys for, and the connection its own engine runs on.                   |
| [Channels](/guide/channels)              | Reach your agents from Telegram or SeaTalk — the way you actually talk to them.                          |

Plus two cross-cutting capabilities: an [encrypted credential store](/guide/credentials) and [vault export and import](/guide/sync).

### Local-first by design

All user state stays on your machine. Cloud services are LLM and tool providers only — they never become the system of record for any vault state. The HTTP API binds to `127.0.0.1`. Your configuration, credentials, and audit history are yours alone; secrets are encrypted at rest and travel only as ciphertext, only when you explicitly export them.

[Get started →](/guide/getting-started)
