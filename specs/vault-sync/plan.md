# Implementation Plan: Vault Sync

> 中文版: [plan.zh.md](./plan.zh.md)

Sync is a **cross-cutting service**, not a resource kind (see
[Vault Sync](../../docs/decisions/vault-sync.md)). It follows the
retention/credentials pattern across the four layers, and the only user-entered
row it owns is the single `sync_remotes` config row; the convergence pointer is
machine-local state and the machine registry is the working tree itself.

The spec fixes the algorithm; this plan fixes the names, the boundaries and the
order.

**Nothing is renamed.** `bundle.py` stays `bundle.py`, `git_mirror.py` stays
`git_mirror.py`, `backup.py` stays `backup.py`. Every one of them changes
behaviour substantially, and none of that is helped by churning the docstring
reference in every file that imports them.

## Layering

```
domain/sync/          pure value objects + contracts
  convergence.py      JoinKind, ConvergeStatus, GuardDirection,
                      PendingConfirmation, ConvergeRun                    (new)
  diff.py             ChangeStatus, DocChange, DeletionGuard, DiffSummary,
                      area_of, NON_VAULT_AREAS                            (new)
  machine.py          derive_machine_id, MachineDescriptor                (new)
  fernet_time.py      encrypted_at, is_fresher                        (restored)
  errors.py           the SyncError family, + SyncJoinAmbiguous
  backup.py           BackupRemote (the remote's configuration)
  models.py           AreaCount, ExportSummary
  serialization.py    deterministic Resource <-> doc projection (pure)
  portability.py      ${HOME} normalization / expansion (pure)
  manifest.py         Manifest, SCHEMA_VERSION

application/sync/
  convergence.py      ConvergeRound — the seven steps, plus reverse_to    (new)
  service.py          ConvergeService — remote, lock, audit, key bootstrap (new)
  appliers.py         TreeApplier, ResourceApplier, StateApplier,
                      CredentialApplier                                   (new)
  conflicts.py        ConflictArbiter                                     (new)
  joining.py          JoinResolver, Join                                  (new)
  machines.py         MachineRegistry, MachineView                        (new)
  worker.py           ConvergeWorker — the timer, shaped like RetentionWorker
  exporter.py         SyncExporter — the serializer a round calls at step 1
  ports.py            + ConvergenceStatePort, ConflictResolverPort,
                      VaultApplyPort, SyncRemoteRepoPort

infrastructure/sync/
  git_mirror.py       GitMirror — the one place that runs git
  bundle.py           Bundle — the tree's layout and its document IO
  tree_mirror.py      _mirror_tree / _converge_files — differential, `protected`
  machine_id.py       resolve, MachineIdentity                            (new)
  credentials.py      ciphertext dump/load
  paths.py            the mirrored trees

infrastructure/persistence/
  sync_remote_repo.py the single sync_remotes row
  (+ the ConvergenceStatePort adapter — machine-local, see below)

surfaces/
  http/sync_routes.py + sync_wiring.py    /api/v1/sync/*
  cli/sync_cmd.py                         `coffer sync` group
  frontend/src/pages/sync/                the top-level Sync page
```

Six units carry the weight, and each is named for exactly what it does:

- **`ConvergeRound`** (`application/sync/convergence.py`) owns steps 0–6 and
  nothing else owns any of them. It takes an already-prepared working tree and
  no database, which is what lets the algorithm be tested against a fake mirror.
  Join detection sits in its `_base` step, **not in the adopt command**: the
  spec requires it on *any* pointer-less round, so a `remote set` on a machine
  that has forgotten its pointer gets the same treatment as an explicit `adopt`.
- **`ConvergeService`** owns policy: the remote's configuration, the lock, the
  audit trail, the push-credential resolution, the master-key bootstrap, and
  what `confirm` / `reject` / `rollback` mean. The split from `ConvergeRound` is
  the reason either can be read on its own.
- **The four appliers** are the only writers into the live vault, one per bundle
  area, each owning a `prefix` and exactly two operations — `upsert` and
  `remove`. Two rather than one "sync this path" because **removal is the
  operation that had to be authorised**; it belongs at the seam, not inside a
  branch. Each raises `CofferError` to report a per-path failure the round
  catches.
- **`JoinResolver`** reads the remote's registry and returns a `Join`. It is a
  separate unit because the decision it makes — new versus returning — is the
  one place where getting it wrong loses data silently.
- **`MachineRegistry`** reads and writes descriptors through `BundlePort`;
  `infrastructure/sync/machine_id.resolve` derives the id. They are separate
  because the id must resolve before any repository exists, and the registry
  cannot exist without one.
- **`ConflictArbiter`** is a working-tree-only unit: it takes paths and a
  mirror, and returns `(resolved_by_agent, unresolved)`. It never sees the
  vault, which is what makes the spec's rule structural rather than remembered.

## Rewritten, deleted, kept

| Existing unit | Fate |
| --- | --- |
| `domain/sync/backup.py` | **kept** — `BackupRemote` is the remote's configuration and its fields are unchanged. `record_run` now takes a `ConvergeRun` |
| `domain/sync/models.py` | **trimmed** — `ImportSummary` goes with the importer; `AreaCount` and `ExportSummary` stay, because the exporter still produces them |
| `domain/sync/errors.py` | **extended** — gains `SyncJoinAmbiguous`; the bundle and master-key errors stay, because the bundle layout is still what the working tree holds |
| `domain/sync/serialization.py` | **kept**, carrying the two-axis `scope` |
| `domain/sync/portability.py`, `manifest.py` | **kept** unchanged |
| `application/sync/exporter.py` | **kept** — `SyncExporter` is the serializer step 1 calls. What changed is underneath it: `Bundle` now converges differentially instead of clearing |
| `application/sync/importer.py` | **deleted** — a bundle-wins whole-tree import is precisely the operation this spec removes; `appliers.py` replaces it |
| `application/sync/backup_service.py` | **deleted** — `ConvergeService` + `ConvergeRound` replace it |
| `application/sync/backup_worker.py` | **deleted** — `worker.py`'s `ConvergeWorker` replaces it, same shape |
| `application/sync/ports.py` | **extended** — four new ports (below), twelve additions to `GitMirrorPort`, and the `machines/` methods on `BundlePort`. `SyncedStatePort` gains `delete_docs`; `CredentialSyncPort`, `MasterKeyPort`, `ImportGate`, `PostImportHook` unchanged |
| `infrastructure/sync/bundle.py` | **rewritten in place** — `open_for_write` clears nothing; every area converges differentially; a `held_paths` callback names what the export must preserve; `write_machine_descriptor` / `read_machine_descriptors` / `delete_machine_descriptor` arrive |
| `infrastructure/sync/git_mirror.py` | **extended in place** — the askpass/token handling is untouched; `merge`, `commit_merge`, `abort_merge`, `take_side`, `diff_paths`, `file_count`, `reset_hard`, `tag`, `tags`, `delete_tag`, `read_file`, `read_worktree` are added, plus the `EMPTY_TREE` constant |
| `infrastructure/sync/tree_mirror.py` | **extended** — `_mirror_tree` and `_converge_files` take `protected`, the destination-relative paths that survive a convergence because this vault has not absorbed them |
| `infrastructure/sync/credentials.py`, `paths.py` | **kept** |
| `infrastructure/persistence/sync_remote_repo.py` | **kept** — same single row, new `last_status` vocabulary |
| `frontend/.../settings/SyncBundleCard.tsx` | **deleted** with export/import |
| `frontend/.../settings/SyncBackupCard.tsx` | **rewritten** into the Sync page's Status tab |
| `frontend/.../settings/SyncMasterKeyCard.tsx` | **kept**, moved onto the Status tab |

Nothing from the 0.3.0 convergence attempt is resurrected: no tombstone table,
no TTL, no timestamp arbitration, no quarantine table. The diff is the ledger.

### The four new ports

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
  `last_run`, so the application layer keeps no infrastructure import.

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
waives the deletion guard only when `confirmed_tip` equals the current tip. If
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
tidy worker**. Both rewrite vault content, and an export taken half-way through
a rewrite is a torn snapshot that git reads as a deliberate change. That is why
the lock is injectable rather than private.

## Build order (TDD, each a committable chunk)

1. **Scope's machine axis** — `domain/scope.py` becomes the two-axis `Scope`
   value object with `excluded_by` naming the axis; `mcp_server` and `skill`
   carry it, the gateway and the supervisor pass `machine=` alongside `agent=`;
   `coffer scope set` gains `--machines` / `--no-machines` and
   `PUT /resources/{kind}/{name}/scope` takes the object shape. Migration `0069`
   rewrites every `scope_json` by **addition** — `["claude-code"]` becomes
   `{"agents": ["claude-code"], "machines": null}`, `NULL` stays `NULL` — and
   inlines the shape rather than importing the domain, so the revision means the
   same thing forever. No load-time shim reads the old shape afterwards.
2. **Machine identity** — `derive_machine_id` (pure), `machine_id.resolve` (the
   three sources and their order), `MachineIdentity` carrying `derived`. Unit
   tests: the raw host identifier never appears in the output; the same raw id
   hashes stably; the fallback file is written `0600` and never rewritten,
   because regenerating it would split this machine's identity in two.
3. **domain/sync value objects** — `convergence.py`, `diff.py`, `machine.py`,
   `fernet_time.py`. Unit tests: `area_of` maps every row of the spec's apply
   table and `NON_VAULT_AREAS` excludes `machines` and `manifest`;
   `DeletionGuard.breached_areas` fires above the share **or** the floor, treats
   an area absent from `totals` as wholly at risk, and returns nothing for a
   diff with no deletions; `MachineDescriptor.from_doc` tolerates fields a newer
   build wrote; `is_fresher` orders two tokens without a key and answers False
   on a tie or an unparseable header.
4. **The convergence-state adapter** — the SQLite table behind
   `ConvergenceStatePort`. Integration tests: the pointer, the two held sets and
   a `PendingConfirmation` round-trip; `hold`/`release` move a path between the
   sets; `set_pending(None)` clears.
5. **`Bundle` differential writes** — `open_for_write` clears nothing,
   `_converge_files` and `_mirror_tree` honour `protected`, and the machine
   descriptor methods land. Integration tests: an unchanged vault produces an
   unchanged tree; a deleted document is removed; a **held** path is never
   removed; an unchanged descriptor is not rewritten, which is what stops an
   idle machine committing a heartbeat.
6. **`GitMirror`'s new commands** — merge with conflict list, `commit_merge`,
   `abort_merge`, `take_side`, `diff_paths`, `file_count`, tags, `read_file`,
   `read_worktree`, `reset_hard`, `EMPTY_TREE`. Integration tests run against a
   real local bare repository, so no network is involved. Three pin the security
   rules the backup remote already had: the token never reaches `.git/config`,
   never appears in an argument vector, and a failed push's message carries no
   secret. One pins `core.quotepath=false`, because a conflicted file with a
   non-ASCII name came back C-quoted once already and crashed the resolver into
   a retry loop.
7. **The appliers** — every row of the apply table against a real
   `ResourceService`, the real credential store and tmp vault dirs. Integration
   tests: an addition registers and runs the kind's import gate; a deletion
   removes the resource and releases the credentials nothing else cites; a
   deletion of something already gone here is agreement, not a failure;
   `TreeApplier` leaves no empty collection directory behind;
   `CredentialApplier` refuses a blob older than the one it holds even outside a
   merge conflict.
8. **`ConflictArbiter`** — the credential rule first, then the bounded agent
   pass. Unit tests with a fake resolver: a surviving conflict marker is
   rejected, an unparseable resource or state document is rejected, a
   credential conflict where neither header orders the two sides is left
   unsettled rather than guessed, and a deletion-versus-edit on a credential
   falls through to the next layer. With no model configured, nothing is
   resolved and everything is reported.
9. **`JoinResolver` + `MachineRegistry`** — the join decision and the registry.
   Integration tests: an absent descriptor joins as `NEW` from `EMPTY_TREE`; a
   present one with a reachable commit joins as `RETURNING` from that commit; a
   present one whose commit is gone from the history raises
   `SyncJoinAmbiguous` rather than guessing, and `join_choice="keep-local"` is
   the explicit answer; a descriptor this build cannot parse still proves the
   machine has been here. Registry tests: two machines' descriptors merge with
   no conflict; `publish_self` restamps `last_converged_on` at most once per
   calendar day; `retire` removes the descriptor **and** strips the id from
   every `scope.machines` in the same change, and refuses to retire self.
10. **`ConvergeRound`** — the seven steps. Unit tests with fakes cover step
    order and each `ConvergeStatus`; integration tests use two tmp vaults and
    one bare repository as machines A and B and replay the spec's scenarios:
    union on a new join, recovered base on a returning join, a stale machine not
    resurrecting a deletion, a clean hunk merge, an unresolved conflict leaving
    the vault untouched and the pointer unmoved, the apply-side guard holding a
    deletion, the **publish-side** guard holding a wiped vault's deletions, a
    waiver honoured for the recorded tip and refused after the remote moves,
    `reverse_to` landing on the pre-apply snapshot, and a drifted HEAD being
    reset to the pointer before step 1. One more pins the rule that makes
    "an unchanged vault makes no commit" true: a staged diff confined to
    `manifest.json` is a **restamp, not a change** — `staged_paths` and
    `discard_staged` exist for exactly that, and `_serialize_and_commit` must
    consult them before it commits.
11. **`ConvergeService` + `ConvergeWorker`** — policy and the timer.
    `run_once` never raises for anything the user can be told about, so the
    loop has no judgement to make; an exception inside a round never ends it.
    Tests: a disabled remote returns `DISABLED` without touching git; a held
    round returns immediately on the next tick; `confirm` re-derives with the
    recorded tip; `reject` resets the tree and leaves the vault alone;
    `rollback` diffs from the pointer to the newest snapshot and applies that,
    and pushes nothing. The tidy setting gains its owner machine in
    `state/settings/internal-engine.yaml` here, and a pass is a no-op off-owner
    and skipped while a conflict or a hold is outstanding.
12. **HTTP + wiring** — the operations below, each with an explicit response
    model; `ConvergeWorker` started and stopped in `_lifespan`. Contract test
    against `contracts/api.openapi.yaml`. A test asserts the remote's payload
    carries only the credential *reference*.
13. **CLI** — `coffer sync remote set|show|clear`, `adopt`, `now`, `status`,
    `restore`, `confirm`, `reject`, `rollback`, `machines`,
    `machine rename|remove`, `key export|import`, over the loopback client.
    `adopt` takes the same remote flags as `remote set`, since it configures
    one, and prints what it found — which kind of join, when this machine last
    converged — before it proceeds.
14. **Frontend** — a top-level **Sync** page with a **Status** tab (remote form,
    last and next round, what recent rounds changed, a run button, the
    master-key card) and a **Machines** tab (the registry table, with the local
    machine marked, a fingerprint mismatch stated in words, and a warning where
    the id came from the fallback file rather than the host). Conflicts and
    holds render as a banner on Status. The scope editor gains a machine
    pick-list built from the registry — never a free-text id — and says which
    axis made a resource dormant here.
15. **Docs** — architecture.md cross-cutting row, roadmap status, docs-site
    guide and architecture pages, bilingual companions; acceptance markers tie
    each `spec.md` scenario to a test.

## API shapes

Under `/api/v1/sync`, all loopback-token guarded. Schema names are the FastAPI
response-model names, because `make verify-contract` checks the two against
each other. The routes are a thin projection of two objects: `ConvergeService`
(`run_once`, `confirm`, `reject`, `rollback`, `key_fingerprint`, `export_key`,
`import_key`) and `MachineRegistry` (`list`, `describe_self`, `retire`).

| Operation | Request | Response | Behind it |
| --- | --- | --- | --- |
| `GET /sync/remote` | — | `SyncRemoteStateOut` | `SyncRemoteRepoPort.get` |
| `PUT /sync/remote` | `SyncRemoteIn` | `SyncRemoteOut` | `SyncRemoteRepoPort.set` |
| `DELETE /sync/remote` | — | `SyncRemoteClearedOut` | `SyncRemoteRepoPort.clear` |
| `POST /sync/run` | `RunIn` | `ConvergeRunOut` | `run_once(join_choice=…)` |
| `POST /sync/adopt` | `AdoptIn` | `ConvergeRunOut` | `set` then `run_once` |
| `GET /sync/status` | — | `SyncStatusOut` | `last_run` + state + registry |
| `POST /sync/restore` | `RestoreIn` | `ConvergeRunOut` | an earlier revision through the same appliers |
| `POST /sync/confirm` | — | `ConvergeRunOut` | `confirm()` |
| `POST /sync/reject` | — | `SyncRejectedOut` | `reject()` |
| `POST /sync/rollback` | — | `ConvergeRunOut` | `rollback()` |
| `GET /sync/machines` | — | `MachineListOut` | `MachineRegistry.list` |
| `PATCH /sync/machines/self` | `MachineRenameIn` | `MachineOut` | `describe_self` + rename |
| `DELETE /sync/machines/{id}` | — | `MachineRetiredOut` | `MachineRegistry.retire` |
| `GET /sync/key/fingerprint` | — | `KeyFingerprintOut` | `key_fingerprint()` |
| `POST /sync/key/export` | `EmptyIn` | `KeyMaterialOut` | `export_key()` |
| `POST /sync/key/import` | `KeyMaterialIn` | `KeyImportOut` | `import_key()` |

`confirm` and `reject` get separate paths because they are separate methods
with genuinely different shapes: confirming re-runs a round and returns one,
while rejecting only resets the tree and returns nothing but the fact that it
did. Folding them into one body field would have hidden that.

Three shapes carry the design, and they are worth stating here rather than only
in the yaml:

- **`ConvergeRunOut` is `ConvergeRun`, field for field.** `status`
  discriminates (`ok`, `no_change`, `conflict`, `awaiting_confirmation`,
  `push_failed`, `failed`, `disabled`) and `join` is `new` / `returning` /
  absent. `applied` and `published` are both reported, because "what this round
  took" and "what this round gave" are different questions and the publish-side
  guard makes the second one load-bearing.
- **`PendingConfirmationOut` names its direction and its tip.** `direction` is
  `apply` or `publish`; `breaches` is `(area, deleted, total)` per breached
  area; `remote_tip` is what the waiver is scoped to. `GET /sync/status`
  reports a hold in either direction, because a hold outlives the request that
  raised it.
- **`MachineOut` is `MachineView` flattened** — the descriptor's fields plus
  `is_self` and a nullable `key_matches`, which is `null` when either side has
  published no fingerprint rather than a misleading `false`. Note the field is
  `last_converged_on`, a **date**: it is restamped at most once per calendar
  day, so it means "the last day this machine converged".

Error codes and their HTTP mappings: `BACKUP_REMOTE_INVALID` (422),
`SYNC_JOIN_AMBIGUOUS` (409), `SYNC_NOTHING_PENDING` (409),
`SYNC_NOTHING_TO_ROLL_BACK` (409), `SYNC_CANNOT_RETIRE_SELF` (422),
`SYNC_BUNDLE_TOO_NEW` (409), `SYNC_BUNDLE_INVALID` (422),
`SYNC_SERIALIZATION_INVALID` (422), `SYNC_APPLIER_MISSING` (422),
`MASTER_KEY_FILE_INVALID` (422).

## Key constraints honored

- Every file ≤ 400 lines; `application/sync/convergence.py` is the one to watch,
  and `joining.py` and `conflicts.py` are already split out of it.
- `application/` must not import `infrastructure/`: git, the bundle, the
  convergence state, the remote's row and the host id are all injected as ports.
- `domain/sync` stays pure (no sqlalchemy, no fs, no subprocess) — including
  `machine.py`, which hashes but does not read the host.
- `ConflictArbiter` never receives a handle to the vault — the working tree is
  its whole world, which makes the spec's rule structural rather than
  remembered.
- **Network egress is a bounded exception** (constitution 0.6.0): the only
  outbound traffic is `git fetch` / `git push` against the user's own remote,
  from the single subprocess adapter, with the credential resolved for the
  length of one call and redacted from every recorded error — twice, once in
  the adapter and again in the service.
- `response_model` on every route; mypy --strict; importlinter contract for the
  `sync` package (it imports no other kind — kind modules reach it through
  `SyncedStatePort` and `ImportGate`, registered by the composition root).
