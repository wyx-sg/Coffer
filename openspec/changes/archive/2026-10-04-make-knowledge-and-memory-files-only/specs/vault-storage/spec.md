## MODIFIED Requirements

### Requirement: Move an existing home into the vault layout once, on request, reversibly
Moving a home from the single-database layout SHALL be one explicit step,
`coffer migrate`, run with the daemon stopped; the daemon MUST refuse to start
on a home that still holds only `coffer.db` and name that command. The step
SHALL back up `coffer.db` (and its `-wal`/`-shm`) as `coffer.db.pre-vault` and
keep the old knowledge history, the stamped documents and `daemon-config.json`
under `~/.coffer/pre-vault/` before changing anything; SHALL write every
resource, secret, boundary record, state document and machine-local setting
with the stores' own encoding; SHALL move every tree by rename into its class
directory; SHALL replay the old knowledge history into the vault under
`knowledge/`; SHALL commit the vault as one daemon commit with
`Coffer-Layout: db -> 3`; and SHALL rename the database to `runs.db`. Every step
SHALL be recorded before it runs, so `coffer migrate --rollback` restores the
old home byte for byte from a finished or a half-finished upgrade and holds the
home until `coffer migrate --resume`; `coffer migrate --rehearse` SHALL run the
whole upgrade on a copy and leave the source untouched. A sync remote in the old
layout MUST NOT be converted: it is refused until it is rebuilt from an upgraded
machine. When the home holds secrets, the report MUST say, by count only, that
the upgrade carries no approvals, so each secret's first use at each destination
(a provider, an MCP server, a channel, the sync remote) waits once for the
person's approval in the Coffer app.

#### Scenario: the upgrade carries every item
- **GIVEN** a home at the single-database layout with resources of every kind, secrets, approvals, knowledge with history, skills, memory and media
- **WHEN** `coffer migrate` runs
- **THEN** every item is in its class directory with its uid, reach and bytes, and the knowledge history is readable in the vault

#### Scenario: the report says carried secrets wait for approval
- **GIVEN** a home at the single-database layout that holds secrets
- **WHEN** `coffer migrate` finishes
- **THEN** its report counts the secrets and says each one's first use at each destination waits once for approval in the Coffer app

#### Scenario: the daemon refuses a home that was not upgraded
- **GIVEN** a home that holds only `coffer.db`
- **WHEN** the daemon starts
- **THEN** it refuses and names `coffer migrate`

#### Scenario: rollback restores the old home byte for byte
- **GIVEN** a home upgraded by `coffer migrate`
- **WHEN** `coffer migrate --rollback` runs
- **THEN** every file of the old home has its old bytes, the vault is set aside, and the home is held until `coffer migrate --resume`

#### Scenario: a rehearsal leaves the source untouched
- **GIVEN** a home at the single-database layout
- **WHEN** `coffer migrate --rehearse` runs
- **THEN** it reports what the upgrade carries and every byte of the source home is unchanged
