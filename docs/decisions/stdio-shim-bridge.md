# Agents Reach the Gateway Through a stdio Shim, Not a Native HTTP Entry

**Status**: Accepted
**Date**: 2026-09-19
**Deciders**: Yuxing Wu
**Related**: [Detect-or-Spawn](daemon-detect-or-spawn.md), [Daemon Auth and Origin Guard](daemon-auth-and-origin-guard.md), [Daemon Binds a Fixed Port](daemon-binds-a-fixed-port.md), [Session Subprocess Model](session-subprocess-model.md), [Per-Agent Resource Scope](per-agent-resource-scope.md), [Resource Identity Is an Immutable uid](resource-identity-is-an-immutable-uid.md), spec mcp-gateway "Present Coffer as one MCP server", spec mcp-gateway "Take the agent identity from the handshake", spec agent-registry "Install Coffer's MCP server into an agent in one action", PR #219, PR #408

## Context

Coffer's MCP gateway lives in the daemon, at `/mcp`, as JSON-RPC over HTTP
with an SSE stream for server-to-client messages
(`surfaces/http/mcp/protocol_routes.py`). Claude Code and Codex each need an
entry in their own MCP configuration that reaches it, and Coffer writes that
entry for them ("Install Coffer's MCP server into an agent in one action").

What the entry has to cope with:

- **The token changes on every daemon start** and exists only in
  `~/.coffer/daemon.json` ([Daemon Auth and Origin Guard](daemon-auth-and-origin-guard.md)).
  Anything written once into an agent's config file cannot hold it.
- **There may be no daemon.** An agent starting in a terminal at 9 a.m. may be
  the first thing to need one ([Detect-or-Spawn](daemon-detect-or-spawn.md)).
- **The daemon restarts under a running agent** — an upgrade, `coffer daemon
  restart`, a crash — and the agent's session must survive it, or at least fail
  cleanly rather than hang.
- **The gateway must know which agent is calling**, because resources are
  scoped per agent ([Per-Agent Resource Scope](per-agent-resource-scope.md)).
- **Coffer does not revisit the entry.** It is written into a file the agent
  owns and read by a process Coffer did not start, possibly months later and
  after several upgrades.

## Options Considered

### Option A — A stdio shim that bridges to the daemon's HTTP/SSE endpoint (chosen)

The agent's entry is a stdio MCP server whose command is the absolute path of
`coffer-mcp-shim`, with `--agent-uid <uid>` as its argument
(`domain/agent/mcp_install.py`). The shim (`surfaces/shim/main.py`):

- finds or spawns the daemon through the shared detect-or-spawn helper, and
  reads the port and token from `daemon.json`;
- forwards each JSON-RPC line on stdin as a `POST /mcp` with `X-Coffer-Token`
  and the `Mcp-Session-Id` the daemon returned, dispatching envelopes
  concurrently so a slow `tools/call` cannot starve pings; drains the `GET /mcp`
  SSE stream to stdout; and validates every reply, turning a non-JSON or error
  response into a JSON-RPC error tied to the request id, because stdout is the
  MCP wire and one stray line crashes the client;
- stamps `coffer/agent-uid` and the launch `coffer/cwd` into the `initialize`
  handshake's `_meta`, where the gateway reads the session's identity.

Pros: the agent's config holds nothing that expires — no port, no token; the
daemon is started on demand; restarts are recovered inside the shim; stdio is
the one MCP transport every client supports. Cons: one more process per agent
session; a hop that adds latency (budgeted at 50 ms median in spec mcp-gateway
"Present Coffer as one MCP server"); the shim's path must stay valid across
upgrades. Wins because it is the only option that keeps a write-once config
entry correct across daemon restarts and token changes.

### Option B — A native HTTP MCP entry in the agent's config, token included

Claude Code and Codex both accept an HTTP MCP server with static headers. Pros:
no extra process, no bridge code. Cons: the token would be written into the
agent's config file and go stale at the next daemon start, so every restart
would require Coffer to rewrite every agent's config — and a running agent reads
its config once, so its session would still hold the dead token. It cannot
spawn a daemon that is not running. Persisting a long-lived token to make this
work is the trade [Daemon Auth and Origin Guard](daemon-auth-and-origin-guard.md)
rejects. Loses. It remains available to a user who wires a client by hand
(documented in the connect-client guide) with the stated cost.

### Option C — A per-agent stdio MCP server that does the work in-process

The agent launches a Coffer process that loads the gateway itself and talks to
upstreams directly. Pros: no daemon hop. Cons: each agent session would own its
own copy of the registry, credentials, capability preferences and upstream
processes, with no single writer to the vault's database and no shared view for
the UI, channels or audit. This is the "entry point owns the daemon" design
[Detect-or-Spawn](daemon-detect-or-spawn.md) rejects. Loses.

### Option D — SSE-only transport, or a long-lived HTTP connection with no stdio

Point the agent at an SSE URL and let the client hold the stream. Pros: no
shim. Cons: the same stale-token and no-spawn problems as Option B, plus a
deprecated transport. Loses for the same reasons.

## Decision

Coffer installs itself into an agent as a stdio MCP server,
`<absolute path to coffer-mcp-shim> --agent-uid <uid>`, and the shim bridges to
the daemon's `/mcp` over HTTP and SSE, finding or starting the daemon itself.

**The path is absolute and resolved when the entry is written**
(`default_shim_resolver` in `application/agent/mcp_service.py`), in this
order: the `COFFER_MCP_SHIM_PATH` override, a `PATH` lookup, the running
interpreter's scripts directory (where pip and uv put console scripts, found
via `sysconfig` even when the venv's `bin` is not on `PATH`), then the binary
next to the running executable. A daemon launched from the Dock, by launchd or
by a venv does not inherit the user's shell `PATH`, so a bare
`coffer-mcp-shim` would resolve in the user's terminal and nowhere else. When
the resolved path is the deployed shim, the entry names the public
`~/.coffer/bin/coffer-mcp-shim` symlink rather than the versioned directory
behind it, because deploys prune old version directories and an entry pinned to
one breaks two upgrades later (PR #408). If no shim resolves, the install is
refused and nothing is written.

**Identity is the agent's uid, never its name.** The entry outlives renames,
and the gateway matches it against scopes that hold uids. The argument parser
sets `allow_abbrev=False` so the older `--agent` flag is not taken as a prefix of
`--agent-uid`; an entry carrying only `--agent` reports no identity and sees
strictly less (spec mcp-gateway "Take the agent identity from the handshake").
Unknown flags are ignored rather than fatal.

**A restarted daemon is recovered in place** (PR #219). The shim caches the
`initialize` envelope. When a POST fails to connect, it re-reads `daemon.json`
for up to 5 s; if a live daemon answers at a different port *or with a
different token*, it rebinds its client, drops the dead session id, replays the
cached handshake (without forwarding the reply, which the agent already has)
and retries the call once. A blip against the same daemon is not recovered
this way; a daemon that is gone surfaces as a JSON-RPC error on that request
rather than a hang.

**Exit codes are a contract:** `0` on stdin EOF or SIGTERM, `1` on an uncaught
fatal error, `3` when no daemon answers within 10 s of spawning one, with the
reason pointing at `~/.coffer/logs/daemon.log`.

## Consequences

- An agent's `coffer` entry never needs rewriting because the daemon restarted;
  it needs rewriting only when the shim moves, and the public symlink keeps even
  upgrades from moving it.
- With the fixed port of [Daemon Binds a Fixed Port](daemon-binds-a-fixed-port.md)
  the port rarely changes, but the token changes on every start, so recovery
  still runs on every restart; it compares the token as well as the address.
- Each agent session is one shim process and one gateway session with its own
  upstream processes ([Session Subprocess Model](session-subprocess-model.md)).
- The shim's stdin reader accepts lines up to 64 MiB, because the default
  64 KiB limit silently dropped large tool calls (a Confluence page body).
- Each shim writes its own log, `~/.coffer/logs/shim-<pid>-<time>.log`, opened
  only on the first record; the daemon's retention worker ages them out.
  Nothing diagnostic may go to stdout.
- Identity is self-reported and unverified: any local process that can open the
  loopback connection with the token can claim any agent uid. That is accepted
  under the single-user loopback posture.
