# One Upstream Subprocess Set Per Downstream Client Session

**Status**: Accepted
**Date**: 2026-05-20
**Deciders**: Yuxing Wu
**Related**: spec `mcp-gateway` (Edge Cases — concurrent clients), [Detect-or-Spawn](daemon-detect-or-spawn.md)

## Context

When two MCP clients (e.g., Claude Code and Codex) connect to Coffer at the
same time, the gateway must decide how upstream MCP server subprocesses are
managed:

- One upstream subprocess shared across all downstream client sessions, with
  the gateway multiplexing MCP protocol traffic.
- One independent set of upstream subprocesses per downstream client session,
  with no sharing.

MCP is a per-session protocol: each connection begins with an `initialize`
handshake that negotiates protocol version and client / server capabilities,
and the server may then carry session-scoped state (subscriptions,
notification routing, progress tokens). Sharing one server across multiple
clients implies the gateway re-implementing session semantics on top of MCP —
not part of the protocol's design.

The cost of _not_ sharing is N × M subprocesses (N concurrent client sessions
× M registered upstreams). On a single-user developer machine N rarely exceeds
3, and most stdio MCP servers start in under a second and use less than 100 MB
of memory.

## Decision

**One independent set of upstream subprocesses per downstream client session.**

- A `MCPGatewaySession` is created when a downstream client connects (through
  the HTTP/SSE endpoint or through `coffer-mcp-shim`).
- Within that session, each upstream MCP server is spawned **lazily** — on
  first need (first `tools/list` or first call routed to it) — not eagerly on
  session start.
- All subprocesses owned by the session are reaped on session disposal.
- Sessions do not share subprocess state across each other.

## Consequences

**Positive**

- MCP protocol correctness preserved: each session is one upstream session, no
  multiplexing layer required.
- Implementation simplicity: the gateway forwards JSON-RPC over a single
  upstream connection per `(session, upstream)` pair, with straightforward
  request-id correlation.
- Failure isolation: an upstream that crashes inside one client's session does
  not affect another client's session.
- Capability discovery cache (see [Capability State Model](capability-state-model.md)) is naturally per-session, fitting
  the per-session lifetime of the subprocess connection.

**Negative**

- Resource cost grows with N × M. With 3 concurrent clients and 10 registered
  upstreams, that's up to 30 subprocesses. For the current user base (single
  developer) this is acceptable. For a hypothetical fleet deployment, a
  multiplexing layer would be revisited.
- Cold-start latency on first call: each session pays the first upstream's
  spawn + initialize time once. Mitigated by lazy spawn (only upstreams that
  are actually used pay this cost).

**Operational follow-on**

- Subprocess supervision: spawn, health check, respawn-with-backoff, and reap
  are implemented at the session level. Orphan handling on daemon crash is a
  separate concern (PID files swept on next daemon startup).

## Alternatives Considered

**Shared upstream + session multiplexing at the gateway.** Rejected.

- MCP's per-session `initialize` handshake and capabilities negotiation are
  not designed to fan out: serving two clients with different declared
  capabilities from one upstream session forces the gateway to fabricate or
  proxy state mid-stream.
- Notification routing (which client should receive `tools/list_changed`?
  `progress` for which request id?) becomes a non-trivial bookkeeping layer.
- Estimated implementation effort: ~3× per-session approach, with substantial
  risk of subtle bugs (notification leakage between clients, capability
  mismatch).
- Resource savings (one subprocess vs N) do not justify the complexity at
  single-user scale.

**Eager spawn (all registered upstreams started on session begin).** Rejected.

- Wasteful when a client only uses 2 of 10 registered servers in a session.
- Adds noticeable latency to session start, where users notice it most.
- Lazy + 60s capability cache gives the same eventual-warmth without the
  upfront cost.

**Daemon-level singleton subprocess pool (shared across all sessions).**
Equivalent in spirit to multiplexing; same rejection reasons. Additionally, a
daemon-restart would invalidate every session's state at once, which the
per-session model already isolates better.

## Implementation notes

What one session forwards, as the gateway implements it today:

- **Coffer is the server downstream and a client upstream** — two separate
  `initialize` handshakes. Coffer answers the client's `initialize` itself and
  issues its own to each upstream on first need.
- **Requests forwarded upstream**: `tools/list`, `tools/call`, `resources/list`,
  `resources/read`, `prompts/list` and `prompts/get`
  (`infrastructure/mcp/dispatch.py`, one table both transports share). Any
  other method is refused rather than passed through blind.
- **Names are rewritten both ways**: a tool or prompt is presented as
  `<server>__<name>`, a resource URI as `coffer://<server>/<uri>`
  (`domain/mcp/namespace.py`). The `__` separator was chosen because `:`,
  `.`, `/` and `-` are all legal inside upstream tool names.
- **Upstream → client requests** (`sampling/createMessage`, `roots/list`) are
  relayed to the session's own client; sampling is relayed only when that
  client declared `sampling` in its handshake, and refused otherwise
  (`application/mcp/gateway_server_requests.py`).
- **Upstream notifications**: the three `list_changed` notifications and
  `resources/updated` invalidate the session's discovery cache and are
  forwarded (the URI rewritten); `notifications/message` and
  `notifications/progress` are dropped rather than forwarded
  (`application/mcp/gateway_notifications.py`). Public MCP gateways make the
  same progress choice. A long `tools/call` is still protected: it is issued
  with a per-request read timeout and a progress callback, so a tool that
  reports progress is not cut off.
- An upstream's stderr goes to its own file, `~/.coffer/logs/upstream/<name>.log`,
  not to the daemon's log.
