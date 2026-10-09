## MODIFIED Requirements

### Requirement: Supervise the model proxy from the daemon
The daemon MUST supervise the local model proxy as its one sibling process, started from the
daemon's own binary in proxy mode (`coffer-daemon proxy`): at start it re-attaches to a running
proxy of the same version found through `~/.coffer/proxy.json` (`port`, `pid`, `started_at`,
`version` and a control token, mode `0600`) — after checking that it is Coffer's (below) — asks a proxy of another version to drain and replaces
it once it exits, and spawns one when none is running; it health-checks the proxy on a short period
and restarts it after a crash. It pushes the proxy what it serves — the agents' token digests and
each agent's route with the decrypted keys, held only in the proxy's memory — over the proxy's
authenticated loopback control route after every reconcile pass that could have changed it — every
pass but a periodic one that wrote nothing, failed no new target and left the same differences
open — and whenever a token changes. The
daemon stopping or restarting MUST NOT stop the proxy, so agents' in-flight model streams outlive a
daemon upgrade. `GET /api/v1/proxy/status` reports whether it runs, its
port, pid, version, restart count and last error.

`proxy.json` and the loopback port are writable by any process of the same user, and the push
carries the provider keys, so the daemon MUST know a proxy is its own before it pushes anything.
It derives an attest key from the master key (context `coffer-proxy-attest-key/v1`) and hands it
to the proxy it spawns on the child's standard input, never in its arguments or environment. Before
every `/_coffer/state` push, and before re-attaching to a proxy found through `proxy.json`, it
challenges `POST /_coffer/attest` with a fresh nonce and accepts only an answer that is the
HMAC-SHA256 of the nonce and the proxy's own port under that key. A process that fails the
challenge, or a proxy that holds no key, MUST be sent nothing and is logged as
`model_proxy.attest_failed`: the daemon does not attach to it, reports the reason as the proxy's last error, and never sends it a key.

#### Scenario: the daemon restarts a crashed proxy
- **GIVEN** a supervised proxy
- **WHEN** the proxy process is killed
- **THEN** the supervisor spawns a new one on the same port, pushes it the current state, and counts the restart

#### Scenario: a daemon restart re-attaches to the running proxy
- **GIVEN** a proxy started by an earlier supervisor that has since stopped
- **WHEN** a new supervisor starts
- **THEN** it attaches to the same proxy process rather than spawning another

#### Scenario: a periodic pass that changes nothing tells no pass listener
- **GIVEN** a reconciler with a pass listener, whose first periodic pass found a difference it only reports
- **WHEN** a second periodic pass finds the same difference and writes nothing
- **THEN** the listener is not called for it
- **AND** a hinted pass, a periodic pass that repairs drift, and a periodic pass after which a difference closed are each heard
