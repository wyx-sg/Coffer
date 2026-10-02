# Sync Only Pulls and Pushes the Vault Repository; a Clean Merge Is Applied, Any Conflict Stops for the Person

**Status**: Accepted
**Date**: 2026-09-29
**Deciders**: Yuxing Wu
**Related**: [A Sync Round That Would Lose Too Much Is Held, in Both Directions, Counting Losses Not Moves](sync-deletion-breaker.md), [A Machine Is Identified by a Hash of Its Host's Own ID, and Owns One Descriptor in the Tree](sync-machine-identity.md), [Secrets Cross Machines Only as Ciphertext; the Master Key and the Push Token Never Enter the Repository](secrets-cross-machines-only-as-ciphertext.md), [An Unattended Rewriter of Synced Content Runs on One Named Owner Machine](single-owner-machine-for-unattended-rewrites.md), [Sync Withholds Derived Output; Each Machine Renders Its Own](sync-withholds-derived-output.md), [Knowledge Curation Merges New Material Into the Documents](knowledge-curation.md), [Storage Is Five Classes by Nature; Whether a Class Syncs Is Policy](storage-is-five-classes-by-nature.md), [A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](identity-is-the-uid-inside-the-file.md), [Every Vault File Carries Its Own Format Version; One Owner Machine Commits Layout Upgrades](every-vault-file-carries-its-format-version.md), [Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer](every-vault-write-is-a-validated-commit-naming-its-writer.md), [One Level-Triggered Reconciler Converges What Coffer Writes Outside Its Database, Comparing Parameters](one-level-triggered-reconciler-compares-parameters.md), [principles](../../docs-site/architecture/principles.md) (Local-First — the user-owned sync remote exception; "Not a hosted sync service"), research note [multi-machine sync](../research/multi-machine-sync.md), spec vault-sync "Run a round as pull, merge, guard, check out, push", spec vault-sync "Never overwrite a person's unsettled edit", spec vault-sync "Keep the pointer local", spec vault-sync "Snapshot before checking out and roll a round back from it", spec vault-sync "Guard both directions", spec vault-sync "Let the fresher secret ciphertext win", spec vault-sync "Stop the round on any conflict", spec vault-sync "Answer each conflicting file and continue the round", spec vault-sync "Show a conflict as a banner"

## Context

Coffer is local-first: each machine owns its vault, and no vendor cloud is a
system of record. A developer who works from a laptop and a desktop produces
vault state on both and needs the two to be one vault rather than two islands.
The principles allow exactly one exception to "state stays on your devices": a
git remote the user owns, as a rendezvous rather than a system of record.

The forces on the answer:

- **The vault is a git repository in which every accepted write is already a
  commit**
  ([Every Vault Write Is One Validated, Compare-and-Swap Commit](every-vault-write-is-a-validated-commit-naming-its-writer.md)),
  made of plain files (resources, knowledge, skills). There is no database to
  serialize and nothing to translate back, so convergence can be a git
  operation on the repository itself. `git merge-tree --write-tree` computes a
  merge in the object store without touching the working tree or the index, so
  the result can be judged before any vault file changes.
- **Nobody approves a round.** Whatever converges the vault runs on a timer and
  writes the user's data with no human reading the diff. A wrong deletion or a
  silently chosen side is the failure that matters; a held round is
  recoverable.
- **The incident that shaped the safety rules.** On 2026-07-10 two machines on
  different builds mutually deleted skills, memory and resources. An earlier
  sync cleared a tree and rewrote it from local state before the machine's
  first import, so "I never had this" and "I deleted this" looked identical;
  in the same incident a machine re-exported a months-old orphaned credential
  blob and won simply by syncing last (PR #293 carries the guards that came
  out of it).
- **What the research shows about conflicts.** Every tool in the survey that
  uses git as its transport stops on a conflict and hands it to the person:
  chezmoi surfaces an ordinary rebase conflict and prompts before overwriting a
  drifted target; yadm is git's behaviour, and its clone never overwrites a
  differing local file; obsidian-git shows "You have conflicts in N files" and
  refuses to push until they are gone. The two products that resolve
  automatically (VS Code Settings Sync, a per-key three-way merge against a
  last-synced base; Obsidian Sync, diff-match-patch for Markdown and
  last-modified-wins for the rest) do it through a **vendor server** that
  holds the base and the structure, which the principles rule out ("Not a
  hosted sync service"). The research note's own summary: unattended tools
  keep both copies, interactive tools stop and ask; none of the git-transport
  tools picks one side silently.

## Options Considered

### Option A — A convergence round in a second copy of the vault, with layered automatic arbitration

The design this replaced, from when the vault was a database plus two file
trees. Git can only merge files, so a round worked in a **second working
tree** outside the vault: serialize the vault into it (differentially, never
clearing and rewriting a directory), commit the result as `L`, fetch and merge
the remote into it (`M`), take the diff `L..M` as exactly what the remote
contributed, guard it, snapshot `L`, apply `L..M` to the vault path by path
(deletions included), and push. A machine-local pointer row recorded the commit
this vault had provably absorbed, and a retry set held paths that failed to
apply so the serializer never published them as deletions. What git could not
settle went to an arbiter in layers: credential ciphertext ordered by its
cleartext Fernet encryption time; in notes and skills a delete-versus-edit
conflict kept the edit; where an internal model was configured, a bounded agent
pass rewrote the remaining conflicted files in the working tree, gated by a
syntactic check (file exists, no conflict marker, a document still parses);
otherwise the round aborted with the vault untouched.

- **Pros.** The git remote as arbiter was a sound base: git already does diff,
  history, three-way merge and transport, and every developer holds
  credentials for a forge; committing local state before the merge gives git
  the three inputs a three-way merge needs; a conflict rarely stopped
  convergence, so two machines kept agreeing without the person looking.
- **Cons.** The serialize and apply steps, the document projection, the
  per-kind import ports and the retry set were most of the sync package: a
  translation layer whose only job was to turn files into a projection and
  back, and whose per-path, in-place apply could overwrite a person's edit made
  mid-round. The agent pass and the "keep the edit" layer write the person's
  own notes and skills with no one reviewing the result; the gate checks
  syntax, not meaning, so a clean, parseable, wrong merge passes, and "keep
  the edit" silently undoes a deletion the other machine's person made on
  purpose. An automatic resolution is, by definition, the case nobody was
  shown. It is also the one design in the survey with no precedent over a git
  transport.
- **Why it lost.** Its reason to exist, a database git could not merge, is
  gone, and it spent the most code on the rarest case, resolving it in the one
  way a person cannot audit afterwards.

### Option B — Thin sync: pull and push the vault repository; apply a clean merge, stop on any conflict (chosen)

Coffer only fetches and pushes the vault repository, on the configured
schedule or when the person asks ("Sync now"). A round:

```
0 Check     — not inside a synchronised folder; the vault is a repository, git >= 2.40
1 Local     — settle a person's valid edits; L := HEAD (every accepted write is committed)
2 Fetch     — R := origin/<branch>
3 Merge     — git merge-tree --write-tree L R -> tree T, or conflicts;
              nothing in the vault touched
4 Stop?     — any conflict: stop here. Nothing is checked out, nothing is pushed
5 Guard     — validate T; the deletion breaker in both directions
6 Check out — safety snapshot of L; M := commit(T; parents L and R);
              read T into the vault, refusing first if any path it changes
              differs from L on disk; HEAD := M
7 Publish   — this machine's descriptor; refuse a plaintext secret; push M
```

- **A conflict stops the round, whole.** No file is checked out and nothing
  is pushed, so neither the vault nor the remote holds a half-merged state.
  The person is shown each conflicting file with two choices, **keep this
  Mac's** or **take the other's**, and **open in editor** for a hand merge,
  which opens a scratch copy under `derived/sync-conflicts/` holding git's
  marked-up merge of that file; the vault's own file never receives a
  conflict marker. The answers are `coffer sync conflicts`, `resolve <path>
  --mine|--theirs|--edited`, `edit <path>` and `continue`. When every file has
  an answer, the resolved tree goes through the same steps 5–7: validation, the
  breaker, the snapshot, the checkout, the push. A stop is a question about one
  pair of commits: it records the remote tip it was raised against, and if
  either side moves before the person answers, the round is re-derived and
  asked again. Local writes keep being committed while a round is stopped; only
  convergence waits. A resource with the same name and a different uid on the
  two sides (two machines created it independently) stops the round the same
  way ([A Resource's Identity Is the `uid` Inside Its File](identity-is-the-uid-inside-the-file.md)).
- **Joining is explicit.** A new machine takes the union, previewed first: files
  only the remote has come down, files only this machine has go up, and a file
  both hold with different content stays exactly as it is on disk here and is
  not pushed until the person chooses (`coffer sync choose <path>
  --mine|--theirs`). Nothing is deleted on either side. A returning machine,
  one whose descriptor is already in the remote, resumes from the descriptor's
  last converged commit as an ordinary merge
  ([A Machine Is Identified by a Hash of Its Host's Own ID](sync-machine-identity.md)).
- **The ciphertext subtree keeps its rule.** With the remote's
  `include_secret` off, `secret/` is never committed, so it is neither pushed
  nor merged. With it on, two ciphertexts for one ref are still ordered by
  their cleartext Fernet encryption time
  ([Secrets Cross Machines Only as Ciphertext; the Master Key and the Push Token Never Enter the Repository](secrets-cross-machines-only-as-ciphertext.md)).
  That rule stays because it is not a judgement about content: it is decidable
  without the key, and the two-choice prompt would show a person two opaque
  blobs they cannot compare. Ciphertext that has entered a pushed commit cannot
  be withdrawn; revocation is rotation. Before every push the round also reads
  every blob the remote lacks and refuses to publish a plaintext secret.
- **The deletion breaker** holds a round in both directions, with its
  thresholds (20% of an area or 20 files): incoming is `L → T`, outgoing is
  what `L` deletes relative to the merge base. For resource files it counts
  lost uids, so a moved or renamed file is a move by construction; for other
  files it keeps content-id and rename pairing
  ([A Sync Round That Would Lose Too Much Is Held](sync-deletion-breaker.md)).
  A layout commit is checked by its stricter no-loss rule
  ([Every Vault File Carries Its Own Format Version](every-vault-file-carries-its-format-version.md)),
  and the remote's layout must match this build's exactly: an older one is
  rebuilt from an upgraded machine, not converted.
- **A safety snapshot before every checkout, and rollback from it.** `L` is
  tagged before every checkout (ten kept). Rolling back checks a snapshot out
  through the ordinary write path as a new commit, never by moving `HEAD`
  backwards (`coffer sync rollback <round>`).
- **The checkout is a compare-and-swap on the whole tree.** Under the vault's
  write lock, git's two-tree read (`read-tree -m -u L M`) verifies every path
  it will change against `L` before writing any file, and refuses if a person
  has an uncommitted or invalid edit there; the round then waits and names the
  path. Each changed resource produces one `Changed` hint for the reconciler,
  which re-renders the per-machine side effects
  ([One Level-Triggered Reconciler Converges What Coffer Writes Outside Its Database](one-level-triggered-reconciler-compares-parameters.md)).
- **The pointer is the vault repository's `HEAD`**: by construction the last
  tree this vault checked out after validation and guarding, and never an
  input another machine reads. There is no pointer table and no retry set.
- **Synced machines.** The Sync page lists every machine that has converged with
  the remote, with its label, last round and key fingerprint; a person can
  rename a machine's label and retire a machine, which removes its descriptor in
  an ordinary commit.
- **A vault inside a file synchroniser is warned about.** If the vault path is
  inside a Syncthing or Dropbox folder, iCloud Drive
  (`~/Library/Mobile Documents/`) or a File Provider root
  (`~/Library/CloudStorage/`), the Sync page and `coffer sync status` say it is
  unsupported: those tools resolve by last writer or conflict copy and would
  replicate the repository's internals underneath git.
- **Remote failures are named**: `remote unreachable`, `sign-in refused` and
  `push failed` (applied here, refused by the remote) are distinct round
  results, and none of them loses anything. The push token is sent with a
  username, `coffer` by default and settable per remote, because Bitbucket and
  Azure DevOps need a particular one where GitHub and GitLab ignore it.

Pros: no translation layer, no second working tree, no pointer table, no retry
set and no automatic content resolver; a merge git can do cleanly is still
applied unattended, which is the common case (two machines editing different
files, or different parts of one file); nothing Coffer did on its own ever
needs to be found and undone; the behaviour matches every git-transport tool a
user may already know.

Cons: a real conflict stops convergence on this machine until the person
answers; two-choice resolution is per file, so a file both machines edited in
different places that git could not merge loses one side's edit unless the
person hand-merges; a person who never opens the Sync page leaves the vault
stopped, which is why a stop is surfaced where they already are (the
navigation mark, `coffer sync status`, the desktop notification).

It wins because it keeps every guarantee that protects data (base-relative
merge, the breaker, the snapshot, the compare-and-swap checkout) and drops
exactly the part that changes data without anyone deciding.

### Option C — Per-resource timestamps and tombstones in Coffer's own code

Coffer arbitrates: tombstones with a TTL record deletions, a per-resource
timestamp decides competing edits, failed imports are quarantined and retried,
and a file watcher plus a remote probe pushes and pulls within seconds. This
was Coffer's first sync.

- **Pros.** Near-real-time; conflicts never stop a round.
- **Cons.** Timestamp arbitration is "newest commit wins", a fact about when a
  machine ran, not about what the user meant: it is how the months-old
  credential blob won on 2026-07-10. When the content is a projection of a
  database, the diff git computes is not the diff the vault made, and every
  guarantee has to be re-established outside git. Tombstones, arbitration and
  quarantine are four things git already provides in its commit graph.
- **Why it loses.** It re-implements outside git what git does, and orders by
  the wrong thing.

### Option D — Last writer wins by file modification time

Treat each path as a register; the copy with the later mtime wins.

- **Pros.** Trivial; no merge.
- **Cons.** mtimes are wall-clock values from different machines, reset by
  checkouts and restores, and a stale machine that merely touches a file wins.
  Two edits to different sections of one note, the common case, lose one of
  them outright where git would have merged both. A deletion has no mtime at
  all, so it needs tombstones, which is Option C again.
- **Why it loses.** It loses data in the commonest concurrent case and orders by
  an unreliable clock.

### Option E — A CRDT or state-based replication

Model documents as CRDTs (Automerge, Yjs) or replicate operation logs, so
concurrent edits merge without conflicts by construction.

- **Pros.** No conflict ever stops a round; merges are principled.
- **Cons.** A CRDT merges *operations*, and nothing that writes the vault
  produces them: people edit notes in their own editors and agents write with
  their own file tools, so every write would have to be diffed back into
  operations after the fact. The storage stops being plain files a person can
  read or a forge can show. A conflict-free merge of two contradictory edits to a
  note or a resource config is still a wrong document, only a silent one. And
  it needs a relay or a store of its own.
- **Why it loses.** It fights the "plain files, any editor" property and hides
  exactly the disagreements a user should see.

### Option F — Backup only: push, never pull

Commit and push the vault on a schedule; never fetch or apply anything.

- **Pros.** Nothing inbound, so nothing can damage the vault; the remote is a
  complete off-machine history; the least code.
- **Cons.** Two machines drift apart and Coffer neither notices nor helps;
  pointing two machines at one remote makes pushes fail or, forced, overwrite
  each other. Closing the gap by hand needs an import, which is Option G's
  hazard.
- **Why it loses.** It answers "my disk died", not "my laptop and my desktop
  should agree". Every Coffer machine keeps local history anyway.

### Option G — Export and import through a directory

`export <dir>` writes a bundle; `import` reads one back and overwrites.

- **Pros.** Explicit, simple, no background writer.
- **Cons.** An import is a wholesale overwrite with **no base**, so a stale
  bundle silently overwrites a fresh vault and deletions cannot be told from
  absences, the shape of the 2026-07-10 incident. It also relies on someone
  remembering to do it, and keeping it keeps a supported path by which a stale
  machine overwrites a fresh vault.
- **Why it loses.** Its uses are covered with a base: a new machine joins, an
  offline medium is a `file://` remote, a copy for someone else is `git clone`.

### Option H — A hosted Coffer sync service

A Coffer-run endpoint stores and merges every user's vault.

- **Pros.** The best onboarding; no forge or credential for the user to set up.
- **Cons.** A vendor-controlled system of record, which the principles forbid
  outright ("Not a hosted sync service"), and a service to run.
- **Why it loses.** On principle.

### Option I — File-level sync of the Coffer directory (Syncthing, a cloud drive)

Point a file synchroniser at the whole directory.

- **Pros.** Zero Coffer code.
- **Cons.** It carries machine-local state (`runs.db`, `daemon-config.json`,
  logs) that cannot be merged, and it replicates the repository's internals
  under git. These tools resolve by last writer wins and keep no history to
  restore from.
- **Why it loses.** It syncs the wrong things and cannot merge the right ones;
  Coffer detects and refuses it instead.

### Option J — No sync

Leave multi-machine use to the person's own tools.

- **Pros.** No code and no risk.
- **Cons.** A person who runs `git pull` in the vault themselves gets none of
  the protections (no breaker, no validation before checkout, no snapshot).
  Leaving the remote unconfigured already gives users who want no sync exactly
  that.
- **Why it loses.** The unprotected route would be the only route.

### How the clean merge is computed

Three mechanics were weighed for Option B's step 3 and lost:

- **Keep the separate working tree with its serialize and apply steps.** Its
  reason to exist is gone, and its per-path, in-place apply is what overwrites
  a person's edit made mid-round.
- **Merge in the vault's own working tree (`git pull` / `git merge`).** A
  conflicted merge writes markers into live files that agents read, and the
  breaker could only look after the files had changed, the reverse of the
  order it depends on. obsidian-git's users live with exactly this.
- **Rebase local commits onto the remote.** It rewrites the commit ids that
  audit rows and a skill's History tab cite, and turns one conflict into one
  per replayed commit.

## Decision

Coffer's sync only fetches and pushes the vault repository, at most one
user-owned remote, on a schedule or on demand. The remote is a rendezvous and
never a system of record: every machine's vault stays complete, so the remote
can be deleted and rebuilt from any single machine. A merge git completes
cleanly is computed with `git merge-tree --write-tree` outside the working
tree, validated, passed through the deletion breaker in both directions,
snapshotted, checked out under the vault's write lock with a whole-tree
compare-and-swap, and pushed. **Any conflict stops the round**: nothing is
checked out and nothing is pushed, and the person resolves each file (keep this
machine's, take the other's, or open it in an editor), after which the resolved
tree takes the same path. Coffer resolves no content conflict itself. Secret
ciphertext is committed only when the remote carries secrets and is ordered by
its encryption time. The pointer is `HEAD`. A vault inside a file synchroniser
is reported as unsupported.

Rules a future change must respect:

- The change applied is always relative to the last absorbed state, never a
  wholesale copy of one side over the vault.
- Git's three-way merge is the only merge. A new "newest wins" or model-driven
  resolver for anything other than secret ciphertext is a regression to
  Option A or C.
- One lock covers every rewriter of vault content, which knowledge curation
  shares ([Knowledge Curation Merges New Material Into the Documents](knowledge-curation.md)).
- Unattended rewrites run on a single owner machine, because a clean merge
  would still duplicate two machines' curation silently
  ([An Unattended Rewriter of Synced Content Runs on One Named Owner Machine](single-owner-machine-for-unattended-rewrites.md)).
- Reach never travels, and derived output never travels
  ([Sync Withholds Derived Output; Each Machine Renders Its Own](sync-withholds-derived-output.md)).
- The push token reaches git through a per-invocation credential helper with
  the user's git configuration pinned away, and a vault that needs a human
  says so where the user already is.

## Consequences

- The only egress is `git fetch` / `git push` to the user's own remote.
- [A Sync Round That Would Lose Too Much Is Held](sync-deletion-breaker.md)
  counts uids for resource files.
- [An Unattended Rewriter of Synced Content Runs on One Named Owner Machine](single-owner-machine-for-unattended-rewrites.md)
  has no "an edit beats a curation deletion" fallback: a curation deletion that
  meets an edit elsewhere is a conflict the person resolves.
- A git version check (2.40: the merge passes `--merge-base` to `git
  merge-tree --write-tree`) runs at boot and in `coffer sync status`.
- A vault that needs a human (stopped, held, failing to push, or waiting to
  join) says so in `coffer sync status` (non-zero exit), the navigation mark and
  the desktop notification. A stopped vault converges no further, so a stop
  nobody sees is an outage.
- The behaviour is covered by tests that a clean merge applies, any conflict
  stops with the vault and remote untouched, the breaker holds every loss and
  passes every move, a person's uncommitted edit on a path the round would
  change is never overwritten, and a vault inside a file synchroniser is
  reported.
