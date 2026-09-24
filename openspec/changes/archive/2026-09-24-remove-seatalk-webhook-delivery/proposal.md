## Why

SeaTalk inbound has two transports today, and one of them is most of the channel
layer's machinery: webhook delivery needs a public URL, so Coffer ships a
separate `coffer-callback` listener process, verifies a signature on every
request, answers the `event_verification` handshake, supervises a `cloudflared`
tunnel from a connector token, records a public base URL, and runs a
reachability probe — all to make up for an address a loopback-only vault
deliberately does not have. The websocket transport needs none of it: the daemon
dials out and the platform pushes events down that connection. The owner's
SeaTalk bot runs on websocket delivery in production. The owner has decided that
SeaTalk inbound is websocket-only and that the webhook path is deleted rather
than maintained as a second path.

## What Changes

- **channels/seatalk**: SeaTalk inbound arrives over one outbound websocket
  connection per channel, and nothing Coffer runs for a SeaTalk channel is
  reachable from the network. A SeaTalk channel's configuration is `app_id` and
  `app_secret_ref` plus the common fields; `delivery`, `signing_secret_ref`,
  `public_base_url` and `tunnel_token_ref` no longer exist. Status reports the
  websocket connection as the channel's inbound state and nothing else. An
  installation without the operator-supplied SDK has no SeaTalk inbound; its
  SeaTalk channels report `sdk_missing` and still send. The SDK is still never
  vendored and never declared.
- **Migration `0103`** strips the four webhook-era keys from every stored
  SeaTalk channel and leaves the credential values their refs cited in the
  credential store. Its downgrade writes `delivery: "websocket"`.
- **The `coffer-callback` binary and its package are deleted**:
  `backend/coffer/surfaces/callback/`, the listener and tunnel controllers,
  signature verification, the callback probe, and the routes
  `POST /api/v1/channels/{uid}/events` and
  `POST /api/v1/channels/{uid}/callback-test`.
- **channels**: the edit dialog edits a SeaTalk channel's app id and app secret
  only; channel status carries an `inbound` block (renamed from `callback`)
  holding `websocket_state` and `websocket_error`.
- **daemon**: the terminal archive and the frozen deploy carry three binaries —
  `coffer`, `coffer-daemon`, `coffer-mcp-shim`. A deploy removes the
  `~/.coffer/bin/` link of any binary the build no longer ships, which retires
  the `coffer-callback` link on existing installs. The daemon's long-lived
  children no longer include a listener or a tunnel; the Host-guard rule no
  longer carves out a second process; the daemon log no longer has a child's
  zerolog to parse.
- **desktop-app**: the `.dmg` embeds the same three binaries.
- **web-ui**: the Activity page's daemon tab no longer lists a `cloudflared`
  child among the log's writers.
- **vault-sync**: a channel document describes its inbound surface as a polled
  bot or a held websocket connection, and a synced SeaTalk channel carries its
  app-secret ref.
- **Principles amendment**: `docs/principles.md` Technology constraint "Network
  defaults" loses its sentence about the one public-reachable surface running as
  a separate process limited to signed callback paths. With the listener gone,
  Coffer has no public-reachable surface at all. The PR description records the
  owner's decision as the authority for the amendment.

## Capabilities

### New Capabilities

### Modified Capabilities

- `channels/seatalk`
- `channels`
- `daemon`
- `desktop-app`
- `web-ui`
- `vault-sync`

## Impact

- Backend: channel config model and validators, channel runtime and supervision
  ports, channel service and routes, channel CLI, channel wiring, log reader,
  binary deploy, import-linter contracts in `backend/pyproject.toml`, one Alembic
  migration; `backend/coffer/surfaces/callback/`,
  `infrastructure/channel/listener_spawn.py`, `tunnel_spawn.py`,
  `domain/channel/signing.py`, `application/channel/callback_probe.py` and
  their tests are deleted.
- Contract: `openspec/specs/channels/contracts/api.openapi.yaml` loses two
  routes and three schemas; `CallbackInfoOut` becomes `InboundInfoOut` under
  `ChannelStatusOut.inbound`. The frontend client is regenerated.
- Frontend: the SeaTalk add and edit dialogs lose the delivery selector and the
  webhook fields; the channel detail page's callback card becomes an inbound card
  showing the websocket state; en/zh strings are updated.
- Packaging: `backend/coffer-callback.spec`, the `coffer-callback` legs of
  `scripts/build_binaries.sh`, the `Makefile`, `.github/workflows/release.yml`,
  and the desktop shell's `externalBin` and sidecar list.
- Docs: `docs/principles.md`, `docs/architecture.md`, the SeaTalk websocket,
  channel adapter framework and PyInstaller distribution ADRs, the other ADRs
  that mention the listener, `README.md`, and the `docs-site` channel guide and
  architecture pages.
