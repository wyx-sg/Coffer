# Sync Only Pulls and Pushes the Vault Repository; a Clean Merge Is Applied, Any Conflict Stops for the Person

**Status**: Proposed
**Date**: 2026-09-29
**Deciders**: Yuxing Wu
**Related**: [The Vault Converges With One User-Owned Git Remote, Git's Merge as Arbiter](vault-sync.md) (superseded by this ADR once accepted), [A Sync Round That Would Lose Too Much Is Held, in Both Directions, Counting Losses Not Moves](sync-deletion-breaker.md), [A Machine Is Identified by a Hash of Its Host's Own ID, and Owns One Descriptor in the Tree](sync-machine-identity.md), [Credentials Cross Machines Only as Ciphertext; the Master Key and the Push Token Never Enter the Repository](credentials-across-machines.md), [An Unattended Rewriter of Synced Content Runs on One Named Owner Machine](single-owner-machine-for-unattended-rewrites.md), [Sync Withholds Derived Output; Each Machine Renders Its Own](sync-withholds-derived-output.md), [Knowledge Curation Merges New Material Into the Documents](knowledge-curation.md), [Storage Is Five Classes by Nature; Whether a Class Syncs Is Policy](storage-is-five-classes-by-nature.md), [A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](identity-is-the-uid-inside-the-file.md), [Every Vault File Carries Its Own Format Version; One Owner Machine Commits Layout Upgrades](every-vault-file-carries-its-format-version.md), [Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer](every-vault-write-is-a-validated-commit-naming-its-writer.md), [One Level-Triggered Reconciler Converges What Coffer Writes Outside Its Database, Comparing Parameters](one-level-triggered-reconciler-compares-parameters.md), [principles](../../docs-site/architecture/principles.md) (Local-First — the user-owned sync remote exception; "Not a hosted sync service"), research note [multi-machine sync](../research/multi-machine-sync.md), spec vault-sync "Run the seven round steps in order", spec vault-sync "Keep the working tree outside the vault", spec vault-sync "Keep the pointer local", spec vault-sync "Snapshot before applying and roll back from it", spec vault-sync "Guard both directions", spec vault-sync "Let the fresher credential ciphertext win", spec vault-sync "Let an edit beat a curation deletion", spec vault-sync "Resolve remaining conflicts with an agent only in the working tree", spec vault-sync "Validate an agent's resolution", spec vault-sync "Abort the round on an unresolved conflict", spec vault-sync "Show a conflict as a banner"

## Context

[The Vault Converges With One User-Owned Git Remote](vault-sync.md) runs a
seven-step round in a **second copy** of the vault — a git working tree at
`~/.coffer/sync` (`DEFAULT_WORKTREE`, `domain/sync/backup.py:34`) — because
the vault was a database plus two file trees and git can only merge files:

```
0 Repair  1 Serialize (vault → tree, commit L)  2 Merge (git merge in the tree → M)
3 Diff L..M  4 Guard  5 Apply (tree → vault, path by path)  6 Publish (push; pointer := M)
```

Steps 1 and 5 are translations: the exporter, the three appliers, the
document projection and the backwards-compatibility layer are 1,094 of the
sync package's 6,720 lines, with 512 more in per-kind `sync_state` /
`sync_reconcile` adapters. The merge runs in that tree with
`git merge --allow-unrelated-histories` (`infrastructure/sync/git_mirror.py:142-157`).
The apply copies each path back into the live vault with an unconditional,
in-place `write_bytes` (`application/sync/appliers.py:91-101`). The pointer is
a row in machine-local SQLite (`infrastructure/persistence/convergence_state_repo.py`).

What git cannot merge goes to `ConflictArbiter` (`application/sync/conflicts.py`)
in four layers: (1) two credential ciphertexts are ordered by their cleartext
Fernet encryption time; (2) in `knowledge/` and `skills/`, a delete-versus-edit
conflict keeps the edit; (3) where an internal model is configured, a bounded
agent pass (`infrastructure/sync/conflict_resolver.py`) rewrites the remaining
conflicted files in the working tree, gated only by a syntactic check — file
exists, no conflict marker, a document still parses; (4) otherwise the round
aborts. Layers 2 and 3 decide the content of a person's notes and skills with
nobody watching, and layer 3 does it with a model whose choice no validator
can judge for meaning.

Two changes remove the reasons for most of this machinery:

- **The vault becomes a git repository in which every accepted write is
  already a commit**
  ([Every Vault Write Is One Validated, Compare-and-Swap Commit](every-vault-write-is-a-validated-commit-naming-its-writer.md)),
  so there is nothing to serialize and nothing to translate back. `git
  merge-tree --write-tree` (git 2.38 and later; the development machine runs
  `git version 2.50.1 (Apple Git-155)`) computes a merge in the object store
  without touching the working tree or the index, so the result can be judged
  before any vault file changes.
- **What the research shows about conflicts.** Every tool in the survey that
  uses git as its transport stops on a conflict and hands it to the person:
  chezmoi surfaces an ordinary rebase conflict and prompts before overwriting a
  drifted target; yadm is git's behaviour, and its clone never overwrites a
  differing local file; obsidian-git shows "You have conflicts in N files" and
  refuses to push until they are gone. The two products that resolve
  automatically — VS Code Settings Sync (a per-key three-way merge against a
  last-synced base) and Obsidian Sync (diff-match-patch for Markdown,
  last-modified-wins for the rest) — do it through a **vendor server** that
  holds the base and the structure, which the principles rule out ("Not a
  hosted sync service"). The research note's own summary: unattended tools
  keep both copies, interactive tools stop and ask; none of the git-transport
  tools picks one side silently.

## Options Considered

### Option A — Full automatic convergence (the current layered design, moved onto the vault repository)

Keep every arbiter layer and move it onto `merge-tree`: settle delete-versus-edit
by keeping the edit, run the bounded agent pass in a scratch worktree, abort
only what is left.

- **Pros.** A conflict rarely stops convergence; two machines keep agreeing
  without the person looking.
- **Cons.** It is the one design in the survey with no precedent over a git
  transport. The agent pass writes the person's own notes and skills with no
  one reviewing the result, and its gate checks syntax, not meaning — a clean,
  parseable, wrong merge passes. Delete-versus-edit "keep the edit" silently
  undoes a deletion the other machine's person made on purpose. And every layer
  is code whose failure is invisible by design: an automatic resolution is, by
  definition, the case nobody was shown.
- **Why it loses.** It spends the most code on the rarest case and resolves it
  in the one way a person cannot audit afterwards.

### Option B — Thin sync: pull and push the vault repository; apply a clean merge, stop on any conflict (chosen)

Coffer only fetches and pushes the vault repository, on the configured
schedule or when the person asks ("Sync now"). A round:

```
0 Check     — the vault is a repository, git ≥ 2.38, no stopped round waiting
1 Local     — L := HEAD (every accepted write is already committed)
2 Fetch     — origin/<branch>
3 Merge     — git merge-tree --write-tree L origin/<branch> → tree T, or conflicts;
              nothing in the vault touched
4 Stop?     — any conflict: stop here. Nothing is checked out, nothing is pushed
5 Guard     — validate T; the deletion breaker in both directions
6 Check out — safety snapshot of L; M := commit(T, parents L and origin);
              read T into the vault, refusing first if any path it changes
              differs from L on disk; HEAD := M
7 Publish   — push M
```

- **A conflict stops the round, whole.** No file is checked out and nothing
  is pushed, so neither the vault nor the remote holds a half-merged state.
  The person is shown each conflicting file with two choices — **keep this
  Mac's** or **take the other's** — and **open in editor** for a hand merge,
  which opens a scratch copy under `derived/sync-conflicts/` holding git's
  marked-up merge of that file; the vault's own file never receives a
  conflict marker. When every file has an answer, the resolved tree goes
  through the same steps 5–7: validation, the breaker, the snapshot, the
  checkout, the push. A stop is a question about one pair of commits: it
  records the remote tip it was raised against, and if either side moves
  before the person answers, the round is re-derived and asked again. Local
  writes keep being committed while a round is stopped; only convergence waits.
- **The ciphertext subtree keeps its rules.** With the remote's
  `include_credentials` off, `vault/credentials/` is never committed, so it is
  neither pushed nor merged. With it on, two ciphertexts for one ref are still
  ordered by their cleartext Fernet encryption time
  ([Credentials Cross Machines Only as Ciphertext](credentials-across-machines.md)).
  That rule stays because it is not a judgement about content: it is decidable
  without the key, and the two-choice prompt would show a person two opaque
  blobs they cannot compare. Ciphertext that has entered a pushed commit cannot
  be withdrawn; revocation is rotation.
- **The deletion breaker stays**, with its thresholds (20% of an area or 20
  documents) and both directions ([A Sync Round That Would Lose Too Much Is Held](sync-deletion-breaker.md)):
  incoming is `L → T`, outgoing is what `L` deletes relative to the merge base.
  For resource files it counts lost uids, so a moved or renamed file is a move
  by construction ([A Resource's Identity Is the `uid` Inside Its File](identity-is-the-uid-inside-the-file.md));
  for tree files it keeps content-id and rename pairing. A layout commit is
  checked by its stricter no-loss rule
  ([Every Vault File Carries Its Own Format Version](every-vault-file-carries-its-format-version.md)).
- **A safety snapshot before every apply, and rollback from it.** `L` is tagged
  before every checkout (ten kept). Rolling back checks a snapshot out through
  the ordinary write path as a new commit, never by moving `HEAD` backwards.
- **The checkout is a compare-and-swap on the whole tree.** Under the vault's
  write lock, git's two-tree read (`read-tree -m -u L M`) verifies every path
  it will change against `L` before writing any file, and refuses if a person
  has an uncommitted or invalid edit there; the round then waits and names the
  path. Each changed resource produces one `Changed` hint for the reconciler,
  which re-renders the per-machine side effects the post-import hooks did.
- **The pointer is the vault repository's `HEAD`**: by construction the last
  tree this vault checked out after validation and guarding, and never pushed
  as data. The pointer table goes away.
- **Synced machines.** The machine descriptors stay: the Sync page lists every
  machine that has converged with the remote, with its label, last round and
  key fingerprint; a person can rename a machine's label and retire a machine,
  which removes its descriptor in an ordinary commit
  ([A Machine Is Identified by a Hash of Its Host's Own ID](sync-machine-identity.md)).
- **A vault inside a file synchroniser is warned about.** If the vault path is
  inside a Syncthing folder (an ancestor holds `.stfolder`), iCloud Drive
  (`~/Library/Mobile Documents/`) or a File Provider root
  (`~/Library/CloudStorage/`), the Sync page and `coffer sync status` say it is
  unsupported: those tools resolve by last writer or conflict copy and would
  replicate the repository's internals underneath git.

Pros: the translation layer, the second working tree, the pointer table, the
retry set and every automatic content resolver are deleted; a merge git can do
cleanly is still applied unattended, which is the common case (two machines
editing different files, or different parts of one file); nothing Coffer did
on its own ever needs to be found and undone; the behaviour matches every
git-transport tool a user may already know.

Cons: a real conflict stops convergence on this machine until the person
answers; two-choice resolution is per file, so a file both machines edited in
different places that git could not merge loses one side's edit unless the
person hand-merges; a person who never opens the Sync page leaves the vault
stopped, which is why a stop is surfaced where they already are (the
navigation mark, `coffer sync status`, the desktop notification).

It wins because it keeps every guarantee that protects data — base-relative
merge, the breaker, the snapshot, the compare-and-swap checkout — and drops
exactly the part that changes data without anyone deciding.

### Option C — Backup only: push, never pull

Commit and push the vault on a schedule; never fetch or apply anything, as the
one-way backup of PR #362 did.

- **Pros.** Nothing inbound, so nothing can damage the vault; the remote is a
  complete off-machine history; the least code.
- **Cons.** Two machines drift apart and Coffer neither notices nor helps; the
  "one vault on my machines" the principles' sync exception exists for is not
  delivered. Pointing two machines at one remote makes pushes fail or, forced,
  overwrite each other.
- **Why it loses.** It answers "my disk died", not "my laptop and my desktop
  should agree". Every Coffer machine keeps local history anyway
  ([Every Vault Write Is One Validated, Compare-and-Swap Commit](every-vault-write-is-a-validated-commit-naming-its-writer.md)).

### Option D — No sync

Leave multi-machine use to the person's own tools.

- **Pros.** No code and no risk.
- **Cons.** A person who runs `git pull` in the vault themselves gets none of
  the protections — no breaker, no validation before checkout, no snapshot —
  and file synchronisers are unsafe over a git repository (above). Leaving
  the remote unconfigured already gives users who want no sync exactly that.
- **Why it loses.** The unprotected route would be the only route.

### How the clean merge is computed

Three mechanics were weighed for Option B's step 3 and lost:

- **Keep the separate working tree with its serialize and apply steps.** Its
  reason to exist — a database git could not merge — is gone, and its per-path,
  in-place apply is what overwrites a person's edit made mid-round.
- **Merge in the vault's own working tree (`git pull` / `git merge`).** A
  conflicted merge writes markers into live files that agents read, and the
  breaker could only look after the files had changed — the reverse of the
  order it depends on. obsidian-git's users live with exactly this.
- **Rebase local commits onto the remote.** It rewrites the commit ids that
  audit rows and a skill's History tab cite, and turns one conflict into one
  per replayed commit.

## Decision

Coffer's sync only fetches and pushes the vault repository, on a schedule or
on demand. A merge git completes cleanly is computed with `git merge-tree
--write-tree` outside the working tree, validated, passed through the deletion
breaker in both directions, snapshotted, checked out under the vault's write
lock with a whole-tree compare-and-swap, and pushed. **Any conflict stops the
round**: nothing is checked out and nothing is pushed, and the person resolves
each file — keep this machine's, take the other's, or open it in an editor —
after which the resolved tree takes the same path. Coffer resolves no content
conflict itself. Credential ciphertext is committed only when the remote
carries credentials and is ordered by its encryption time. The pointer is
`HEAD`. A vault inside a file synchroniser is reported as unsupported.

What survives from [The Vault Converges With One User-Owned Git Remote](vault-sync.md):
at most one user-owned remote, a rendezvous and never a system of record; git's
three-way merge as the only merge; the change applied is always relative to
the last absorbed state, never a wholesale copy; the fresher-ciphertext rule;
abort with the vault untouched when a merge is not clean; pre-apply snapshot
tags (ten) and rollback from them; the deletion breaker; one lock over every
rewriter of vault content, which curation shares; the single owner machine for
unattended rewrites (a clean merge would still duplicate two machines'
curation silently); machine identity and descriptors; the push token through a
per-invocation credential helper with the user's git configuration pinned
away; "a vault needs a human" surfaced where the user is.

What is removed: the delete-versus-edit layer ("keep the edit") and the agent
resolution pass with its validation gate (`application/sync/conflicts.py`
layers 2 and 3, `infrastructure/sync/conflict_resolver.py`); the separate
working tree `~/.coffer/sync`; the serialize and apply steps with their
exporter, appliers, document projection and backwards-compatibility layer; the
`SyncedStatePort`, `ImportGate`, `ImportNormaliser` and `PostImportHook` ports
(replaced by the shared validator and reconciler hints); the pointer table and
the retry set; the bundle-wide manifest gate (replaced by per-file versions);
path-by-path, rename-blind application.

## Consequences

- **Supersedes** [The Vault Converges With One User-Owned Git Remote](vault-sync.md)
  when accepted; that ADR is then marked superseded rather than deleted,
  because its options (tombstones, mtime, CRDTs, export/import, file-level sync)
  remain the argument for the parts that survive.
- **Keeps** [A Sync Round That Would Lose Too Much Is Held](sync-deletion-breaker.md),
  with the uid count added for resource files.
- [An Unattended Rewriter of Synced Content Runs on One Named Owner Machine](single-owner-machine-for-unattended-rewrites.md)
  loses its "an edit beats a curation deletion" fallback: a curation deletion
  that meets an edit elsewhere is now a conflict the person resolves.
- Spec vault-sync is rewritten: the round's steps; "Let an edit beat a curation
  deletion", "Resolve remaining conflicts with an agent only in the working
  tree" and "Validate an agent's resolution" are removed; "Abort the round on an
  unresolved conflict" and "Show a conflict as a banner" become the per-file
  resolution requirement; "Keep the working tree outside the vault" becomes
  "merge outside the vault's files"; the pointer requirement names `HEAD`.
- **Obligations.** A git version check at boot and in `coffer sync status`;
  the conflict view (per-file keep / take / open in editor) on the Sync page
  and in the CLI; property tests over random pairs of vault histories that a
  clean merge applies, any conflict stops with the vault and remote untouched,
  and the breaker holds every loss and passes every move; a test that a
  person's uncommitted edit on a path the round would change is never
  overwritten; a test that a vault under `.stfolder` or `~/Library/Mobile
  Documents/` is reported; a cross-version sync test with a fixture from the
  previous build.
