# Upstreams Speak stdio or Streamable HTTP; the Old SSE Transport Stays With the Agent

**Status**: Accepted
**Date**: 2026-11-06
**Deciders**: Yuxing Wu
**Related**: [Session Subprocess Model](session-subprocess-model.md), spec agent-registry "Plan an import of agents' direct MCP entries", spec mcp-gateway "Forward tools, resources and prompts"

## Context

MCP has had two remote transports. The 2024-11-05 specification defined
**HTTP+SSE**: the client opens a long-lived `GET` on an SSE endpoint, the server
names a second URL in its first event, and the client `POST`s requests there.
The 2025-03-26 specification replaced it with **Streamable HTTP** (one
endpoint, `POST` per message, an optional SSE stream per response) and kept
HTTP+SSE only as a deprecated transport for backwards compatibility.

Coffer's gateway reaches remote upstreams with the MCP SDK's Streamable HTTP
client only. An agent's config can still hold an old entry
(`"type": "sse"` in Claude Code's `.claude.json`). Until now Coffer read every
entry with a URL as an HTTP server, so importing or adopting an SSE entry
registered a server that could never connect, and removed the working entry
from the agent's file.

Comparable tools: Claude Code still accepts `sse` entries and its docs mark
the transport deprecated in favour of HTTP; the MCP SDKs keep an SSE client for
old servers. The agents Coffer serves can therefore reach an SSE server
themselves.

## Options Considered

### Option A — Recognise SSE entries and leave them with the agent (chosen)

An entry whose `type` is `sse` is listed on the agent's MCP servers tab and
marked as the old transport. Import plans report it as unavailable and
adoption refuses it, both with `MCP_SSE_NOT_SUPPORTED`, so the entry stays in
the agent's file, where the agent keeps reaching the server itself.

- Pros: no broken server is ever registered and no working entry is removed;
  a few lines in the entry parser and two refusals; nothing new to maintain.
- Cons: an SSE server is not curated, recorded or tiered by Coffer.
- Why it wins: the transport is deprecated and the agent already speaks it;
  the person loses nothing they had.

### Option B — Support SSE upstreams in the gateway

Add the SDK's SSE client beside the Streamable HTTP one, with its own
connection lifecycle (a long-lived `GET`, a second endpoint, reconnects).

- Pros: every remote server could move into Coffer.
- Cons: a second remote transport to supervise, probe, test and document, for
  a transport the specification deprecated; every server that still speaks only
  SSE is on its way to Streamable HTTP.
- Loses: Coffer's rule is to do what the agent cannot. The agent can reach an
  SSE server already.

### Option C — Read SSE entries as HTTP (the previous behaviour)

- Cons: the registered server never connects, and the entry that worked is
  gone from the agent's file.
- Loses: it breaks a working setup silently.

## Decision

Coffer's upstreams are stdio or Streamable HTTP. An agent's `type: "sse"`
entry is listed as such and is never imported or adopted
(`MCP_SSE_NOT_SUPPORTED`, 422); it stays with the agent.

## Consequences

- A server that offers both transports is added by its Streamable HTTP URL,
  usually the same host with `/mcp` in place of `/sse`; the refusal says so.
- If a server the person needs speaks only SSE and must be curated by Coffer,
  Option B is the change to reopen; it would go in `docs/TODO.md` first.
