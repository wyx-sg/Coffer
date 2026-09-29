## RENAMED Requirements

- FROM: `### Requirement: Apply knowledge and skill file changes`
- TO: `### Requirement: Apply knowledge, skill and memory-trigger file changes`

## MODIFIED Requirements

### Requirement: Apply knowledge, skill and memory-trigger file changes
For `knowledge/**`, `skills/**` and `memory-triggers/**` — the authored memory
triggers of `vault/memory-triggers/` ([memory](../memory/spec.md) "Keep
triggers in the vault, armed only by a person") — an addition or a modification
MUST write the file and a deletion MUST remove it. A round publishes the three
trees the same way, and a conflict in any of them is resolved as a file-tree
conflict.

#### Scenario: an arriving file is written and a deleted one removed
- **GIVEN** a diff that adds a knowledge file and a skill file and deletes another knowledge file
- **WHEN** it is applied to the vault
- **THEN** the added files are written into the knowledge and skill stores
- **AND** the deleted file is removed from the vault

#### Scenario: an arriving memory trigger is written into the vault
- **GIVEN** a diff that adds `memory-triggers/<id>.md` and deletes another trigger's file
- **WHEN** it is applied to the vault
- **THEN** the trigger's file is written into `vault/memory-triggers/` and the deleted one is removed
- **AND** a bundle published from this vault carries every file of `vault/memory-triggers/` under `memory-triggers/`
