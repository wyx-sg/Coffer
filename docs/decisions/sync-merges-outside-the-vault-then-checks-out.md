# Sync Merges Outside the Vault With `git merge-tree`, Then Guards, Then Checks Out

**Status**: Proposed
**Date**: 2026-09-29
**Deciders**: Yuxing Wu
**Related**: [The Vault Converges With One User-Owned Git Remote, Git's Merge as Arbiter](vault-sync.md) (superseded by this ADR once accepted), [A Sync Round That Would Lose Too Much Is Held, in Both Directions, Counting Losses Not Moves](sync-deletion-breaker.md), [A Machine Is Identified by a Hash of Its Host's Own ID, and Owns One Descriptor in the Tree](sync-machine-identity.md), [Credentials Cross Machines Only as Ciphertext; the Master Key and the Push Token Never Enter the Repository](credentials-across-machines.md), [An Unattended Rewriter of Synced Content Runs on One Named Owner Machine](single-owner-machine-for-unattended-rewrites.md), [Sync Withholds Derived Output; Each Machine Renders Its Own](sync-withholds-derived-output.md), [Storage Is Five Classes by Nature; Whether a Class Syncs Is Policy](storage-is-five-classes-by-nature.md), [A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](identity-is-the-uid-inside-the-file.md), [Every Vault File Carries Its Own Format Version; One Owner Machine Commits Layout Upgrades](every-vault-file-carries-its-format-version.md), [Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer](every-vault-write-is-a-validated-commit-naming-its-writer.md), [One Level-Triggered Reconciler Converges What Coffer Writes Outside Its Database, Comparing Parameters](one-level-triggered-reconciler-compares-parameters.md), [principles](../../docs-site/architecture/principles.md) (Local-First — the user-owned sync remote exception), research note [multi-machine sync](../research/multi-machine-sync.md), spec vault-sync "Run the seven round steps in order", spec vault-sync "Keep the working tree outside the vault", spec vault-sync "Keep the pointer local", spec vault-sync "Snapshot before applying and roll back from it", spec vault-sync "Guard both directions", spec vault-sync "Let the fresher credential ciphertext win", spec vault-sync "Abort the round on an unresolved conflict"

## Context

[The Vault Converges With One User-Owned Git Remote](vault-sync.md) runs a
seven-step round in a **second copy** of the vault — a git working tree at
`~/.coffer/sync` (`DEFAULT_WORKTREE`, `domain/sync/backup.py:34`) — because
the vault was a database plus two file trees, and git can only merge files:

```
0 Repair  1 Serialize (vault → tree, commit L)  2 Merge (git merge in the tree → M)
3 Diff L..M  4 Guard  5 Apply (tree → vault, path by path)  6 Publish (push; pointer := M)
```

Steps 1 and 5 are translations, and most of the package's weight: the
exporter, the three appliers, the document projection and the
backwards-compatibility layer are 1,094 of its 6,720 lines, with 512 more in
per-kind `sync_state` / `sync_reconcile` adapters. The merge itself runs in the
tree with `git merge --allow-unrelated-histories`
(`infrastructure/sync/git_mirror.py:142-157`), writing conflict markers into
the tree's files for the arbiter to settle. The apply copies each path back
into the live vault with an unconditional, in-place `write_bytes`
(`application/sync/appliers.py:91-101`). The pointer — the last commit this
vault absorbed — is a row in machine-local SQLite
(`infrastructure/persistence/convergence_state_repo.py`), beside a retry set of
paths that failed to apply.

Once the vault is itself a git repository in which every accepted write is
already a commit
([Every Vault Write Is One Validated, Compare-and-Swap Commit](every-vault-write-is-a-validated-commit-naming-its-writer.md)),
the second copy has nothing left to do: there is nothing to serialize, and the
merged result can be checked out into the vault directly — if the merge can be
computed without touching the vault's files, so that the guard runs before
anything changes. `git merge-tree --write-tree` (git 2.38 and later) computes
a merge entirely in the object store and prints the resulting tree and its
conflicts, touching neither the working tree nor the index. The development
machine runs `git version 2.50.1 (Apple Git-155)`.

## Options Considered

### Option A — Merge in the object store, validate and guard the result, then check it out (chosen)

The vault repository is the only repository. A round:

```
0 Check    — the vault is a repository, git ≥ 2.38, no merge left in progress
1 Local    — L := HEAD (every accepted write is already committed)
2 Fetch    — origin/<branch>
3 Merge    — git merge-tree --write-tree L origin/<branch> → tree T + conflicts,
             nothing in the vault touched
4 Settle   — the arbiter's layers settle what git could not; unresolved → abort
5 Guard    — validate T; the deletion breaker in both directions
6 Check out — tag L as the snapshot; M := commit(T, parents L and origin);
             read T into the vault, refusing first if any path it changes
             differs from L on disk; HEAD := M
7 Publish  — push M
```

- **The pointer is the vault repository's `HEAD`.** It is by construction the
  last tree this vault checked out after validation and guarding — "the commit
  this vault has provably absorbed" — and like every ref, it never travels
  unless pushed as a branch, which it is not. The pointer table and its
  repository go away.
- **Settling (step 4) keeps today's layers.** Credential ciphertext changed on
  both sides is settled by the fresher Fernet encryption time, read from the
  two blobs without the key; a path only one side changed is simply taken, so
  ciphertext never reaches a text merge. In `knowledge/` and `skills/`, a
  delete-versus-edit conflict keeps the edit. Where an internal model is
  configured, a bounded agent pass attempts the rest in a scratch worktree of
  the vault repository under `derived/`, and its output must pass the same
  validation gate. Anything else aborts the round with the vault untouched and
  the paths named. The settled tree is written through a temporary index, not
  the vault's.
- **Guarding (step 5) happens before any file changes.** The merged tree is
  validated by the same validator every writer passes (a duplicate uid, a
  file at an unreadable format version, a malformed document). The breaker
  keeps its thresholds (20% of an area or 20 documents) and both directions:
  incoming is `L → T`, outgoing is what `L` deletes relative to the merge base.
  For resource files it counts **lost uids**, so a moved or renamed file is a
  move by construction
  ([A Resource's Identity Is the `uid` Inside Its File](identity-is-the-uid-inside-the-file.md));
  for tree files it keeps content-id and rename pairing. A layout commit is
  checked by its stricter no-loss rule instead
  ([Every Vault File Carries Its Own Format Version](every-vault-file-carries-its-format-version.md)).
- **Checking out (step 6) is a compare-and-swap on the whole tree.** Under the
  vault's write lock, git's two-tree read (`read-tree -m -u L M`) verifies
  every path it will change against `L` **before writing any file**, and
  refuses if a person has an uncommitted or invalid edit there; the round then
  waits and names the path rather than overwrite it. Watch hints for the paths
  the checkout writes are suppressed, and each changed resource produces one
  `Changed` hint for the reconciler, which re-renders every per-machine side
  effect — the job the post-import hooks did.
- **Rollback** checks out a snapshot tag through the same write path, as a new
  commit, and does not move `HEAD` backwards.
- **Ciphertext subtree.** With the remote's `include_credentials` off,
  `vault/credentials/` is never committed, so it is neither pushed nor merged;
  with it on, it is committed and settled as above. Ciphertext that has entered
  a pushed commit cannot be withdrawn; revocation is rotation.
- **A vault inside a file synchroniser is warned about.** If the vault path is
  inside a Syncthing folder (an ancestor holds `.stfolder`), iCloud Drive
  (`~/Library/Mobile Documents/`) or a File Provider root
  (`~/Library/CloudStorage/`), the Sync page and `coffer sync status` say that
  this is unsupported: those tools resolve conflicts by last writer or conflict
  copy and would replicate the repository's internals underneath git (the
  research note's survey; [the superseded ADR's](vault-sync.md) Option H).

Pros: the translation layer, the second working tree, the pointer table and
the retry set are deleted rather than maintained; the breaker judges a merge
before it lands instead of after the tree has been written; a person's
in-flight edit is never overwritten by a round, because git refuses the
checkout first; conflict markers never appear in files an agent or a person
reads.

Cons: it depends on git 2.38 or later; a round that finds a person's edit on a
path it would change waits until the edit is committed or discarded; the agent
resolution pass needs a scratch worktree, the one place a second checkout
survives; the checkout rewrites files one by one, so a reader can see a mix of
`L` and `M` while it runs — bounded by the write lock for Coffer's own readers,
not for an editor that happens to read then.

It wins because it keeps every safety property of the current round — base,
three-way merge, guard, snapshot — while removing the two translations that
were only needed because the vault was not files.

### Option B — Keep the separate working tree and its serialize and apply steps

Leave the round as it is, pointed at a vault that is now files.

- **Pros.** The code exists and its guards are proven in the field.
- **Cons.** It keeps two copies of every file and copies between them twice a
  round; the apply stays per path and in place, so a person's edit between
  serialize and apply is overwritten and a reader can see a half-written file;
  and the 1,606 lines of translation stay to move files that no longer need
  translating.
- **Why it loses.** Its reason to exist — a database git could not merge — is
  gone.

### Option C — Merge in the vault's own working tree (`git pull` / `git merge`)

- **Pros.** The most ordinary git workflow; no temporary index.
- **Cons.** A conflicted merge writes markers into live files that agents read
  and the reconciler projects; an aborted merge must be undone in the vault
  itself; and the guard can only look at the merge after the working tree has
  already changed, which reverses the order the breaker depends on.
- **Why it loses.** It makes the vault the scratch space for a merge that may
  be refused.

### Option D — Rebase local commits onto the remote

Replay this machine's commits on top of `origin/<branch>` for a linear history.

- **Pros.** A linear, readable history.
- **Cons.** A rebase rewrites every local commit, changing the ids that audit
  rows and a skill's History tab cite, and turns one merge into one conflict
  per replayed commit. It also rewrites history the other machine may already
  have fetched.
- **Why it loses.** History that Coffer cites must never be rewritten.

### Option E — A permanent second worktree of the vault repository for merging

Do today's merge in a `git worktree` of the vault repository rather than a
separate repository, and check out from there.

- **Pros.** No new git plumbing; the merge still happens outside the vault's
  files.
- **Cons.** A full second checkout of the vault on every machine, kept in step
  on every round, to host a merge that `merge-tree` computes without one.
- **Why it loses.** It is only needed for the rare agent-resolution pass, and
  there it is kept.

## Decision

A sync round merges the vault's `HEAD` with the remote in git's object store
using `git merge-tree --write-tree`, touching no vault file; settles what git
could not by the existing layered rules or aborts; validates the merged tree
and runs the deletion breaker in both directions, counting lost uids for
resource files; then tags the pre-merge snapshot and checks the merged tree
out under the vault's write lock, refusing before any write if a path it
changes has an uncommitted edit; and pushes. The pointer is the vault
repository's `HEAD`. Credential ciphertext is committed, and therefore
merged, only when the remote carries credentials, and is settled by the
fresher encryption, never a text merge. A vault inside a file synchroniser is
reported as unsupported.

What survives from [The Vault Converges With One User-Owned Git Remote](vault-sync.md),
unchanged: at most one user-owned remote, a rendezvous and never a system of
record; git's three-way merge as the arbiter, with no "newest wins" beyond
ciphertext; the applied change is the difference against the last absorbed
state, never a wholesale copy; the layered conflict rules and the
abort-untouched rule; the pre-apply snapshot tags (ten kept) and rollback from
them; the deletion breaker in both directions with its fixed thresholds; one
lock over every rewriter of vault content, which the curation pass shares; the
single owner machine for unattended rewrites; machine identity and
descriptors; the push token through a per-invocation credential helper with
the user's git configuration pinned away; "a vault needs a human" surfaced
where the user is; the `vault_sync` experimental switch.

What is replaced: the separate working tree `~/.coffer/sync`; the serialize
and apply steps with their exporter, appliers, document projection and
backwards-compatibility layer; the `SyncedStatePort`, `ImportGate`,
`ImportNormaliser` and `PostImportHook` ports (by the shared validator and
reconciler hints); the pointer table and the retry set; the bundle-wide
manifest gate (by per-file versions); path-by-path, rename-blind application.

## Consequences

- **Supersedes** [The Vault Converges With One User-Owned Git Remote](vault-sync.md)
  when accepted; that ADR is then marked superseded rather than deleted,
  because its options (tombstones, mtime, CRDTs, export/import, file-level sync)
  are still the argument for the parts that survive.
- **Keeps** [A Sync Round That Would Lose Too Much Is Held](sync-deletion-breaker.md),
  with the uid count added for resource files.
- Spec vault-sync is rewritten: the round's steps, "Keep the working tree
  outside the vault" becomes "merge outside the vault's files", the pointer
  requirement names `HEAD`, and the apply requirements collapse into the
  checkout.
- **Obligations.** A git version check at boot and in `coffer sync status`;
  property tests over random pairs of vault histories that the breaker holds
  every loss and passes every move; a test that a person's uncommitted edit on
  a path the round would change is never overwritten; a test that a vault under
  `.stfolder` or `~/Library/Mobile Documents/` is reported; a cross-version
  sync test with a fixture from the previous build.
