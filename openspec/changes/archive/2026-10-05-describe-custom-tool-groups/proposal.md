## Why

A custom-tool group's description could only be set from Edit group, was shown
nowhere, and never reached an agent, so it could not help an agent find the
group's tools. Choosing the group in Add custom tool was a radio list that grows
with every group, and the Secrets page's Used by labelled a custom-tool group as
an MCP server.

## What Changes

- Add custom tool asks for the group in a select you can type into, starting on
  New group.
- A new group takes a description, by hand or from the OpenAPI spec's
  `info.description`; reading a spec returns that description.
- The group's definition shows its description.
- `coffer__search_tools` scores each group's tools against the group's
  description too and returns it beside them as `group_description`.
- Used by on the Secrets page reads a custom-tool group as a custom tool and
  opens its group page.

## Impact

- Backend: gateway tool search, OpenAPI import, custom-tool read route.
- Frontend: Add custom tool flow, group definition, Secrets Used by.
- Specs (edited in place, `skip_specs`): mcp-gateway "Describe a custom-tool
  group" (new) and the built-in search contract; web-ui "Manage custom tool
  groups on their own page" and "Manage stored secrets on the Secrets page".
