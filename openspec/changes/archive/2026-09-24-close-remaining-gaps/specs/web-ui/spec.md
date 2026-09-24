## MODIFIED Requirements

### Requirement: Keep the command-line record readers
Bringing the three records onto one page MUST NOT change or withdraw the
command-line readers — `coffer audit list` and `coffer mcp invocations [<server>]` keep working,
and scripts keep `GET /api/v1/audit`, so a script that read a record before this page
existed still does. Without a server, `coffer mcp invocations` reads the same
cross-server log the Calls tab renders (`GET /api/v1/mcp/invocations`), Coffer's own
built-in calls (`coffer`) and deleted servers' rows (`deleted:<name>`) included; with
one, it reads that server's log. Both keep `--status`, `--since`, `--limit` and `--json`.

#### Scenario: the command-line readers still read the records
- **GIVEN** a running daemon that has recorded an audit entry and MCP invocations on
  two servers, on Coffer's own built-in tools and on a deleted server
- **WHEN** a script runs `coffer audit list`, `coffer mcp invocations <server>` and
  `coffer mcp invocations` with no server
- **THEN** each exits successfully and prints that record's entry, the per-server
  reader only that server's calls and the reader with no server every row, each
  naming its server
