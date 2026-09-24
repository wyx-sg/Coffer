# One Upstream Subprocess Set Per Downstream Client Session

**Status**: Accepted
**Date**: 2026-05-20
**Deciders**: Yuxing Wu
**Related**: [Detect-or-Spawn](daemon-detect-or-spawn.md), [stdio Shim Bridge](stdio-shim-bridge.md), [Capability State Model](capability-state-model.md), [Tool Overload: Tier the List, Search the Rest](tool-overload-tier-the-list-search-the-rest.md), spec mcp-gateway "Present Coffer as one MCP server", spec mcp-gateway "Support stdio and HTTP upstreams", spec daemon "Own and reap the daemon's long-lived children"

## Context

Several MCP clients connect to Coffer's gateway at once — Claude Code and Codex
through their shims, and Coffer's own internal engine through an in-process
session. The gateway must decide how the upstream MCP servers behind it are
run: one upstream connection shared by every client session, or an independent
set per client session.

MCP is a per-session protocol. Each connection begins with an `initialize`
handshake that negotiates protocol version and client and server capabilities,
and the server may then keep session-scoped state (subscriptions, notification
routing, progress tokens). Sharing one upstream session among several clients
means the gateway re-implements session semantics on top of MCP, which the
protocol was not designed for.

The cost of not sharing is N × M upstream connections (N concurrent client
sessions × M registered upstreams). Coffer is single-user: N is in the low
single digits, and most stdio MCP servers start in under a second and use less
than 100 MB.

## Options Considered

### Option A — One independent upstream set per client session, spawned lazily (chosen)

A `MCPGatewaySession` is created per downstream session — one per `/mcp`
session id, plus the long-lived `coffer-builtin-agent` session the internal
engine uses (`surfaces/http/chat_wiring.py`). Each session owns a
`SubprocessSupervisor` (`application/mcp/supervisor.py`) that starts an upstream
on first need (the first `tools/list` or the first call routed to it), not at
session start, and closes every upstream the session started when the session
is disposed. Sessions share no upstream state.

Pros: MCP stays correct with no multiplexing layer — one upstream session per
`(session, upstream)` pair, with plain request-id correlation; an upstream that
crashes in one client's session does not affect another's; upstream-to-client
requests and notifications have exactly one possible recipient. Cons: resources
grow with N × M; each session pays an upstream's cold start once. Wins because
the protocol correctness and isolation are worth more than the resources at
single-user scale.

### Option B — One shared upstream per server, multiplexed by the gateway

Pros: one process per upstream regardless of client count. Cons: serving two
clients with different declared capabilities from one upstream session forces
the gateway to fabricate or proxy state mid-stream; notification routing (which
client gets `tools/list_changed`, whose request a `progress` belongs to) becomes
a bookkeeping layer with a real risk of leaking one client's notifications to
another; upstream `sampling/createMessage` would have to pick a client. The
implementation estimate was about three times the per-session approach. The
resource saving does not justify it at this scale. Loses; it would be revisited
only for a fleet deployment, which Coffer is not.

### Option C — Eager spawn of every registered upstream at session start

Pros: the first call is warm. Cons: wasteful when a session uses 2 of 10
registered servers; adds latency to session start, where users notice it most.
Lazy spawn plus the 60 s capability cache (`application/mcp/discovery.py`)
gives the same eventual warmth without the upfront cost. Loses.

### Option D — A daemon-wide upstream pool shared across sessions

Equivalent in effect to Option B, with the same session-semantics problems, and
a restart or crash of one pooled upstream would disturb every session at once,
which the per-session model isolates. Loses.

## Decision

Each downstream client session gets its own set of upstream connections, spawned
lazily and closed when the session is disposed. Stdio upstreams are subprocesses
the session owns; HTTP upstreams are connections the session owns. No upstream
state is shared between sessions.

What one session forwards:

- **Coffer is a server downstream and a client upstream** — two separate
  `initialize` handshakes. Coffer answers the client's handshake itself and
  sends its own to each upstream on first need.
- **Forwarded requests**: `tools/list`, `tools/call`, `resources/list`,
  `resources/read`, `prompts/list`, `prompts/get`, from one table both
  transports share (`infrastructure/mcp/dispatch.py`). Any other method is
  refused rather than passed through blind.
- **Names are rewritten both ways**: a tool or prompt appears as
  `<server>__<name>`, a resource URI as `coffer://<server>/<uri>`
  (`domain/mcp/namespace.py`). `__` was chosen because `:`, `.`, `/` and `-`
  are all legal inside upstream tool names.
- **Upstream-to-client requests** (`sampling/createMessage`, `roots/list`) go
  to the session's own client; sampling only when that client declared
  `sampling` in its handshake (`application/mcp/gateway_server_requests.py`).
- **Upstream notifications**: the three `list_changed` notifications and
  `resources/updated` invalidate the session's discovery cache and are
  forwarded; `notifications/message` and `notifications/progress` are dropped
  (`application/mcp/gateway_notifications.py`). A long `tools/call` is still
  issued with a progress callback, so a tool that reports progress is not cut
  off by the read timeout.

## Consequences

- With 3 concurrent clients and 10 registered upstreams, up to 30 upstream
  processes can exist. Two bounds keep that in check:
  - **Idle sessions are reaped.** A `/mcp` session that has seen neither a
    request nor an upstream notification for 30 minutes is disposed, with its
    upstreams, by the session reaper (`surfaces/http/mcp/protocol_routes.py`);
    `COFFER_MCP_SESSION_IDLE_S` and `COFFER_MCP_SESSION_REAPER_INTERVAL_S`
    (default 60 s) tune it. This is what reclaims the upstreams of a client that
    vanished without closing its session, on a daemon that otherwise never
    exits ([Daemon Is a Resident Login Service](daemon-is-a-resident-login-service.md)).
    The internal engine's in-process session is not reaped; it is disposed at
    shutdown.
  - **Cold starts are capped per session.** A listing fan-out over many servers
    would otherwise start them all at once and push every spawn past its
    timeout; a supervisor starts at most 4 upstreams concurrently
    (`COFFER_MCP_MAX_CONCURRENT_SPAWNS`).
- Each session pays an upstream's spawn and handshake once, on first use.
- A failing upstream is retried at 1 s, 5 s and 30 s, then put in a 60 s
  cooldown during which calls fail fast; this is per session, so one client's
  bad luck does not cool another's upstream.
- Upstream subprocesses are reaped authoritatively on close: each spawn records
  its pid and command line under `~/.coffer/upstream-pids/`, and closing kills
  the recorded process tree (the upstream is usually a `uv`/`npx` wrapper over
  an interpreter grandchild) if the SDK teardown left it alive. The next
  daemon's startup sweep reaps what a crash left behind
  ([Detect-or-Spawn](daemon-detect-or-spawn.md)).
- The capability discovery cache is per session, matching the lifetime of the
  connections it describes ([Capability State Model](capability-state-model.md)).
- An upstream's stderr goes to its own file under `~/.coffer/logs/upstream/`,
  not to `daemon.log`.
