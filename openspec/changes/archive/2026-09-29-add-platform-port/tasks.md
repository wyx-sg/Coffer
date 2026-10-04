## 1. Port and package

- [x] 1.1 `PlatformPort` and `PrivilegedPaths` in `application/platform_port.py`
- [x] 1.2 `infrastructure/platform/` — `host`, `paths`, `desktop`, `links`, `process`, `identity`, `HostPlatform`
- [x] 1.3 Add both to the kind-agnostic import-linter fence

## 2. Call sites

- [x] 2.1 `agent/service.py`, `agent/sync_reconcile.py`: privileged-path rules from the port
- [x] 2.2 `fs/open_service.py`, `fs/pick_service.py`, `fs/editor_service.py`: argv and editor detection from the port
- [x] 2.3 `skill/lifecycle_ops.py`, `skill/binding_ops.py`: `infer_link_mode` through `SyncEnginePort`
- [x] 2.4 `sync/machines.py`: OS label from the port
- [x] 2.5 `skill/sync_engine.py`, `daemon/spawn.py`, `daemon/login_service.py`, `sync/machine_id.py`: call the platform package
- [x] 2.6 Build `HostPlatform` in the lifespan and pass it through kind wiring, background workers / sync wiring, and the fs route dependencies

## 3. Gate and docs

- [x] 3.1 `scripts/check_platform_calls.py`, in `make lint`
- [x] 3.2 Gate tests and per-OS package tests; existing tests follow the moved code
- [x] 3.3 `docs-site/architecture/platform.md`, nav and index; layering tree and gate table; testing gate list; `.agents/stack.md`, `.agents/harness.md`
- [x] 3.4 `make verify`
