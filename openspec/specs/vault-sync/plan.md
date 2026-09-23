# Implementation Plan: Vault Sync

Sync is a **cross-cutting service**, not a resource kind (see
[Vault Sync](../../../docs/decisions/vault-sync.md)). It follows the
retention/credentials pattern across the four layers, and the only user-entered
row it owns is the single `sync_remotes` config row; the convergence pointer is
machine-local state and the machine registry is the working tree itself.

The spec fixes the algorithm; this plan fixes the names and the boundaries.

## Layering

```
domain/sync/          pure value objects + contracts
  backup.py           BackupRemote (the remote's configuration), its URL and
                      branch validators, worktree_conflict, redact
  convergence.py      JoinKind, ConvergeStatus, GuardDirection,
                      PendingConfirmation, ConvergeRun, RunRecord
  diff.py             ChangeStatus, DocChange, DeletionGuard, DiffSummary,
                      area_of, NON_VAULT_AREAS, the two guard thresholds
  errors.py           the SyncError family: SyncBundleTooNew,
                      SyncBundleInvalid, SyncSerializationError,
                      MasterKeyFileInvalid, BackupRemoteInvalid,
                      SyncJoinAmbiguous
  fernet_time.py      encrypted_at, is_fresher — ordering two ciphertexts
                      without the key
  machine.py          derive_machine_id, MachineDescriptor
  manifest.py         Manifest, SCHEMA_VERSION
  models.py           AreaCount, ExportSummary
  portability.py      ${HOME} normalization / expansion (pure)
  serialization.py    deterministic Resource <-> doc projection (pure)

application/sync/
  convergence.py      ConvergeRound — the seven steps
  convergence_backwards.py  BackwardsMixin — reverse_to, and the rollback and
                      rebuild that run a round's applier backwards over it
  convergence_ops.py  the round's helpers that need nothing from the round:
                      is_inapplicable, commit_message, held_run, failed_run,
                      applier_for
  service.py          ConvergeService — the lock, the audit trail, the
                      master-key bootstrap, confirm / reject / rollback
  service_remote.py   RemoteMixin — the remote's configuration half
  service_machines.py MachinesMixin — the registry half
  service_history.py  HistoryMixin — the run-history half
  appliers.py         TreeApplier, ResourceApplier, StateApplier,
                      CredentialApplier
  conflicts.py        ConflictArbiter
  joining.py          JoinResolver, Join
  machines.py         MachineRegistry, MachineView
  exporter.py         SyncExporter — the serializer step 1 calls
  worker.py           ConvergeWorker — the timer, shaped like RetentionWorker
  ports.py            ImportGate, PostImportHook, SyncedStatePort,
                      CredentialSyncPort, MasterKeyPort, BundlePort,
                      ConvergenceStatePort, ConflictResolverPort,
                      VaultApplyPort, SyncRemoteRepoPort
  git_port.py         GitMirrorPort — half of ports.py on its own, so it lives
                      on its own

infrastructure/sync/
  git_mirror.py       GitMirror — the one place that runs git
  bundle.py           Bundle — the tree's layout and its document IO
  tree_mirror.py      _mirror_tree / _converge_files — differential, `protected`
  machine_id.py       resolve, MachineIdentity — the host's stable identifier
  identity.py         resolve_identity, machine_name — the id and the label,
                      resolved once and cached in daemon-config.json
  conflict_resolver.py AgenticConflictResolver — the bounded model pass
  credentials.py      CredentialSyncAdapter — ciphertext dump/load
  paths.py            the mirrored trees

infrastructure/persistence/
  sync_remote_repo.py    the single sync_remotes row, and the sync_runs history
  convergence_state_repo.py  the pointer, the held round and the held paths
                             — machine-local, see below

surfaces/
  http/sync_routes.py       /api/v1/sync/*
  http/sync_schemas.py      the wire shapes those routes declare
  http/sync_wiring.py       the composition root for one round's object graph
  http/sync_contributions.py  what each kind contributes, collected explicitly
  cli/sync_cmd.py           `coffer sync` group
  cli/sync_machine_cmd.py   `coffer sync machine` and `coffer sync key`
  frontend/src/pages/sync/  the top-level Sync page
```

Both splits above are the file-size tier rather than new seams: `ConvergeRound`
is one unit across `convergence.py`, `convergence_backwards.py` and
`convergence_ops.py`, and `ConvergeService` is one unit across `service.py` and
its three mixins.

Six units carry the weight, and each is named for exactly what it does:

- **`ConvergeRound`** (`application/sync/convergence.py`) owns the seven steps
  of FR-035 and nothing else owns any of them. It takes an already-prepared working tree and
  no database, which is what lets the algorithm be tested against a fake mirror.
  Join detection sits in its `_base` step, **not in the adopt command**:
  FR-049 requires it on *any* pointer-less round, so a `remote set` on a machine
  that has forgotten its pointer gets the same treatment as an explicit `adopt`.
- **`ConvergeService`** owns policy: the remote's configuration, the lock, the
  audit trail, the push-credential resolution, the master-key bootstrap, and
  what `confirm` / `reject` / `rollback` mean. The split from `ConvergeRound` is
  the reason either can be read on its own.
- **The four appliers** are the only writers into the live vault, one per bundle
  area (FR-050 … FR-054), each owning a `prefix` and exactly two operations —
  `upsert` and `remove`. Two rather than one "sync this path" because **removal is the
  operation that had to be authorised**; it belongs at the seam, not inside a
  branch. Each raises `CofferError` to report a per-path failure the round
  catches.
- **`JoinResolver`** reads the remote's registry (FR-042) and returns a `Join`. It is a
  separate unit because the decision it makes — new versus returning — is the
  one place where getting it wrong loses data silently.
- **`MachineRegistry`** reads and writes descriptors through `BundlePort`;
  `infrastructure/sync/machine_id.resolve` derives the id. They are separate
  because the id must resolve before any repository exists, and the registry
  cannot exist without one.
- **`ConflictArbiter`** is a working-tree-only unit: it takes paths and a
  mirror, and returns `(resolved_by_agent, unresolved)`. It never sees the
  vault, which is what makes FR-061 structural rather than remembered.

Nothing from the 0.3.0 convergence attempt is resurrected: no tombstone table,
no TTL, no timestamp arbitration, no quarantine table. The diff is the ledger.

### Four of the ports

- **`ConvergenceStatePort`** — the pointer, the retry set and the
  not-applicable set (`pointer` / `set_pointer` / `held_paths` / `hold` /
  `release`), plus the held round (`pending` / `set_pending`). None of it
  travels.
- **`ConflictResolverPort`** — `available()` and `resolve(paths)`. Unavailable
  reports rather than raises, because "stop and hand it to the user's own git"
  is the designed fallback, not an error path.
- **`VaultApplyPort`** — `prefix`, `upsert(path)`, `remove(path)`. The appliers
  implement it structurally.
- **`SyncRemoteRepoPort`** — `get` / `set` / `clear` / `record_run` /
  `last_run` / `list_runs`, so the application layer keeps no infrastructure
  import. `record_run` is one step that writes two things — the remote's
  `last_*` columns and a `sync_runs` row — in one transaction, because a round
  the history missed would make the two disagree about the same moment.

### Where the convergence state lives

`ConvergenceStatePort` is backed by **machine-local SQLite**, in
`infrastructure/persistence/` beside `sync_remote_repo.py` — not by a JSON file
of its own. `coffer.db` is already machine-local and already excluded from the
bundle, so putting the pointer there adds no second store to reason about, no
second thing to write atomically, and no second thing to explain in the "what
never travels" list. It holds one row of convergence state (the pointer, and
the held `PendingConfirmation` with its direction, commit, `remote_tip`,
breaches and paths) and one row per held path with an `applicable` flag that
separates the retry set from the not-applicable set.

### The guard waiver

`PendingConfirmation` carries **`remote_tip`**: the remote tip the hold was
raised against. A confirmed round is **re-derived, not resumed** —
serialization is deterministic, so an unchanged vault against an unchanged
remote yields exactly the diff the user was shown — and `ConvergeRound.run`
waives the deletion guard (FR-066, FR-067) only when `confirmed_tip` equals the
current tip. If
the remote moved in the meantime, the guard runs again and the round is held
afresh.

This is a decision, not an implementation detail. A confirmation is an answer
about a specific set of documents, not a standing permission to delete, and a
"yes" that outlived the diff it was given for is the shape of an accident.
`reject` is the other half: the guard runs before the apply, so the vault was
never touched and rejecting only has to `reset_hard` the tree back to the
pointer.

### One lock

`ConvergeService.lock` is exposed as a property and **shared with the knowledge
tidy worker** (FR-071). Both rewrite vault content, and an export taken half-way through
a rewrite is a torn snapshot that git reads as a deliberate change. That is why
the lock is injectable rather than private.

## API shapes

Under `/api/v1/sync`, all loopback-token guarded. Schema names are the FastAPI
response-model names, and `contracts/api.openapi.yaml` declares the same ones.
The routes are a thin projection of two objects: `ConvergeService` (`run_once`,
`confirm`, `reject`, `rebuild`, `rollback`, `restore`, `runs`,
`key_fingerprint`, `export_key`, `import_key`) and `MachineRegistry` (`list`,
`describe_self`, `retire`).

| Operation | Request | Response | Behind it |
| --- | --- | --- | --- |
| `GET /sync/remote` | — | `SyncRemoteStateOut` | `SyncRemoteRepoPort.get` |
| `PUT /sync/remote` | `SyncRemoteIn` | `SyncRemoteOut` | `SyncRemoteRepoPort.set` |
| `DELETE /sync/remote` | — | `SyncRemoteClearedOut` | `SyncRemoteRepoPort.clear` |
| `POST /sync/run` | — | `RoundOut` | `run_once()` |
| `POST /sync/adopt` | `AdoptIn` (optional) | `RoundOut` | `run_once(join_choice=…)` — there is no separate adopt method, because joining is detected by the absent pointer |
| `GET /sync/status` | — | `SyncStatusOut` | `last_run` + state + registry |
| `GET /sync/runs` | `limit` query | `SyncRunListOut` | `runs(limit)` — every round, newest first |
| `POST /sync/restore` | `RestoreIn` (optional) | `RoundOut` | an earlier revision through the same appliers |
| `POST /sync/confirm` | — | `RoundOut` | `confirm()` |
| `POST /sync/reject` | — | `SyncRemoteClearedOut` | `reject()` |
| `POST /sync/rebuild` | — | `RoundOut` | `rebuild()` |
| `POST /sync/rollback` | — | `RoundOut` | `rollback()` |
| `GET /sync/machines` | — | `MachineListOut` | `MachineRegistry.list` |
| `PATCH /sync/machines/self` | `MachineRenameIn` | `MachineOut` | `describe_self` + rename |
| `DELETE /sync/machines/{machine_id}` | — | `MachineRemovedOut` | `MachineRegistry.retire` |
| `GET /sync/key/fingerprint` | — | `KeyFingerprintOut` | `key_fingerprint()` |
| `POST /sync/key/export` | — | `KeyMaterialOut` | `export_key()` |
| `POST /sync/key/import` | `KeyMaterialIn` | `KeyImportOut` | `import_key()` |

`confirm`, `reject` and `rebuild` get three separate paths rather than one body
field, because they are three separate methods with genuinely different shapes:
confirming re-derives a round and returns one, rebuilding runs a different
round, and rejecting only resets the tree and returns nothing but the fact that
it did. Folding them into one `decision` field would have hidden that.

Four shapes carry the design, and they are worth stating here rather than only
in the yaml:

- **`RoundOut` is `ConvergeRun` projected field for field.** `status`
  discriminates (`ok`, `no_change`, `conflict`, `awaiting_confirmation`,
  `push_failed`, `failed`, `disabled`) and `join` is `new` / `returning` /
  null. `applied` and `published` are both reported, because "what this round
  took" and "what this round gave" are different questions and the publish-side
  guard makes the second one load-bearing. Every round-shaped operation — run,
  adopt, restore, confirm, rebuild, rollback — answers with this one shape, so
  a surface renders one component for all six.
- **`RunRecordOut` widens `RoundOut` rather than standing beside it** — the
  same report plus `id`, `started_at` and `finished_at`. A subtype rather than
  a shape of its own, so the status page and the history table cannot drift
  into describing one round two ways. `SyncRunListOut` is a list of them.
- **`DiffCountsOut` carries the paths, not only the tally.** `added` /
  `modified` / `deleted` is what a history row shows; `changes` is every path
  that side touched with its status, which is what opening the row is for. A
  round reporting `+1 ~1` and nothing further would be refusing the only
  question the row raises.
- **`MachineOut` is `MachineView` flattened** — the descriptor's fields plus
  `is_self` and a nullable `key_matches`, which is `null` when either side has
  published no fingerprint rather than a misleading `false`. Note the field is
  `last_converged_on`, a **date**: it is restamped at most once per calendar
  day, so it means "the last day this machine converged".

`PendingConfirmationOut` deliberately stops short of the domain object it comes
from. `PendingConfirmation` carries `remote_tip` because the waiver is scoped
to it; the wire shape carries `direction`, `breaches`, `paths` and `raised_at`
and **not** the tip, because a caller has no use for a revision it cannot act
on — confirming is "yes, that one", and which tip that was is the service's
business. `GET /sync/status` reports a hold in either direction, because a hold
outlives the request that raised it.

Error codes and their HTTP mappings: `BACKUP_REMOTE_INVALID` (422),
`GIT_MIRROR_FAILED` (502), `SYNC_JOIN_AMBIGUOUS` (409),
`SYNC_NOTHING_PENDING` (409), `SYNC_NOTHING_TO_ROLL_BACK` (409),
`SYNC_CANNOT_RETIRE_SELF` (422), `SYNC_BUNDLE_TOO_NEW` (409),
`SYNC_BUNDLE_INVALID` (422), `SYNC_SERIALIZATION_INVALID` (422),
`MASTER_KEY_FILE_INVALID` (422).

## Key constraints honored

- Every backend file ≤ 400 lines. `ConvergeRound` and `ConvergeService` are the
  two to watch, and both are already split for it — the round across
  `convergence.py`, `convergence_backwards.py` and `convergence_ops.py` with
  `joining.py` and `conflicts.py` beside it, the service across `service.py`
  and three mixins. Each split follows a seam that was already there, so the
  cap never bought an arbitrary boundary.
- `application/` must not import `infrastructure/`: git, the bundle, the
  convergence state, the remote's row and the host id are all injected as ports.
- `domain/sync` stays pure (no sqlalchemy, no fs, no subprocess) — including
  `machine.py`, which hashes but does not read the host.
- `ConflictArbiter` never receives a handle to the vault — the working tree is
  its whole world, which makes FR-061 structural rather than remembered.
- **Network egress is a bounded exception** (constitution 0.6.0): the only
  outbound traffic is `git fetch` / `git push` against the user's own remote,
  from the single subprocess adapter, with the credential resolved for the
  length of one call and redacted from every recorded error — twice, once in
  the adapter and again in the service.
- `response_model` on every route; mypy --strict; importlinter contract for the
  `sync` package (it imports no other kind — kind modules reach it through
  `SyncedStatePort` and `ImportGate`, registered by the composition root).
