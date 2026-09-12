# Implementation Plan: Vault Export and Import

> 中文版: [plan.zh.md](./plan.zh.md)

Export/import is a **cross-cutting service**, not a resource kind (see
[Vault Export and Import](../../docs/decisions/vault-export-import.md)). It follows the
retention/credentials pattern across the four layers, and it owns no persistent
state.

## Layering

```
domain/sync/          pure value objects + contracts
  manifest.py         Manifest, SCHEMA_VERSION
  models.py           ExportResult, ImportResult, ResourceFailure, area counts
  serialization.py    deterministic Resource <-> dict projection (pure)
  paths.py            ${HOME} normalization / expansion (pure)
  errors.py           SyncError family (codes for the error envelope)

application/sync/
  ports.py            BundleLayout, SyncedStatePort protocols
  exporter.py         vault -> bundle (files, resources, state, ciphertext)
  importer.py         bundle -> vault (mirror+reindex, reconcile, ciphertext)
  service.py          SyncService: export / import / key export / key import

infrastructure/sync/
  bundle.py           file mirror + manifest read/write + ciphertext dump/load

surfaces/
  http/sync_routes.py + sync_wiring.py    /api/v1/sync/*
  cli/sync_cmd.py                         `coffer sync` group
```

The backup remote (spec `## Backup`, constitution 0.5.0) adds exactly four
things to that picture, and nothing else:

```
domain/sync/backup.py                    BackupRemote, BackupRun, redact (pure)
application/sync/ports.py                + GitMirrorPort
application/sync/backup_service.py       configure / run_once / restore
application/sync/backup_worker.py        the timer, shaped like RetentionWorker
infrastructure/sync/git_mirror.py        the one place that runs git
infrastructure/persistence/
  sync_remote_repo.py                    the single sync_remotes row
```

No tombstone table, no machine identity, no file watcher, no conflict
arbitration — those belonged to convergence, which is still not built.

## Build order (TDD, each a committable chunk)

1. **Removal migration** — drop `sync_config`, `sync_state`, `machine_identity`
   and `sync_tombstones`, and delete the code that read them. Integration test:
   a vault created on the previous revision upgrades cleanly.
2. **domain/sync** — manifest, deterministic serialization, path normalization,
   result models, errors. Unit tests: serialization determinism (sorted keys,
   excluded fields, round trip), `${HOME}` normalize/expand on both path shapes.
3. **infrastructure/sync bundle** — the file/manifest/ciphertext IO against a
   tmp directory. Integration test: writing and re-reading a bundle.
4. **application/sync exporter + importer** — using a real `ResourceService`,
   the real credential store, and tmp vault dirs. Integration tests: export →
   import round-trip reproduces resources, files, state areas and decryptable
   credentials; a second export of the unchanged vault is byte-identical apart
   from `created_at`; import never deletes a local-only resource; a resource
   that cannot apply here is reported without failing the run.
5. **application/sync service** — orchestrate the two operations plus key
   export/import. Integration test: two tmp vaults simulate machine A and B;
   assert the bundle wins, credentials stay locked without the key, and the
   bundle never contains the master key.
6. **surfaces http + wiring** — routes, schemas, error codes; wire in
   `_lifespan`. No worker to start. Contract test for `/api/v1/sync/*`.
7. **surfaces cli** — `coffer sync export|import` and `coffer sync key
   export|import` over the loopback client. Contract test.
8. **frontend** — Settings → Sync: an export button and an import button over
   the daemon-hosted native directory picker (spec agent-registry FR-042), a result
   summary, and the master-key card — the card itself uses the browser's own
   download and `<input type="file">`, so the key material crosses the API and
   the daemon opens no path. The fleet view and the
   remote/auto-sync/conflict UI are removed.
9. **docs** — architecture.md cross-cutting row, roadmap status, docs-site
   guide + architecture pages, bilingual companions; acceptance markers tie each
   `spec.md` scenario to a test.

## Build order — the backup remote

Each step is a committable chunk with its own tests.

1. **domain/sync/backup.py** — `BackupRemote` with its validation, `BackupRun`
   and `BackupRunStatus`, and `redact`. Unit tests: defaults match the spec,
   invalid interval/url/branch refused, redaction removes every occurrence.
2. **`sync_remotes` table** — model, migration, `SqlAlchemySyncRemoteRepo`. The
   single-row rule is a check constraint (`id = 1`), not a convention.
   Integration test: set/get round-trips every field, setting twice keeps one
   row, a recorded run reads back.
3. **`GitMirrorPort` + `GitMirror`** — init or adopt, stage, commit, push,
   fetch, clone, resolve a revision or a date, detach and return. Integration
   tests run against a real local bare repository, so no network is involved.
   Two of them exist only to pin the security rule: the token never reaches
   `.git/config`, and a failed push's message carries no secret.
4. **`BackupService`** — the run: export into the working tree, commit only
   when the export differs, push, record. Unit tests with a fake mirror cover
   the four outcomes, including that a failed push keeps its commit and the
   next run pushes it without committing again.
5. **`BackupWorker`** — catch-up run on start, then the configured interval; an
   exception inside a run never ends the loop.
6. **HTTP** — `/sync/remote`, `/sync/push`, `/sync/restore`, `/sync/status`,
   each with an explicit response model. A test asserts the remote's payload
   carries only the credential *reference*.
7. **CLI** — `coffer sync remote set|show|clear`, `push`, `restore`, `status`.
   `remote set` prints what a push will contain before it is enabled.
8. **UI** — a backup card in Settings → Sync, shaped like the retention card:
   auto-save, last-run status, and a "back up now" button.

## Key constraints honored

- Every file ≤ 400 lines; split `exporter.py`/`importer.py` if they grow.
- `application/` must not import `infrastructure/`: the bundle IO is injected as
  a `BundleLayout` port.
- `domain/sync` stays pure (no sqlalchemy, no fs).
- New error codes added to the HTTP error envelope `_STATUS` map.
- **No network egress at all** — export and import touch the local filesystem
  only, so the slice needs no outbound-HTTP or git-subprocess exception.
- `response_model` on every route; mypy --strict; importlinter contract for the
  `sync` package (it imports no other kind).
