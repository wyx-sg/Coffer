## Why

The daemon stands down after an idle window — twelve hours by default — and
every subsystem that has to be reachable at any hour must hold that clock open
to survive it: a channel's inbound connection above all, and an MCP stream an
agent keeps open overnight. A login service already decides when the daemon
starts; the idle window only adds a way for it to be down when a message
arrives, plus a setting, a CLI group, a REST field and a UI control to manage
that. The owner has decided the daemon never stands down on its own.

## What Changes

- **daemon**: "Stand down after an idle window" is removed. The daemon serves
  until it is stopped or superseded by another daemon.
- **daemon**: residency is the login service alone. `GET`/`PUT
  /api/v1/daemon/residency` carry `login_service_supported` and
  `login_service_installed`; `idle_shutdown_hours` leaves both schemas and the
  `daemon_residency_updated` audit details. The `coffer daemon idle` command
  group is removed. `~/.coffer/daemon-config.json` no longer holds an idle
  window: a key an earlier build wrote is ignored on read and dropped by the
  next write.
- **daemon**: a login service restarts the daemon only on an unsuccessful exit;
  the clean exits it leaves alone are `coffer daemon stop`, a quit from the
  desktop shell, and a superseded daemon standing down.
- **web-ui**: the settings card for when the daemon runs has one control, the
  Start at login switch.
- The idle clock, its named holds, the request-tracking middleware that fed it
  and the idle watcher task are deleted.

## Capabilities

### New Capabilities

### Modified Capabilities

- `daemon`
- `web-ui`

## Impact

- Backend: `infrastructure/daemon/activity.py`, the idle watcher in
  `infrastructure/daemon/entry.py`, the request middleware in
  `surfaces/http/activity.py`, `surfaces/cli/daemon_idle_cmd.py`, the idle key in
  `infrastructure/daemon/config.py`, the residency schemas and routes, the
  `daemon_residency_updated` details, the channel runtime's `service_hold`
  callback and its caller, and their tests.
- Contract: `openspec/specs/daemon/contracts/api.openapi.yaml` residency schemas
  lose `idle_shutdown_hours`; the frontend client is regenerated.
- Frontend: `DaemonResidencySettings` keeps the login switch only; en/zh strings.
- Docs: `docs/architecture.md`, the detect-or-spawn ADR, and the docs-site pages
  that describe the idle stand-down.
