## MODIFIED Requirements

### Requirement: Report the passes in flight in one cross-kind read
The system MUST answer, in one cross-kind read, which long passes this
daemon is running right now — memory's aggregate and distil passes, each named by its kind, its target and when it started, and, for a run that works through several items one pass at a time, how many of them it has done of how many —
so that a surface can tell whether a pass is under way without every kind growing a
near-identical endpoint of its own. The read MUST start nothing, and the registry MUST
NOT outlive the process: a restart ends any pass it was running and the list comes back
empty, which is the truth rather than a lost record. Whether a pass runs on a timer at
all is internal-engine's; what a pass *does* is its own kind's. The read is served over
REST (`GET /api/v1/upkeep/runs`) and on the command line as the "passes in flight" section
of `coffer daemon status`, which prints the same list, says so when nothing is running, and
carries the list under `--json`.

#### Scenario: the daemon names the passes in flight
- **GIVEN** a long pass over one memory partition is running,
- **WHEN** any surface reads the in-flight list,
- **THEN** that pass is named with its kind, its target and when it started,
- **AND** a target absent from the list has no pass running, and the read starts nothing.

#### Scenario: the command line reads the passes in flight
- **GIVEN** passes over two memory partitions are running
- **WHEN** the operator runs `coffer daemon status --json`, and again once both have ended
- **THEN** the first lists both passes with their kind, target and start time, oldest first,
- **AND** the second lists none, and the table form of `coffer daemon status` says that no pass is running.
