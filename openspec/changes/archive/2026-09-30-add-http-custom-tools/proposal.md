# Add HTTP API custom tools

## Why

Many of the tools a developer wants an agent to have are one HTTP request
against an API they already use — list invoices, roll back a deploy, query a
dashboard. Today that needs an MCP server someone has to write, run and keep
alive. The web UI's Custom tools page (change `revise-web-ui-ia`, spec web-ui
"Manage custom tools on their own page") fixes where such tools are managed;
this change adds what the page manages: a third MCP transport, **HTTP API**,
whose tools are requests Coffer's gateway makes itself.

## What Changes

- **A custom-tool group is an `mcp_server` of the new `http_api` transport.**
  Its fixed name is the prefix agents see (`<group>__<tool>`); it holds a base
  URL, optional static headers, an optional auth header whose value is a stored
  secret (bound by its Secrets-page name), a timeout, a default reach and its
  tools. Each tool carries a method, a path template (with `{argument}` holes,
  query included), optional headers, an optional JSON body template, an
  argument schema, an on/off switch and a **changes data** flag (on by default
  for every method but GET). A tool's **reach override** narrows the group's
  reach for that one tool and stays on this machine.
- **The gateway makes the request.** On `tools/call` it renders the request
  from the arguments, adds the auth header from the secret store, sends it with
  the group's timeout, no redirects followed and the response cut at 1 MiB,
  and returns the status line and body with the secret's value masked. The
  call is routed, gated, audited and logged like any other upstream tool.
- **Tools carry MCP annotations.** A tool that changes data is listed with
  `readOnlyHint: false` and `destructiveHint: true`, any other with
  `readOnlyHint: true`, so each agent's own approval prompt applies. Upstream
  servers' own annotations are passed through as well.
- **The secret goes only where a person approved.** Binding a secret to a
  group's auth header is a new destination: the group waits for the approval
  of that header at that base URL before any call carries it (spec credentials
  "Hold a secret for a new destination until a person approves it"); changing
  the base URL asks again.
- **OpenAPI import.** An OpenAPI 3.x document, JSON or YAML, read from a URL
  (through the SSRF guard) or given as a file, lists its operations as draft
  tools; the chosen ones become a new group. **Re-import** reads the source
  again and previews the operations it would add and remove; applying it keeps
  every kept tool's switch, flag and reach override.
- **Surfaces.** REST `/api/v1/custom-tools…`, CLI `coffer tool …` (groups) and
  `coffer tool op …` (one tool), and the Custom tools page. The MCP servers
  list and its Add dialog leave these groups out.

Capability whose requirements change: `mcp-gateway` (the transport, the
annotations, the per-tool gate, the OpenAPI import and the surfaces).
