# Introduction

Coffer is a local-first AI agent vault that lets you manage all your MCP servers from one place.

Coffer is a daemon + CLI that aggregates upstream MCP servers and re-exposes them to MCP clients (Claude Code, Codex) through a unified, namespaced surface. Configure once; every client sees the same tools. All state lives on your machine — no cloud accounts, no vendor lock-in.

## Why Coffer?

Before Coffer, adding a new MCP server meant updating the configuration of every AI client separately — Claude Code, Codex, and any future clients. Each client kept its own list, so the same server had to be registered over and over, and a change in one place did not propagate to the others.

Coffer solves this by acting as the single source of truth for your MCP servers. Register a server once in Coffer, and every client that connects through the shim automatically sees the same set of tools.

### Local-first by design

All user state stays on your machine. Cloud services are LLM and tool providers only — they never become the system of record for any vault state. The HTTP API binds to `127.0.0.1`. Your configuration, credentials, and audit history are yours alone.

[Get started →](/guide/getting-started)
