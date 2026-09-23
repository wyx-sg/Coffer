## MODIFIED Requirements

### Requirement: Keep the command-line record readers
Bringing the three records onto one page MUST NOT change or withdraw the
command-line readers — `coffer audit list` and `coffer mcp invocations <server>` keep working
as they are, and scripts keep `GET /api/v1/audit`, so a script that read a
record before this page existed still does.

#### Scenario: the command-line readers still read the records
- **GIVEN** a running daemon that has recorded an audit entry and an MCP invocation
- **WHEN** a script runs `coffer audit list` and `coffer mcp invocations <server>`
- **THEN** each exits successfully and prints that record's entry

### Requirement: Let the user choose when the daemon runs
The General tab MUST carry a card for when Coffer's daemon runs, with two
controls: a **Start at login** switch and a **Stand down after** choice of idle
window that offers a set of hour values and **Never** as its own option, never
as a number. It MUST read and write both through
[daemon](../daemon/spec.md) "Change residency from the settings page or the command line",
and every change MUST send both halves in one request. A clicked control MUST
move to the clicked value at once and then settle on what the daemon reports:
the controls are disabled until the daemon has first answered, a successful
write shows the values the daemon answers with, a window set from the command
line that the list does not offer is still shown, the switch is shown
unavailable rather than off on a host with no login service, and a failed write
MUST put the controls back to what the daemon last reported and show the error
beside them.

#### Scenario: the general tab sets when the daemon runs
- **GIVEN** the daemon reports a login service that is supported and not installed, and an idle window of 12 hours
- **WHEN** the user turns on Start at login, and then picks Never as the idle window
- **THEN** each change sends one request carrying both halves — first `login_service_installed: true` with `idle_shutdown_hours: 12`, then `login_service_installed: true` with `idle_shutdown_hours: null`
- **AND** the idle window offers 1, 4, 12, 24 and 72 hours and Never
- **AND** when the second request fails, the idle window goes back to 12 hours and the error is shown beside it
