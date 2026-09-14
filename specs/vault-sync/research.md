# Research — Vault Sync

> 中文版: [research.zh.md](./research.zh.md)

> **Historical record.** This file captures the research that led to
> **continuous multi-machine sync over a user-owned git repository**. That
> approach has since been withdrawn: spec vault-sync now ships a one-shot vault
> **export/import** to a directory, with no remote, no workspace, and no
> background worker ([Vault Export and Import](../../docs/decisions/vault-sync.md),
> constitution 0.4.0). The notes below are kept as the record of the options
> that were weighed — they do not describe the current shape. Path portability,
> ciphertext-only credentials with an out-of-band key, and the determinism
> requirement are the parts that survived.
>
> **Amended 2026-09-13.** The withdrawal above was itself reversed: spec
> vault-sync now ships **bidirectional convergence** with a user-owned git
> remote (constitution 0.6.0). The 2026-06 notes below still describe the
> options that were weighed, and the transport choice they reached is the one
> in force again. What changed, and why, is appended as the last section of
> this file rather than edited into them.

Decision rationale lives in
[Vault Export and Import](../../docs/decisions/vault-sync.md) and the
constitution 0.3.0 amendment. This file records the background and the options
weighed.

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

## Why a separate workspace + export/import (not commit the live dir)

`coffer.db` is binary and unmergeable, and the live runtime dir mixes truth
(knowledge/memory files) with rebuildable/local state (db, logs, daemon.json).
A dedicated workspace with a text export keeps git diffs meaningful and lets
SQLite remain the local system of record. Knowledge/memory are already files, so
they mirror directly; config and credentials are projected to text.

## Why ciphertext-only + out-of-band key

Putting the master key in the repo would make the ciphertext pointless and
violate the amendment. Exporting only ciphertext means even a GitHub-hosted
remote holds nothing usable. The one-time per-machine key bootstrap is the
accepted cost; until the key is present, ciphertext is reported as locked rather
than silently failing.

## Why manual default + opt-in auto

A single user is usually on one machine at a time, so manual `coffer sync` is
predictable and conflict-light. Auto-sync (debounced push + interval pull) is
offered for hands-off convergence but stays opt-in to avoid surprise background
network and surprise conflicts.

## Determinism

Clean merges depend on stable serialization: sorted keys, normalized timestamps,
and excluding machine-local fields (`id`, `created_at`, `updated_at`). This is
unit-tested because it is load-bearing for the whole merge story.

## 2026-09-13 — why convergence came back

Appended after the 0.4.0 withdrawal was reversed. Three findings drove it, and
each is checkable against the repository rather than remembered.

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

### 3. What replaced it did not answer the question, and half of it came back anyway

Export/import is a wholesale overwrite with no base: the importer takes the
bundle's version of everything the bundle contains. That is the same operation
that caused the incident, performed deliberately by hand. Three days later the
backup remote (constitution 0.5.0) re-added the git working tree and the
background worker for one-way use — two of the three pieces 0.4.0 had removed,
back within the same week, for a strictly weaker purpose.

### What this changed in the design

- The base is a **pointer**, kept locally and never travelling. A pointer that
  travelled would be another machine's assertion read as your own.
- Export is **differential**, normatively. It is the single root cause, so it is
  a rule in the spec rather than a property of an implementation.
- Deletions come from the diff, which makes **tombstones, their TTL and
  timestamp arbitration unnecessary** — the majority of the 0.3.0 machinery.
- `machine_id` is **derived from the host**, so the registry can answer "have I
  been here before?" with no local state at all. That is what separates a new
  machine (take the union) from a returning one (recover the base), and it is
  the reason the join check can be trusted after a reinstall.
- The **Fernet freshness comparator returns verbatim** from `ad430204`. It was
  correct, it is cheap, and it is the only rule that can order two ciphertexts
  without the key.
- The circuit breaker guards **both directions**. The apply side was always
  obvious; the publish side is what stops a wiped vault from exporting its own
  loss — the 2026-07-10 shape reached from the other end.

### What survives from the 2026-06 research, and what is reversed

Survives: git as the transport, ciphertext-only credentials with an out-of-band
key, the determinism requirement, and path portability against each machine's
home.

Reversed: **"manual default + opt-in auto"** — convergence is the point, so the
worker runs as soon as a remote is configured. And **"a separate workspace +
export/import"** is half-reversed: the separate workspace is exactly right and
stays, while the export/import verb it was built to serve is deleted.
