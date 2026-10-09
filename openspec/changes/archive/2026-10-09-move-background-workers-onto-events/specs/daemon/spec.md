## ADDED Requirements

### Requirement: Wake background workers on events and park them without demand
A background worker whose work follows from a change MUST run when that change
is announced rather than on a short timer, and a worker with nothing to serve
MUST park with no timer at all, because an idle daemon that wakes several times
a second costs the machine's battery for nothing. The channel runtime MUST run a
pass on every resource write (sync and hand edits included), on every secret
stored or approved, and when a failed start's retry wait is over, and otherwise
at most every 5 minutes. The model proxy watchdog MUST park while no proxy runs
and none is needed, until the next state push; while a proxy runs it MUST keep
probing it and restart it after a crash. The usage ingest MUST empty the spool
on its period only while a proxy runs, MUST run one more pass when the proxy
stops, and then park. The MCP session reaper MUST park while no session is
open. Each of them MUST be listed on `runtime.workers`.

#### Scenario: a resource write brings the channel runtime's next pass forward
- **GIVEN** a running channel runtime whose fallback is far off, and a channel switched on without its pass having run
- **WHEN** the resource write is announced to it
- **THEN** the channel's adapter starts without waiting for the fallback
- **AND** before that announcement no pass has started it

#### Scenario: a failed channel start is retried when its wait is over
- **GIVEN** a channel whose first start fails
- **WHEN** the retry wait passes with nothing else waking the runtime
- **THEN** the runtime starts the channel again, and it runs

#### Scenario: an idle model proxy watchdog parks until a push wakes it
- **GIVEN** no agent routed through the model proxy and no proxy running
- **WHEN** the supervisor has found none is needed
- **THEN** `model-proxy` is listed as `parked` with no next run, and it asks nothing while parked
- **AND** a state push after an agent is routed wakes it, and it tries to start a proxy

#### Scenario: the usage ingest drains once when the proxy stops and then parks
- **GIVEN** the usage ingest running while a proxy runs
- **WHEN** the proxy stops with a spool file it just completed
- **THEN** that file is ingested and `usage-ingest` is then listed as `parked`

#### Scenario: the MCP session reaper parks with no session open
- **GIVEN** the reaper started with no session open
- **WHEN** a session becomes active and is later reaped as idle
- **THEN** the reaper is `parked` before the session, runs while it is open, and is `parked` again once it is reaped
