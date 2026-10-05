## Why

The MCP server page and the custom tool group page each carried an Invocations tab that repeated the Activity page's Tool calls, scoped to one server. Calls are read in one place, Activity. A custom tool group, with that tab gone, has too little for two tabs.

## What Changes

- The MCP server page loses its Invocations tab and the per-call drawer that opened from it. Its Overview link and the HTTP failure banner's View errors open Activity's Tool calls tab searching the server (and filtered to failed calls for View errors).
- The custom tool group page loses its Invocations tab and its Overview and Tools tabs merge into one page with no tab in the address: the definition, then the Tools section. The failing banner's View calls opens Activity.
- No backend route changes: the per-server invocation routes still feed the tool detail's last-caller line and the 24-hour summary.
