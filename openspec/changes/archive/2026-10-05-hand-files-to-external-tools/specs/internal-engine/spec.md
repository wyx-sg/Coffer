## MODIFIED Requirements

### Requirement: Audit every write to the engine settings
Every write to the settings MUST record an `internal_engine_model_set` audit
entry naming the actor and carrying the values after the write. A change another
machine made arrives as a sync commit to the settings document, and is as visible
in that document's history as one made here ([vault-storage](../vault-storage/spec.md) "Keep the vault a git repository whether or not it syncs").

#### Scenario: record every settings write with its actor and values
- **GIVEN** the internal-engine settings,
- **WHEN** one pass's switch and the speech-to-text model are each
  written by an actor,
- **THEN** each write records an `internal_engine_model_set` audit entry naming
  that actor,
- **AND** each entry's details carry the value as it stands after that write.

