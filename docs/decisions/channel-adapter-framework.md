# Channels Are Thin Transport Adapters Over One Shared Core, Supervised In-Daemon

**Status**: Accepted
**Date**: 2026-09-24
**Deciders**: Yuxing Wu
**Related**: spec channels ("Run the channel lifecycle through the resource framework", "Render replies by the adapter's declared capabilities", "Route the owner's messages into a turn-platform conversation", "Drive every managed agent from one bot", "Bind each channel to the one machine that runs it");
[Channel Owner Gate](channel-owner-gate.md), [Channel Live Surface Strategy](channel-live-surface-strategy.md),
[SeaTalk Inbound Over WebSocket](seatalk-websocket-inbound.md), [Telegram Long Polling](telegram-long-polling.md),
[Chat Is a Single-Owner Live Mirror](chat-single-owner-live-mirror.md), [Resource Framework Designed Upfront](resource-framework-upfront.md),
[Per-Agent Resource Scope](per-agent-resource-scope.md);
research note [IM–agent bridges](../research/im-agent-bridges.md); PRs #59, #375, #431

## Context

Coffer lets its one owner drive a managed agent (Claude Code or Codex) from a
messaging app — Telegram and SeaTalk today — and receive notifications there.
More platforms and more agents are both expected, so the integration cost must
stay **N + M**: a new platform must not touch agent code, and a new agent must
not touch platform code.

The forces:

- **The daemon already owns all state and already supervises long-lived work**
  — in-process background workers (retention, sync) and MCP child processes —
  and it never idle-exits ([Daemon Is a Resident Login
  Service](daemon-is-a-resident-login-service.md)), so an inbound message that
  arrives at night finds it up.
- **Nothing but the daemon's loopback socket may listen**
  ([principles](../../docs-site/architecture/principles.md), "Network
  defaults"). Both transports honour that from the outside in: Telegram is a
  long poll the daemon makes ([Telegram Long
  Polling](telegram-long-polling.md)) and SeaTalk is one outbound websocket the
  daemon opens ([SeaTalk Inbound Over WebSocket](seatalk-websocket-inbound.md)).
  No inbound path requires a public endpoint, a separate listener process or a
  signature check.
- **The platforms differ in exactly the places that shape a reply**: Telegram
  can edit a delivered message and has reactions and a draft-streaming API;
  SeaTalk cannot edit a text message at all but can stream one, has a typing
  cue but no reactions, and can fetch a thread's history. A core that branched
  on platform would grow a conditional per platform per behaviour.
- **The chat platform already exists** — conversations, a per-conversation turn
  queue, interrupt, the live event bus ([Chat Is a Single-Owner Live
  Mirror](chat-single-owner-live-mirror.md)) — and the web Chat page already
  drives it through its seams.
- **A bot identity tolerates one consumer.** Two daemons answering one bot
  would answer the owner twice, and a channel resource now travels between
  machines with vault sync.

## Options Considered

### Option A — Thin transport adapters declaring capabilities, one shared core, in-daemon reconciler (chosen)

- **Channels are a resource kind** (`channel`), riding the generic lifecycle,
  audit and credential-reference machinery; secrets live in the credential
  store and config carries refs, probed at registration.
- **An adapter is transport only**: start/stop, outbound send/edit/stream,
  normalising inbound platform payloads into the envelopes in
  `domain/channel/envelopes.py` (`InboundMessage`, `InboundCallback`,
  `InboundLifecycle`), and a `ChannelCapabilities` declaration —
  `supports_edit`, `supports_live_text`, `live_text_persists`,
  `supports_typing`, `supports_reactions`, `supports_buttons`,
  `supports_card_update`, `supports_media`, `supports_groups`,
  `supports_history_fetch`, `max_message_chars`, mention templates.
- **The core** (`application/channel/`) owns pairing and the owner gate,
  commands, conversation mapping, queueing, rendering strategy and turn
  context, and picks behaviour from capabilities, never from adapter type
  (`turn_render.py`, `turn_context.py`).
- **The chat platform is reached only through its seams.** A channel message
  goes through `TurnOrchestrator.enqueue_message`
  (`application/channel/turn_driver.py`) exactly as a web message does, so web
  and channel share one FIFO per conversation and a turn that ends on either
  surface advances the same queue; the channel keeps only an `on_start` sink
  that hands it the turn's event queue to render. A chat's backlog is bounded
  at `QUEUE_MAX = 10` pending messages, past which the bot says it is busy;
  control commands (`/stop`, `/new`) bypass the queue. Conversations are
  created through the chat service's `create_conversation`. The agent cannot
  tell a channel turn from a web turn.
- **Adapters run in-daemon as supervised asyncio tasks**, managed by
  `ChannelRuntime` (`application/channel/runtime.py`): every 2 s it asks the
  gate in `application/channel/wanted.py` which channels this machine should
  run and converges. The gate has three parts, in order: **enabled**; **the
  machine binding** (`runs_on` names this machine — failing closed for another
  machine, an unknown one or none); **routing** (the channel names a
  registered default agent inside its own scope). The same gate is the one
  place an agent uid becomes the turn platform's agent key. A running channel
  is rebuilt when its config or its routing changes; a failed start is retried
  after 30 s (`FAILURE_RETRY_SECONDS`). REST, CLI and UI never start or stop an
  adapter; they edit the resource and the next tick converges. A SeaTalk
  channel's websocket connection is reconciled in the same tick
  (`runtime_supervision.py`), keyed by the channel's uid so a rename does not
  re-register the socket.
- **No platform SDKs for anything Coffer can speak itself.** Both transports
  call their HTTP APIs with `httpx` against fixed hosts. The one exception is
  SeaTalk's websocket client, which has no published wire protocol and is
  loaded from an operator-supplied directory ([SeaTalk Inbound Over
  WebSocket](seatalk-websocket-inbound.md)).

Pros: a new platform is one adapter plus one config schema plus its
import-linter entries, and a test fake adapter (`application/channel/ports.py`
names it as the recipe) exercises the whole core. A new agent registered with
the chat platform is reachable from every channel with no channel code. Status
is truthful because one loop owns every runtime transition. Everything runs in
the process that already holds the state it needs.

Cons: a platform feature the capability set cannot express needs a new
capability flag, which touches the envelope module and every adapter's
declaration. A channel adapter that misbehaves (a blocking call on the event
loop) degrades the daemon, not a separate process. The 2 s tick is the latency
of an enable or a rebind.

Wins because it holds N + M with the smallest process surface, and the
capability split has already paid for itself: when SeaTalk gained streaming,
only its adapter changed (`supports_live_text` became true) while the renderer
stayed identical.

### Option B — Adopt platform SDKs or bot frameworks (python-telegram-bot, aiogram, a SeaTalk SDK for everything)

How it works: each adapter wraps a mature SDK, which brings its own polling
loop, retry and rate-limit handling, and typed payloads.

Pros: less wire code; some flood-control handling for free.

Cons: each SDK brings its own event loop and lifecycle model, which the
reconciler would have to wrap rather than own; import confinement needs a
contract per SDK; the Bot API methods Coffer uses are a small set, so the SDK
adds a dependency to save a few dozen lines. For SeaTalk, the only SDK is
distributed from an internal portal under no public licence, so it cannot be a
declared dependency of an MIT project at all.

Loses because the leverage is small and the ownership cost (a second lifecycle
model per platform, a dependency that cannot be declared) is not.

### Option C — A separate channel-gateway process per channel or for all channels

How it works: a sidecar process (the shape OpenClaw uses) owns the platform
connections and forwards normalised events to the daemon over loopback.

Pros: a crashing or blocking adapter cannot hurt the daemon; the gateway could
be restarted independently.

Cons: doubles the process-management surface for a single-user local daemon —
detect-or-spawn, pidfiles, orphan sweeps, log plumbing, a token handshake, a
second binary to ship. The gateway would still need the daemon for every
decision (pairing, conversations, turns), so the isolation buys little. Coffer
did run one extra process for a time — a SeaTalk webhook listener, justified
only because a public endpoint must not live inside the daemon — and it was
deleted with webhook delivery in PR #431 once no inbound path needed a
listening socket.

Loses because with no public-facing ingress left, nothing justifies the second
process.

### Option D — Fat per-platform adapters that each own pairing, commands and rendering

How it works: every adapter implements the whole bot — its own owner gate, its
own command handling, its own reply rendering tuned to its platform.

Pros: each adapter can use its platform to the fullest with no shared
abstraction in the way.

Cons: the owner gate, the security boundary, would be written once per
platform, and a fix to one would not reach the others. Command semantics
(`/agent`, `/model`, `/stop`) would drift between platforms. The cost of a new
platform becomes the cost of a whole bot.

Loses because the security boundary and the command vocabulary must be single
sources.

### Option E — A generic external IM bridge (cc-connect-style) in front of the agents' CLIs

How it works: run an existing bridge that connects a chat platform to an
agent CLI, and let Coffer stay out of the message path.

Pros: no channel code in Coffer at all.

Cons: such bridges drive a CLI of their own rather than the conversation the
web page shows, so a phone turn would not appear on, or be steerable from, the
Chat page; none speaks SeaTalk; each couples to its own agent runtime and
process model. Coffer's channel value is precisely one paired bot driving any
managed agent through the same conversations as the web page.

Loses because it forfeits the shared conversation and does not cover SeaTalk.

### Option F — Channels as MCP servers

How it works: expose each platform as an MCP server the agent calls.

Pros: reuses the gateway machinery.

Cons: inverts the data flow — MCP is agent-to-tool and outbound; a channel is
user-to-agent and inbound, and needs to start turns, not answer tool calls.

Loses on direction.

## Decision

A channel is a resource kind whose adapter implements transport only and
declares what it can do as `ChannelCapabilities`; the kind-agnostic core in
`application/channel/` owns pairing, the owner gate, commands, conversations,
queueing and rendering, and selects every strategy from capabilities. The core
reaches the chat platform only through `enqueue_message` and the conversation
service, like the web page. Adapters run as asyncio tasks inside the daemon,
started and stopped only by `ChannelRuntime`'s 2 s reconcile against the
three-part gate (enabled, bound to this machine, routable). Transports speak
their platforms over `httpx`; a vendor library is used only where no wire
protocol is published.

Rules a future change must respect:

- No platform conditional in `application/channel/`. A behaviour that differs
  by platform becomes a capability.
- Nothing starts or stops an adapter except the reconciler.
- No channel code path opens a listening socket.
- A new channel type adds an adapter and a config-union member; it does not
  touch agent code.

## Consequences

- Adding a platform: one adapter module set under `infrastructure/channel/`,
  one member of the config union in `domain/channel/config.py`, its
  import-linter entries, and a child spec under `openspec/specs/channels/`.
- A channel's reported status is what is actually running, because only the
  reconciler changes it; a channel that is dark because it is bound to another
  machine or routes nowhere logs why once rather than every tick.
- Rebinding a channel to another machine, narrowing its scope or editing its
  config needs no restart: each is a config change, and a config change is a
  tick.
- Adapters are held in the runtime by channel name, while the SeaTalk
  websocket controller is keyed by uid; a rename therefore rebuilds the
  adapter binding on the next tick but does not re-register the socket.
- Enforced by: `ChannelCapabilities` in `domain/channel/envelopes.py`; the
  `ChannelAdapter` port in `application/channel/ports.py`; the gate in
  `application/channel/wanted.py`; the reconciler in
  `application/channel/runtime.py`; spec channels "Render replies by the
  adapter's declared capabilities".
