## MODIFIED Requirements

### Requirement: Report the websocket connection as the channel's inbound state
**Status MUST report a SeaTalk channel's websocket connection as its inbound
state**, on every surface: the connection state — `connecting`, `connected`,
`kicked`, `sdk_missing`, `rejected` or `error`, or none before the first
attempt — and the last error behind it, verbatim, so the owner can act on it.
`rejected` MUST mean only that SeaTalk refused the app at the register handshake,
the one frame that carries the App ID and App Secret; every other failed attempt
(a DNS failure, a timeout, a dropped socket) is `error`. Both are retried on the
connection's backoff. The Channels page MUST word `rejected` as a rejected
secret and offer to replace it, and MUST word `error` as a network problem being
retried, offering to reconnect and never to replace the secret. Status MUST NOT
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

#### Scenario: a refused app reads as rejected, a network failure does not
- **GIVEN** an enabled seatalk channel
- **WHEN** SeaTalk refuses its register handshake, and separately when an attempt fails on a DNS lookup or a read timeout
- **THEN** the refusal is reported as `rejected` and the Channels page offers to replace the secret
- **AND** the network failure is reported as `error` and the Channels page shows a network problem being retried, with no offer to replace the secret
