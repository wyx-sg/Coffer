## ADDED Requirements

### Requirement: Mark an experimental feature's sidebar entry
While an experimental feature is switched on, its web sidebar entry MUST carry
a marker that says the feature is experimental, beside the label on an expanded
rail and in the tooltip on a collapsed one. An entry outside the registry MUST
NOT carry it.

#### Scenario: a switched-on feature's entry says it is experimental
- **GIVEN** the daemon reports `vault_sync`, `knowledge` and `memory` on
- **WHEN** the expanded sidebar renders
- **THEN** the Sync, Knowledge and Memory entries each carry the experimental marker
- **AND** no other entry carries it
