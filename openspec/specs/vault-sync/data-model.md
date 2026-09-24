# Data Model — Vault Sync

Sync persists in three places, and which one holds what is the whole design:

| Where | What | Why there |
| --- | --- | --- |
| SQLite | the one sync remote's configuration, and the history of rounds | it is user-entered config and machine-local record, like any other |
| SQLite | the pointer, the held round, the retry set, the not-applicable set | `coffer.db` is already machine-local and already excluded from the tree, so this state **never** travels without a second store to reason about |
| the working tree | every vault document, and the machine registry | it is what git merges |

The vault itself keeps its existing system of record: knowledge and skills are
files, config resources are rows reached through `ResourceService`, credentials
are ciphertext rows. Sync owns none of them.

## SQLite — `sync_remotes`

Unchanged from the backup remote, single row by construction (`id = 1` is a
check constraint, not a convention). Bidirectional convergence needs no extra
column: the base of a round is the pointer, which is local, and the registry is
the tree.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | int | pinned to 1 |
| `url` | str | the user's own repository |
| `branch` | str | default `main` |
| `credential_ref` | str? | a **reference** into the credential store, never a secret |
| `include_credentials` | bool | whether ciphertext rides along; default off |
| `interval_seconds` | int | default 3600, `> 0` by check constraint |
| `enabled` | bool | sync is off until the user configures a remote; `false` pauses a configured remote — rounds report `disabled` and record nothing — while the remote, pointer and history are kept |
| `worktree_path` | str | default `~/.coffer/sync` |
| `last_started_at` | ts? | when the most recent round began — the pair with `last_run_at` is what tells a surface how long a round took, and how long one that never finished has been running |
| `last_run_at` | ts? | when the most recent round finished |
| `last_status` | str? | see the vocabulary below |
| `last_join` | str? | `new` / `returning` when the most recent round joined a remote; null otherwise |
| `last_error` | str? | redacted of the push credential before it is written |
| `last_commit` | str? | the commit the last round landed on |
| `last_run_json` | str? | everything else that round carried, as one JSON document — the two diff summaries and their paths, the conflicted and agent-resolved paths, the per-path failures, the locked refs and any held confirmation. The same column-versus-payload split as `sync_runs` below, so the status surface reads one row and no column can disagree with the payload beside it |
| `updated_at` | ts | |

Because `credential_ref` is a reference, the whole row can be read into an API
response or a log line without redaction.

`last_status` gains the round's whole vocabulary, written verbatim from
`ConvergeStatus`: `ok`, `no_change`, `conflict`, `awaiting_confirmation`,
`push_failed`, `failed`, `disabled`, `awaiting_join`. Two of those are
successes rather than skips — `no_change` means there was nothing to do on
either side, and `disabled` that no remote is configured or it is switched off.
`awaiting_join` means this machine has no pointer and has not adopted the
remote, so an ordinary round applied and pushed nothing; like an outstanding
confirmation it is recorded once and re-stamped rather than appended again. Whether the round *joined* a
remote is a different question, answered by `last_join` (`new` / `returning`),
not a status of its own. The `last_*`
columns are the most recent round denormalised onto the remote, so a status
surface reads the current state without touching the history; every round,
including that one, is also appended to `sync_runs` below.

## SQLite — `sync_runs`

Every converge round this machine has run. The remote's `last_*` columns answer
"what happened just now"; they cannot answer "what has been happening", and
that is the question a user actually brings to the page — a round that failed
once is noise, a round that has failed every hour since Tuesday is the answer,
and a vault that has quietly published nothing for a week looks identical to a
healthy one through a single row.

Machine-local and **never synced**, for the same reason the pointer is: a
history that travelled would be another machine's account of rounds this one
never ran. Each machine keeps its own; the git history on the remote remains
the record of what *changed*.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | int | autoincrement; a row key for a surface, never shown |
| `started_at` | ts | |
| `finished_at` | ts | indexed — read newest-first, pruned oldest-first |
| `status` | str | the same vocabulary as `last_status` |
| `join_kind` | str? | `new` / `returning` when the round joined; else null |
| `commit_sha` | str? | `commit` is reserved in SQL |
| `error` | str? | redacted of the push credential before it is written |
| `payload_json` | str? | everything else a `ConvergeRun` carries |

Same column-versus-payload split as the remote row, and for the same reason:
what a table reads at a glance is a column, and the two diff summaries, the
conflicted and agent-resolved paths, the per-path failures, the locked refs and
any held confirmation are one JSON document written exactly once. The counts a
row shows are derived from that document rather than stored a second time.

Recording a round writes this table and the remote's `last_*` columns in **one
transaction**, so the newest row here and those columns can never describe
different rounds — and both are skipped together when no remote is configured,
so a cleared remote discards the round rather than leaving it orphaned here.

`commit_sha` is the one place the two deliberately differ. The remote row
carries the previous commit forward through a round that landed none, because
that revision is what the user is being told is still waiting; a history row
does not, because it would put a commit on a round that never produced one.

Swept by the retention worker as `sync_runs` (default 90 days): a round runs on
a timer, so an unbounded log of them is a leak rather than a record.

## SQLite — `sync_convergence_state` and `sync_held_paths`

The pointer and its two companion sets. They live in `coffer.db` because that
database is already machine-local and already excluded from the working tree,
so there is no second store to reason about — and **the pointer must never
travel**: it is this machine's assertion about what it has absorbed, and
another machine reading it as its own base is exactly the mutual-deletion shape
the spec exists to prevent.

`sync_convergence_state` is a single pinned row:

| Column | Meaning |
| --- | --- |
| `pointer` | the commit this vault has provably absorbed; the base of every diff. `NULL` means **joining**, which the round detects and resolves against the remote's registry before it does anything |
| `pending_json` | a held round — the guard's direction, the commit it reached, the remote tip it was raised against, the per-area breaches and the paths. `NULL` when nothing is held |
| `updated_at` | when either of the two above last changed |

`sync_held_paths` carries both companion sets in one table, told apart by
`applicable`:

| `applicable` | Meaning |
| --- | --- |
| `true` | **retry** — a path the tree holds that this vault has not absorbed. Re-attempted every round, reported as an error, released on success |
| `false` | **not applicable** — a path that cannot apply on this machine at all (an `agent` whose `config_dir` does not exist here). Preserved identically, but never retried and never reported, because a fact about this machine should not become an error the user learns to ignore |

Either way the exporter MUST NOT delete a held path. Deleting one would turn
"this vault could not absorb it" into "the user deleted it" — the confusion the
whole design exists to prevent, arriving through a different door.

The **remote tip** stored with a held round is what makes a confirmation mean
something specific. A confirmed round is re-derived rather than resumed —
serialization is deterministic, so an unchanged vault against an unchanged
remote yields the diff the user was shown — and the deletion guard is waived
only for that exact tip. If the remote moved in the meantime the guard runs
again and the round is held afresh.

`EMPTY_TREE` — git's empty-tree hash — is the pointer a **new** machine starts
from. It is an ordinary value in this column, not a flag, which is why "a new
machine cannot delete anything" is a structural property rather than a special
case in the code.

Ten pre-apply snapshots are kept as git tags in the working tree
(`coffer/pre-apply/<timestamp>`), not as rows: the tag's tree *is* the vault's
state immediately before an apply, so a rollback is the same applier run
backwards over that diff.

## Working tree — `~/.coffer/sync`

The directory the vault is serialized into, which is also the git working tree.
An existing repository there is adopted with its history intact.

```
manifest.json                  tree schema version
knowledge/                     mirror of ~/.coffer/knowledge
skills/                        mirror of ~/.coffer/skills (master skill store)
resources/<kind>/<uid>.yaml    one deterministic file per config resource
state/<area>/...yaml           module-owned shared state docs
credentials/<ref>.enc          Fernet ciphertext, base64 text; never the key
machines/<machine_id>.yaml     one descriptor per machine
```

`credentials/` exists only when the remote is configured to carry ciphertext.

Every write into this tree is **differential**: changed documents are written,
documents the vault no longer holds are removed, and no directory is ever
cleared and rewritten. That rule is what keeps "I never had it" and "I deleted
it" distinguishable in the diff git sees.

### `manifest.json`

| Field | Type | Notes |
| --- | --- | --- |
| `schema_version` | int | bumped on incompatible tree layout changes |

Current version: **2**. The tree is a new format with its own lineage; neither
the withdrawn git workspace's version (which had reached 3) nor the export
bundle's carries over.

Version 2 moved resource documents from `<name>.yaml` to `<uid>.yaml`. The bump
is not cosmetic: a build on version 1 reading a version 2 tree would see every
resource path change at once and apply it as "deleted everything, created
everything" — which is the exact loss the uid layout exists to prevent, so the
older build must be stopped before it reads rather than allowed to converge
half-understood.

`schema_version` is checked before a round applies anything: a tree newer than
the running build fails closed with `SYNC_BUNDLE_TOO_NEW`, mirroring the DB
`DB_SCHEMA_TOO_NEW` rule. The `created_at` the bundle manifest used to carry is
**gone** — a timestamp restamped every round would make a manifest-only diff the
one thing that always changed, and determinism is what lets a round with nothing
to say produce no commit at all. Applying a diff ignores `manifest.json` in both
directions.

### Resource serialization (`resources/<kind>/<uid>.yaml`)

Deterministic projection of a `Resource`:

```yaml
uid: 9f2c1a7b4e8d4c1fa0b3d5e6f7081920
kind: mcp_server
name: confluence
description: "..."
config: { ... }          # the validated, json-mode config; keys sorted
```

The `uid` is the document's identity and its filename. The `name` travels
**inside** the document, which is the whole of what makes a rename a
modification of one file instead of a deletion beside an addition
([Resource Identity Is an Immutable `uid`](../../../docs/decisions/resource-identity-is-an-immutable-uid.md)).

- `created_at` / `updated_at` / the local integer `id` are **excluded** —
  machine-local, and they would make every round produce a commit. The `uid` is
  the opposite of machine-local and is the one identifier that DOES travel.
- `enabled` and `scope` are **excluded** for a stronger reason than churn: they
  are one thing, the resource's reach, and reach is machine-local (see "Keep
  reach machine-local"). They are **rejected** like any other unknown key. They
  used to be parsed and discarded so that a machine which had not upgraded could
  not stall convergence for the rest — but the version 2 bump retires that
  argument rather than softening it: a build old enough to write them cannot
  reach this parser at all, because it refuses the whole tree first.
- A `channel` gets an ordinary document like every other kind. It once got none
  at all; it travels now because its config names the one machine whose daemon
  runs its adapter (`runs_on`, spec channels "Bind each channel to the one
  machine that runs it"), so the document can move without the adapter moving
  with it.
- Mapping keys are sorted; there is exactly one document per resource, so an
  unchanged vault produces an unchanged tree.
- String values under this machine's home are normalized to `${HOME}/...` and
  expanded against the applying machine's home (see below).

Applying an addition or a modification upserts by **`uid`** through the
kind-agnostic `ResourceService`, with the kind's import gate run: a resource
this vault does not hold is created *at the uid the document carries*, so both
machines keep one identity for one resource, and a document whose `name`
differs from the local row's is applied as a **rename** of that row — which is
what fires the kind's own `on_rename` and moves a directory named after it.
Applying a deletion deletes the resource, which releases the credentials no
remaining resource cites. After the whole diff is applied, each kind's post-import hook
re-applies its machine-local side effects — native config projections, shims,
skill deliveries — from current state.

### `scope_json` — back to one axis

The machine axis is removed, and a migration rewrites every row that carried
one:

| | before | after |
| --- | --- | --- |
| unrestricted | `null` | `null` |
| agents only | `{"agents": ["claude-code"], "machines": null}` | `{"agents": ["claude-code"]}` (later rewritten to agent uids by migration 0096) |
| dormant | `{"agents": [], "machines": null}` | `{"agents": []}` |
| named machines, this one among them | `{"agents": A, "machines": [… this id …]}` | `{"agents": A}` |
| named machines, this one not among them | `{"agents": A, "machines": [… other ids …]}` | `{"agents": []}` |

The last two rows are the whole of the migration's argument. A row that named
machines was, *on this machine*, either admitted by that list or dormant because
of it, and the answer it already gave here is the answer it must keep giving:
dropping the key outright would turn "active only on the desktop" into "active
everywhere", which is the one direction that cannot be allowed. The machine id
is read from the `daemon-config.json` cache beside the database — the very value
the running daemon evaluated scope against — and when it cannot be determined
the row takes `agents: []`, dormant, because narrowing is visible and reversible
while widening is silent.

The migration is idempotent: a row with no `machines` key is left untouched, so
a re-run matches nothing. It is one-way and leaves no load-time shim —
`Scope.from_json` accepts the single-axis shape only.

An unknown agent uid is legal and simply never matches, so a resource can be
scoped to an agent that has not been registered here yet.

### Machine descriptor (`machines/<machine_id>.yaml`)

One document per machine. Each machine writes **only its own**, so the documents
occupy disjoint paths and cannot conflict; git merges them trivially. The
registry is whatever `machines/*.yaml` currently holds — a derived view, not a
synced table.

The id is the file name, not a key inside the document (here
`machines/a3f21c9e4b7d2610.yaml`):

```yaml
name: Desktop
os: Darwin 24.6.0
hostname: studio.local
coffer_version: 0.5.0
last_converged_on: 2026-09-13
last_converged_commit: <40-hex commit sha>
key_fingerprint: <12-hex sha256 of the master key>
agents: [claude-code, codex]
```

| Field | Notes |
| --- | --- |
| `machine_id` (the file name) | `sha256("coffer-machine:" + raw)` truncated to 16 hex characters. The raw host identifier — `IOPlatformUUID` on macOS, `/etc/machine-id` on Linux — is a hardware identifier and MUST NOT be written here. When neither is readable, the raw value is a UUID generated once into `~/.coffer/machine-id` (mode `0600`); that one does not survive deleting `~/.coffer`, and the machines page says so |
| `name` | the user's label, defaulting from the hostname. Mutable at any time and at no cost, because nothing keys on it |
| `os`, `hostname`, `coffer_version` | descriptive, for the machines table; `os` is the platform name and release (`Darwin 24.6.0`) |
| `last_converged_on` | a **date**, restamped at most once per calendar day, so an idle machine does not commit a heartbeat every round. The UI says "last converged day", not "last converged at" |
| `last_converged_commit` | this machine's pointer, published so the remote can hand it back. Restamped with `last_converged_on`, so at most once per calendar day — and filled in once if the day's first descriptor carried none. This is what a **returning** machine recovers its base from when its local pointer is gone |
| `key_fingerprint` | the same short hash `GET /sync/key/fingerprint` returns, so the machines table can state that another machine's credentials cannot be decrypted here |
| `agents` | the names of the agents registered on that machine |

The id is cached in `daemon-config.json` and recomputed if lost; the name lives
here, so it syncs. The asymmetry matters: `machine_id` is the descriptor
filename, the curation owner's reference and a table key, and a machine that comes
back under a new identity becomes a ghost — it rejoins as a stranger, its old
descriptor lingers with nobody to update it, and anything that named it stops
meaning this machine.

Applying a diff does **nothing** with `machines/*.yaml` in either direction (see
"Never apply the registry or the manifest"): the registry is read from the tree,
never projected into anything local.

### State areas (`state/<area>/...yaml`)

Module-owned shared state that belongs to the vault rather than to one machine.
Each module implements `SyncedStatePort` and the composition root registers the
providers — the sync slice never imports kind modules. Current areas:

- `mcp-preferences/<server_uid>.yaml` — the DISABLED capabilities per server,
  keyed by the server's uid (enabled is the default; seen-timestamps stay
  machine-local).
- `agent-plugins/<agent>.yaml` — the plugin inventory: which plugins and
  marketplaces each agent has on each machine. An **inventory, not a
  replicator** — applying one writes nothing into any agent's configuration.
- `channel-peers/<channel_uid>/<chat>.yaml` — one channel pairing, keyed by the
  channel's uid: the chat id, the sender id the owner gate checks, the display
  name and the pairing time. Platform identity, all of it, which is why it travels: a channel moves
  between machines now, and one that arrived without its pairings would make
  the owner re-pair from their phone on every rebind. The **active conversation
  pointer is not in the document**, and neither is the agent a thread has stuck
  to — conversations are machine-local and that agent is one this machine has
  installed, so an incoming pairing keeps whatever this machine already held. The file
  name is a sanitised chat id and therefore only an address; the payload
  carries the true ids.
- `settings/internal-engine.yaml` — the internal-engine singleton: `model`, the
  speech-to-text model, the bound on one model call, `curate_owner_machine_id`,
  and an `upkeep` block carrying an `enabled` flag and an `interval_s` for each
  of the three unattended passes (`aggregate`, `distil`, `curate`).
  `auto_curate_enabled` is also written at the top level, because that is where
  every document written so far put curation's switch, and a document that
  carries no `upkeep` block is still read for it. A key the document does not
  carry leaves this machine's value alone — an older machine is not a decision
  (spec [internal-engine](../internal-engine/spec.md) "Leave settings alone for
  keys an incoming document omits").

  ```yaml
  model: <model id>
  model_timeout_s: 180
  transcribe_model: <model id>
  auto_curate_enabled: true
  curate_owner_machine_id: a3f21c9e4b7d2610
  upkeep:
    aggregate: { enabled: true, interval_s: null }
    distil: { enabled: true, interval_s: null }
    curate: { enabled: true, interval_s: null }
  ```

  An `interval_s` of `null` means "the pass's own default", so the default
  stays in the worker that owns the pass and raising it later reaches every
  vault that never chose one. An `upkeep` entry that IS present is
  authoritative in both halves, `interval_s: null` included — that is a
  fleet-wide "back to the default" and must clear an interval this machine
  chose. A pass the document says nothing about is left exactly as this machine
  has it, because an older machine in the fleet is not a decision.

  What the passes are *allowed* to do travels with the model for one reason:
  switching a rewriter off is exactly the decision a second machine must not be
  left out of. `curate_owner_machine_id` is what makes an unattended rewriter
  safe on several machines: a curation pass is a no-op on every machine but the
  owner, and `NULL` means "wherever this is read", which is correct for a
  single-machine vault.

  The area publishes a **decision, not a row** — the general rule every state
  area follows (see "Let each state area define its document's deletion").
  Nothing is written while the singleton holds the defaults — no model, no
  speech-to-text model, no chosen call bound, no curation owner, all three
  passes on — and a machine that has persisted no singleton at all writes
  nothing either. So the tree holds this document exactly while some machine
  holds a non-default choice, a deletion of it means "back to the defaults", and
  honouring that deletion leaves nothing to republish. Had a machine published
  its defaults as a document, a fresh machine — which never persists a default
  it already has — would delete it on every round, and the two would ping-pong
  forever.

Skill delivery bindings (`skill_agent_bindings`) stay machine-local by decision:
delivery is a side-effectful file operation against directories that differ per
machine.

### Credential blob (`credentials/<ref>.enc`)

The Fernet ciphertext for `ref`, base64-encoded as text. No master key, no
plaintext, no metadata beyond the ref, which is the path.

`ref` may be namespaced with slashes (e.g. `channel/seatalk/app-secret`), so the
blob lives at the matching nested path. The full slash ref is rebuilt from the
relative path on the way back.

These blobs never reach a text merge. A Fernet token carries its encryption time
in cleartext, so two ciphertexts for one ref can be ordered **without the key**,
and the fresher encryption wins. That rule applies here and nowhere else.

Ciphertext applied onto a machine that does not hold the matching master key is
stored as-is and reported as `locked_refs` on the round; the affected resources refuse
to spawn rather than failing decryption silently. The key is bootstrapped
out-of-band (`coffer sync key export` / `coffer sync key import`) and never
enters the repository. Those commands move the key **material** over the
loopback API — `POST /sync/key/export` returns `{material}`, `POST
/sync/key/import` accepts it — and each surface does its own file I/O: the CLI
writes and reads the file itself (`0600`), the web UI uses a browser download
and an `<input type="file">`. The daemon opens no caller-named path.

## Path portability

A document written on one machine must apply on another whose home directory
differs.

| Path shape | Written as | Applied as |
| --- | --- | --- |
| Under `$HOME` | `${HOME}/...` | expanded against the applying machine's home |
| Outside `$HOME` | verbatim | verbatim; may not resolve here |

A verbatim path that does not exist here surfaces as a per-path failure — the
path plus the reason in the round report — never as a silent mismatch and never
as a fatal error for the round.

## Machine-local, never in the tree

`~/.coffer/logs/`, `coffer.db`, `daemon-config.json`, PID and
port files, chat history, conversations, the audit log, MCP invocation records,
and the master key file / keychain entry.

Conversations and the audit log are excluded deliberately: they are records of
what happened *on a machine*, and a merged history of two machines' activity
would be a different feature with a different shape.

## Derived files (excluded + regenerated)

A file *regenerated* from source-of-truth files is excluded from the mirror,
because carrying it would let a stale copy overwrite a freshly rebuilt one. The
set is `NON_CONVERGING_TREE_PATHS` in `infrastructure/sync/paths.py`, beside the
tree layout, and both the exporter and the applier consult it.

Today it holds one entry, `skills/coffer-guide/` — Coffer's own generated skill,
which each machine renders from its own build, the knowledge files and its own
reach (see "Withhold derived output in both halves" and "Leave the paths of
withheld derived output inert"). The name is a literal in the sync layer because
import-linter's cross-kind fences keep that layer from reading it off the skill
kind; `backend/tests/contract/test_non_converging_tree_paths.py` pins it to the spelling
the kind uses.

Everything else under `knowledge/` and `skills/` is source of truth, hidden
entries included — today that means each collection's `.inbox/` material, which
converges like the notes beside it. The knowledge layer's catalogue is generated
per call and is not a file, so there is nothing there to exclude.
