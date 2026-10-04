## ADDED Requirements

### Requirement: Hand a daemon error about the environment to an agent
A record of `GET /api/v1/daemon/logs` that is an ERROR (or CRITICAL) whose message
or folded lines show a cause outside Coffer — a refused or reset connection, a
timeout, a name that does not resolve, a certificate error, a missing or
unreadable file or program — MUST carry `handoff`: a prompt with the logger, the
message and the traceback, every line passed through the secret scrub, and this
machine, asking for the cause and a proposed fix before anything changes. Every
other record — a warning, an error with no such cause — carries none.

#### Scenario: an environment error carries a hand-off and an internal one does not
- **GIVEN** a daemon log holding an ERROR about a refused connection with a traceback, an ERROR that is a Coffer `KeyError`, and a warning that mentions a refused connection
- **WHEN** the log is read
- **THEN** only the first carries a `handoff`, and it quotes the logger, the message and the traceback
