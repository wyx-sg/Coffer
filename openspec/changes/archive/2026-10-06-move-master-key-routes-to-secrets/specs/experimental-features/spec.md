## MODIFIED Requirements

### Requirement: Close the sync feature's surfaces
While `sync` is off, `/api/v1/sync` MUST answer 404 `FEATURE_DISABLED`, the
convergence worker MUST skip its rounds, and the sync attention source MUST be
tagged `sync` and not asked. The configured remote and the
history stay untouched. The master key's routes are the secret store's, under
`/api/v1/secrets/key`, and stay open ([secret](../secret/spec.md)
"Import a master key after showing whose key it is").

#### Scenario: sync off closes the sync routes
- **GIVEN** `sync` off
- **WHEN** a route under `/api/v1/sync` is requested
- **THEN** it answers 404 `FEATURE_DISABLED` naming `sync`

#### Scenario: sync off skips convergence rounds and keeps the remote
- **GIVEN** `sync` on with a configured remote
- **WHEN** `sync` is switched off and the convergence worker comes due
- **THEN** it skips the round, the remote and the history are unchanged, and the sync attention source is not asked
