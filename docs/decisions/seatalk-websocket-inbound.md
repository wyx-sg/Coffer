# SeaTalk Inbound Is One Outbound WebSocket, Through an Operator-Supplied SDK

**Status**: Accepted
**Date**: 2026-09-24
**Deciders**: Yuxing Wu
**Related**: spec channels/seatalk ("Receive every event over one outbound websocket connection", "Report the websocket connection as the channel's inbound state", "Load the websocket client library from an operator-supplied directory", "Configure a SeaTalk channel by app id and secret reference");
spec channels ("Bind each channel to the one machine that runs it", "Process each inbound event once");
[Channels Are Thin Transport Adapters](channel-adapter-framework.md), [Telegram Long Polling](telegram-long-polling.md),
[Daemon Is a Resident Login Service](daemon-is-a-resident-login-service.md);
change archive `openspec/changes/archive/2026-09-24-remove-seatalk-webhook-delivery/`; PRs #375, #431

## Context

SeaTalk offers a bot two ways to receive events, and **a bot uses exactly one
of them at a time**, chosen in SeaTalk's Developer Portal:

- **Webhook.** The platform POSTs each event to a public URL.
- **WebSocket Event Callback.** The bot holds one outbound connection to the
  platform, registers on it with its `app_id` and `app_secret`, and events
  arrive on the socket it opened.

The facts about the websocket path that shape the decision:

- **One live connection per app; the newest registration wins.** Registering
  the same app from a second process kicks the first.
- **The protocol is unpublished; only a client library is documented.** The
  register handshake, framing, ack and kick semantics are available only
  through SeaTalk's own Python SDK, `seatalk-oapi-sdk-py`.
- **That SDK is distributed from an internal corporate portal**, is absent
  from public PyPI, and carries no public licence. Coffer is MIT and
  open-source-bound.
- **The SDK is synchronous and thread-based and does not reconnect.**
  `connect()` blocks on the handshake, `listen()` blocks for the life of the
  connection, and its dispatcher acks each event itself as soon as the
  handler returns.
- **The portal's Re-verify passes only while a connection is live**, so the
  order is: enable the channel in Coffer, then verify in the portal.

Coffer's own constraints: nothing but the daemon's loopback socket may listen
([principles](../../docs-site/architecture/principles.md), "Network
defaults"); the daemon is always up once started ([Daemon Is a Resident Login
Service](daemon-is-a-resident-login-service.md)); and a channel runs on exactly
one machine, named by its `runs_on`.

SeaTalk is also the platform where Coffer is the only possible bridge: no
official or third-party integration connects it to any coding agent.

## Options Considered

### Option A — WebSocket only, with the SDK supplied by the operator (chosen)

- **One connection per SeaTalk channel, inside the daemon.** A connector
  (`infrastructure/channel/seatalk_ws.py`) runs the SDK's blocking calls on a
  thread it owns and crosses each event back to the event loop with
  `call_soon_threadsafe`; the handler never waits for the turn and never
  raises, so one bad frame cannot drop the connection. Every event is ingested
  at `ChannelService.ingest_event`, the channel's single entry point for
  de-duplication, the owner gate, media and the turn.
- **Supervision is Coffer's.** On failure the connector backs off
  exponentially from 1 s to 30 s. A kick backs off a flat 60 s instead of
  racing the other holder, since two processes fighting over one app starve
  each other. The channel runtime reconciles one connector per enabled SeaTalk
  channel bound to this machine, keyed by channel uid
  (`application/channel/runtime_supervision.py`).
- **Configuration is `app_id` and `app_secret_ref`**, plus the common channel
  fields (`domain/channel/config.py`). Migration `0103` removed the webhook-era
  fields — `delivery`, `signing_secret_ref`, `public_base_url`,
  `tunnel_token_ref` — from every stored SeaTalk channel and left the
  credential values they cited in the store, because a migration that deletes
  secrets cannot be reversed.
- **The SDK is an optional runtime dependency the operator provides.**
  `infrastructure/channel/seatalk_sdk.py` looks in `$COFFER_SEATALK_SDK_DIR`,
  else `~/.coffer/vendor`, adds that directory to the import path only if it
  exists, and imports lazily when a connection starts. When the import fails,
  the channel's inbound state is `sdk_missing`, naming the directory searched
  and the platform's documentation, and the connector keeps retrying, so
  dropping the SDK in needs no restart. Outbound sends never touch the SDK and
  keep working.
- **Status reports the connection as the channel's inbound state**:
  `connecting`, `connected`, `kicked`, `sdk_missing` or `error`, with the last
  error verbatim. There is no listener, port, public URL or reachability probe
  to report.

Pros: nothing Coffer runs for SeaTalk is reachable from the network — no
public URL, no listener, no signature scheme, no tunnel — so the loopback-only
rule has no exception. No second process. Setup is two values. The
repository never contains or declares code it has no licence to distribute.

Cons: an installation without the SDK has **no SeaTalk inbound** — such a
channel can send to its owner but receives nothing — which is what an outside
user of this project gets. Events that arrive while the connection is down
(restart, network drop, back-off) are the platform's to retry or drop; Coffer
cannot queue them. A second machine registering the same app takes the events
away, which is why the machine binding matters.

Wins because it removes every piece of machinery that existed only to
compensate for Coffer having no public address, for the one installation that
uses SeaTalk in earnest, while staying legal to publish.

### Option B — Webhook only

How it works — the design first shipped: the daemon spawned a separate
callback-listener process (a publicly reachable surface was not allowed inside
the daemon) serving `POST /seatalk/{channel}` on a loopback port. It answered
the platform's `event_verification` challenge, verified
`sha256(body + signing_secret)` on every request and forwarded valid events to
the daemon over loopback. A tunnel — first one the owner ran by hand, later a
`cloudflared` child the daemon supervised from a token on the channel — gave
it a public hostname, recorded on the channel as `public_base_url` and probed
by a reachability test.

Pros: needs no vendor library, so it works for anyone who can create a
SeaTalk app; the protocol is documented.

Cons: a second binary (`coffer-callback`), a signature scheme, a supervised
tunnel child, a public hostname and a reachability probe — all to undo the
fact that a local vault has no public address — and the only publicly
reachable surface in the product.

Loses because every part of it exists to manufacture an address the vault
deliberately does not have.

### Option C — WebSocket, with webhook kept as the fallback for installations without the SDK

How it works — the design that ran from PR #375 until PR #431: a `delivery`
field on each SeaTalk channel chose `webhook` (the default) or `websocket`,
and the whole webhook apparatus stayed for owners who could not obtain the
SDK.

Pros: an outside user still gets SeaTalk inbound; the websocket path is an
upgrade, not a floor.

Cons: two transports to test and document, a config field that decides which
other fields may exist, and the listener, signature check and tunnel kept
alive for one remaining user — an installation that cannot obtain the SDK. The
owner's production bot ran on websocket. The archived change's design records
the trade: the owner accepted losing inbound for SDK-less installations to
delete the apparatus
(`openspec/changes/archive/2026-09-24-remove-seatalk-webhook-delivery/design.md`).

Loses on carrying cost for a user base of zero.

### Option D — Run both methods on one bot, webhook as the fallback for a dropped socket

How it works: when the websocket drops, events arrive by webhook instead.

Pros: no gap in delivery during a reconnect.

Cons: the platform forbids it — a bot has one delivery method at a time. A
fallback would mean flipping the portal setting from code mid-outage, which
Coffer cannot do and would be hidden state that makes an outage harder to
reason about.

Loses because the platform does not allow it.

### Option E — Vendor the SDK into the repository

How it works: copy `seatalk_oapi_sdk` into Coffer's source tree.

Pros: works out of the box for everyone.

Cons: redistributes code under no public licence from an internal portal in a
public MIT repository.

Loses outright on licensing.

### Option F — Declare the SDK as a dependency

How it works: list it in `pyproject.toml`.

Pros: normal dependency management.

Cons: it is not on public PyPI, so every outside install and CI would fail to
resolve it.

Loses because a dependency nobody can fetch is a broken build.

### Option G — Reimplement the wire protocol

How it works: speak the websocket protocol directly, as a few hundred lines
over a websocket library, reverse-engineered from the SDK.

Pros: no vendor library; works for everyone.

Cons: the handshake, envelope, ack and kick semantics are unpublished; Coffer
would own a guess that the platform is free to change without notice, with no
contract to test against.

Loses because a transport built on reverse-engineering has no specification to
stay correct against.

## Decision

SeaTalk inbound is one outbound websocket connection per channel, held and
supervised inside the daemon (exponential back-off to 30 s, flat 60 s after a
kick), configured by `app_id` and `app_secret_ref` alone, and ingested at the
channel's single entry point. The platform's SDK is an operator-supplied
optional dependency loaded lazily from `$COFFER_SEATALK_SDK_DIR` or
`~/.coffer/vendor`; without it a SeaTalk channel reports `sdk_missing` and can
only send. There is no webhook transport. Outbound SeaTalk calls do not use the
SDK.

Rules a future change must respect:

- The SDK is never vendored, declared, or imported at daemon import time.
- No SeaTalk code path opens a listening socket.
- Connection state is reported as the channel's inbound state, never inferred
  from logs.
- Enable a SeaTalk channel on one machine only; the kick back-off makes a
  conflict visible but does not resolve it.

## Consequences

- Coffer has no public-reachable surface; the `coffer-callback` binary is
  gone and frozen deploys prune its stale `~/.coffer/bin/` link.
- An outside user without access to the SDK can use SeaTalk for notifications
  but not to drive agents; Telegram is unaffected.
- The test suite codes against a stub of the SDK surface; no test skips for
  lack of the real SDK.
- A new SeaTalk-side capability (streaming, cards, thread reads) is an
  outbound `httpx` call and does not involve the SDK.
- Enforced by: `infrastructure/channel/seatalk_ws.py`,
  `seatalk_ws_controller.py` and `seatalk_sdk.py`; `SeaTalkChannelConfig` in
  `domain/channel/config.py`; migration `0103`.
