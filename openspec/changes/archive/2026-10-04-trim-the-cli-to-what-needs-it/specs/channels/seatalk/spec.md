## MODIFIED Requirements

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
  `sdk_missing`, with a detail naming the missing library, the directory that
  was searched and the platform documentation for it — a statement of fact, not
  a procedure. The connection keeps retrying on its back-off ladder, so dropping
  the SDK in needs no daemon restart. Nothing crashes, the daemon stays up,
  every other channel keeps running, the channel's outbound sends — replies and
  notifications, which never touch the SDK — are unaffected, and the reason is
  reported as that channel's own state rather than left in a log for someone to
  find.
- Putting the SDK in place is handed to the person's agent (see
  [principles](../../../../docs-site/architecture/principles.md) "AI-Native").
  The download stays with the person, because the portal needs their login;
  everything after it is the agent's. While a channel reports `sdk_missing`,
  its status (`GET /api/v1/channels/{uid}/status`) MUST carry a `handoff`
  prompt naming the directory the daemon imports from (and whether
  `$COFFER_SEATALK_SDK_DIR` chose it), the platform documentation where the
  person downloads the archive, and the steps: find the downloaded archive
  (usually in `~/Downloads`), unpack it so that `<directory>/seatalk_oapi_sdk/`
  exists without pip-installing it, check the package landed, and confirm from the
  channel's status that the websocket reads connected; `handoff` is
  null in every other state. The channel page MUST show one sentence linking
  the platform's download page, the hand-off (Copy prompt, and Ask an agent
  when a managed agent is available) and the header's Retry — and no manual
  procedure. The Overview's attention item for the channel MUST carry the same
  prompt as its `handoff`, with the reason code `channel_sdk_missing` and a
  reason sentence that names no command.
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

#### Scenario: a missing sdk is handed to an agent from the channel page
- **GIVEN** a SeaTalk channel whose websocket reports `sdk_missing`, with `$COFFER_SEATALK_SDK_DIR` set
- **WHEN** its status is read and its page is opened
- **THEN** the status carries a `handoff` prompt naming `<dir>/seatalk_oapi_sdk/`, the variable that chose the directory, the platform's download page, `~/Downloads` and the channel's status, and leaving the login to the person
- **AND** the page's banner links the platform's download page and offers Copy prompt beside the header's Retry, without the error text
- **AND** once the websocket connects, `handoff` is null

#### Scenario: a missing sdk is handed to an agent on the Overview
- **GIVEN** an enabled SeaTalk channel bound to this machine whose websocket reports `sdk_missing`
- **WHEN** the attention list is read
- **THEN** the channel's item has reason code `channel_sdk_missing`, a reason that names no command, and the same hand-off prompt as its status

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
- **WHEN** the user queries status via REST and on the Channels page
- **THEN** each reports the connection state as the channel's inbound state, and
  the failed one carries its last error verbatim
- **AND** neither surface reports a listener, port, path, public URL or tunnel
  for either channel
