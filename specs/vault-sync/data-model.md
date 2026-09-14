# Data Model — Vault Sync

> 中文版: [data-model.zh.md](./data-model.zh.md)

Sync persists in three places, and which one holds what is the whole design:

| Where | What | Why there |
| --- | --- | --- |
| SQLite | the one sync remote's configuration | it is user-entered config, like any other |
| a local JSON file | the pointer, the retry set, the not-applicable set | it must be readable before the DB opens and it must **never** travel |
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
| `enabled` | bool | sync is off until the user configures a remote |
| `worktree_path` | str | default `~/.coffer/sync` |
| `last_run_at` | ts? | the most recent round |
| `last_status` | str? | see the vocabulary below |
| `last_error` | str? | redacted of the push credential before it is written |
| `last_commit` | str? | the commit the last round landed on |
| `updated_at` | ts | |

Because `credential_ref` is a reference, the whole row can be read into an API
response or a log line without redaction.

`last_status` gains the round's vocabulary: `ok`, `no_change`, `joined`,
`conflict`, `awaiting_confirmation`, `push_failed`, `error`. The `last_*`
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
resources/<kind>/<name>.yaml   one deterministic file per config resource
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

Current version: **1**. The tree is a new format with its own lineage; neither
the withdrawn git workspace's version (which had reached 3) nor the export
bundle's carries over.

`schema_version` is checked before a round applies anything: a tree newer than
the running build fails closed with `SYNC_TREE_TOO_NEW`, mirroring the DB
`DB_SCHEMA_TOO_NEW` rule. The `created_at` the bundle manifest used to carry is
**gone** — a timestamp restamped every round would make a manifest-only diff the
one thing that always changed, and determinism is what lets a round with nothing
to say produce no commit at all. Applying a diff ignores `manifest.json` in both
directions.

### Resource serialization (`resources/<kind>/<name>.yaml`)

Deterministic projection of a `Resource`:

```yaml
kind: mcp_server
name: confluence
description: "..."
enabled: true
scope:
  agents: [claude-code]
  machines: ["a3f21c9e4b7d2610"]
config: { ... }          # the validated, json-mode config; keys sorted
```

- `created_at` / `updated_at` / the local `id` are **excluded** — machine-local,
  and they would make every round produce a commit.
- Mapping keys are sorted; there is exactly one document per resource, so an
  unchanged vault produces an unchanged tree.
- String values under this machine's home are normalized to `${HOME}/...` and
  expanded against the applying machine's home (see below).

Applying an addition or a modification upserts by `<kind>:<name>` through the
kind-agnostic `ResourceService`, with the kind's import gate run; applying a
deletion deletes the resource, which releases the credentials no remaining
resource cites. After the whole diff is applied, each kind's post-import hook
re-applies its machine-local side effects — native config projections, shims,
skill deliveries — from current state.

### `scope_json` — from a list to two axes

The persisted shape changes, and a migration rewrites every row:

| | before | after |
| --- | --- | --- |
| unrestricted | `null` | `null` |
| agents only | `["claude-code"]` | `{"agents": ["claude-code"], "machines": null}` |
| machines only | — | `{"agents": null, "machines": ["a3f21c9e4b7d2610"]}` |
| both | — | `{"agents": ["claude-code"], "machines": ["a3f21c9e4b7d2610"]}` |
| dormant | `[]` | `{"agents": [], "machines": null}` |

The two axes are `AND`-ed and each `null` means unrestricted, so every existing
row migrates **by addition**: `machines: null` reproduces today's behaviour
exactly. The migration is one-way and leaves no load-time shim — `Scope.from_json`
accepts the object shape only.

The machine axis is keyed by `machine_id`, never by the display name, so
renaming a machine costs nothing. An unknown machine id is legal and simply
never matches, exactly as an unknown agent name already is. A scope editor
builds the machine list from the registry rather than accepting free text, so a
mistyped id cannot silently disable a resource.

### Machine descriptor (`machines/<machine_id>.yaml`)

One document per machine. Each machine writes **only its own**, so the documents
occupy disjoint paths and cannot conflict; git merges them trivially. The
registry is whatever `machines/*.yaml` currently holds — a derived view, not a
synced table.

```yaml
machine_id: a3f21c9e4b7d2610
name: Desktop
os: darwin
hostname: studio.local
coffer_version: 0.5.0
last_converged_at: 2026-09-13
last_converged_commit: <40-hex commit sha>
key_fingerprint: <12-hex sha256 of the master key>
agents: [claude-code, codex]
```

| Field | Notes |
| --- | --- |
| `machine_id` | `sha256("coffer-machine:" + raw)` truncated to 16 hex characters. The raw host identifier — `IOPlatformUUID` on macOS, `/etc/machine-id` on Linux — is a hardware identifier and MUST NOT be written here. When neither is readable, the raw value is a UUID generated once into `~/.coffer/machine-id` (mode `0600`); that one does not survive deleting `~/.coffer`, and the machines page says so |
| `name` | the user's label, defaulting from the hostname. Mutable at any time and at no cost, because nothing keys on it |
| `os`, `hostname`, `coffer_version` | descriptive, for the machines table |
| `last_converged_at` | a **date**, restamped at most once per calendar day, so an idle machine does not commit a heartbeat every round. The UI says "last converged day", not "last converged at" |
| `last_converged_commit` | this machine's pointer, published so the remote can hand it back. Restamped every round. This is what a **returning** machine recovers its base from when its local pointer is gone |
| `key_fingerprint` | the same short hash `GET /sync/key/fingerprint` returns, so the machines table can state that another machine's credentials cannot be decrypted here |
| `agents` | the names of the agents registered on that machine |

The id is cached in `daemon-config.json` and recomputed if lost; the name lives
here, so it syncs. The asymmetry matters: `machine_id` is the descriptor
filename, a `scope.machines` reference and a table key, and a machine that comes
back under a new identity becomes a ghost — everything scoped to the old one
silently stops.

Applying a diff does **nothing** with `machines/*.yaml` in either direction: the
registry is read from the tree, never projected into anything local.

### State areas (`state/<area>/...yaml`)

Module-owned shared state that belongs to the vault rather than to one machine.
Each module implements `SyncedStatePort` and the composition root registers the
providers — the sync slice never imports kind modules. Current areas:

- `channel-peers/<channel>/<chat>.yaml` — pairing identity (chat_id, sender_id,
  display name, preferred agent, paired_at; the machine-local
  `active_conversation_id` never travels). A document referencing a channel not
  present here is reported as a per-path failure and joins the retry set.
- `mcp-preferences/<server>.yaml` — the DISABLED capabilities per server
  (enabled is the default; seen-timestamps stay machine-local).
- `agent-plugins/<agent>.yaml` — the plugin inventory: which plugins and
  marketplaces each agent has on each machine. An **inventory, not a
  replicator** — applying one writes nothing into any agent's configuration.
- `settings/internal-engine.yaml` — the internal-engine singleton: `model`,
  `auto_tidy_enabled`, and now `tidy_owner_machine_id`. The owner field is what
  makes an unattended rewriter safe on several machines: a tidy pass is a no-op
  on every machine but the owner. The document is exported only once this
  machine has persisted the singleton locally, so a fresh machine never
  publishes its defaults over the fleet's configured values.

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
stored as-is and reported as `credentials_locked`; the affected resources refuse
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

The exclusion set is **empty today**, and that is worth stating rather than
leaving implicit: everything under `knowledge/` and `skills/` is source of
truth, hidden entries included — a collection's `.raw/` originals and the
revisions a tidy pass moved into `.history/` are as much the other machine's
business as the notes themselves. The knowledge layer's catalogue is generated
per call and is not a file, so there is nothing there to exclude.

The rule stands for when one appears: a file *regenerated* from source-of-truth
files is excluded from the mirror, because carrying it would let a stale copy
overwrite a freshly rebuilt one. The set lives in `infrastructure/sync/`
alongside the tree layout.
