## MODIFIED Requirements

### Requirement: Read the audit log from the command line
The system MUST let a terminal read the audit log with `coffer log audit`, over the same route
the web UI reads (`GET /api/v1/audit`). It MUST take the filters that route affords,
`--kind`, `--name`, `--event-type`, `--nature` (`change` or `use`), `--since` and `--limit`, and the route's cursor as
`--cursor`, and MUST print the entries newest first. Each entry MUST show its time, actor,
event type, and the label the resource carried at that moment; when more entries follow the
page, the output MUST end with the `--cursor` value that reads the next one. With `--json` it
MUST print the route's answer — its entries and its `next_cursor` — as one parseable document
with no human-readable framing.

#### Scenario: the command line reads the audit log
- **GIVEN** the user has disabled a resource and then renamed another resource
- **WHEN** they run `coffer log audit --limit 2`, and then `coffer log audit --kind <kind> --json`
- **THEN** the first prints both changes newest first, each with its time, actor, event type and label
- **AND** the second prints a parseable JSON document holding only that kind's entries

#### Scenario: the command line reads secret uses apart from changes
- **GIVEN** the user stored a secret and Coffer then handed it to an MCP server it started
- **WHEN** they run `coffer log audit --nature use` and `coffer log audit --nature change`
- **THEN** the first prints only the hand-off and the second only the stored secret

#### Scenario: the command line pages the audit log by cursor
- **GIVEN** three audit entries
- **WHEN** the user runs `coffer log audit --limit 2 --json` and then `coffer log audit --limit 2 --cursor <next_cursor> --json` with the cursor the first printed
- **THEN** the first prints the two newest entries and a `next_cursor`, and the second prints the oldest entry and a `null` `next_cursor`

## ADDED Requirements

### Requirement: Tell a secret's use from a change in the audit log
The audit log MUST keep a secret's use beside its changes and MUST let a reader
ask for either alone. A **use** is an event in which a secret's value left the
store for a moment of use and nothing in the vault changed: `secret_resolved`
(Coffer handed the value to a server, custom tool or connection it started, or
`coffer run` handed it to a program) and `secret_revealed` (a person revealed it
in the Coffer app). Every other event is a **change**. `GET /api/v1/audit` MUST
take `nature=change` or `nature=use` and apply it before paging and counting, so
a page and its `total` hold only that nature; the cursor is bound to it like any
other filter. A `secret_resolved` row MUST name the secret (`ref`) and where it
went: for Coffer's own hand-off the destination's kind, uid and name and the slot
(the environment variable or header) it filled; for `coffer run` the program
(`argv0`) and the folder (`cwd`). Neither ever holds the value.

#### Scenario: the audit route reads uses apart from changes
- **GIVEN** a stored secret (`secret_set`), Coffer handing it to an MCP server (`secret_resolved`) and a person revealing it (`secret_revealed`)
- **WHEN** a client reads `GET /api/v1/audit?nature=use` and `GET /api/v1/audit?nature=change`
- **THEN** the first answers the two uses with `total` 2 and the second the stored secret with `total` 1
- **AND** `nature=other` is refused with 422
