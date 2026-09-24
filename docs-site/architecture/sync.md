# Vault Sync

::: tip Mental model
Vault sync converges the vault with **one user-owned git remote** (spec `vault-sync`, ADR vault-sync), so that the user's own machines hold one vault rather than several. It is the one bounded exception to [Local-First](/architecture/principles#i-local-first-non-negotiable): the remote is a rendezvous, never a system of record; secrets travel as ciphertext only; and the feature is off by default. It is cross-cutting, not a kind, and it is an [experimental feature](/architecture/experimental-features) (`vault_sync`). For the user-facing view see the guide page [Sync](/guide/sync).
:::

## Where it lives

`application/sync/` (the converge round, exporter, appliers, worker and ports) + `infrastructure/sync/` (the git mirror, tree mirror, bundle and machine id), with CLI (`coffer sync …`) and HTTP (`/api/v1/sync`) surfaces. The sync package imports no kind — kinds reach it through `SyncedStatePort` / `ImportGate` (`application/sync/ports.py`), registered at the composition root.

## The converge round

A worker shaped like `RetentionWorker` runs a **converge round** on a timer; `coffer sync now` forces one. A round:

1. serializes the vault differentially into the git working tree and commits it as `L`;
2. merges `origin/<branch>` into `L`, giving `M`;
3. applies the diff `L..M` back into the vault path by path — deletions included;
4. pushes, and advances the **pointer**: the local-only record of the commit this vault provably absorbed, and the base of every diff.

Paths that fail to apply join a **retry set** the exporter must not delete, so a pending document is never published as a deletion. A machine with no pointer is **joining**, and the machine registry tells a new one (pointer := git's empty tree, so the diff can only add) from a returning one (pointer := the commit its descriptor names).

Applying a diff writes knowledge and skill files, upserts resource documents through the resource service with `${HOME}` expanded and the kind's import gate run, hands `state/<area>/**` to its owning module, and re-runs each kind's post-import hook.

## Arbitration and safety

- **Git's three-way merge arbitrates.** Credential blobs are ordered by encryption time instead; an unresolved conflict aborts the round untouched.
- **A pre-apply snapshot tag** (`coffer/pre-apply/…`) marks the commit before each apply.
- **A circuit breaker** holds an oversized deletion for confirmation, in both directions (`sync_held_paths`, see [Persistence](/architecture/persistence#table-map)); both answers are audited.
- **The round's lock is shared with the knowledge curation pass**, so no export captures a half-finished rewrite.

What does and does not leave the machine — ciphertext only, the master key moved only out-of-band — is in [Security → Sync security](/architecture/security#sync-security).

## Machines

Each machine writes one `machines/<machine_id>.yaml` it alone owns, so the registry is a derived view of the tree rather than a synced table. `machine_id` is derived from the host and hashed before it travels, so a reinstall leaves no ghost. The pointer, retry set, not-applicable set and any held round live in machine-local SQLite (`infrastructure/persistence/convergence_state_repo.py`).

## What travels

- **A resource document carries identity, description and config alone.** A resource's **reach** — its `enabled` flag and its agent `scope` — is machine-local and never converges, so an import leaves the local reach exactly as this machine set it, and a newly arrived resource lands at this machine's own default (ADR per-agent-resource-scope).
- **Every converging kind is serialized, `channel` included.** A channel carries the one machine whose daemon runs its adapter (`runs_on`) inside its own config, so the document converges while the adapter stays put (spec channels "Bind each channel to the one machine that runs it"). Channel peer pairings are a synced state area for the same reason — a channel that travelled without them would make the owner re-pair on every rebind — carrying platform identity only, never this machine's conversation pointer.
- **Derived rows are withheld.** A kind declares `converges=False` to hold back all its rows (`memory`, whose partitions are derived from the agents installed on one machine) or `converges_row` to hold back one: `skill` withholds the `coffer-guide` row, whose rendered text lists this machine's *enabled* collections and so differs between machines. The mirrored `skills/` tree leaves that folder alone in both directions (spec vault-sync "Withhold derived output in both halves"); each machine renders its own.
- **No one-shot export or import.** The export-to-a-directory and import-of-one-back surfaces are deleted — a wholesale overwrite with no base has no place beside the diff-based apply.
