## ADDED Requirements

### Requirement: Apply knowledge and skill file changes
What a round applies MUST be a checkout of the merged tree: an added or modified file
under `knowledge/`, `skills/`, `resources/`, `state/`,
`secret/` or `machines/` is written, and a deleted one removed, in the one
compare-and-swap step that refuses to overwrite a person's unsettled edit (see
"Never overwrite a person's unsettled edit"). Stores that read the vault reload
from the new `HEAD`, so an arriving resource file is a resource and an arriving
state document is in effect without any per-kind import step.

#### Scenario: an arriving file is written and a deleted one removed
- **GIVEN** two machines that each wrote a knowledge document
- **WHEN** both run rounds
- **THEN** each machine holds the other's document with the same bytes

## REMOVED Requirements

### Requirement: Apply knowledge, skill and memory-trigger file changes
**Reason**: Memory triggers are removed, so the requirement no longer names `memory-triggers/`; it is replaced by "Apply knowledge and skill file changes", which carries the same behaviour for the remaining areas.

**Migration**: None. The replacement requirement keeps its scenario unchanged.
