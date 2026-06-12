# ADR-014: Channel Adapter Framework

> 中文版: [ADR-014-channel-adapter-framework.zh.md](./ADR-014-channel-adapter-framework.zh.md)

**Status**: Accepted
**Spec**: [009-channels](../../specs/009-channels/spec.md)

## Context

Coffer needs messaging channels (Telegram, SeaTalk, more later) through which
the single owner talks to any agent on the chat platform (spec 008), approves
tool calls, and receives notifications. More channels AND more agents are
expected, so the integration cost must stay N + M: a new channel must not
touch agent code, and a new agent must not touch channel code.

Two platform constraints shape the design:

- The constitution requires public-reachable surfaces to run as a separate
  process limited to signed callback paths; SeaTalk delivers events only by
  public webhook.
- The daemon is the single owner of all state and already runs supervised
  background workers (retention worker) and child processes (MCP upstreams).

## Decision

1. **Channels are a resource kind** (`channel:<name>`, ADR-007) riding the
   generic lifecycle, audit, and credential-ref machinery. Secrets live in
   the credential store; config carries refs, probed at registration.
2. **Thin adapters over a shared core.** An adapter implements transport
   only: lifecycle, outbound send/edit, inbound normalization into common
   envelopes, and a `ChannelCapabilities` declaration (can it edit messages?
   show buttons? type?). Pairing, the owner gate, commands, queueing,
   conversation mapping, rendering strategy, and approval bridging live in
   the kind-agnostic channel core. The core selects behavior from
   capabilities, never from adapter type — Telegram streams progress by
   editing one message, SeaTalk degrades to ack-then-final, with zero
   platform conditionals in the core.
3. **The chat platform is reached only through its existing seams** —
   `ChatService.create_conversation`, `TurnOrchestrator.start_turn` /
   `submit_approval` / `interrupt_turn` — in-process, exactly as the web UI
   does over HTTP. Channels know nothing about agents; agents cannot tell a
   channel turn from a UI turn. Any registered agent is reachable from any
   channel with no code change on either side.
4. **Adapters run in-daemon as supervised asyncio tasks** managed by a
   reconciler loop (RetentionWorker pattern): every tick it diffs enabled
   channel resources against running adapters and starts/stops/restarts to
   match. No new lifecycle hooks in the resource framework; disable, config
   edits, and delete all converge within a tick.
5. **SeaTalk ingress is a separate callback-listener process**, spawned by
   the daemon while any SeaTalk channel is enabled. It serves only
   `POST /seatalk/{channel}` on a loopback port: answers the platform's
   verification challenge, verifies `sha256(body + signing_secret)`, and
   forwards valid events to the daemon over loopback with the daemon token.
   The user points a tunnel (cloudflared/ngrok) at the port; Coffer never
   exposes the daemon itself.
6. **Owner binding is pairing-code-only**: an 8-character single-use code
   (unambiguous alphabet, 1-hour TTL, bounded guesses, memory-only) issued
   from the UI/CLI and sent to the bot from the owner's account. Everyone
   else is ignored silently. Re-pairing replaces the binding. No
   user-id-entry path exists — pairing also proves the transport round-trip,
   and a typo'd id would bind silently to the wrong account.
7. **No platform SDKs.** Both transports speak raw httpx to fixed hosts; the
   API surface used is small, and an SDK would add a dependency plus an
   import-confinement contract for no leverage.

## Alternatives considered

- **Separate channel-gateway process (OpenClaw shape)** — better isolation,
  but doubles the process-management surface (detect-or-spawn, PID, logs)
  for a single-user local daemon; rejected.
- **Channels as MCP servers** — inverts the data flow (MCP is agent→tool
  outbound; channels are user→agent inbound); rejected.
- **Webhook relay service for SeaTalk** — a hosted relay would spare the
  user a tunnel but adds operated infrastructure and a third-party trust
  root; the tunnel keeps everything user-owned. Revisit if real usage
  demands it.
- **Direct user-id allowlist as a pairing alternative** — rejected; see
  decision 6.

## Consequences

- A third channel = one adapter + one config schema + symmetric importlinter
  entries; the suite's fake adapter demonstrates the recipe.
- A second agent on the platform is immediately reachable from Telegram and
  SeaTalk; the suite drives a scripted provider through a channel to pin
  this.
- The reconciler owns all runtime state transitions; REST/CLI/UI never
  start or stop adapters directly, which keeps status truthful.
- The listener's spawn pattern (env-injected secrets, pidfile, orphan sweep)
  reuses the MCP-subprocess conventions, including frozen-build sibling
  binary resolution.
