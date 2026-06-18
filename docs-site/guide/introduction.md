# Introduction

Coffer is a local-first **AI agent vault** — one secure, shared interface for every AI agent on your machine.

Coffer is a daemon + CLI + desktop app. It started as a unified **MCP gateway** — aggregating upstream MCP servers and re-exposing them to MCP clients (Claude Code, Codex) through one namespaced surface — and grew into a vault that also manages your **skills**, **knowledge bases**, shared **memory**, registered **agents**, and **chat**, reachable over **channels** and kept consistent across machines by **sync**. Configure once; every agent sees the same vault. All state lives on your machine — no cloud accounts, no vendor lock-in.

## Why Coffer?

Before Coffer, every AI client kept its own siloed configuration. Adding an MCP server, a skill, or a memory meant updating Claude Code, Codex, and every future client separately — the same thing registered over and over, and a change in one place never propagated to the others.

Coffer is the single source of truth instead. Register a tool, deliver a skill, curate a knowledge base, or write a memory **once** in Coffer, and every agent that connects sees it. Secrets are encrypted at rest behind a master key you control, every action is audited, and nothing leaves your machine unless you sync it to a git remote you own.

### What Coffer manages

| Kind                                     | What it is                                                                                               |
| ---------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| [MCP servers](/guide/register-server)    | Aggregate upstream MCP servers; re-expose their tools namespaced through one endpoint.                   |
| [Agents](/guide/agents)                  | Detect and register Claude Code / Codex; edit their config, deliver skills, install Coffer's MCP server. |
| [Skills](/guide/skills)                  | One master skill library, delivered into the agents you choose.                                          |
| [Knowledge bases](/guide/knowledge-base) | Document stores your agents can search (grep / keyword / vector), never write.                           |
| [Memory](/guide/memory)                  | One shared set of facts across all agents, projected natively into each.                                 |
| [Chat](/guide/chat)                      | Talk to Coffer's built-in agent, or drive Claude Code / Codex.                                           |
| [Channels](/guide/channels)              | Reach your agents from Telegram or SeaTalk.                                                              |

Plus two cross-cutting capabilities: an [encrypted credential store](/guide/credentials) and [multi-machine sync](/guide/sync).

### Local-first by design

All user state stays on your machine. Cloud services are LLM and tool providers only — they never become the system of record for any vault state. The HTTP API binds to `127.0.0.1`. Your configuration, credentials, and audit history are yours alone; secrets are encrypted at rest and travel only as ciphertext, only when you choose to sync.

[Get started →](/guide/getting-started)
