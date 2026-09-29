## ADDED Requirements

### Requirement: Page growing lists by an opaque cursor
A list that can grow while it is being read — the audit log, the MCP
invocation log, an agent's transcript sessions and the chat conversation
listings — MUST page by an opaque cursor rather than by `offset`. A request
MUST take `limit` and an optional `cursor`; the answer MUST carry
`next_cursor`, which is `null` exactly when no row follows the page. The list
MUST have a stable order with a unique tie-break, and the page read with a
cursor MUST hold the rows that follow the cursor's row in that order, so a row
written at the head between two reads neither repeats an earlier row nor
skips a later one. A cursor MUST be bound to the list and the filters it was
issued for: one that does not decode, or that is sent to another list or with
other filters, MUST be refused `400 CURSOR_INVALID`.

#### Scenario: a page read after new rows arrive neither repeats nor skips
- **GIVEN** an audit log of five entries read with `limit=2`, and a new entry recorded after the first page was read
- **WHEN** the next two pages are read with each answer's `next_cursor`
- **THEN** together the three pages hold the five original entries exactly once each, newest first, and the new entry is not among them

#### Scenario: the last page carries no next cursor
- **GIVEN** an audit log of three entries
- **WHEN** it is read with `limit=3`
- **THEN** the answer holds all three and its `next_cursor` is `null`

#### Scenario: a malformed or foreign cursor is refused
- **GIVEN** a cursor issued for the audit log filtered by one kind
- **WHEN** it is sent with another kind's filter, and a string that is not a cursor is sent as `cursor`
- **THEN** both requests are refused `400 CURSOR_INVALID`

## MODIFIED Requirements

### Requirement: Read the audit log from the command line
The system MUST let a terminal read the audit log with `coffer log audit`, over the same route
the web UI reads (`GET /api/v1/audit`). It MUST take the filters that route affords,
`--kind`, `--name`, `--event-type`, `--since` and `--limit`, and the route's cursor as
`--cursor`, and MUST print the entries newest first. Each entry MUST show its time, actor,
event type, and the label the resource carried at that moment; when more entries follow the
page, the output MUST end with the `--cursor` value that reads the next one. With `--json` it
MUST print the route's answer — its entries and its `next_cursor` — as one parseable document
with no human-readable framing.

#### Scenario: the command line reads the audit log
- **GIVEN** the user has disabled a resource and then changed another resource's title
- **WHEN** they run `coffer log audit --limit 2`, and then `coffer log audit --kind <kind> --json`
- **THEN** the first prints both changes newest first, each with its time, actor, event type and label
- **AND** the second prints a parseable JSON document holding only that kind's entries

#### Scenario: the command line pages the audit log by cursor
- **GIVEN** three audit entries
- **WHEN** the user runs `coffer log audit --limit 2 --json` and then `coffer log audit --limit 2 --cursor <next_cursor> --json` with the cursor the first printed
- **THEN** the first prints the two newest entries and a `next_cursor`, and the second prints the oldest entry and a `null` `next_cursor`
