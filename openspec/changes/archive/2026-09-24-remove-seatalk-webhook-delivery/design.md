## Context

[SeaTalk Inbound Over WebSocket](../../../docs/decisions/seatalk-websocket-inbound.md)
added the websocket transport beside webhook delivery and kept webhook as the
floor for an installation without the SDK. The owner's production bot now runs
on websocket delivery, and the owner has decided to delete the webhook path: its
cost is a second process, a signature scheme, a supervised tunnel and a public
hostname, and its only remaining user would be an installation that cannot
obtain the SDK. That ADR is amended by this change; the architecture it
describes is in [`docs/architecture.md`](../../../docs/architecture.md).

## Goals / Non-Goals

**Goals:**

- One SeaTalk inbound path, the outbound websocket connection, ending at the
  existing `ChannelService.ingest_event` seam.
- No public-reachable surface anywhere in Coffer, so the principles' "Network
  defaults" constraint describes a loopback-only system with no exception.
- Existing installs upgrade without a manual step inside Coffer: stored rows are
  rewritten, the stale `~/.coffer/bin/coffer-callback` link disappears.

**Non-Goals:**

- Changing the websocket connector, its supervision, its back-off or the SDK
  loading rules beyond the `sdk_missing` wording.
- Changing Telegram.

## Decisions

### Delete the `delivery` field rather than pin it to `websocket`

A field with one legal value decides nothing, and the spec already calls a
configuration field that decides nothing a lie about the system. Migration
`0103` removes it with the three ingress keys. `SeaTalkChannelConfig` keeps
pydantic's default of ignoring unknown keys, as every channel config does
([channels](../../../openspec/specs/channels/spec.md)), so a document still
carrying the old keys — for instance from a second machine that has not yet
upgraded — is read cleanly and the keys have no effect.

Rejected: keep `delivery` with a single `websocket` literal "for
forward-compatibility". There is no second transport on the horizon, and a
reintroduction would be a new field with its own migration anyway.

### Leave orphaned credential values in the store

`signing_secret_ref` and `tunnel_token_ref` cite rows in the credential store.
The migration drops the refs and leaves the rows, the same choice the channels
spec already made when a channel switched to websocket delivery. A migration that
deletes secrets cannot be reversed by its downgrade, and the values are inert
ciphertext; `coffer credentials delete <ref>` removes them on purpose.

### Downgrade writes `delivery: "websocket"`

The pre-0103 model defaults `delivery` to `webhook` and then requires
`signing_secret_ref`, which the upgrade removed, so a plain inverse would leave
every SeaTalk row unreadable by the older build. Writing `websocket` is both
readable by that build and true of the channel.

### Rename the status block `callback` → `inbound`, websocket fields only

`CallbackInfoOut` described both transports and reported webhook facts as
absent on websocket. With one transport, `port`, `path`, `listener_running`,
`delivery`, `public_base_url`, `public_callback_url`, `tunnel_managed` and
`tunnel_running` have nothing to describe. The block is renamed so its name
says what it is; `InboundInfoOut` carries `websocket_state` and
`websocket_error`, both required and nullable. It stays null for Telegram.

### Remove the listener's idle hold with the listener

Today a running callback listener holds the daemon's idle clock open
(`service_hold` in `channel_wiring.py`). Deleting the listener deletes that
hold and the runtime's `service_hold` callback. The idle stand-down itself is
removed by the separate change `remove-daemon-idle-stand-down`, so this change
does not move the hold to the websocket supervisor and does not modify daemon
"Stand down after an idle window".

### Prune stale `~/.coffer/bin/` links generically

`binary_deploy` removes every public `~/.coffer/bin/<name>` that is a symlink
into a `~/.coffer/bin/<version>/` directory under a name the running build does
not ship. The rule is generic rather than a hard-coded `coffer-callback`
cleanup, so the next binary a release drops needs no special case. Anything at
such a path that is not one of Coffer's symlinks is left alone, matching the
daemon's "not provably ours means leave it alone" posture. Version directories
themselves are pruned by the existing two-newest rule, so the old
`coffer-callback` file disappears with its version directory.

### Scenario handling under the pinned OpenSpec CLI

The pinned CLI refuses a MODIFIED block that drops or renames a scenario of the
current requirement. The SeaTalk requirements whose scenarios change are
therefore REMOVED and re-ADDED under new titles ("Receive every event over one
outbound websocket connection", "Report the websocket connection as the
channel's inbound state"). The channels scenario "channel status reports
runtime, pairing, and callback details" keeps its name, and its steps say
"inbound state".

## Risks / Trade-offs

- **An outside user without the SDK loses SeaTalk inbound.** → Accepted by the
  owner. The channel reports `sdk_missing` naming the directory searched, and
  outbound sends keep working, so the state is visible rather than silent.
- **A bot still on webhook delivery in SeaTalk's portal goes quiet after the
  upgrade.** → The channel guide and the release notes say to switch the portal
  to WebSocket and re-verify once Coffer's connection is live.
- **A second machine on an older build keeps a webhook channel running.** → Its
  document still carries the old keys, which this build ignores; the channel runs
  only on the machine its `runs_on` names, so the two never both answer.
- **Migration number `0103`** may collide with a migration on the long-lived
  `feature/workflow` branch; whichever merges second renumbers.
