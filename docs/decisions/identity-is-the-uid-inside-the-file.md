# A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label

**Status**: Accepted
**Date**: 2026-09-29
**Deciders**: Yuxing Wu
**Related**: [Names Visible to Agents Are Fixed](names-visible-to-agents-are-fixed.md), [Storage Is Five Classes by Nature; Whether a Class Syncs Is Policy](storage-is-five-classes-by-nature.md), [Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer](every-vault-write-is-a-validated-commit-naming-its-writer.md), [Every Vault File Carries Its Own Format Version; One Owner Machine Commits Layout Upgrades](every-vault-file-carries-its-format-version.md), [Sync Only Pulls and Pushes the Vault Repository; a Clean Merge Is Applied, Any Conflict Stops for the Person](sync-applies-clean-merges-and-stops-on-any-conflict.md), [A Sync Round That Would Lose Too Much Is Held, in Both Directions, Counting Losses Not Moves](sync-deletion-breaker.md), [One Level-Triggered Reconciler Converges What Coffer Writes Outside Its Database, Comparing Parameters](one-level-triggered-reconciler-compares-parameters.md), spec resource-framework "Address every resource by an immutable uid through one kind-agnostic surface", spec resource-framework "Treat a resource's name as a mutable label", spec vault-storage "Identify a resource by the uid inside its file", spec knowledge "Use the file path as a document's identity", PR #406, PR #409

## Context

Every resource needs an identifier that the outside world holds: REST paths,
CLI arguments, cross-resource references (a resource's per-agent reach lists
agents; a channel's `default_agent` names one), the resource's place in the
vault the machines converge through, and the audit trail. The identifier has to
answer two different questions:

1. *What do I call this?* — a label a person reads and types.
2. *Is the thing on that machine the same thing as the thing on this one?* —
   an identity that survives every edit a user is allowed to make, and that two
   machines holding one vault agree on without talking to each other, since a
   vault converges through a git remote with no online handshake
   ([sync](sync-applies-clean-merges-and-stops-on-any-conflict.md)).

For a long time the external identifier was the string `<kind>:<name>`, backed
by a unique constraint on kind and name. That answered question 1 well and was
chosen when there was no other Coffer to distinguish from. Sync made question 2
real, and a name cannot answer it, because a name is exactly what the user is
allowed to change. The failures that accumulated are the evidence the options
below are weighed against:

- **A rename crossed the sync remote as a deletion plus a creation.** The
  synced document lived at a path built from its name and spelled its own name,
  so a rename changed both its path and its bytes. The old applier took the
  diff path by path, so a changed path was always a delete and an add; the
  receiving machine ran the full delete, whose cascade dropped the resource's
  paired chats, its per-tool switches and its skill bindings, and released the
  API key no remaining row cited. Whether the re-creation then succeeded
  depended on whether the new name sorted before or after the old one (PR #406).
- **Rename was one kind's private operation.** Only `provider` had it, because
  its name was written into another tool's config file. Every other kind
  offered delete-and-re-create, paying the same cascade locally.
- **The label carried the identity's constraints.** A name had to be a URL
  segment and a file name.
- **Cross-resource references needed translating.** "Which agent" was spelled
  three ways — agent resource names in skill and channel scopes, agent types in
  provider scopes, and agent keys in a channel's `default_agent` — and a module
  existed only to translate between two of them.
- **The deletion breaker held a vault for four days** over the migration that
  gave every resource a uid, because it could only compare paths and blob ids;
  git's rename detection had to be added to see that 28 documents had moved,
  not vanished (PR #409). That is what a path-as-identity costs.

The identity was first an opaque `uuid4().hex` minted once and held in a
database column behind a unique index. When the vault became the files
themselves ([Storage Is Five Classes by Nature](storage-is-five-classes-by-nature.md)),
nothing is written *from* a row any more. A person edits the files in an
editor, copies one to start a similar resource, moves one to tidy a folder; git
renames them in a merge; a future second root (a team's shared repository, a
marketplace) holds files this machine did not mint. A database no longer stands
behind the identity, so the files have to carry it and the rules that the
unique index used to enforce have to be stated.

## Options Considered

### Option A — The uid is a field inside the file; path and name are only location and label (chosen)

- **Every resource file carries its `uid`**, first, beside `kind` and
  `format_version`
  ([Every Vault File Carries Its Own Format Version](every-vault-file-carries-its-format-version.md)).
  The uid is an opaque `uuid4().hex` (122 random bits, so globally unique), not
  a ULID. For a kind whose content is a directory an agent reads (a skill's
  master folder, a knowledge collection) the uid lives in the kind's resource
  file, which names the directory; the agent-facing files (`SKILL.md`, the
  Markdown documents) carry no Coffer identity.
- **The path is chosen for people.** Coffer files a new resource at
  `vault/resources/<kind>/<name>.json`; resources that are machine-local or
  derived are filed under `local/` or `derived/` by the same layout
  ([Storage Is Five Classes by Nature](storage-is-five-classes-by-nature.md)).
  When the name is taken by an unrelated file, the file falls back to
  `<name>-<uid[:8]>.json`. Nothing keys on the path: a person may move or rename
  the file, git may rename it in a merge, and the resource is the same
  resource. When Coffer renames a renamable label it moves the file in the same
  commit, so paths stay readable; it never has to.
- **Files are JSON.** Every other vault document Coffer parses is JSON, JSON has
  one canonical serialisation for a deterministic writer, and a person editing
  by hand gets a precise parse error. A file may carry an optional `title`
  beside the name, for the label pages show.
- **A file with no uid is a new resource.** Validation asks for a fix that
  mints a `uuid4().hex`, which the writer commits as a daemon write right after
  the person's own commit, the way a person creates a resource by hand.
- **References are uids.** Reach entries, a channel's `default_agent`, audit
  rows: a uid, never a path, never a name. `enabled` and reach are true of this
  machine only and live in `local/reach.json`, not in the file
  ([Reach Is Machine-Local: Stored by uid in `local/reach.json`, Never Synced](reach-is-machine-local-stored-by-uid-never-synced.md)).
- **uid to file is an in-memory index over `HEAD`.** The resource store lists
  the committed tree once, parses each resource file by its blob, and indexes
  what it finds by uid; a commit through the writer patches that cache from the
  committed paths. It is the only way from a uid to a file, and rebuilding it
  costs one tree listing.
- **A duplicate uid: the later one is invalid.** "Later" is the path that did
  not hold the uid in the incumbent tree, the vault's `HEAD`, the last state
  every writer's validation accepted. A copy a person makes of a resource file
  therefore fails validation (`DUPLICATE_UID`: "a copy needs no uid of its
  own"), is flagged and is never committed or activated; the original is
  untouched. A path going away in the same change makes the uid's new home a
  move, not a duplicate. A merged tree that holds one uid at two paths, or one
  name with two different uids, stops the sync round as a conflict before
  checkout: in practice it can only arise alongside the modify/delete conflict
  of a rename git failed to pair, or from two machines creating the same name
  independently, and only a person knows which content is right. mtime never
  decides. A name must stay unique within a kind (`NAME_TAKEN`).
- **A name is a mutable label** except where it is visible outside Coffer: a
  kind declares it fixed and refuses a changed name
  ([Names Visible to Agents Are Fixed](names-visible-to-agents-are-fixed.md)).
  Its rule (`^[a-zA-Z0-9_.-]+$`, at most 64 characters) stays because `skill`
  and `knowledge` turn a name into a directory, not because it is an
  identity constraint.
- **Reserved for more than one root.** When Coffer later reads a second root (a
  team repository, a marketplace), three rules are meant to hold:
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

Pros: identity survives every move a person, git or a later root can make; the
deletion breaker counts lost uids instead of paths, so a relocation is visibly
not a loss ([A Sync Round That Would Lose Too Much Is Held](sync-deletion-breaker.md));
the reconciler hint carries the uid
([One Level-Triggered Reconciler Converges What Coffer Writes Outside Its Database](one-level-triggered-reconciler-compares-parameters.md));
a rename is a modification of one file and nothing else holds the name; the
vault is readable by name; the multi-root rules need no new identity scheme.

Cons: uniqueness is a validation rule instead of a database constraint, so it
is only as good as the one validator every writer passes through; a hand-copied
file is refused rather than silently becoming something, which a user must
learn to read; a URL is no longer guessable from a name, so the CLI resolves
names to uids (one lookup) and nobody types a uid.

It wins because it is the only option that fixes every failure above, and in
which a path can change without meaning anything. The readability it gives up
is recovered by keeping `kind` and `name` as fields on every response and
letting humans keep typing names.

### Option B — `<kind>:<name>` is the identity (the design this replaced)

A `(kind, name)` pair parsed at the domain boundary; routes
`/<kind>/<name>`; references and synced paths by name.

- **Pros.** Short and self-describing (`mcp_server:filesystem`), needs no
  lookup to know which kind to ask, maps directly onto URLs and CLI arguments;
  nothing to mint, nothing to index.
- **Cons.** Every failure in the Context. The colon also had to be excluded
  from names and every consumer had to know the convention.
- **Why it loses.** It cannot answer question 2, and question 2 is the one that
  loses data.

### Option C — Keep the name as identity; teach sync to recognise renames

Record a rename event (or pair a delete and an add by content similarity) and
apply it as a move.

- **Pros.** No identity change, no surface churn.
- **Cons.** It invents a rename protocol on top of a system whose arbiter is
  git, and similarity pairing is a guess. It leaves the other failures
  untouched: rename stays one kind's private operation, and the label stays
  welded to the identity.
- **Why it loses.** It replaces a data-loss bug with a consistency protocol.

### Option D — The path is the identity

Address each resource by its path in the vault, as knowledge documents already
are (spec knowledge "Use the file path as a document's identity").

- **Pros.** Nothing to mint, nothing to index, no duplicate possible; what a
  person sees is what everything references.
- **Cons.** It is Option B's failure for resources: every rename or tidy-up
  move is a deletion plus a creation to every reference, every reach entry and
  every other machine. It fits knowledge documents because nothing references a
  document by identity and a person owns its location; resources are
  referenced from other resources and from machine-local reach.
- **Why it loses.** It brings back the rename-as-deletion failure the uid
  exists to prevent.

### Option E — The file is named by uid (`resources/<kind>/<uid>.json`)

Make the vault's layout the layout the first sync documents had.

- **Pros.** The filesystem makes a duplicate uid within a kind impossible; path
  and uid cannot drift apart; no index is needed to find a file.
- **Cons.** The vault becomes 32-hex-digit file names that a person editing it
  by hand cannot navigate, and the vault being readable and editable is a
  product promise. The protection is also only local: a duplicate can still
  arrive across kinds, across roots, or by a person copying a file to a new
  uid-shaped name, so the duplicate rule is needed anyway.
- **Why it loses.** It pays in readability for a uniqueness guarantee that does
  not cover the cases that need one.

### Option F — A per-machine integer row id as the identity

Promote the autoincrement key the database tables used.

- **Pros.** Already exists, already the foreign-key target.
- **Cons.** It is a per-machine row number: machine A's row 7 and machine B's
  row 7 are different resources. As a file name it would three-way-merge two
  unrelated resources.
- **Why it loses.** It is not an identity across machines, and with the
  resources as files there is no table to hold it.

### Option G — A deterministic `uuid5` of `(kind, name)` for every resource

- **Pros.** Deterministic with no coordination, ever: two machines that
  independently create `skill:foo` get the same uid.
- **Cons.** The identity becomes a function of a label at the moment of
  creation. Deleting `foo` and creating a new `foo` would hand the new resource
  the dead one's identity (its audit trail here, its config on every other
  machine), which is the confusion this decision exists to end. Two unrelated
  resources created under one name on two machines would silently become one
  document and fight every round.
- **Why it loses.** Determinism was needed exactly once, to give rows that
  already existed the same uid on every machine without coordination, and the
  one-time migration used it there. Two machines that independently create the
  same name now meet as a conflict a person answers, which is the honest
  outcome.

### Option H — ULID, a URN, a path-style `<kind>/<name>`, or a composite key

- **ULID (or another time-ordered id).** Sortable by creation time, shorter,
  good index locality; but nothing lists resources by creation order, a few
  hundred files gain nothing from locality, and it is a second id spelling
  beside the `uuid4().hex` already used for secret refs and machine-id
  fallbacks.
- **A URN (`urn:coffer:<kind>:...`).** Standard and namespaced; but wrapping a
  name keeps every failure of Option B, and wrapping a uid adds a prefix that
  only restates `kind`. The machines sharing a vault are one user's, so there
  is no foreign Coffer to distinguish from.
- **Path-style `<kind>/<name>`.** Reads naturally in URLs; but it is Option B
  with a slash that collides with URL and file-path separators.
- **A composite key `(kind, name)` never serialised as one string.** No string
  format to parse; but it is still name-as-identity, and every cross-resource
  reference needs an object instead of a field.
- **Why they lose.** Each is ceremony around a label, or answers a question
  Coffer does not ask.

### Option I — Source-prefixed uids (`<root>:<uid>`)

Qualify each uid by the root that holds it, so roots cannot collide.

- **Pros.** Where a resource came from is visible in every reference.
- **Cons.** Random uids do not collide, so the prefix solves nothing; it makes
  identity a function of location, so moving a resource between roots silently
  changes it, and every reference must be rewritten.
- **Why it loses.** Provenance belongs in `forked_from`, recorded once at the
  moment of copying, not in every reference forever.

### Option J — Keep a registry of uids beside the files

Files hold content; a table in `local/` or `derived/` holds the uid of each
path and enforces uniqueness.

- **Pros.** A unique index keeps working as it did when resources were rows.
- **Cons.** The identity would live outside the file, so a person moving a file
  in an editor, or git renaming it in a merge, breaks the association; the
  table would need to converge between machines to mean the same thing
  everywhere. A machine-local table cannot, and a synced one is the translation
  layer again.
- **Why it loses.** An identity that does not travel with the file is not an
  identity of the file.

## Decision

A resource's identity is the `uid` written inside its own file: an opaque
`uuid4().hex`, minted once (by the service on registration, or by validation
for a file that has none), never changed, never reused, the same on every
machine that holds the resource. It is spelled `uid` everywhere. Its path and
its name are a location and a label; nothing references either, and a name is
unique within its kind and fixed only where it is visible outside Coffer. The
resource store indexes the committed files by uid and is the only way from a
uid to a file. When two paths claim one uid, the one that did not hold it in the
vault's `HEAD` is invalid and is neither committed nor activated; a merged tree
with a duplicate uid, or one name under two uids, stops the sync round as a
conflict.

## Consequences

- Resource files are `<name>.json` (with a `-<uid[:8]>` fallback), not named by
  uid; a rename moves the file in the same commit.
- The deletion breaker counts **lost uids** for resource files: a path that
  disappears while its uid reappears elsewhere in the same diff is a move by
  construction, with no similarity judgement.
- The reconciler's `Changed` hint carries the kind, the uid and the operation;
  a pass compares content, so no revision counter exists.
- Validation refuses a duplicate uid and mints a missing one; the identity
  rules are covered by tests that copy a resource file and assert the copy is
  flagged and the original unchanged.
- Not built yet: a second root. The three multi-root rules above are written as
  constraints on any future root, and `forked_from` provenance is not recorded
  anywhere because nothing yet copies a resource across roots.
