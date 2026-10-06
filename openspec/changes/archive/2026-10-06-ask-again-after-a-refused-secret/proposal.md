## Why

After a person refused a custom-tool group's secret binding, the group's page
kept saying the secret waits for approval, its environment kept a "Waiting for
approval" badge, and Open approvals opened a list that no longer held it: the
group view counted a refused binding as a pending one. A refusal also had no
way back short of changing the destination, so the person was stuck.

## What Changes

- A group (and each environment) reports a refused binding as `rejected`, with
  `rejected_approvals` and `rejected_secrets`, instead of `pending_approval`;
  its health reason is `approval_rejected`. An MCP server's Requires row says
  `refused` for the same reason, where it said `waiting_approval`.
- `POST /api/v1/secrets/approvals/{id}/ask-again` and `coffer approval
  ask-again <id>` retire a refusal and put a new pending approval up for the
  same target. They take no presence grant: asking grants nothing.
- The group page's refused banner offers Ask again; in the desktop app it asks
  for Touch ID at once and approves. The environment badge and the Overview's
  Requires row say Refused.

## Impact

- Backend: custom-tool views and schemas (additive fields, one new state), the
  secret boundary, one new route, one new CLI command.
- Frontend: the group banner, environment badge, overview rows, list row.
- Specs: secret, mcp-gateway, web-ui. Docs: custom tools and secrets guides,
  CLI reference (en + zh).
