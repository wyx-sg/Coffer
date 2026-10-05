## Why

A custom tool group is an `mcp_server`, served through the same gateway, but its page shows less than an MCP server's: no record of who called it in the last 24 hours, no list of what it needs from this machine, no busiest tools, and no way to choose how each of its tools reaches agents. With the Invocations tab gone, the group page also lost its tabs, which leaves it the only detail page laid out differently from the rest.

## What Changes

- A custom tool group's page has two tabs again, Overview and Tools, each at its own address (`/custom-tools/<group>`, `/custom-tools/<group>/tools`), laid out like every other detail page.
- Overview stacks the group's definition, then the same blocks as an MCP server's Overview: Last 24 hours (calls and errors per calling agent, View in Activity), Requires (each secret the group's headers cite, Set, Missing or Waiting for approval, linked to Secrets) and Most-called tools (the busiest four, read-only).
- Tools holds the tools table, with each tool's exposure — Auto, Always listed, Search only — set by the same control as an MCP server's tools.
- A custom tool's exposure is stored, audited and honoured by the gateway exactly as an MCP server tool's, keyed by the group's uid; a group's tools are read from its config, so they take an exposure before any agent has listed the group.
- The MCP server Overview's Last 24 hours block becomes one shared component, used by both pages.
- The web-ui requirement "Manage custom tool groups on one page" is renamed "Manage custom tool groups on their own page".
