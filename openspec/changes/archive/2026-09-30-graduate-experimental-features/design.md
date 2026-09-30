## Context

[experimental-features](../../specs/experimental-features/spec.md) lets `main` carry a capability
that a stable build keeps switched off. It was written for three features — Sync, Knowledge and
Memory — and its requirements named them. Those three are ready, and this change graduates them.
The choice of feature gates over a release branch is argued in
[Experimental Features Instead of a Release Branch](../../../docs/decisions/experimental-features-instead-of-a-release-branch.md).

## Decisions

### 1. Keep the mechanism, graduate the three

The three features graduate; the mechanism does not go with them. The registry, the order of
decision (pin, setting, channel), the switch routes and CLI keys, the error codes and the generic
gates stay, with an empty registry. The next feature that is not ready joins with one entry and
reuses every surface as it is.

*Rejected:* deleting the whole mechanism with the last three features. Rebuilding it for the next
unready feature would mean re-deciding every gate, and the gates are already written against the
registry rather than against any one key, so keeping them costs almost nothing while the registry
is empty.

### 2. How a feature joins and leaves

A feature **joins** by adding one registry entry naming its route prefixes and the kinds it owns,
and by tagging its other surfaces with its key: a built-in tool, an agent directory, an attention
source, a sidebar entry, a background pass. The generic gates then close each of them while it is
off. Anything a feature puts in front of agents outside those tags — a hook, a guide section, a
channel command — needs its own withdrawal, and the spec requirement "Withdraw what a
switched-off feature put in front of agents" names that obligation.

A feature **leaves** by deleting its entry and every gate and tag naming it, in the same change,
plus a migration that strips its key from `~/.coffer/daemon-config.json`. Migration 0116 does
this for `vault_sync`, `knowledge` and `memory`.

### 3. An unregistered stored key is ignored, not an error

A daemon config written by an older build, or a key the migration could not strip (an unreadable
file), holds a key the registry does not name. Every read ignores it and logs it; nothing lists it
and nothing fails on it. *Rejected:* refusing to start, which would turn a stale preference into an
outage, and deleting the key on read, which is a write the migration already owns.

### 4. The memory hook is installed only by a person's act

Switching `memory` on used to install the delivery hook into every connected agent. With no
switch, nothing unattended installs it: connecting an agent installs every part its type has,
and a boot or periodic reconcile pass reports a missing hook (the connection reads partial) until
the user connects the agent or applies the item. This keeps memory's rule that Coffer never
installs a hook silently.

### 5. The General card renders only while a feature is registered

An empty card, or a heading over nothing, is the placeholder the web UI's sidebar rules already
refuse. The card component stays mounted on General and renders nothing while the registry is
empty, so a feature that joins gets its switch with no UI change.
