## Context

The idle stand-down is specified in [daemon](../../../openspec/specs/daemon/spec.md)
"Stand down after an idle window" and implemented as one monotonic clock plus a
set of named holds (`infrastructure/daemon/activity.py`), fed by an ASGI
middleware that brackets every request and read by an idle-watcher task in
`infrastructure/daemon/entry.py`. The only hold a subsystem registers is the
SeaTalk callback listener's, which change `remove-seatalk-webhook-delivery`
deletes with the listener. Residency is described in
[Detect-or-Spawn](../../../docs/decisions/daemon-detect-or-spawn.md).

## Goals / Non-Goals

**Goals:**

- The daemon never exits on its own for want of use.
- Every surface that configured the window — REST, CLI, the settings page, the
  config file — stops offering it, and an existing config file keeps working.

**Non-Goals:**

- Changing the login service, supersession ("Stand down only when provably
  superseded") or the `/mcp` session evictor, which reaps idle MCP sessions and
  is not the daemon's own lifetime.

## Decisions

### Delete the clock rather than default the window to "never"

"Never" was already a setting, so the smallest change would have made it the
default. That keeps a clock, a hold registry, a middleware on every request, a
CLI group and a UI control whose only remaining use is to switch on the
behaviour the owner has ruled out. Deleting them removes the class of bug the
holds existed for — a subsystem that must be reachable but forgot to hold.

### Drop the stale config key on write, ignore it on read

`daemon-config.json` is written by merge so that a key from a newer build
survives an older one. `idle_shutdown_hours` is the exception: every write
removes it, so the file stops stating a setting that decides nothing, and a read
ignores it until then. No migration is involved, because the file is read
before the database opens. A downgrade to an earlier build reads an absent key
as that build's default of twelve hours, which is that build's own behaviour.

### Keep `PUT /api/v1/daemon/residency` as the route

The route keeps its name and shape minus one field, so the settings page and any
script calling it keep working with a smaller body. A body still carrying
`idle_shutdown_hours` is accepted and the field ignored, per the request model's
default handling of unknown fields.

### Coordination with `remove-seatalk-webhook-delivery`

That change deletes the listener's hold and the channel runtime's `service_hold`
callback along with the listener; this change deletes the hold mechanism the
callback fed. Whichever lands its code first owns `channel_wiring.py` and
`application/channel/runtime.py` for that edit; the other finds it done. The two
changes' spec deltas touch disjoint requirements.

## Risks / Trade-offs

- **A daemon nobody uses stays resident.** → Accepted: its footprint is one
  process, and `coffer daemon stop` or removing the login service ends it.
