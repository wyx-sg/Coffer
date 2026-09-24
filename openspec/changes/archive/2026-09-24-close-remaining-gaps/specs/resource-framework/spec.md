## MODIFIED Requirements

### Requirement: Report the passes in flight in one cross-kind read
The system MUST answer, in one cross-kind read, which long model-driven passes this
daemon is running right now — each named by its kind, its target and when it started —
so that a surface can tell whether a pass is under way without every kind growing a
near-identical endpoint of its own. The read MUST start nothing, and the registry MUST
NOT outlive the process: a restart ends any pass it was running and the list comes back
empty, which is the truth rather than a lost record. Whether a pass runs on a timer at
all is internal-engine's; what a pass *does* is its own kind's. The read is served over
REST (`GET /api/v1/upkeep/runs`) and on the command line (`coffer engine upkeep runs
[--json]`), which prints the same list and says so when nothing is running.

#### Scenario: the daemon names the passes in flight
- **GIVEN** a long, model-driven pass over one kind's target is running,
- **WHEN** any surface reads the in-flight list,
- **THEN** that pass is named with its kind, its target and when it started,
- **AND** a target absent from the list has no pass running, and the read starts nothing.

#### Scenario: the command line reads the passes in flight
- **GIVEN** a pass over a knowledge collection and a pass over a memory partition are running
- **WHEN** the operator runs `coffer engine upkeep runs --json`, and again once both have ended
- **THEN** the first lists both passes with their kind, target and start time, oldest first,
- **AND** the second lists none, and the table form says that no pass is running.
