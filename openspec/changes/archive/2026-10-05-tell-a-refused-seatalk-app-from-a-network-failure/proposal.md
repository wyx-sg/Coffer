## Why

Every failed SeaTalk connection attempt was reported as the websocket state
`error`, and the Channels page words `error` as "SeaTalk rejected the
connection — replace the secret". Most failures are the network: a DNS failure
or a read timeout shows that banner for a second before the retry connects, and
replacing the secret would not have helped.

## What Changes

- The websocket reports `rejected` when SeaTalk refuses the app at the register
  handshake (the one frame that carries the App ID and App Secret), and keeps
  `error` for every other failed attempt. Both are still retried.
- The Channels page shows `rejected` as a rejected secret with **Replace secret**,
  and `error` as a network problem that is being retried, with **Reconnect now**
  and no offer to replace the secret.

## Impact

- Backend: SeaTalk websocket connector, status route, channel attention source.
- Frontend: channel state, status banner, en/zh copy.
- Specs: channels/seatalk.
