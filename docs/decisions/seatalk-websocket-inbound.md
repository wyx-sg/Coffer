# SeaTalk Inbound Over WebSocket, With an Operator-Supplied SDK

> 中文版: [seatalk-websocket-inbound.zh.md](./seatalk-websocket-inbound.zh.md)

**Status**: Accepted
**Date**: 2026-09-12
**Deciders**: Yuxing Wu
**Related**: spec [channels](../../specs/channels/spec.md) (FR-071, FR-072);
[Channel Adapter Framework](channel-adapter-framework.md);
[Daemon Detect-or-Spawn](daemon-detect-or-spawn.md)

## Context

SeaTalk inbound has always been a webhook. The platform POSTs an event to a
public URL, so Coffer — a local-first vault that binds to loopback and owns no
public address — has to manufacture one. The apparatus that does it is the most
elaborate piece of machinery in the channel layer:

- a **separate listener process**, spawned by the daemon while a SeaTalk channel
  is enabled, because the constitution will not let a publicly reachable surface
  live inside the daemon;
- **signature verification** on every request, which exists solely because the
  endpoint is reachable by anyone who finds it;
- a **tunnel** from that endpoint to the loopback port — originally one the owner
  stood up by hand, and since the managed-tunnel work a `cloudflared` child the
  daemon spawns and supervises from a connector token on the channel;
- a **public base URL** recorded on the channel so status can report what the
  platform was given, and a reachability test to probe it.

Every part of that exists to undo the fact that the bot has no public address.
None of it is what the product is about.

SeaTalk now documents a second delivery method: **WebSocket Event Callback**. The
bot holds one outbound connection to the platform, registers on it with its app
credentials, and events arrive on the socket it opened. No public URL, no
listener, no tunnel, no signature. The platform's own constraint is that a bot
uses **one delivery method at a time** — the two are alternatives, not layers.

This was previously recorded as out of scope, for two reasons that have both
changed:

1. **The protocol was undocumented.** The published material covered only how to
   call a vendor SDK. The capability is documented now, so the behaviour Coffer
   implements is a contract rather than a guess.
2. **The SDK was unusable by an MIT repository.** `seatalk-oapi-sdk-py` is
   distributed from an internal corporate portal, is absent from public PyPI, and
   carries no public licence. That has *not* changed. What changed is the
   realisation that Coffer does not need to solve it — see the decision below.

## Decision

**Adopt WebSocket as a second inbound transport for SeaTalk, selected per
channel, and treat the platform's SDK as an optional dependency the operator
supplies rather than something this repository carries.**

1. **`delivery` is a field on the SeaTalk channel config** — `webhook` (the
   default, and what every channel stored before the field is) or `websocket` —
   and it decides which other fields may exist at all. A websocket channel
   forbids `signing_secret_ref`, `public_base_url`, and `tunnel_token_ref`: there
   is no body to sign, no URL to describe, no tunnel to supervise, and a config
   field that decides nothing misrepresents the running system. `app_id` and
   `app_secret_ref` are required on both, because the register handshake
   authenticates with them.

2. **The transport ends at the existing ingest seam, one line above the
   adapter.** The SDK's generic event handler hands over the raw event dict,
   which is the same shape the webhook body already had, so the connector calls
   the same channel-service ingest entry point the HTTP route calls. Everything
   downstream — dedup, normalization, the owner gate, media download, threading,
   the turn — is shared, unchanged, and untested-per-transport because there is
   nothing per-transport left to test. Only the two genuinely webhook-shaped
   things stay behind in the listener: signature verification and the
   `event_verification` handshake.

3. **Supervision is Coffer's, because the SDK has none.** The SDK is synchronous
   and thread-based and does not reconnect. So each websocket channel gets a
   connector with its own supervision loop — connect, listen on a worker thread,
   back off and retry on failure — owned by a per-channel controller shaped like
   the existing tunnel controller, reconciled by the channel runtime exactly as
   tunnels are. The runtime's listener count now includes only webhook channels,
   so a websocket-only deployment runs no listener at all.

4. **The SDK is an operator-supplied optional dependency.** Coffer does not
   vendor it, does not declare it, and does not import it at daemon import time.
   It looks for it in a vendor directory — `$COFFER_SEATALK_SDK_DIR` when set,
   otherwise `~/.coffer/vendor` — prepends that to the import path only when the
   directory exists, and imports lazily when a websocket channel starts. A
   missing SDK is a per-channel condition with an actionable message naming the
   directory searched and the platform's documentation, not a crash and not a
   daemon-wide failure.

## Alternatives Considered

- **Vendor the SDK into this repository.** Rejected outright. Coffer is MIT and
  OSS-bound; the SDK is distributed from an internal corporate portal under no
  public licence. Copying it in would put code in a public repository that nobody
  has licensed us to redistribute. No amount of convenience survives that.

- **Declare it as a dependency.** Rejected: it is not on public PyPI, so every
  outside user's install would break, and CI could not resolve it either. A
  dependency that cannot be fetched is not a dependency, it is a broken build.

- **Reimplement the wire protocol.** Tempting, because the SDK is a thin client
  over raw sockets with its own framing and a ping thread — a few hundred lines.
  Rejected because the protocol is not published: the register handshake, the
  envelope and ack shapes, and the kick semantics would all be reverse-engineered
  from a binary nobody documents, and the platform is free to change any of them
  without notice. We would own a guess and call it a transport. Reading the
  documented SDK surface and asking the operator for the SDK is honest about what
  we know.

- **Keep webhook as the only transport.** Rejected: it keeps a listener process,
  a signature scheme, a tunnel child, and a public hostname alive to compensate
  for an address the vault deliberately does not have — for the one platform where
  Coffer is the only possible bridge. Where an owner can supply the SDK, the
  better-shaped transport should be available to them.

- **Run both methods on one bot, webhook as fallback for a dropped socket.**
  Rejected because the platform forbids it: a bot uses one delivery method at a
  time. Building a fallback would mean flipping the app's own portal setting from
  code during an outage, which is both unavailable to us and precisely the kind of
  hidden state that makes an outage worse.

## Consequences

- **One connection per SeaTalk app, and the newest registration wins.** If the
  same app is registered from a second machine — another install, a colleague
  testing — that registration kicks this one, and events go there. The connector
  reports the kicked state and backs off on a long flat delay instead of fighting
  for the socket, because two processes racing to register would starve both. An
  owner who runs Coffer on two machines must enable the channel on only one; this
  is the same single-consumer rule the spec already states for a channel's
  platform identity, now with a visible failure mode.

- **Event delivery pauses while the connection is down.** There is no public
  endpoint absorbing events during a restart, a network drop or a back-off
  window; whatever the platform does with undeliverable events is the platform's
  behaviour, not something Coffer can queue around. Webhook delivery has the same
  exposure whenever the tunnel is down, but a tunnel's uptime is the owner's to
  see, while this one is inside the daemon — hence the connection state being a
  first-class thing status reports, rather than a log line.

- **The delivery method is a two-sided setting.** It lives on the channel here and
  on the app in SeaTalk's Developer Portal, and the two must move together.
  Switching in Coffer clears the fields the other method owns, which is honest
  rather than lossy: the switch was never free, because the portal has to change
  in step. On the websocket side the portal's Re-verify only passes while the
  connection is actually live, so the order is *enable in Coffer, then verify
  there* — a sequencing trap worth documenting, because getting it backwards
  looks like a broken product.

- **An install without the SDK is a first-class configuration.** That is what an
  outside user of this project has, and webhook delivery remains fully supported
  for exactly that reason. WebSocket is a capability an operator can add, never a
  floor the product stands on; no test may skip because the real SDK is absent,
  so the suite codes against a stub that is the contract.

- **The webhook apparatus stays.** Nothing is deleted: the listener, the signature
  check, the managed tunnel, the public base URL and the reachability test are all
  still the right implementation of webhook delivery, and remain the only option
  for an owner who cannot obtain the SDK. The cost of the second transport is
  therefore a second path to maintain — paid because the new one removes the
  public surface entirely, which no amount of polishing the old one can do.
