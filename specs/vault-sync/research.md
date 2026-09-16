# Research — Vault Sync

What ships is **bidirectional convergence with a git remote the user owns**
(constitution 0.6.0). This file records the background and the options weighed
to get there. Decision rationale lives in
[Vault Sync](../../docs/decisions/vault-sync.md).

That answer was reached twice. Convergence was withdrawn once in favour of a
one-shot vault export/import to a directory, and then reinstated; the section
[Why convergence came back](#why-convergence-came-back) is the argument for the
reinstatement, and it is the one place in this file that reasons about the
withdrawal. Export and import are **deleted** — nothing below advocates them.

## Problem

A single user runs Coffer on several machines; each vault diverges. The
constitution forbade a vendor cloud as system of record, so sync was a non-goal
until a bounded amendment allowed a **user-owned** medium.

## Transport options

| Option                         | History/merge | Local-first fit | Conflict handling | Verdict |
| ------------------------------ | ------------- | --------------- | ----------------- | ------- |
| **User-owned git repo**        | built-in      | strong (user owns remote) | git 3-way + per-file granularity | **chosen** |
| Peer-to-peer (Syncthing-style) | none          | strongest       | last-writer-wins, no history | deferred |
| User-owned object store (S3)   | none          | strong          | weak              | rejected |
| Hosted Coffer service          | n/a           | violates Principle I | n/a          | rejected |

Git wins for a developer audience: they already have git credentials, and we get
diff/history/merge for free.

## Why a separate working tree (not commit the live dir)

`coffer.db` is binary and unmergeable, and the live runtime dir mixes truth
(knowledge and skill files) with rebuildable or machine-local state (the db,
logs, `daemon-config.json`). A dedicated working tree that the vault is
serialized *into* keeps git diffs meaningful and lets SQLite remain the local
system of record. Knowledge and skills are already files, so they mirror
directly; config and credentials are projected to text.

This is the part of the 2026-06 research that is unchanged and load-bearing.
What it was originally built to serve — a one-shot export to a directory and an
import back — is gone, and the tree serves a converge round instead: the same
serialization, committed as a base git can three-way-merge against. The
argument for the tree never depended on the verb.

## Why ciphertext-only + out-of-band key

Putting the master key in the repo would make the ciphertext pointless and
violate the amendment. Exporting only ciphertext means even a GitHub-hosted
remote holds nothing usable. The one-time per-machine key bootstrap is the
accepted cost; until the key is present, ciphertext is reported as locked rather
than silently failing.

## Why convergence is automatic, not opt-in

The 2026-06 research reached the opposite answer — manual by default, auto as
an opt-in — on the reasoning that a single user is on one machine at a time, so
a round taken by hand is predictable and conflict-light. That was rejected once
convergence became the point of the feature rather than a convenience on top of
it: a vault that only converges when someone remembers to ask is the island
problem with an extra step, and two machines that disagree because nobody ran a
command is exactly the outcome the spec exists to prevent.

So the worker converges on the remote's interval as soon as a remote is
configured and enabled, which a configured remote is by default. The knob that
remains is the interval, and `enabled` is the off switch. `coffer sync` is a
command **group**, not a command — `coffer sync now` is the manual round, and
it is a way to not wait for the timer rather than the only way a round happens.

The surprises the opt-in was meant to avoid are handled where they occur
rather than by withholding the feature: background network is confined to
`git fetch` / `git push` against the user's own remote, an unchanged vault
makes no commit at all, a conflict stops the round with the vault untouched,
and an oversized deletion is held for confirmation in both directions.

## Determinism

Clean merges depend on stable serialization: sorted keys, normalized timestamps,
and excluding machine-local fields (`id`, `created_at`, `updated_at`). This is
unit-tested because it is load-bearing for the whole merge story.

## Why convergence came back

The reinstatement rests on three findings, and each is checkable against the
repository rather than remembered.

### 1. The 2026-07-10 incident was a defect in the export, not a refutation of convergence

Two commits closed it, and both name the same root cause.

`c856196f` — *merge-safe export, auto-resolve conflicts, remote probe (#290)*.
Its own description of the incident: two machines on different builds mutually
deleted skills, memory and resources because **export was destructive** — it
`rmtree`d and rewrote from local state — and ran **before** either machine's
first import. The fixes were all about making the exported tree honest: preserve
workspace documents that have no local row and no tombstone (pending import, not
deleted); propagate tree and credential deletions only after a run has completed
an import on this machine; converge case-alias credential paths (pre-v3
lowercased refs against v3 resource-name casing broke `git add` on macOS);
auto-resolve conflicts newest-wins per path; probe a remote headlessly before
accepting it. A review pass on the same PR found four more, and two of them are
worth carrying forward as lessons about this exact machinery: a conflicted file
with a Chinese name came back C-quoted from `git diff` and crashed auto-resolve
into an error retry loop (`core.quotepath=false` in `ensure_repo`), and a
transient error was suspending deletion propagation in a way that **resurrected
the user's deletions** through the same run's import.

`ad430204` — *credential guards from the 2026-07-10 stale-clobber incident
(#293)*. Three findings: `install_key` truncated the only copy of an existing
master key in place, permanently orphaning everything encrypted under it (it now
backs up to a timestamped sibling first); a Fernet blob embeds its encryption
epoch **in cleartext**, so two ciphertexts for one ref can be ordered with no
key at all, which one shared comparator now does in three places; and deleting a
resource left orphan credential rows that every future export re-seeded into the
vault until one clobbered a re-created ref on another machine — *the incident's
source*, in that commit's own words.

Read together, every one of those is a defect in **how the tree was written**.
None is an argument that two vaults cannot converge. The destructive export is
the single root cause, and a diff-based apply removes it structurally rather
than guarding against it: a deletion can only reach the diff because some
machine actually deleted that document relative to a shared base.

### 2. The 0.4.0 removal deleted the machinery, and the machinery was not what failed

`git show 1d58f5f2 --stat` — *replace continuous sync with vault export and
import (#314)* — is a 57-file change. It deleted the convergence slice outright:
`application/sync/` lost `auto_resolve.py`, `config_service.py`, `identity.py`,
`machines.py`, `slice.py` and `worker.py`; `infrastructure/sync/` lost
`git_repo.py` and `persistence.py`; `domain/sync/` lost `fernet_time.py`.
`exporter.py`, `importer.py`, `ports.py`, `service.py`, `models.py` and
`errors.py` were gutted, and migration 0049 dropped the four sync tables while
collapsing `scope` from two axes to one.

Three of those removals are now being undone, and it is worth being precise
about which: the **machine identity**, the **Fernet time comparator** — which
was the one guard in the whole slice that was provably correct without a key —
and **scope's machine axis**, which had been withdrawn only because the machine
registry that keyed it was going away.

> The machine axis came back and was withdrawn again the same day. The reason
> this time is not that machines stopped existing: a resource's *reach* — its
> `enabled` flag and its `scope` — was declared machine-local instead (FR-014),
> so each machine answers "what does this reach here?" for itself and the axis
> had nothing left to express (FR-032). See
> [Per-agent resource scope](../../docs/decisions/per-agent-resource-scope.md).

### 3. What replaced it did not answer the question, and half of it came back anyway

Export/import is a wholesale overwrite with no base: the importer takes the
bundle's version of everything the bundle contains. That is the same operation
that caused the incident, performed deliberately by hand. Three days later the
backup remote (constitution 0.5.0) re-added the git working tree and the
background worker for one-way use — two of the three pieces 0.4.0 had removed,
back within the same week, for a strictly weaker purpose.

### What this changed in the design

- The base is a **pointer**, kept locally and never travelling (FR-020). A pointer that
  travelled would be another machine's assertion read as your own.
- Export is **differential**, normatively (FR-038). It is the single root
  cause, so it is a rule in the spec rather than a property of an
  implementation.
- Deletions come from the diff (FR-037), which makes **tombstones, their TTL
  and timestamp arbitration unnecessary** — the majority of the 0.3.0
  machinery.
- `machine_id` is **derived from the host** (FR-022), so the registry can
  answer "have I been here before?" with no local state at all. That is what separates a new
  machine (take the union) from a returning one (recover the base), and it is
  the reason the join check can be trusted after a reinstall.
- The **Fernet freshness comparator returns verbatim** from `ad430204`
  (FR-060). It was
  correct, it is cheap, and it is the only rule that can order two ciphertexts
  without the key.
- The circuit breaker guards **both directions** (FR-068). The apply side was always
  obvious; the publish side is what stops a wiped vault from exporting its own
  loss — the 2026-07-10 shape reached from the other end.

### What survives from the earlier research, and what is reversed

Survives: git as the transport, a separate working tree the vault serializes
into, ciphertext-only credentials with an out-of-band key, the determinism
requirement, and path portability against each machine's home.

Reversed: **"manual default + opt-in auto"** — convergence is the point, so the
worker runs as soon as a remote is configured and enabled. And the
**export/import verb** the working tree was originally built to serve, which is
deleted; the tree it needed is not.
