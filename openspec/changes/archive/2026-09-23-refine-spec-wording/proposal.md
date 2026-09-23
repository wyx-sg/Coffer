## Why

A review of the archived `align-specs-with-code` change against the code found
statements that are still more general than the code they describe: a CLI
command named without its subcommand, a secret-rotation rule that holds only for
an existing secret, a model picker described without its Default option, a
sticky agent choice described without the scope check that bounds it, and
similar details in residency, SeaTalk chunking, audit actors and wiring. This
change makes each of those statements exact.

## What Changes

- web-ui: the command-line audit reader is `coffer audit list`; the daemon
  residency card moves to the clicked value at once and settles on the daemon's
  answer.
- channels: `/new` and a recreated conversation use the sticky `/agent` choice
  while it is inside the channel's scope; channel management names what the
  list and the detail page each offer, which CLI group covers each operation,
  and how a first-time SeaTalk secret and a switch to websocket delivery treat
  refs.
- channels/seatalk: replies are split at 3500 characters before rendering and
  at 3900 bytes after it.
- chat and provider-switching: the per-conversation picker leads with a Default
  option, and an active connection that curates models, none of them `text`,
  offers none.
- daemon: `coffer daemon service status` reports "not supported" and succeeds on
  a host with no login service, while `install` and `uninstall` refuse.
- resource-framework: the audit actor vocabulary includes `sync`, named
  `system:` workers and `agent`.
- Data models and one contract description: the curation owner's blank
  normalisation, the audit actor list, the built-in skill seed's audit events,
  the agent kind's `on_enabled_changed` hook, and a test path.

## Capabilities

### New Capabilities

### Modified Capabilities

- `web-ui`
- `channels`, `channels/seatalk`
- `chat`
- `provider-switching`
- `daemon`
- `resource-framework`

## Impact

Specs under `openspec/specs/`, the resource-framework contract's audit `actor`
description, and two acceptance tests that now assert the Default option and
the scope-bounded `/new`. No runtime code changes behaviour.
