# A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label

**Status**: Proposed
**Date**: 2026-09-29
**Deciders**: Yuxing Wu
**Related**: [Resource Identity Is an Immutable `uid`, Not the Name](resource-identity-is-an-immutable-uid.md), [Names Visible to Agents Are Fixed; Every Resource Carries an Editable Title](names-visible-to-agents-are-fixed.md), [Storage Is Five Classes by Nature; Whether a Class Syncs Is Policy](storage-is-five-classes-by-nature.md), [Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer](every-vault-write-is-a-validated-commit-naming-its-writer.md), [Every Vault File Carries Its Own Format Version; One Owner Machine Commits Layout Upgrades](every-vault-file-carries-its-format-version.md), [Sync Merges Outside the Vault With `git merge-tree`, Then Guards, Then Checks Out](sync-merges-outside-the-vault-then-checks-out.md), [A Sync Round That Would Lose Too Much Is Held, in Both Directions, Counting Losses Not Moves](sync-deletion-breaker.md), [One Level-Triggered Reconciler Converges What Coffer Writes Outside Its Database, Comparing Parameters](one-level-triggered-reconciler-compares-parameters.md), spec resource-framework "Address every resource by an immutable uid through one kind-agnostic surface", spec resource-framework "Treat a resource's name as a mutable label", spec vault-sync "Key resource documents by uid", spec knowledge "Use the file path as a document's identity", PR #406, PR #409

## Context

[Resource Identity Is an Immutable `uid`](resource-identity-is-an-immutable-uid.md)
made a resource's identity an opaque `uuid4().hex` minted once by
`ResourceService.register` (`application/resource_service.py:195`), held in
the `resources.uid` column behind a unique index
(`infrastructure/persistence/models.py:41`, index `uq_resources_uid` at line 63). Its
guarantee — one identity per resource, the same on every machine — rests on
SQLite: the index makes a second row with the same uid impossible, and the
sync document `resources/<kind>/<uid>.yaml` is written *from* the row, so its
path and the `uid:` line inside it (`domain/sync/serialization.py:47`) cannot
disagree.

When the vault becomes the files themselves
([Storage Is Five Classes by Nature](storage-is-five-classes-by-nature.md)),
nothing is written *from* a row any more. A person edits the files in an
editor, copies one to start a similar resource, moves one to tidy a folder;
git renames them in a merge; a future second root (a team's shared
repository, a marketplace) holds files this machine did not mint. The
database no longer stands behind the identity, so the files have to carry it
and the rules that the unique index used to enforce have to be stated.

Two facts from the field bound the answer. A rename once crossed the remote as
a deletion plus an addition because the path *was* the identity and the
applier took the diff path by path; the cascade destroyed chats, tool switches
and an API key (the reason for PR #406). And the deletion breaker held a vault
for four days over the uid migration because it could only compare paths and
blob ids; git's rename detection had to be added to see that 28 documents had
moved, not vanished (PR #409). Both are what a path-as-identity costs.

Two corrections to the plan this ADR was drafted from: the uid is a
`uuid4().hex`, not a ULID — ULID was considered and rejected in the uid ADR
(its Option F), and nothing in `backend/coffer/` mints one. And a uid is
already globally unique (122 random bits), which matters for the multi-source
rules below.

## Options Considered

### Option A — The uid is a field inside the file; path and name are only location and label (chosen)

- **Every resource file carries its `uid`**, first, beside `kind` and
  `format_version`
  ([Every Vault File Carries Its Own Format Version](every-vault-file-carries-its-format-version.md)).
  For a kind whose content is a directory an agent reads — a skill's master
  folder, a knowledge collection — the uid lives in the kind's resource file,
  which names the directory; the agent-facing files (`SKILL.md`, the Markdown
  documents) carry no Coffer identity.
- **The path is chosen for people.** Coffer files a new resource at
  `vault/resources/<kind>/<name>.yaml`. Nothing keys on the path: a person may
  move or rename the file, git may rename it in a merge, and the resource is
  the same resource. When Coffer renames a renamable label it moves the file in
  the same commit, so paths stay readable; it never has to.
- **A file with no uid is a new resource.** Validation mints a `uuid4().hex`
  and writes it into the file as a daemon write — the way a person creates a
  resource by hand.
- **References are uids.** Scope and reach entries, a channel's
  `default_agent`, `forked_from`, audit rows: a uid, never a path, never a name.
- **A derived index maps uid → path**, built at boot by reading every resource
  file's uid, kept current by the writer model's hints, and stored in
  `derived/`, so deleting it costs one rebuild. It is the only way from a uid
  to a file.
- **A duplicate uid: the later one is invalid.** "Later" is the path that did
  not hold the uid in the incumbent tree — the vault's `HEAD`, the last state
  every writer's validation accepted. A copy a person makes of a resource file
  therefore fails validation, is flagged ("duplicate of `<path>`; remove its
  `uid` to make it a new resource") and is never committed or activated; the
  original is untouched. A merged tree that holds one uid at two paths is
  refused as a conflict before checkout: in practice it can only arise
  alongside the modify/delete conflict of a rename git failed to pair, and
  only a person knows which content is right. mtime never decides.
- **Reserved for more than one root.** When Coffer later reads a second root
  (a team repository, a marketplace), three rules hold:
  1. **Write only the own root.** Every other root is read-only; an edit to one
     of its resources is a fork.
  2. **Names are unique across roots.** A name is what an agent sees
     (`<server>__<tool>`, a skill's directory), and that namespace is flat, so
     a name offered by a second root that the own root already holds is
     shadowed and reported, never merged.
  3. **Copying into the own vault mints a new uid** and records
     `forked_from: {root, uid}`. The copy is a different resource from the
     original, so both can be present if that root is later added, and
     provenance survives.

  No uid carries a source prefix: a random uid is already unique across roots,
  and a prefix would make identity depend on where a file lives.

Pros: identity survives every move a person, git or a later root can make;
the breaker and the reconciler can count and compare by uid instead of by
path (a relocation is visibly not a loss); the vault is readable by name; the
multi-root rules need no new identity scheme.

Cons: uniqueness is a validation rule instead of a database constraint, so it
is only as good as the one validator every writer passes through; the index is
a second structure to keep current; a hand-copied file is refused rather than
silently becoming something, which a user must learn to read.

It wins because it is the only option in which the identity the uid ADR chose
survives the move to files unchanged, and in which a path can change without
meaning anything.

### Option B — The path is the identity

Address each resource by its path in the vault, as knowledge documents already
are (spec knowledge "Use the file path as a document's identity").

- **Pros.** Nothing to mint, nothing to index, no duplicate possible; what a
  person sees is what everything references.
- **Cons.** It is the design PR #406 retired for resources: every rename or
  tidy-up move is a deletion plus a creation to every reference, every reach
  entry and every other machine. It fits knowledge documents because nothing
  references a document by identity and a person owns its location; resources
  are referenced from other resources and from machine-local reach.
- **Why it loses.** It brings back the rename-as-deletion failure the uid
  exists to prevent.

### Option C — File named by uid (`resources/<kind>/<uid>.yaml`, today's sync layout)

Keep the sync tree's layout as the vault's.

- **Pros.** The filesystem makes a duplicate uid within a kind impossible; path
  and uid cannot drift apart; no index is needed to find a file.
- **Cons.** The vault becomes 32-hex-digit file names that a person editing it
  by hand cannot navigate — the product promise of v0.4 is that the vault is
  readable and editable. The protection is also only local: a duplicate can
  still arrive across kinds, across roots, or by a person copying a file to a
  new uid-shaped name, so the duplicate rule is needed anyway.
- **Why it loses.** It pays in readability for a uniqueness guarantee that does
  not cover the cases that need one.

### Option D — Source-prefixed uids (`<root>:<uid>`)

Qualify each uid by the root that holds it, so roots cannot collide.

- **Pros.** Where a resource came from is visible in every reference.
- **Cons.** Random uids do not collide, so the prefix solves nothing; it makes
  identity a function of location, so moving a resource between roots
  silently changes it, and every reference must be rewritten.
- **Why it loses.** Provenance belongs in `forked_from`, recorded once at the
  moment of copying, not in every reference forever.

### Option E — Keep a SQLite registry of uids beside the files

Files hold content; a table in `local/` or `derived/` holds the uid of each
path and enforces uniqueness.

- **Pros.** The unique index keeps working exactly as today.
- **Cons.** The identity would live outside the file, so a person moving a file
  in an editor, or git renaming it in a merge, breaks the association; the
  table would need to converge between machines to mean the same thing
  everywhere — a machine-local table cannot, and a synced one is the
  translation layer again.
- **Why it loses.** An identity that does not travel with the file is not an
  identity of the file.

## Decision

A resource's identity is the `uid` written inside its own file: an opaque
`uuid4().hex`, minted once (by validation, for a file that has none), never
changed, never reused. Its path and its name are a location and a label;
nothing references either. A derived uid→path index, rebuilt at boot, is the
only way from a uid to a file. When two paths claim one uid, the one that did
not hold it in the vault's `HEAD` is invalid and is neither committed nor
activated; a merged tree with a duplicate is refused as a conflict. For a
future second root: Coffer writes only its own root, names are unique across
roots, and copying a resource into the own vault mints a new uid and records
`forked_from`.

## Consequences

- **Continues** [Resource Identity Is an Immutable `uid`](resource-identity-is-an-immutable-uid.md):
  the uid's spelling, its minting and every reference by uid are unchanged;
  what moves is where the uniqueness guarantee is enforced (validation instead
  of `uq_resources_uid`) and the vault layout (`<name>.yaml`, not `<uid>.yaml`).
  The integer `resources.id` surrogate and the foreign keys on it disappear
  with the table; kind-owned facts reference the uid.
- The deletion breaker counts **lost uids** for resource files: a path that
  disappears while its uid reappears elsewhere in the same diff is a move by
  construction, with no similarity judgement
  ([Sync Merges Outside the Vault](sync-merges-outside-the-vault-then-checks-out.md)).
- The reconciler's `Changed(kind, uid, rev)` hint takes the blob id of the
  file as `rev`, so the `rev` column the reconciler ADR asked for is not
  needed once resources are files.
- **Obligations.** Validation refuses a duplicate uid and mints a missing one;
  the index lives in `derived/` and is rebuilt when absent; the multi-root
  rules are written into the resource-framework spec now, as constraints on
  any future root, with no implementation until one exists; a test copies a
  resource file and asserts the copy is flagged and the original unchanged.
