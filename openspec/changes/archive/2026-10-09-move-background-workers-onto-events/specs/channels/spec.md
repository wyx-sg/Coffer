## MODIFIED Requirements

### Requirement: Report a channel that is starting apart from one that failed to start
The daemon starts an enabled channel on its next reconcile pass, which the write
that switched it on brings forward, so for a moment after a channel is switched
on its adapter is not running although nothing has failed. The channel status MUST carry `starting`,
true while the channel is enabled, not running, and no start
has yet been attempted, found it routes nowhere, or held it on its secret's
approval; it is false in every other case. A channel switched off
MUST forget its last start failure, so switching it back on starts a new run on
the next pass and does not report the previous run's failure. The Channels page
MUST show a starting channel as connecting — never as stopped or as a rejected
token or secret — including while the status it holds was read before the
switch; the Overview MUST NOT raise a "not running" item for it.

#### Scenario: a channel switched on reports starting until its first start attempt
- **GIVEN** a disabled channel
- **WHEN** the owner switches it on and its status is read before the daemon's next pass
- **THEN** the status reports `running: false` and `starting: true`, and the Channels page shows it connecting
- **AND** after the pass it is running and `starting` is false, while a start that failed leaves `starting` false
