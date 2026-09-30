## Why

The final design of Settings (canvas ⑥ System, boards 6.2.07–6.2.19) shows facts and confirmations the
code did not have: the Daemon tab's status line reads "Up 3 days · pid 51233 · 2 agents connected"
instead of a table of version, channel and executable; About shows the build's commit and the data
folder, and no release channel; the sidebar footer carries the running version as `v1.0.0`; and
shortening a retention window says how many records it deletes before anything is saved.

## What Changes

- `GET /api/v1/daemon/status` also answers the daemon's pid, the commit a release build was stamped
  with (`null` in a build from source), Coffer's data folder (written `~/…` under the home folder) and
  how many agents carry Coffer's connection. `scripts/stamp_channel.py` takes `--commit`, and the
  release workflow passes the commit being built.
- Settings › Daemon: the status card is the state and address plus one line (uptime, pid, connected
  agents). Port refusals read "… Pick another port." and "Use a port from 1024 to 65535.", with Save
  disabled until the value is edited; the pending-restart notice is the design's amber strip.
- Settings › About: the head line is the logo, "Version <v>" and Copy diagnostics; Details carries the
  version with its commit, license, source and the data folder. The channel stays in the diagnostics.
- The sidebar footer shows the running version as `v<version>` beside the daemon state.
- Settings › Data › History: a shortening asks "Keep MCP calls for 7 days?" with the number of records
  the next cleanup deletes and the count now and after, from a new read
  `GET /api/v1/retention/policies/{table}/preview?days=<n>`; a refused save names the window still in
  place and offers Try again; a muted line names `coffer config` for the other retention settings;
  the cache confirmation uses the design's words.
- The in-flight change `revise-web-ui-ia` carries the page requirements (footer, Daemon tab, About,
  Data tab, status probe); their text is updated there.

## Capabilities

### New Capabilities

### Modified Capabilities

- `resource-framework`: "Prune each registered log table on its own retention period" gains the
  preview read.

## Impact

- Backend: `surfaces/http/daemon_routes.py` + `daemon_schemas.py`, `surfaces/http/agent_dependencies.py`,
  `build_channel.py`, `scripts/stamp_channel.py`, `.github/workflows/release.yml`, retention service,
  repo and route.
- Frontend: Settings Daemon / About / Data components, the sidebar footer, `lib/version.ts`,
  `useRetentionPreview`, en and zh strings.
- Contracts: daemon and resource-framework regenerated.
