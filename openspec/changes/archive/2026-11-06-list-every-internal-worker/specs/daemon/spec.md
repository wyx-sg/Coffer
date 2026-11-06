## MODIFIED Requirements

### Requirement: Show Coffer's own background work beside the owner's tasks
The Scheduled tasks page MUST show, below the owner's tasks and read-only, a
**Coffer internal** section listing the background workers the daemon's status
reports: each by a name and a one-line description a person reads (in the
interface language), how it is woken, its state, when it last ran and how that
ended, and when it runs next. The workers a person recognises (sync, memory
sync, retention, the reconciler, the vault scanner, the scheduled-tasks worker,
provider health, skill source updates, the release check) come first, in that
order, then every other worker by name; none is folded away. A worker the page has no description for
is shown by its own name. Nothing in the section can be changed there; each
worker's settings stay on the page that owns it.

#### Scenario: the internal section lists the daemon's workers
- **GIVEN** a daemon whose status reports `sync-worker`, `memory-sync`, `reconciler` and `loop-lag-probe`
- **WHEN** the owner opens the Scheduled tasks page
- **THEN** Coffer internal lists sync, memory sync and the reconciler with their descriptions, state and next run
- **AND** `loop-lag-probe` is listed after them, with no Show all to press
