## MODIFIED Requirements

### Requirement: Aggregate on an interval and on demand
Aggregation MUST run on a background worker on an interval and MUST be triggerable by hand. It MAY default to on, because it only reads the agents' files and only writes derived ones. Its switch and its interval MUST both be settable by the operator and MUST be read per pass rather than at boot ([internal-engine](../internal-engine/spec.md) "Apply a changed switch or interval without a restart").

#### Scenario: aggregation runs unattended, without anyone asking for it
- **GIVEN** the aggregate worker configured with an interval, and nobody having asked for a pass
- **WHEN** the daemon starts it
- **THEN** a pass runs **immediately**, not after the first interval elapses
- **AND** the audit actor on that pass is the worker's own, so the log can tell a scheduled pass from a requested one (see "Audit every lifecycle act")
