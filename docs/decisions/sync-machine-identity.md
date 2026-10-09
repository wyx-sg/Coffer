# A Machine Is Identified by a Hash of Its Host's Own ID, and Owns One Descriptor in the Tree

**Status**: Accepted
**Date**: 2026-09-14
**Deciders**: Yuxing Wu
**Related**: [Sync Only Pulls and Pushes the Vault Repository; a Clean Merge Is Applied, Any Conflict Stops for the Person](sync-applies-clean-merges-and-stops-on-any-conflict.md), [A Sync Round That Would Lose Too Much Is Held, in Both Directions, Counting Losses Not Moves](sync-deletion-breaker.md), [Secrets Cross Machines Only as Ciphertext; the Master Key and the Push Token Never Enter the Repository](secrets-cross-machines-only-as-ciphertext.md), spec vault-sync, PRs #66, #381

## Context

A [sync round](sync-applies-clean-merges-and-stops-on-any-conflict.md) itself
needs no machine identity: it merges against a base git finds. But three things
key on "which machine is this" and must keep meaning the same machine for its
whole life:

- **Joining a remote.** A machine with no history with the remote is either new
  to it or returning to it after losing its local state (a reinstall, a wiped
  vault). The two need opposite treatment, and the only way to tell them apart
  is whether the remote already knows this machine.
- **Bindings that name a machine.** A document every machine holds may need
  to say which machine it means, by machine id.
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
action (`coffer sync machine rm`).

It wins because it is the only option under which a machine that lost
everything Coffer stored can still be recognised as itself.

### Option B — A random UUID generated on first use and stored locally

The design this replaced: the first continuous sync (PR #66) minted an id and
kept it in a singleton row of Coffer's own local store.

Pros: portable to any host; no platform code.

Cons: it lives exactly as long as the rest of Coffer's local state, because
both are in `~/.coffer`. A reinstalled machine therefore comes back with a new
id and no local state, is indistinguishable from a new machine, joins by union,
and republishes every document the other machines deleted while it was away,
all at once, with no conflict raised, because a union has no base to disagree
with. Its old registry entry is left behind as a ghost, and any
binding naming it points at nobody.

Lost: an id that dies with the local state cannot answer the one question
joining asks.

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
`machines/<machine_id>.json` and no other machine's, so descriptors cannot
conflict, and the registry is simply whatever `machines/*.json` currently holds
(spec vault-sync "Derive the registry from the descriptors"). Descriptors are
never applied to anything local.

## Decision

`machine_id` is derived from the host and published only as a truncated
SHA-256 of a fixed prefix plus the raw value; `machine_name` is a user-editable
label. Each machine owns one descriptor, `machines/<machine_id>.json`, carrying
its name, OS, hostname, Coffer version, the time and commit of its last
converged round, key fingerprint and each agent with its plugin inventory
(spec vault-sync "Carry the descriptor fields").

**Joining** is decided from the remote's registry whenever this machine has no
history with the remote (`application/sync/round_join.py`;
spec vault-sync "Tell a new machine from a returning one"):

- **Empty remote** — it holds nothing; this machine becomes the first and the
  first round pushes the whole vault.
- **New** — the registry does not hold this id. The machine takes the union:
  files only the remote has come down, files only this machine has go up, and
  a file both hold with different content stays as it is here and is not
  pushed until the person chooses. Joining never removes a file on either side
  (spec vault-sync "Join a new machine by taking the union").
- **Returning** — the registry holds this id. The base is the
  `last_converged_commit` its own descriptor published, and the join is an
  ordinary three-way merge: the remote's deletions apply, local edits survive,
  nothing resurrects
  (spec vault-sync "Recover a returning machine's base from its descriptor").
- **Returning with an empty vault** — the recovered base makes the empty vault
  read as "deleted everything", and the outgoing
  [breaker](sync-deletion-breaker.md) holds it for the person to confirm or
  restore
  (spec vault-sync "Hold a returning machine's empty vault instead of publishing the loss").
- **Returning whose base is gone from the history** — the recovered commit is
  no longer an ancestor of the remote, so the machine joins as new, by union:
  nothing is lost either way.

Joining is explicit and previewed. `coffer sync join` states which case it is
and what it would move before anything changes
(spec vault-sync "Report a join before applying it"); an ordinary round on a
machine that has not joined applies and pushes nothing.

## Consequences

- A reinstalled machine rejoins as itself: its descriptor is updated rather
  than duplicated, and any binding that names it keeps resolving.
- The commit published in a descriptor is a record for that machine's own
  recovery, never an input to another machine's round.
- A machine on the fallback id is warned in the machines table that deleting
  `~/.coffer` makes it a new machine whose old descriptor must be removed by
  hand (`coffer sync machine rm`).
- Retiring a machine is deleting its descriptor; nothing else in the vault
  changes.
- Bindings that name a machine must distinguish "another machine in the
  registry" from "a machine the registry does not hold"; the second is a fault
  to report.
