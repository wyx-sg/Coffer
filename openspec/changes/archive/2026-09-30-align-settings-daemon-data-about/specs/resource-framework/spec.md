## MODIFIED Requirements

### Requirement: Prune each registered log table on its own retention period
The system MUST provide per-table retention configuration (in days, or "keep forever")
over a registry of prunable tables, seeded with each table's default when the daemon
starts, plus a periodic background pass that prunes entries older than their table's
period and an on-demand prune for the impatient. Entries newer than the period MUST be
retained, and the cleanup MUST NOT block concurrent API calls. Only a registered table
MAY be pruned, and only through its registered timestamp column. Policies are upserted at
startup from the prunable-table registry and never deleted, so a table that stops
existing leaves a policy that prunes nothing rather than a prune aimed at an unknown
table. Changing a policy MUST itself be audited. This is the retention contract every
log-writing kind inherits.

On the command line each table's period MUST be the setting `retention.<table>`, read and
changed with `coffer config get|set|unset retention.<table>` (see "Change every setting through
one key-value command"), taking a whole number of days or `forever`, with `unset` returning the
table to its registered default. The on-demand prune MUST be `coffer log prune [--table
<table>]`, which prunes every registered table, or only the one named, and prints how many
entries each lost.

Before a shorter period is saved, the web UI MUST be able to ask how many entries it would delete:
`GET /api/v1/retention/policies/{table}/preview?days=<n>` answers the entries the table holds now
and how many of them are older than `n` days, counts them against the same timestamp column the
prune uses, and deletes and changes nothing. It is a read that serves a confirmation, so it has no
command of its own: `coffer config set retention.<table>` saves a period directly.

#### Scenario: configure retention per log
- **GIVEN** the audit and invocation logs grow over time,
- **WHEN** the user sets a retention period for a log (in days, or "keep forever"),
- **THEN** entries older than that period are removed by the next periodic cleanup, and the change itself is audited.

#### Scenario: the command line sets a retention period and prunes now
- **GIVEN** the invocation log holds entries older and newer than 7 days
- **WHEN** the user runs `coffer config set retention.mcp_invocations 7` and then `coffer log prune --table mcp_invocations`
- **THEN** `coffer config get retention.mcp_invocations` prints 7, the policy change is audited, and the prune reports how many entries it removed
- **AND** only entries older than 7 days are gone

#### Scenario: a shorter period is previewed before it is saved
- **GIVEN** the audit log holds 4 entries, 2 of them older than 7 days
- **WHEN** the web UI asks `GET /api/v1/retention/policies/audit_log/preview?days=7`
- **THEN** the answer carries 4 entries now and 2 to delete
- **AND** asking again answers 4 entries now: nothing was deleted
