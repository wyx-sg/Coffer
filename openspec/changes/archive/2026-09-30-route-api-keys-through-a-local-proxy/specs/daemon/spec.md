## ADDED Requirements

### Requirement: Supervise the model proxy from the daemon
The daemon MUST supervise the local model proxy as its one sibling process, started from the
daemon's own binary in proxy mode (`coffer-daemon proxy`): at start it re-attaches to a running
proxy of the same version found through `~/.coffer/proxy.json` (`port`, `pid`, `started_at`,
`version` and a control token, mode `0600`), asks a proxy of another version to drain and replaces
it once it exits, and spawns one when none is running; it health-checks the proxy on a short period
and restarts it after a crash. It pushes the proxy what it serves — the agents' token digests and
each agent's route with the decrypted keys, held only in the proxy's memory — over the proxy's
authenticated loopback control route after every reconcile pass and whenever a token changes. The
daemon stopping or restarting MUST NOT stop the proxy, so agents' in-flight model streams outlive a
daemon upgrade. `coffer proxy status` (`GET /api/v1/proxy/status`) reports whether it runs, its
port, pid, version, restart count and last error.

#### Scenario: the daemon restarts a crashed proxy
- **GIVEN** a supervised proxy
- **WHEN** the proxy process is killed
- **THEN** the supervisor spawns a new one on the same port, pushes it the current state, and counts the restart

#### Scenario: a daemon restart re-attaches to the running proxy
- **GIVEN** a proxy started by an earlier supervisor that has since stopped
- **WHEN** a new supervisor starts
- **THEN** it attaches to the same proxy process rather than spawning another
