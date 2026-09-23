# Channel Adapter Framework

**Status**: Accepted
**Date**: 2026-06-12
**Deciders**: Yuxing Wu
**Spec**: [channels](../../openspec/specs/channels/spec.md)

## Context

Coffer needs messaging channels (Telegram, SeaTalk, more later) through which
the single owner talks to any agent on the chat platform (the Agent Chat spec) and
receives notifications. More channels AND more agents are
expected, so the integration cost must stay N + M: a new channel must not
touch agent code, and a new agent must not touch channel code.

Two platform constraints shape the design:

- Coffer's principles require public-reachable surfaces to run as a separate
  process limited to signed callback paths; SeaTalk delivers events only by
  public webhook.
- The daemon is the single owner of all state and already runs supervised
  background workers (retention worker) and child processes (MCP upstreams).

## Decision

1. **Channels are a resource kind** (`channel:<name>`, [Everything Is a Resource Kind](everything-is-a-resource-kind.md)) riding the
   generic lifecycle, audit, and credential-ref machinery. Secrets live in
   the credential store; config carries refs, probed at registration.
2. **Thin adapters over a shared core.** An adapter implements transport
   only: lifecycle, outbound send/edit, inbound normalization into common
   envelopes, and a `ChannelCapabilities` declaration (can it edit messages?
   show buttons? type?). Pairing, the owner gate, commands, queueing,
   conversation mapping, and rendering strategy live in
   the kind-agnostic channel core. The core selects behavior from
   capabilities, never from adapter type — Telegram streams progress by
   editing one message, SeaTalk degrades to ack-then-final, with zero
   platform conditionals in the core.
3. **The chat platform is reached only through its existing seams** —
   `ChatService.create_conversation`, `TurnOrchestrator.start_turn` /
   `interrupt_turn` — in-process, exactly as the web UI
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

## Implementation notes

What the framework looks like after the channel work that followed this
decision, and the research the decisions above rest on.

- **Two points above were superseded.** Decision 2's "SeaTalk degrades to
  ack-then-final" no longer holds: the core asks one question,
  `supports_live_text` ("is there a surface I can keep updating while the turn
  runs?"), and both transports answer yes — Telegram by editing one status
  message, SeaTalk through its own streaming API. `supports_edit` is a separate
  capability. Each transport buffers its own cadence (Telegram ~1.5 s between
  edits, SeaTalk ~100 ms) and the core adds no throttle of its own (spec
  [channels](../../openspec/specs/channels/spec.md), "Grow a reply in place on
  one live surface"). Decision 5's "only by public webhook" and decision 7's
  "no platform SDKs" hold for webhook delivery and for every outbound call; a
  SeaTalk channel can instead receive over a websocket through an
  operator-supplied SDK ([SeaTalk Inbound Over
  WebSocket](seatalk-websocket-inbound.md)).
- **The turn seam is `TurnOrchestrator.enqueue_message`**, not `start_turn`: a
  channel message joins the conversation's pending queue exactly as a web
  message does, and the `on_start` hook hands the channel that turn's event
  queue. A chat's queue is bounded (`QUEUE_MAX` in
  `application/channel/turn_driver.py`); control commands such as `/stop` and
  `/new` bypass it.
- **The reconciler asks three gates, in order** — `enabled`, then the machine
  binding (`runs_on` names this machine), then scope — so a channel bound to
  another machine is never weighed against this one's agent registry
  (`application/channel/wanted.py`, every ~2 s). The gate is also the one place
  a channel's agent uids (its `scope` and `default_agent`) become the turn
  platform's agent keys; nothing below the live binding compares a uid.
- **Everything the outside world can see is keyed by channel uid, not name**:
  the SeaTalk callback path `/seatalk/<channel uid>` (composed once in
  `callback_ops.callback_path`), the listener's signing-secret map, the managed
  tunnels and the SeaTalk websockets. The owner pastes the path into a portal
  by hand, so a rename must not move it.
- **Conversation identity is `(channel, chat, thread)`**, one level finer than
  the per-peer key both prior arts use: a group's threads are independent
  conversations, and a per-chat key made two of them collide on one turn lock.
- **Pairing codes are memory-only**, so a daemon restart discards an
  outstanding code and status reports none pending; re-issuing is one step.

### Research behind the decisions

Gathered in July 2026 from OpenClaw and NousResearch Hermes (docs and source)
and SeaTalk's official `cs-bot` repository and platform docs. It describes other
products as they were then; nothing in Coffer depends on them still doing it.

| Decision | Choice | Rationale |
| --- | --- | --- |
| Shape | thin adapters over a shared core, capabilities over special-casing | both prior arts converge on it (Hermes' base adapter is three methods; OpenClaw adds optional capability surfaces) |
| Telegram transport | long polling via raw httpx; offset committed only after dispatch | local-first with no ingress; the handful of Bot API methods used do not justify an SDK |
| Telegram rendering | markdown → Telegram's HTML subset, chunked at 4000 characters, plain-text retry when the platform rejects formatting | proven in OpenClaw; MarkdownV2 escaping is a known bug farm |
| Pairing | 8 characters with no `0O1I`, 1 h TTL, bounded guesses, fail closed | matches both prior arts, and Hermes' hardening after a fail-open setup incident |
| Mid-turn input | bounded FIFO queue, control commands bypass | predictable; avoids an interrupt-by-default surprise |
| Adopt or build | build Coffer's own adapters; port patterns (album debounce, edit-to-stream, ack reactions, event dedup), not code | both prior arts are Node monorepos coupled to their own agent runtimes, and neither speaks SeaTalk |

The same survey found no official SeaTalk integration for any coding agent, and
official Telegram/Slack integrations that were either research previews,
personal-only, cloud-hosted or single-agent. That is why the channel plane
manages only Coffer-hosted channels — one paired bot driving any managed agent —
and treats externally hosted gateways and official integrations as out of scope
rather than something to proxy.
