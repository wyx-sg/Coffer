# Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer

**Status**: Accepted
**Date**: 2026-09-29
**Deciders**: Yuxing Wu
**Related**: [One Level-Triggered Reconciler Converges What Coffer Writes Outside Its Database, Comparing Parameters](one-level-triggered-reconciler-compares-parameters.md), [Storage Is Five Classes by Nature; Whether a Class Syncs Is Policy](storage-is-five-classes-by-nature.md), [A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](identity-is-the-uid-inside-the-file.md), [Every Vault File Carries Its Own Format Version; One Owner Machine Commits Layout Upgrades](every-vault-file-carries-its-format-version.md), [Sync Only Pulls and Pushes the Vault Repository; a Clean Merge Is Applied, Any Conflict Stops for the Person](sync-applies-clean-merges-and-stops-on-any-conflict.md), [Standalone Secrets Are Named `coffer://secret/` References, Injected Only Into One Child Process](standalone-secrets-are-named-references-injected-into-one-child.md), [Audit Every Change With Its Actor, Log Invocations Without Payloads, Prune Per Table](audit-and-retention.md), [Secrets Cross Machines Only as Ciphertext; the Master Key and the Push Token Never Enter the Repository](secrets-cross-machines-only-as-ciphertext.md), spec knowledge "Treat a direct file edit as a complete change", spec knowledge "Save a document edited in the web UI", spec skill-manager "Save an existing skill file conditionally", spec vault-storage "Admit every vault write through one compare-and-swap path", spec vault-storage "Show, compare and restore any version of a vault file", spec vault-sync "Snapshot before checking out and roll a round back from it"

## Context

Once the vault is files ([Storage Is Five Classes by Nature](storage-is-five-classes-by-nature.md)),
three kinds of writer change it, and none of them waits for the others:

- **a person** — an editor, an agent's own file tools, a shell, even `git`
  run by hand in the vault (spec knowledge "Treat a direct file edit as a complete
  change" already makes this legal for knowledge);
- **the daemon** — a save from the web UI, a CLI or API change, a knowledge
  sweep, a uid minted for a hand-made file, a layout commit;
- **sync** — a round bringing another machine's changes in.

Before the vault was one repository, the code protected one writer from another
unevenly, and in two places by modification time. A web UI save of a knowledge
document compared a fingerprint of the bytes the editor loaded, but the check
and the replace were not under one lock. A skill file save took the same
fingerprint as an optional argument, with an unconditional last-writer-wins
write when it was omitted. A sync apply wrote nothing conditionally: it
truncated and rewrote the file in place, so a person's edit made between the
round's serialize and its apply was overwritten and a reader could see a
half-written file. And the knowledge sweep decided what a person had edited by comparing a
file's mtime with a stamp, with a realignment of mtime after Coffer's own write
so it was not mistaken for a person's; a file written by a sync apply got a
fresh mtime and so read as a person's edit.

Nothing watched the vault trees, so changes were found by sweeps. And nothing
kept history: an edit left an audit row naming who and when, but the previous
content was gone. The only way back was the sync working tree's own history, a
whole-vault restore to a revision or one of a few pre-apply snapshot tags, and
only while sync was on, at the granularity of an hourly round.

The reconciler ADR set the audit rule for files outside the vault: write, then
record the audit event in the same call, and restore the prior content if
recording fails ([One Level-Triggered Reconciler](one-level-triggered-reconciler-compares-parameters.md)).
Vault writes need the same rule and one more: which writer made each change,
visible afterwards.

## Options Considered

The decision has two halves that only work together — where history lives,
and how a write is admitted — and each is argued on its own.

### Where history lives

#### Option A1 — The vault is always a git repository; every accepted write is a commit (chosen)

`~/.coffer/vault/` is a local git repository from the moment it exists,
whether or not a sync remote is configured; configuring sync only adds a
remote. Every write that passes validation lands as a commit whose author
names the writer (`Coffer (disk)`, `Coffer (daemon)`, `Coffer (sync)`) and
whose trailers carry `Coffer-Writer`, `Coffer-Operation`, `Coffer-Actor` (the
audit actor) and `Coffer-Machine` (the machine id). The writer vocabulary is six
words (`domain/vault/writers.py`): `user` (a person through a Coffer surface),
`disk` (a change found in the working tree that no Coffer operation made — an
editor, a shell, an agent's own file tools, a person's own `git commit`),
`agent`, `daemon`, `curation` and `sync`; `curation` only labels commits made
by the model pass Coffer used to run, which history still shows. `disk` stands for a person's hand edit
because the scanner cannot tell a person's editor from an agent's file tool; a
commit without trailers reads as `disk`.

- **Pros.** Per-file history, diff and restore exist for every user, not only
  for those who sync; git is already how the vault converges, so the history a
  person reads locally is the history the remote holds; the sync round no
  longer serializes local state before merging, because local state is
  already committed; the pointer can be the repository's own `HEAD`
  ([Sync Only Pulls and Pushes the Vault Repository](sync-applies-clean-merges-and-stops-on-any-conflict.md)).
  The first consumer is a skill's History tab — versions with their writer, a
  diff, and restore — at no storage cost beyond git's.
- **Cons.** Coffer requires git (2.40 or newer, because every sync round uses
  `merge-tree --write-tree`) for every user, not only for sync users: on macOS
  without the Command Line Tools, `/usr/bin/git` is a stub that asks to install
  them, so the daemon fails at startup with an error that carries the install
  hand-off for the person's agent. The repository grows with
  every edit, including any large binary a skill carries. A person running
  `git` by hand in the vault is a writer Coffer must tolerate (below).
- **Why it wins.** It is the only option in which "restore last Tuesday's
  version of this skill" works the same for every user, and it deletes a
  mechanism (the round's serialize-and-commit step) instead of adding one.

#### Option A2 — Git only when syncing

Initialise the repository when the user configures a remote; without one, the
vault is plain files.

- **Pros.** No git dependency and no repository growth for single-machine
  users.
- **Cons.** Two write paths, one committing and one not, for the lifetime of
  the product; enabling sync later starts history from zero; the round must
  keep its "commit local state first" step for the case where writes were not
  committed. A single-machine user — the default, since sync is off by default —
  gets no history at all.
- **Why it loses.** It keeps two modes to save a dependency the product
  already needs for its headline multi-machine feature.

#### Option A3 — Coffer's own history store

Keep previous versions in a table in `runs.db`, or content-addressed copies in
`local/`.

- **Pros.** No git dependency; retention can be tuned per kind.
- **Cons.** It reinvents blobs, diffs and restore, is invisible to the user's
  own tools, and becomes a second history beside git's as soon as sync is on —
  two records of the same change that can disagree.
- **Why it loses.** Git is already on the critical path of the vault; a second
  history is cost with no capability git lacks.

#### Option A4 — No history (the design this replaced)

Audit rows say who changed what; content history exists only in sync
snapshots.

- **Pros.** Nothing to build.
- **Cons.** No restore for single-machine users; for sync users, restore is
  whole-vault and only as fine as one round.
- **Why it loses.** Restore is the capability the History tab exists for.

### How a write is admitted

#### Option B1 — Compare by content hash, validate, then commit; never decide by mtime (chosen)

- **One protocol for every writer.** A daemon write names the blob id of the
  file it read. Under the vault's single write lock it re-reads the file,
  compares hashes, writes a sibling temp file and renames it into place, stages
  and commits. A mismatch is `VAULT_FILE_STALE` (409) and the caller re-reads;
  there is no "unconditional" mode, so the skill API's fingerprint is
  mandatory, not optional.
- **Human edits are found, not intercepted.** File-system events (the
  `watchfiles` library, read in `infrastructure/vault/scanner.py`) are a hint,
  debounced until the changed paths have been quiet for a second, so an
  editor's temp-file-and-rename save is one change. A scan every 60 seconds and
  the boot scan are the truth: they ask git which working-tree files differ
  from `HEAD`. Git's stat cache may say "look again"; only content says
  "changed". Edits made while the daemon was down are found at boot.
- **Validation decides what becomes effective.** Every change — a person's,
  the daemon's, a merge's — passes one validator before it is committed: the
  kind's schema and validators, the uid rules
  ([A Resource's Identity Is the `uid` Inside Its File](identity-is-the-uid-inside-the-file.md)),
  and the format-version rules
  ([Every Vault File Carries Its Own Format Version](every-vault-file-carries-its-format-version.md)).
  A plain-text secret is not this validator's to find: the sync round scans
  every blob it is about to publish and stops before pushing one
  ([Standalone Secrets](standalone-secrets-are-named-references-injected-into-one-child.md)).
  A file that fails stays in the working tree, uncommitted, and is flagged on
  its resource with the reason; the effective version is the one at `HEAD` —
  the last valid version — until the file is fixed. The reconciler converges
  only the committed tree, so an invalid edit can never reach an agent's
  config.
- **Granularity: one commit per operation.** A daemon operation — one API call,
  one knowledge sweep, one layout upgrade, one restore — is one commit, however
  many files it touches. A person's edits are one commit per debounce settle. A
  sync round's merge is its merge commit. Writers are never mixed in one
  commit.
- **Audit follows the commit.** The operation records its audit row after
  the commit. Unlike a file outside the vault, the commit is itself a durable
  record of writer, actor and content, so if the audit row cannot be written the
  change is not rolled back: the failure is logged and the commit stands. A
  hand edit found by the scanner is audited when it is committed, as
  `vault_file_edited` with actor `human`, one row per file.
- **Restore is a write.** Restoring a version writes that version's content
  through this same protocol — expected hash, validation, a new commit naming
  the writer and `Coffer-Restored-From: <commit>`. History is never rewritten
  by Coffer.
- **A person's own git.** A commit a person makes by hand in the vault is a
  `disk` write: the daemon sees `HEAD` move, validates the new tree, and flags
  what fails. A person who rewrites history that has already been pushed is told
  the next round must rejoin the remote.
- **Secrets when not carried.** With `include_secret` off,
  `vault/secret/` is excluded from every commit, so there is no local
  history of ciphertext either. Keeping one in a separate ignored repository
  was considered: it would let a person roll a secret back, but it retains the
  old ciphertext of every rotated or compromised secret indefinitely — the
  thing rotation exists to retire — and a Fernet key read once would open all
  of it. Rolling a secret back is re-entering it. With `include_secret`
  on, ciphertext is committed because it must be pushed, and its history is the
  remote's. Stripping ciphertext from commits only at push time is
  not possible without rewriting the commits, which would break `HEAD` as the
  pointer and every merge base.
- **What stays out.** Derived output is under `derived/`, never in the
  repository; the deletion breaker and snapshot tags keep working on the
  committed history (a local mass deletion is committed as a `disk` write,
  recoverable in one restore, and held at push by the outgoing breaker).

Pros: every writer is subject to the same check and the same validator; a
concurrent edit is refused instead of lost; an invalid edit cannot take effect
or spread; mtime no longer decides anything, so a checkout, a restore or a
backup tool touching timestamps cannot fake an edit.

Cons: an external editor can still save in the microseconds between the
daemon's compare and its rename — no portable lock stops another process —
and the next scan then sees the daemon's bytes, not the person's; the person's
editor usually reports the file changed underneath it. The knowledge sweep finds
what a person edited by content rather than by mtime: a document whose bytes
in the working tree differ from the blob at `HEAD` is committed as a `disk`
write.

It wins because it replaces four different protections, two of them
mtime-based, with one that every writer passes through.

#### Option B2 — Last writer wins

Write unconditionally; the most recent writer's bytes stand.

- **Pros.** Simplest; no conflict ever surfaces.
- **Cons.** It was the sync apply's behaviour, and it loses a person's
  edit whenever a round or a sweep lands on the same file.
- **Why it loses.** A lost edit is the one outcome with no recovery short of
  history, and history should be for mistakes, not for the normal case.

#### Option B3 — Decide by modification time

Treat a file whose mtime is newer than Coffer's last write as a person's edit,
as the knowledge sweep once did.

- **Pros.** One `stat` per file, no hashing, no repository.
- **Cons.** A checkout, a restore, a backup tool or a clock change moves
  mtime; Coffer's own write had to realign it to avoid reading itself as a
  person; sync writes read as edits. Two machines' clocks mean
  nothing to each other.
- **Why it loses.** mtime records when bytes were written, not who wrote them
  or whether they changed.

#### Option B4 — Lock files, or make the vault daemon-only

Take an advisory lock around every write, or forbid anyone but the daemon to
write the vault.

- **Pros.** A lock would close the compare-and-rename window; daemon-only
  would remove the problem.
- **Cons.** Editors and agents' file tools do not take Coffer's lock, so the
  lock binds only Coffer. Daemon-only abandons the product goal that the vault
  is ordinary files a person may edit.
- **Why it loses.** It constrains the writers who already cooperate and none
  of the others.

## Decision

`~/.coffer/vault/` is always a local git repository; sync only adds a remote.
There are three writers — a person, the daemon, sync — and every change any of
them makes is admitted the same way: compared by content hash against what the
writer read, validated by one validator, and committed as one commit per
operation whose author and trailers name the writer. A change that fails
validation stays uncommitted and flagged, and the last valid version at `HEAD`
stays in effect. Human edits are detected by debounced watching as a hint and
by content-comparing scans as the truth; mtime never decides staleness. The
audit row follows the commit, and a commit stands if its audit row cannot be
written. Restore is an ordinary write of old content, never a history rewrite.
Secret ciphertext is committed only when the remote carries secrets.

## Consequences

- The sync round loses its serialize step and its pointer table; the
  reconciler reads the committed tree
  ([Sync Only Pulls and Pushes the Vault Repository](sync-applies-clean-merges-and-stops-on-any-conflict.md)).
- Every vault-writing API takes an expected hash: saving a skill file, saving
  a knowledge document and restoring a version all require the fingerprint, and
  there is no unconditional mode. A stale fingerprint is `VAULT_FILE_STALE`
  (409), which the skill and knowledge surfaces report under their own codes.
- The knowledge sweep reads no modification times; it compares the working
  tree's content against `HEAD`.
- Coffer requires git (2.40 or newer) on every machine, not only those that
  sync; the daemon refuses to start without it.
- The vault writer (`infrastructure/vault/writer.py`) owns the lock, the
  compare, the validator call and the commit; history, diff and restore
  (`application/vault/history_service.py`) and the skill History tab are its
  first consumers.
- Not built yet: the boot-time backfill of audit rows for commits that have
  none. A failed audit write is logged and the commit stands, but nothing finds
  such a commit afterwards.
- Not built yet: a measurement of the per-commit cost against an editor saving
  on every keystroke. There is no performance suite for it; the debounce (one
  commit per settle) is the mitigation, not a measured bound.
