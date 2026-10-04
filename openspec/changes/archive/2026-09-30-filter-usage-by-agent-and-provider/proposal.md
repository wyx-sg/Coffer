## Why

The Usage page's final design (canvas 6.4) narrows the API-key section with an Agent and a Provider pill, exports the current range and filters as CSV, names the agents behind each model ("By" column), and gives each day its top agent. The summary had no filters and did not say which agents sent a group's requests, so the page could draw none of these.

## What Changes

- `GET /api/v1/usage/summary` and `GET /api/v1/usage/export.csv` take optional `agent_type` and `connection_uid` filters; `coffer usage` takes `--agent <agent type>` and `--provider <name>`.
- Every summary row carries `agent_types`: the agent types that sent its requests, most requests first.
- The Usage page lays out every board of canvas 6.4: filter pills and the ⋯ Export CSV beside the range, a manual Refresh on Claude Code's quota row, "No subscription quota" for an agent on an API-key provider, the "via API key" tag, the By / Via / Top agent columns, and the by-day list newest first with "Show all".

## Capabilities

### New Capabilities

### Modified Capabilities
- `provider-switching`: the usage summary can be narrowed to one agent type and one connection, and names the agents behind each row.

## Impact

- Backend: `application/usage/query.py`, `surfaces/http/usage_routes.py`, `usage_schemas.py`, `surfaces/cli/usage_cmd.py`; contract regenerated.
- Frontend: `pages/UsagePage.tsx`, `components/usage/*`, `lib/usage/range.ts`, `lib/api/usage.ts`, en + zh strings.
- Docs: the usage guide; the CLI and REST reference pages (generated).
