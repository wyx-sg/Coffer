## Why

Switching a SeaTalk channel on showed "SeaTalk rejected the connection — replace
the secret" for a moment before it turned connected. The daemon starts a
channel on its next reconcile tick, so a status read just after the enable found
the adapter not running, and the Channels page reads every "not running" as a
start that failed, which it words as a rejected secret.

## What Changes

- The channel status carries `starting`: enabled for this machine and not
  running only because the daemon has not reached it yet. It is false once a
  start was attempted (and failed), the channel routes nowhere, or its secret
  waits for approval.
- A channel switched off forgets its last start failure, so switching it back on
  starts a new run at once and does not report the old run's failure.
- The Channels page shows such a channel as connecting, also while the status it
  holds still predates the switch; the Overview raises no "not running" item for it.

## Impact

- Backend: channel runtime, channel status, channel attention source, status route.
- Frontend: channel state.
- Specs: channels.
