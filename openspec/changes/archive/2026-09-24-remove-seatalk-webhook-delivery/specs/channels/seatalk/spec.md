## REMOVED Requirements

### Requirement: Choose exactly one inbound delivery per channel
**Reason**: SeaTalk inbound has one transport, the outbound websocket connection. With nothing to choose between, the `delivery` field and the rule that switching it clears the other method's fields go with it.
**Migration**: Migration `0103` removes `delivery` from every stored SeaTalk channel. Set the bot's event delivery to WebSocket on SeaTalk's Developer Portal and supply the SDK (see "Load the websocket client library from an operator-supplied directory").

### Requirement: Require a signing secret on webhook delivery
**Reason**: Webhook delivery is deleted, so nothing verifies a signature, supervises a tunnel or reports a public URL, and `signing_secret_ref`, `public_base_url` and `tunnel_token_ref` configure nothing.
**Migration**: Migration `0103` strips the three keys from every stored SeaTalk channel. The credential values the two refs cited stay in the credential store; `coffer credentials delete <ref>` removes them.

### Requirement: Serve the signed callback protocol from the listener
**Reason**: The `coffer-callback` listener process, its `POST /seatalk/{channel_uid}` path, the `event_verification` handshake, signature verification, the managed `cloudflared` tunnel and the daemon routes behind them (`POST /api/v1/channels/{uid}/events`, `POST /api/v1/channels/{uid}/callback-test`) are deleted with webhook delivery. Nothing Coffer runs is reachable from the public internet.
**Migration**: Switch the bot's event delivery on SeaTalk's Developer Portal from webhook to WebSocket, enable the channel in Coffer, and then press the portal's Re-verify, which passes only while Coffer's connection is live. A tunnel the owner ran by hand can be shut down.

### Requirement: Carry no ingress fields on websocket delivery
**Reason**: With webhook delivery gone there are no ingress fields to forbid and no listener or tunnel to keep stopped; what the requirement still says about the connection itself moves to "Receive every event over one outbound websocket connection".
**Migration**: None for users. Tests marked with its scenario "a websocket channel runs without the listener or a tunnel" are deleted; the other two scenarios move, by name, to the new requirement.

### Requirement: Keep status truthful per transport
**Reason**: There is one transport, so there is nothing to keep apart per transport; status now reports the websocket connection alone, under "Report the websocket connection as the channel's inbound state".
**Migration**: The status block `callback` is renamed `inbound` and carries only `websocket_state` and `websocket_error`; clients read those two fields there.

## MODIFIED Requirements

### Requirement: Configure a SeaTalk channel by app id and secret reference
A SeaTalk channel's configuration MUST carry **`app_id` and `app_secret_ref`**
and no inbound-transport field: SeaTalk inbound has one transport (see "Receive
every event over one outbound websocket connection"), and the register handshake
authenticates it from those two values alone. The secret lives in the credential
store; the configuration carries the reference, probed at registration ([channels](../spec.md) "Register channels as a credential-referencing resource kind").

A channel stored while webhook delivery existed MUST be rewritten once, by a
migration, so that it carries none of `delivery`, `signing_secret_ref`,
`public_base_url` or `tunnel_token_ref`: a stored key that configures nothing
misdescribes the running system. The credential values those refs cited MUST be
left in the credential store rather than deleted, because a migration that
destroys secrets cannot be undone by its downgrade.

#### Scenario: a seatalk channel without an app id or secret reference is refused
- **GIVEN** a stored SeaTalk app secret under a credential reference
- **WHEN** a seatalk channel is registered missing `app_id`, or missing `app_secret_ref`
- **THEN** the registration is rejected and nothing is persisted
- **AND** the same registration carrying both is accepted with the secret held only as a reference

#### Scenario: a webhook-era seatalk channel keeps only its app credentials
- **GIVEN** a stored seatalk channel carrying `delivery: webhook`, a signing secret ref, a public base URL and a tunnel token ref
- **WHEN** the daemon's startup migrations run
- **THEN** the channel's configuration carries its `app_id`, its `app_secret_ref` and its common fields, and none of the four webhook-era keys
- **AND** the credential values the removed refs cited are still in the credential store

### Requirement: Load the websocket client library from an operator-supplied directory
The WebSocket client library MUST be an **operator-supplied optional
dependency**, never a vendored one. The only client for SeaTalk's websocket
delivery is the platform's own SDK, distributed from an internal corporate
portal, absent from public PyPI, and published under no public licence — so
Coffer, which is MIT, MUST NOT vendor it into this repository and MUST NOT
declare it as a dependency. Reimplementing its wire protocol is not an
alternative either: none is published. See
[SeaTalk Inbound Over WebSocket](../../../../docs/decisions/seatalk-websocket-inbound.md).

- Coffer looks for it at runtime in a vendor directory —
  `$COFFER_SEATALK_SDK_DIR` when set, otherwise `~/.coffer/vendor` — prepended to
  the import path only when that directory exists, following the same
  per-subsystem environment override convention the rest of the vault uses. The
  import is attempted lazily, at the moment a websocket channel starts, never at
  daemon import time, so an installation without the SDK starts exactly as it
  does today.
- When it cannot be imported, the websocket channel's connection MUST NOT come
  up and the channel MUST say precisely why: its websocket state is
  `sdk_missing`, with a detail naming the directory that was searched and the
  platform documentation that says what to put there. The connection keeps
  retrying on its back-off ladder, so dropping the SDK in needs no daemon
  restart. Nothing crashes, the daemon stays up, every other channel keeps
  running, the channel's outbound sends — replies and notifications, which
  never touch the SDK — are unaffected, and the reason is reported as that
  channel's own state rather than left in a log for someone to find.
- An installation without the SDK has **no SeaTalk inbound**. The websocket
  connection is the only inbound transport, so an outside user of this project
  who cannot obtain the SDK can register a SeaTalk channel and send to its
  paired owner, but the channel receives nothing and reports `sdk_missing` for
  as long as the SDK is absent. The SDK is still never vendored and never
  declared; Telegram, whose transport needs no vendor library, is unaffected.

#### Scenario: a websocket channel without the sdk says what is missing
- **GIVEN** a vendor directory that holds no SeaTalk client library
- **WHEN** an enabled websocket-delivery channel tries to connect
- **THEN** its websocket connection never comes up and its reported state is
  `sdk_missing`, naming the missing library and the directory searched for it
- **AND** the connection keeps retrying, so the library can be dropped in without
  a daemon restart
- **AND** the daemon stays up and every other channel keeps working

## ADDED Requirements

### Requirement: Receive every event over one outbound websocket connection
SeaTalk inbound MUST arrive over **one outbound websocket connection per
channel**: the daemon dials out, the register handshake authenticates the
connection once from `app_id` and `app_secret_ref`, and the platform pushes
events down the connection the daemon opened. It is the only inbound transport.
Coffer MUST expose nothing to the network for a SeaTalk channel — no public URL,
no listening port, no tunnel, no signature to verify — so the daemon's loopback
socket stays the only one the vault listens on. Every event MUST be ingested at
the channel's one ingest entry point, so deduplication, the owner gate, media
download and the turn itself are the same for every event. The platform permits
one delivery method per bot, so the bot's event delivery setting on SeaTalk's
Developer Portal is WebSocket; the portal's Re-verify passes only while the
connection is live, so the order is to enable the channel in Coffer first and
verify there second. The kick flag and its reason are written on the SDK's
listen thread and read by the supervisor on the event loop; the two MUST share
the connector's state lock, and a kick signalled from any thread is observed by
the supervisor even when `listen()` then returns without raising.

#### Scenario: a websocket channel receives an event with no public url
- **GIVEN** an enabled seatalk channel carrying only its app id and app secret
  reference among its SeaTalk fields
- **WHEN** the platform pushes a message event down the open connection
- **THEN** it is ingested through the channel's ingest entry point and drives a
  turn, with no signature to verify and nothing listening for a request

#### Scenario: the websocket connection backs off when another process takes it over
- **GIVEN** a connected websocket channel whose SeaTalk app is then registered
  from elsewhere, which kicks this connection — the app allows only one
- **WHEN** the connector observes the kick
- **THEN** it reports the kicked state and waits out a long fixed back-off before
  registering again, rather than fighting the other holder for the connection

### Requirement: Report the websocket connection as the channel's inbound state
**Status MUST report a SeaTalk channel's websocket connection as its inbound
state**, on every surface: the connection state — `connecting`, `connected`,
`kicked`, `sdk_missing` or `error`, or none before the first attempt — and the
last error behind it, verbatim, so the owner can act on it. Status MUST NOT
report a listener, a port, a path, a public URL or a tunnel, because none
exists, and there is no reachability probe: the connection state is the health
answer.

#### Scenario: status names the websocket connection state
- **GIVEN** an enabled seatalk channel whose websocket connection is up, and one
  whose last connection attempt failed
- **WHEN** the user queries status via REST and the CLI
- **THEN** each reports the connection state as the channel's inbound state, and
  the failed one carries its last error verbatim
- **AND** neither surface reports a listener, port, path, public URL or tunnel
  for either channel
