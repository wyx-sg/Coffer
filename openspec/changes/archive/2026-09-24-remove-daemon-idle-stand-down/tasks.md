The three groups own disjoint file sets and can run in parallel. Group 2's
codegen reads the contract, which is already updated in this change.

## 1. Backend (`backend/coffer/**`, `backend/tests/**`)

- [x] 1.1 Delete `infrastructure/daemon/activity.py` and the request-bracketing middleware `surfaces/http/activity.py`, and unregister it in `surfaces/http/app.py`
- [x] 1.2 `infrastructure/daemon/entry.py`: delete `_stand_down_when_idle`, the idle-watcher task and its poll interval; the `/mcp` session evictor stays
- [x] 1.3 `infrastructure/daemon/config.py`: delete `read_idle_shutdown_hours`, the writer, the floor and the default; ignore an `idle_shutdown_hours` key on read and remove it on every write, keeping merge semantics for every other key
- [x] 1.4 Delete `surfaces/cli/daemon_idle_cmd.py` and its registration in `surfaces/cli/daemon_cmd.py`
- [x] 1.5 `surfaces/http/daemon_routes.py`, `surfaces/http/daemon_schemas.py`: residency GET/PUT carry `login_service_supported` / `login_service_installed` only; `domain/audit.py`: `daemon_residency_updated` details `{login_service_installed}`
- [x] 1.6 `application/channel/runtime.py` and `surfaces/http/channel_wiring.py`: remove `service_hold` and the channel hold, unless `remove-seatalk-webhook-delivery` has already done so
- [x] 1.7 `infrastructure/daemon/login_service.py`: update comments that justify restart-on-failure by the idle stand-down; behaviour unchanged
- [x] 1.8 Tests: delete `tests/unit/infrastructure/daemon/test_activity.py`; remove the idle cases from `tests/unit/infrastructure/daemon/test_entry.py`, `test_login_service.py`, `test_daemon_config.py`, `tests/integration/surfaces/http/test_daemon_routes_extended.py`, `tests/integration/surfaces/cli/test_daemon_cmd.py`, `test_cli_parity.py`

## 2. Frontend (`frontend/src/**`)

- [x] 2.1 Run frontend codegen against the updated `openspec/specs/daemon/contracts/api.openapi.yaml`; `lib/api/generated/daemon.ts` loses `idle_shutdown_hours`
- [x] 2.2 `pages/settings/DaemonResidencySettings.tsx`: the Start at login switch only; the request body carries `login_service_installed` only
- [x] 2.3 i18n: remove the "Stand down after" / idle-window / Never strings from `i18n/locales/en.json` and `zh.json`
- [x] 2.4 `pages/settings/DaemonResidencySettings.test.tsx`: assert the new steps of `web-ui` "the general tab sets when the daemon runs"

## 3. Docs (`docs/**`, `docs-site/**`)

- [x] 3.1 `docs/architecture.md`: remove the idle clock, holds and watcher; `scripts/check_architecture_doc.py` passes
- [x] 3.2 Amend `docs/decisions/daemon-detect-or-spawn.md`: the daemon is resident until stopped or superseded; the idle stand-down is withdrawn
- [x] 3.3 `docs-site/architecture/{audit,overview,persistence,processes}.md`, `docs-site/guide/{concepts,getting-started}.md`: remove the idle stand-down, `coffer daemon idle` and the Stand down after control

## 4. Specs, contracts, acceptance markers

- [x] 4.1 Deltas for daemon and web-ui
- [x] 4.2 `openspec/specs/daemon/contracts/api.openapi.yaml` and `openspec/specs/daemon/data-model.md`
- [x] 4.3 New scenario needing a test with its `acceptance(spec, scenario)` marker: `daemon` "an idle window left in the daemon config is ignored and dropped" (`tests/unit/infrastructure/daemon/test_daemon_config.py` or `tests/integration/surfaces/cli/test_daemon_cmd.py`)
- [x] 4.4 Removed scenario whose markers must go: `daemon` "a daemon nothing has wanted stands down" — `tests/unit/infrastructure/daemon/test_entry.py`, `test_login_service.py`, `test_activity.py`, `tests/integration/surfaces/http/test_daemon_routes_extended.py`
- [x] 4.5 Kept scenarios whose steps changed, so their tests must assert the new text: `daemon` "the settings page changes residency in one request" (`test_daemon_routes_extended.py`), "the command line changes residency with no daemon running" (`test_daemon_cmd.py`), "the daemon is up before anything asks for it" (`test_login_service.py`); `web-ui` "the general tab sets when the daemon runs" (`DaemonResidencySettings.test.tsx`)
- [x] 4.6 Update every citation of "Stand down after an idle window" (`scripts/check_spec_citations.py` lists them); `python scripts/audit_acceptance.py` passes

## 5. Close

- [ ] 5.1 Run `make verify`
- [ ] 5.2 Archive the change (`npx openspec archive remove-daemon-idle-stand-down --yes`) in the same PR
