# A Machine Is Identified by a Hash of Its Host's Own ID, and Owns One Descriptor in the Tree

**Status**: Accepted
**Date**: 2026-09-14
**Deciders**: Yuxing Wu
**Related**: [Vault Sync](vault-sync.md), [Sync Deletion Breaker](sync-deletion-breaker.md), [Single Owner Machine for Unattended Rewrites](single-owner-machine-for-unattended-rewrites.md), [Credentials Across Machines](credentials-across-machines.md), spec vault-sync, spec channels, PRs #66, #381

## Context

The [converge round](vault-sync.md) itself needs no machine identity — its only
base is a local pointer. But three things key on "which machine is this" and
must keep meaning the same machine for its whole life:

- **Joining a remote.** A machine with no pointer is either new to the remote
  or returning to it after losing its pointer (a reinstall, a wiped
  `~/.coffer`). The two need opposite treatment, and the only way to tell them
  apart is whether the remote already knows this machine.
- **Bindings that name a machine.** A channel's `runs_on`
  (spec channels "Bind each channel to the one machine that runs it") and the
  curation owner
  ([Single Owner Machine for Unattended Rewrites](single-owner-machine-for-unattended-rewrites.md))
  are machine ids inside documents every machine holds.
- **A registry the user can read**: which machines share this vault, when each
  last converged, and whether each holds the same master key.

An identity that changes under a machine makes it a ghost: it rejoins as a
stranger, its old entry lingers with nobody to update it, and everything that
named it silently stops meaning this machine, with no error to explain why.
And an identifier committed to a remote the user may share must not be a raw
hardware serial.

## Options Considered

### Option A — Derive the id from the host, publish only a hash of it (chosen)

`infrastructure/sync/machine_id.py` reads the operating system's own stable
identifier — `IOPlatformUUID` from `IOPlatformExpertDevice` on macOS,
`/etc/machine-id` falling back to `/var/lib/dbus/machine-id` on Linux — and
`derive_machine_id` (`domain/sync/machine.py`) publishes
`sha256("coffer-machine:" + raw)` truncated to 16 hex characters
(spec vault-sync "Publish only a hash of the host identifier"). The result is
cached in `daemon-config.json`; a lost cache recomputes to the same value.
Where neither host identifier is readable, a UUID is generated once into
`~/.coffer/machine-id` (mode `0600`), and the surfaces say this machine will
not survive deleting `~/.coffer`
(spec vault-sync "Fall back to a stored identifier and say so").

Pros: survives uninstalling and reinstalling Coffer, which is the property
joining depends on; the raw identifier never leaves the machine; no
coordination needed to mint it.

Cons: a new motherboard or an OS reinstall on Linux changes the id, and a
container or unusual host falls back to a stored id with the weaker guarantee.
Both are reported rather than hidden, and a stale descriptor is retired in one
action (`coffer sync machine remove`).

It wins because it is the only option under which a machine that lost
everything Coffer stored can still be recognised as itself.

### Option B — A random UUID generated on first use and stored locally (the first design)

The first continuous sync (PR #66) minted an id and kept it in a singleton
`machine_identity` row in `coffer.db`.

Pros: portable to any host; no platform code.

Cons: it lives exactly as long as the pointer does, because both are in
`~/.coffer`. A reinstalled machine therefore comes back with a new id and no
pointer, is indistinguishable from a new machine, joins by union, and
republishes every document the other machines deleted while it was away — all
at once, with no conflict raised, because a union has no base to disagree
with. Its old registry entry is left behind as a ghost, and any channel or
owner binding naming it points at nobody.

Lost: an id that dies with the pointer cannot answer the one question joining
asks.

### Option C — The hostname

Use the machine's hostname as its id.

Pros: human-readable; survives reinstalling Coffer.

Cons: hostnames change (macOS rewrites them on network conflicts and when the
user renames the computer), collide across machines (`MacBook-Pro`), and leak
a personal label into a shared repository. A rename would re-key every binding.

Lost: not stable and not unique. The hostname survives as the *default* of
`machine_name`, a mutable label nothing references
(spec vault-sync "Treat the machine name as a label").

### Option D — The raw host identifier, unhashed

Publish `IOPlatformUUID` or `/etc/machine-id` as-is.

Pros: same stability as Option A; no hashing.

Cons: it is a hardware identifier, and the remote may be shared or public.
`/etc/machine-id`'s own documentation says it should not be exposed.

Lost: the hash costs nothing and removes the exposure.

### Option E — A synced machines table the machines co-edit

Keep the registry as one shared document or table listing every machine.

Pros: one place to read the fleet.

Cons: every machine writes every round to the same document, so the one piece
of state whose job is to describe the fleet becomes the most contended thing in
the tree and a steady source of merge conflicts.

Lost to one descriptor per machine: each machine writes exactly
`machines/<machine_id>.yaml` and no other machine's, so descriptors cannot
conflict, and the registry is simply whatever `machines/*.yaml` currently holds
(spec vault-sync "Derive the registry from the descriptors"). Descriptors are
never applied to anything local.

## Decision

`machine_id` is derived from the host and published only as a truncated
SHA-256 of a fixed prefix plus the raw value; `machine_name` is a user-editable label. Each machine
owns one descriptor, `machines/<machine_id>.yaml`, carrying its name, OS,
hostname, Coffer version, last converged day and commit, key fingerprint and
agent names (spec vault-sync "Carry the descriptor fields"). The day is
restamped at most once per calendar day, so an idle machine commits no
heartbeat.

**Joining** is decided from the remote's registry whenever a round starts with
no pointer (`application/sync/joining.py`;
spec vault-sync "Tell a new machine from a returning one"):

- **New** — the registry does not hold this id. Pointer := git's empty tree, so
  the diff can only contain additions: the machine takes the union and deletion
  is structurally impossible.
- **Returning** — the registry holds this id. Pointer := the
  `last_converged_commit` its own descriptor published, and the round is an
  ordinary stale-machine round: the remote's deletions apply, local edits
  survive, nothing resurrects
  (spec vault-sync "Recover a returning machine's base from its descriptor").
- **Returning with an empty vault** — the recovered base makes the empty vault
  read as "deleted everything", and the publish-side
  [breaker](sync-deletion-breaker.md) holds it; the user confirms, or rebuilds
  from the remote.
- **Returning whose base is gone from the history** — refused until the user
  picks: `--keep-local` joins as new, or rebuild. There is no safe default.

Joining is explicit. Only `coffer sync adopt` (or the web dialog's confirm)
joins, after stating which case it is and what it would move; an ordinary round
on a machine with no pointer applies and pushes nothing and ends
`awaiting_join` (spec vault-sync "Report a join before applying it").

## Consequences

- A reinstalled machine rejoins as itself: its descriptor is updated rather
  than duplicated, and channel and curation-owner bindings keep resolving.
- The pointer published in a descriptor is a record for that machine's own
  recovery, never an input to another machine's round.
- A machine on the fallback id is warned in the machines table that deleting
  `~/.coffer` makes it a new machine whose old descriptor must be removed by
  hand.
- Retiring a machine is deleting its descriptor; nothing else in the vault
  changes.
- Bindings that name a machine must distinguish "another machine in the
  registry" from "a machine the registry does not hold"; the second is a fault
  to report, which both the channel binding and the curation owner do.
