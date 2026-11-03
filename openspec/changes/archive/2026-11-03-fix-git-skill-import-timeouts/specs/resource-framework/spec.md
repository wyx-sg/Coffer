## ADDED Requirements

### Requirement: Wait for the daemon's answer as long as the operation needs
A command MUST wait for the daemon's answer as long as its route needs, not
one fixed time for every command: connecting has its own short limit (5 s);
an ordinary command waits 15 s; a route that makes a call out (a provider, an
MCP server, a platform's API, an OpenAPI document, a CLI's version probe)
waits 90 s; a route that runs git over the network (a skill's Git source, a
vault sync round) waits 330 s, longer than the daemon's own 300 s deadline for
a Git source operation, so the answer is the daemon's specific error rather
than the CLI giving up first. `coffer --request-timeout <seconds>` replaces the
wait for every request of one command.

A request that gets no answer MUST be reported by what happened, never all as
the daemon crashing: nothing accepting the connection is `DAEMON_UNREACHABLE`
(exit 3); the connection closing before an answer is `DAEMON_CONNECTION_LOST`
(exit 3), saying the daemon may have restarted or crashed; and no answer
within the wait is `CLI_REQUEST_TIMEOUT` (exit 13, a wait ran out), whose
message names the request and the wait, says the operation may still finish
and how to wait longer, and whose `details` carry `method`, `path` and
`waited_s`.

#### Scenario: a slow answer is reported as a timeout, not a crash
- **GIVEN** a healthy daemon that answers every request after a delay longer than the ordinary wait and shorter than a Git source command's
- **WHEN** `coffer skill list --json` and `coffer skill stage-git … --json` are run, and then the second again with `--request-timeout` shorter than the delay
- **THEN** the first exits 13 with `CLI_REQUEST_TIMEOUT` naming `GET /skills` and the wait, without saying the daemon crashed
- **AND** the second prints the daemon's answer, and the third exits 13 naming `POST /skills/stage/git`

#### Scenario: a daemon that is not there is still unreachable
- **GIVEN** nothing listening on the daemon's port
- **WHEN** a command makes its request
- **THEN** it exits 3 with `DAEMON_UNREACHABLE`
