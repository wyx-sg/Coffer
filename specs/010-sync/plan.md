# Spec 010 — Implementation Plan

> 中文版: [plan.zh.md](./plan.zh.md)

Sync is a **cross-cutting service**, not a resource kind (see
[ADR-016](../../docs/decisions/ADR-016-multi-machine-sync.md)). It follows the
retention/credentials pattern across the four layers.

## Layering

```
domain/sync/          pure value objects + contracts
  manifest.py         Manifest, SCHEMA_VERSION
  models.py           SyncConfig, SyncState, SyncStatus enum, ConflictInfo
  serialization.py    deterministic Resource <-> dict projection (pure)
  errors.py           SyncError family (codes for the error envelope)

application/sync/
  ports.py            GitPort, ManifestStore, WorkspaceLayout protocols
  exporter.py         vault -> workspace (files, resources, ciphertext)
  importer.py         workspace -> vault (mirror+reindex, reconcile, ciphertext)
  service.py          SyncService: run/status/config/resolve/key orchestration
  worker.py           SyncWorker: debounced + interval auto-sync loop
  config_service.py   SyncConfigService over the sync_config/sync_state rows

infrastructure/sync/
  git_repo.py         GitPort impl over the `git` subprocess (sole net egress)
  workspace.py        file mirror + manifest read/write + ciphertext dump/load
  persistence.py      SyncConfigModel, SyncStateModel + repos

surfaces/
  http/sync_routes.py + sync_wiring.py    /api/v1/sync/*
  cli/sync_cmd.py                         `coffer sync` group
```

## Build order (TDD, each a committable chunk)

1. **domain/sync** — models, manifest, deterministic serialization, errors.
   Unit tests: serialization determinism (sorted keys, excluded fields, round
   trip), status transitions.
2. **infrastructure/sync persistence** — config/state tables + repos + migration
   `0017`. Integration test: round-trip rows.
3. **infrastructure/sync git_repo + workspace** — git subprocess adapter and the
   file/manifest/ciphertext IO. Integration test against a local **bare** repo
   as `origin` (real git).
4. **application/sync exporter + importer** — using a real `ResourceService` +
   real credential store + tmp vault dirs. Integration test: export → import
   round-trip reproduces resources, files, and decryptable credentials.
5. **application/sync service + config_service** — orchestrate a run, status,
   resolve, key export/import. Integration test: two tmp vaults + one bare repo
   simulate machine A and B; assert convergence, locked-credentials, conflict
   stop/resolve, and that the workspace never contains the master key.
6. **surfaces http + wiring** — routes, schemas, error codes; wire in `_lifespan`
   and start `SyncWorker` (gated on `auto`). Contract test for `/api/v1/sync/*`.
7. **surfaces cli** — `coffer sync` group over the loopback client. Contract test.
8. **frontend** — Sync settings panel (config, status, run, resolve) on the
   existing API/query-key conventions.
9. **docs** — architecture.md cross-cutting row, README feature line, bilingual
   companions; acceptance markers tie each `spec.md` scenario to a test.

## Key constraints honored

- Every file ≤ 400 lines; split `service.py`/`importer.py` if they grow.
- `application/` must not import `infrastructure/`: git/workspace/persistence are
  injected as `GitPort` / `WorkspaceLayout` / repo protocols.
- `domain/sync` stays pure (no git, no sqlalchemy, no fs).
- New error codes added to the HTTP error envelope `_STATUS` map.
- Outbound git uses the user's ambient credentials via subprocess, not the
  Coffer HTTP client; no new loopback-binding exception.
- `response_model` on every route; mypy --strict; importlinter contract for the
  `sync` package (it imports no other kind).
