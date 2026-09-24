## MODIFIED Requirements

### Requirement: Let the user choose when the daemon runs
The General tab MUST carry a card for when Coffer's daemon runs, with one control: a **Start at
login** switch. It MUST read and write it through
[daemon](../daemon/spec.md) "Change residency from the settings page or the command line".
A clicked switch MUST move to the clicked value at once and then settle on what the daemon reports:
the switch is disabled until the daemon has first answered, a successful write shows the value the
daemon answers with, the switch is shown unavailable rather than off on a host with no login
service, and a failed write MUST put the switch back to what the daemon last reported and show the
error beside it. The card MUST NOT offer an idle window or a stand-down choice, because the daemon
never stands down on its own.

#### Scenario: the general tab sets when the daemon runs
- **GIVEN** the daemon reports a login service that is supported and not installed
- **WHEN** the user turns on Start at login
- **THEN** one request is sent carrying `login_service_installed: true` and no idle window
- **AND** the card offers no idle-window or stand-down control
- **AND** when the request fails, the switch goes back to off and the error is shown beside it
