## Why

Coffer is released for macOS only, but its foundation must not assume macOS. OS checks (`sys.platform`, `platform.system()`) were spread over ten modules, six of them in the application layer, so porting would mean finding every one and a missed check would silently do the macOS thing. import-linter cannot catch this: the check is an attribute read, not an import.

## What Changes

- New `backend/coffer/infrastructure/platform/` package, the only code that asks which OS Coffer runs on: host identity, privileged-path rules, desktop file-action argv, editor detection, directory links (symlink / junction / copy), process spawn flags and the launchd check, and the OS-kept machine id.
- New `PlatformPort` in `application/platform_port.py`, implemented by `HostPlatform`, built once in the composition root and passed to `AgentService`, `AgentImportGate`, `MachineRegistry` and the three `fs` services. `SyncEnginePort` gains `infer_link_mode`.
- Every existing OS check moves behind the port or into the package; `application/` and `domain/` contain none.
- New AST gate `scripts/check_platform_calls.py` in `make lint`, failing on an OS check outside the package.
- Docs: a new architecture page (Platform port), the layering tree and gate table, the testing gate list, `.agents/stack.md` and `.agents/harness.md`.

## Capabilities

### New Capabilities

### Modified Capabilities

None: an architecture-only refactor. macOS behaviour is unchanged, and no requirement, endpoint or schema changes.

## Impact

- Backend: `application/{agent/service,agent/sync_reconcile,fs/*,skill/{ports,lifecycle_ops,binding_ops},sync/machines}.py`, `infrastructure/{skill/sync_engine,daemon/spawn,daemon/login_service,sync/machine_id}.py`, the composition root under `surfaces/http/`.
- Import contracts: the new port and package join the kind-agnostic fence.
- Tests: per-OS unit tests for the package, fake-port unit tests for the `fs` services, gate tests; existing tests follow the moved functions.
