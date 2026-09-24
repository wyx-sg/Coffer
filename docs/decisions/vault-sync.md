# The Vault Converges With One User-Owned Git Remote, Git's Merge as Arbiter

**Status**: Accepted
**Date**: 2026-09-13
**Deciders**: Yuxing Wu
**Related**: [principles](../../docs-site/architecture/principles.md) (Local-first — the user-owned sync remote exception), spec vault-sync, [Sync Deletion Breaker](sync-deletion-breaker.md), [Sync Machine Identity](sync-machine-identity.md), [Credentials Across Machines](credentials-across-machines.md), [Sync Withholds Derived Output](sync-withholds-derived-output.md), [Single Owner Machine for Unattended Rewrites](single-owner-machine-for-unattended-rewrites.md), [Resource Reach Is Machine-Local](resource-reach-is-machine-local.md), [Knowledge Is Plain Files](knowledge-is-plain-files.md), [Experimental Features Instead of a Release Branch](experimental-features-instead-of-a-release-branch.md), research note [multi-machine sync](../research/multi-machine-sync.md), PRs #66, #293, #314, #362, #381

## Context

Coffer is local-first: each machine owns its vault, and no vendor cloud is a
system of record. A developer who works from a laptop and a desktop produces
vault state on both — knowledge files, skills, MCP registrations, agent and
provider configuration, channel definitions, credentials — and needs the two to
be one vault rather than two islands.

The forces on the answer:

- **The vault is mostly files now.** Since
  [the knowledge layer became a directory of files](knowledge-is-plain-files.md)
  the bulk content is markdown under `~/.coffer/knowledge/` and skill folders
  under `~/.coffer/skills/`, edited by people in editors and by agents with
  their own file tools. What remains in SQLite is a few dozen small resource
  and state records that serialize deterministically to YAML.
- **Nobody approves a round.** Whatever converges the vault runs on a timer and
  writes the user's data with no human reading the diff. A wrong deletion is
  the failure that matters; a duplicate or a held round is recoverable.
- **The incident this design answers.** On 2026-07-10 two machines on different
  builds mutually deleted skills, memory and resources. The exporter of the
  first sync design cleared the tree and rewrote it from local state, and it
  ran before the machine's first import, so "I never had this" and "I deleted
  this" looked identical. In the same incident a machine re-exported a
  months-old orphaned credential blob and won simply by syncing last (PR #293
  carries the guards that came out of it).
- **The principles allow exactly one exception** to "state stays on your
  devices": a git remote the user owns, as a rendezvous rather than a system of
  record, converged under the safety rules the sync spec carries.

## Options Considered

### Option A — A convergence round against one git remote the user owns (chosen)

A background worker (default interval one hour, `DEFAULT_INTERVAL_SECONDS` in
`domain/sync/backup.py`) runs a **round** in a dedicated git working tree
(`~/.coffer/sync` by default, never inside the vault) in a fixed order
(spec vault-sync "Run the seven round steps in order"):

```
0  Repair    — working tree HEAD back to the pointer; refuse a layout this build does not know
1  Serialize — write the vault into the tree differentially, commit as L
2  Merge     — fetch, merge origin/<branch> into L → M
3  Diff      — D := L..M, exactly what the remote contributed
4  Guard     — deletion breaker in both directions; tag L as the pre-apply snapshot
5  Apply     — apply D to the vault path by path, deletions included
6  Publish   — push M; pointer := M; unapplied paths join the retry set
```

- **Local state is committed before the merge.** Pulling first fast-forwards a
  tree with no local commit, so git never gets the three inputs a three-way
  merge needs and the remote's version of a path overwrites whatever the vault
  changed there. Committing first gives git base, local and remote; since the
  vault equals `L` at that moment, `L..M` is precisely the remote's
  contribution, and applying it lands the vault on `M` with local edits intact.
- **The pointer** is the commit this vault has provably absorbed. It is stored
  in machine-local SQLite (`infrastructure/persistence/convergence_state_repo.py`)
  and is never an input another machine reads
  (spec vault-sync "Keep the pointer local"). It advances only when a round
  completes (spec vault-sync "Advance the pointer only on absorption"). Because
  everything applied is relative to it, a deletion reaches the vault only when
  some machine actually deleted that document against a shared base; a machine
  that merely *lacks* a document has changed nothing relative to its own base
  (spec vault-sync "Apply a deletion only when the diff carries one").
- **The retry set** holds paths the tree carries that this vault failed to
  absorb. The exporter never publishes a retry-set path as a deletion
  (spec vault-sync "Never export a retry-set path as a deletion"), and the
  exporter writes differentially, never clearing and rewriting a directory
  (spec vault-sync "Export differentially") — the two rules that keep the diff
  honest. A path that cannot apply on this machine at all (an `agent` whose
  `config_dir` does not exist here) is held as *not applicable here* rather
  than retried.
- **Git's three-way merge is the arbiter.** Two machines editing different
  parts of one document is the common case and git merges it unaided. What git
  cannot settle goes to `ConflictArbiter` (`application/sync/conflicts.py`), in
  narrowing layers:
  1. credential ciphertext is ordered by its cleartext Fernet encryption time
     and the fresher encryption wins, without the key
     ([Credentials Across Machines](credentials-across-machines.md));
  2. in `knowledge/` and `skills/`, a delete-versus-edit conflict keeps the
     edit — the deletion is a housekeeping judgement a curation pass will make
     again, the edit is unrecoverable if lost
     (spec vault-sync "Let an edit beat a curation deletion");
  3. where an internal model is configured, a bounded agent pass
     (`infrastructure/sync/conflict_resolver.py`: caps on files, file size and
     time) attempts the rest **in the working tree only**, and its output must
     pass a validation gate — file exists, no conflict marker, a resource or
     state document still parses (spec vault-sync "Validate an agent's resolution");
  4. otherwise the round aborts: the vault is untouched, the pointer does not
     move, and the surfaces name the conflicted paths and the working tree
     (spec vault-sync "Abort the round on an unresolved conflict").
- **Two guards bound a defect in the apply.** `L` is tagged as a pre-apply
  snapshot (ten kept, `SNAPSHOTS_KEPT` in `application/sync/convergence_ops.py`),
  so rollback is the same machinery run backwards and does not move the pointer
  (spec vault-sync "Snapshot before applying and roll back from it"). And the
  [deletion breaker](sync-deletion-breaker.md) holds a round that would lose
  too much, in either direction.

Pros: git already does diff, history, three-way merge and transport, and every
developer already holds credentials for a forge. Tombstones dissolve into the
commit graph; arbitration dissolves into `git merge`; quarantine collapses to a
retry set; identity collapses to a local pointer. The remote is inspectable
with ordinary tools, `git clone` of it is a full backup, and a `file://` remote
on a USB drive is an offline medium.

Cons: Coffer now writes the vault unattended, which is why the pointer, the
snapshot and the breaker are normative rather than nice to have. A real
conflict blocks convergence on both machines until someone resolves it. The
serializer's determinism becomes load-bearing: a non-deterministic field would
be a spurious conflict every round (spec vault-sync "Serialize deterministically").

It wins because every guarantee convergence needs is either something git
already provides or a small, locally checkable rule around it — and because the
content being converged is, at last, the files git sees rather than a
projection of a database.

### Option B — Per-resource timestamps and tombstones in Coffer's own code (the first design)

The first sync (PR #66, extended through PRs #281–#293) converged a git
repository too, but arbitrated in Coffer: tombstones with a TTL recorded
deletions, a per-resource timestamp decided competing edits, failed imports
were quarantined and retried, and a file watcher plus a remote probe pushed and
pulled within seconds.

Pros: near-real-time; conflicts never stopped a round.

Cons: the bulk content was then a database projected into files, so the diff
git computed was not the diff the vault made, and every guarantee had to be
re-established outside git against a projection that could disagree with its
source. Timestamp arbitration is "newest commit wins", which is a fact about
when a machine ran, not about what the user meant — exactly how the months-old
credential blob won on 2026-07-10. The exporter's wholesale rewrite is what
made the mutual deletion possible.

Lost on the incident. It was removed in PR #314 (2026-09-09). The machinery it
priced as too expensive is cheap now only because the content moved into
files; rebuilding tombstones and arbitration today would re-implement outside
git four things git does.

### Option C — Last writer wins by file modification time

Treat each path as a register; the copy with the later mtime wins.

Pros: trivial; no merge.

Cons: mtimes are wall-clock values from different machines, reset by checkouts
and restores, and a stale machine that merely touches a file wins. Two edits to
different sections of one note — the common case — lose one of them outright
where git would have merged both. A deletion has no mtime at all, so it needs
tombstones, which is Option B again.

Lost: it loses data in the commonest concurrent case and orders by an
unreliable clock.

### Option D — A CRDT or state-based replication

Model documents as CRDTs (Automerge, Yjs) or replicate operation logs, so
concurrent edits merge without conflicts by construction.

Pros: no conflict ever stops a round; merges are principled.

Cons: a CRDT merges *operations*, and nothing that writes the vault produces
them — people edit notes in their own editors and agents write with their own
file tools, so every write would have to be diffed back into operations after
the fact. The storage format stops being plain files a person can read or a
forge can show. A conflict-free merge of two contradictory edits to a note or
a resource config is still a wrong document; it is just a silent one. And it
needs a relay or a store of its own.

Lost: it fights the "plain files, any editor" property the knowledge layer was
built on, and hides exactly the disagreements a user should see.

### Option E — One-way backup push

A worker exports the vault on a timer into a git working tree, commits and
pushes; it never pulls, so nothing arbitrates. Shipped in PR #362 (2026-09-12).

Pros: no inbound writes, so nothing can corrupt the vault; answers "my disk
died" and "restore what I deleted last week".

Cons: two machines still drift apart, and Coffer neither notices nor
reconciles. Closing the gap needs a manual import, which is Option F's hazard.

Lost: it solves backup, not "one vault". Its working tree and timer worker are
what Option A reuses.

### Option F — Export and import through a directory

`coffer sync export <dir>` writes a bundle; `import` reads one back and
overwrites. Shipped in PR #314 as the replacement for Option B.

Pros: explicit, simple, no background writer.

Cons: an import is a wholesale overwrite with **no base**, so a stale bundle
silently overwrites a fresh vault and deletions cannot be told from absences —
the shape of the 2026-07-10 incident. It also relies on someone remembering to
do it.

Lost, and deleted in PR #381: it cannot coexist with a diff-based apply,
because keeping it keeps a supported path by which a stale machine overwrites
a fresh vault. Its uses are covered with a base: a new machine runs
`coffer sync adopt`, an offline medium is a `file://` remote, a copy for
someone else is `git clone ~/.coffer/sync`.

### Option G — A hosted Coffer sync service

A Coffer-run endpoint stores and merges every user's vault.

Pros: the best onboarding; no forge or credential for the user to set up.

Cons: a vendor-controlled system of record, which the principles forbid
outright ("Not a hosted sync service"), and a service to run.

Lost on principle.

### Option H — File-level sync of `~/.coffer` (Syncthing, a cloud drive)

Point a file synchroniser at the whole directory.

Pros: zero Coffer code.

Cons: it carries machine-local state (`coffer.db`, `daemon-config.json`, logs,
the memory tree), and the database is a binary SQLite file under WAL that
cannot be merged or partially applied — two machines writing it produce a
conflicted copy or a corrupt one. These tools resolve by last writer wins
(Option C) and keep no history to restore from.

Lost: it syncs the wrong things and cannot merge the right ones.

### Option I — Leave the file trees to the user's own git and sync only structured state

Let users version `knowledge/` and `skills/` themselves; Coffer syncs the
SQLite-backed records.

Pros: less Coffer code; users keep full control of their notes.

Cons: if Coffer runs the pull it is convergence anyway and needs Option A's
rules; if the user runs it, Coffer is not syncing and the drift stays. It also
cuts through the `skill` kind, whose folder and registry row are two faces of
one resource, leaving half of it on each side.

Lost: it splits single resources across two mechanisms and solves nothing.

## Decision

Coffer converges the vault with **at most one** git repository the user owns
(spec vault-sync "Allow at most one user-owned sync remote"), by the seven-step
round of Option A. The remote is a rendezvous, never a system of record: every
machine's vault stays complete, so the remote can be deleted and rebuilt from
any single machine (spec vault-sync "Keep the remote a rendezvous, not a system of record").

Rules a future change must respect:

- Local state is committed before the merge; the applied change is always
  `L..M` relative to the local pointer, never a state copied over the vault.
- The exporter writes differentially and never publishes a retry-set path as a
  deletion.
- Coffer adds no arbitration of its own beyond the layered rules above; a new
  "newest wins" resolver for anything other than credential ciphertext is a
  regression to Option B.
- An unresolved conflict stops the round with the vault untouched.
- One lock guards every rewriter of vault content: the converge service's lock
  (`application/sync/service.py`) is injected into the knowledge curation
  pass, because an export taken mid-rewrite is a torn snapshot git reads as a
  deliberate change (spec vault-sync "Never overlap a curation pass and a round").
- The sync package imports no kind. Kinds reach it through ports the
  composition root registers — `ImportGate`, `ImportNormaliser`,
  `PostImportHook` and `SyncedStatePort` in `application/sync/ports.py` — and
  the "Cross-kind imports forbidden (sync)" import-linter contract in
  `backend/pyproject.toml` enforces it.
- Reach (`enabled`, `scope`) never travels
  ([Resource Reach Is Machine-Local](resource-reach-is-machine-local.md)); derived
  output never travels ([Sync Withholds Derived Output](sync-withholds-derived-output.md));
  conversations, the audit log and MCP invocation records stay machine-local
  (spec vault-sync "Keep machine-local state out of the repository").
- The whole capability is the `vault_sync` experimental feature
  (`domain/features.py`), off by default on the stable channel: while off, the
  `/api/v1/sync` routes answer `FEATURE_DISABLED` and the worker skips its
  rounds ([Experimental Features Instead of a Release Branch](experimental-features-instead-of-a-release-branch.md)).

## Consequences

- The only egress is `git fetch` / `git push` to the user's own remote, from one
  git adapter (`infrastructure/sync/git_mirror.py`, `git_invoke.py`) run with the
  user's global and system git config pinned away.
- A round with nothing to say makes no commit and is still recorded as
  successful (spec vault-sync "Make no commit for a round with nothing to say"),
  so an idle vault does not fill the remote's history.
- A vault that needs a human — held, conflicted, failing to push, or waiting to
  join — says so where the user already is: `coffer sync status` exits non-zero,
  the web navigation entry is marked and the desktop shell notifies
  (spec vault-sync "Say a vault needs a human where the user already is"). A held
  vault converges no further, so a hold nobody sees is an outage.
- Paths are stored against a `${HOME}` sentinel so a config survives a machine
  with a different home directory; paths outside home travel verbatim and may
  fail per path.
- A remote written by a newer layout is refused (`SYNC_BUNDLE_TOO_NEW`) rather
  than half-applied.
- Joining a remote is its own decision ([Sync Machine Identity](sync-machine-identity.md)),
  as are the breaker ([Sync Deletion Breaker](sync-deletion-breaker.md)), the
  master key and push credential ([Credentials Across Machines](credentials-across-machines.md))
  and the one-owner rule for unattended rewriters
  ([Single Owner Machine for Unattended Rewrites](single-owner-machine-for-unattended-rewrites.md)).
