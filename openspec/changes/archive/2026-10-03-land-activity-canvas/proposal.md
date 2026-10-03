## Why

The finished Activity design changes what the page filters by, how it lays out
its records and when it hands a failure to an agent. The Server filter goes
(the search already matches a server's name), Agent becomes By, Kind splits
into the three records on Everything and the kinds of change on Changes, the
time range follows the shared picker, the tabs lose their counts, a record
opens in the shared right-hand drawer, and Export moves out of the ⋯ menu to
the header. A failure that depends on this machine — a call its server never
answered, a daemon error about an external service — is handed to the person's
agent with a prompt the backend writes.

## What Changes

- web-ui: "Gather the three records on one Activity page" — no tab counts, a
  warning icon on a tab whose log failed, no summary line above the rows, the
  day as a heading row inside the table's box, the Daemon log's file line with
  **Open in Finder**.
- web-ui: "Filter each Activity tab and expand any row" — search, time range,
  **By**, **Kind** in the shared filter row; MCP calls and Daemon log lead with
  a segmented status or level; presets Last hour / 24 h / 7 days / 30 days and a
  custom range; no Server filter; the drawer is the shared 640 drawer.
- web-ui: "Query only the visible Activity tab and isolate failures" — one
  warning banner with Retry for the failed log only.
- web-ui: "Export the filtered Activity records from the overflow menu" is
  renamed "Export the filtered Activity records from the header".
- web-ui: new "Keep Activity's filters in the address", "Show the first run
  with nothing to filter", "Hand an environment failure on Activity to an agent".
- mcp-gateway: new "Hand a failing MCP call's diagnosis to an agent" and "Read
  every failed call at once" (`status=failed`).
- daemon: new "Hand a daemon error about the environment to an agent".

## Impact

- `GET /api/v1/mcp/invocations` accepts `status=failed`; every invocation
  carries `handoff` (null unless the server never answered).
- `GET /api/v1/daemon/logs` records carry `handoff` (null unless an ERROR about
  the environment).
