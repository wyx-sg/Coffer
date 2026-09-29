# Design — HTTP API custom tools

## Context

The Custom tools page is fixed by spec web-ui "Manage custom tools on their
own page" (change `revise-web-ui-ia`, design §12): tools managed in groups, one
group = one `mcp_server`, a fixed name that is the agent-visible prefix, a
shared base URL and auth, per-tool switch, changes-data flag and reach
override, OpenAPI import and re-import, hand-made requests, a Test in a drawer.
This design says how the gateway runs such a tool and how the pieces are
stored and served. The gateway's general model is
[MCP gateway](/architecture/mcp-gateway); the secret rules are
[Security](/architecture/security) and ADR
only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.

## Decisions

### 1. A third transport, not a new kind

A group is `MCPServerConfig.transport = HttpApiTransport(type="http_api")`.
Everything the gateway already does for a server — namespacing, the disabled
and reach gates, invocation logging, audit, deletion, sync of the definition,
the attention source's missing-secret check — applies unchanged. The upstream
"connection" is an in-process adapter (`infrastructure/mcp/http_api_client.py`)
that answers `initialize` and `tools/list` from the config and makes the HTTP
request on `tools/call`; `resources/list` and `prompts/list` answer
METHOD_NOT_FOUND, which discovery already reads as "none".

*Rejected:* a new resource kind (`custom_tool`) — it would duplicate the
gateway's routing, gating, logging and the agents' MCP projection for no
behaviour of its own; one resource per tool (design §12 of revise-web-ui-ia).

### 2. Stored shape

```text
HttpApiTransport
  type: "http_api"
  base_url: HttpUrl                  # http or https; tools' paths are appended
  headers: {name: value}             # static, non-secret (secret-looking values refused)
  auth_header: str | None            # e.g. "Authorization"
  auth_prefix: str = ""              # e.g. "Bearer " — prepended to the secret's value
  credential_refs: {auth_header: ref}  # the one secret, a standalone "secret/<name>" ref
  timeout_seconds: int = 30          # 1..300, per request
  source: OpenApiSource | None       # set by an import
  tools: [HttpApiTool]               # unique names

OpenApiSource
  kind: "url" | "file"
  location: str                      # the URL, or the file name
  title, version: str | None         # info.title / info.version
  fetched_at: datetime
  skipped: [operation key]           # operations seen and not imported

HttpApiTool
  name: ^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$
  description: str
  method: GET | POST | PUT | PATCH | DELETE
  path: str                          # "/invoices/{id}?status={status}"; starts with "/"
  headers: {name: value}             # static, may hold {argument} holes
  body_template: str | None          # JSON text with {argument} holes
  input_schema: JSON Schema object   # what the agent is told the arguments are
  enabled: bool = True
  changes_data: bool | None = None   # None → method != GET
  operation: str | None              # "GET /invoices/{id}" when imported
```

`credential_refs` keeps its meaning from the other two transports (slot →
ref), so the kind's credential-ref extractor, the resource service's
missing-credential probe, `cited_credential_refs`, the MCP attention source and
the secret boundary's destination enumeration all cover a group without a
change. The API takes and returns the secret by its Secrets-page **name**; the
ref is `secret/<name>`.

**Per-tool reach overrides are not in the config.** Reach is machine-local
(spec vault-sync "Keep reach machine-local") and the config travels with sync,
so overrides live in a new table `mcp_tool_reach(resource_uid, tool,
agents_json, updated_at)`, primary key `(resource_uid, tool)`, migration 0113.
An override is a list of agent uids; the tool reaches an agent only when both
the group's scope and the override admit it (an override narrows, never
widens). Rows for a tool are deleted with the tool, and for a group with the
group. The per-tool **switch** is in the config, because a capability's on/off
state already travels between machines for every other MCP server.

### 3. Rendering a request

- **Path and query.** The path template is split at `?`. A hole in the path
  part is replaced with the argument's value percent-encoded with no safe
  characters, so a value can never add a segment, a query or a host. The query
  part is `name=value` pairs; a pair whose value is one hole is dropped when
  the argument is absent, repeated for a list, and every pair is re-encoded.
  The URL is `base_url` (trailing `/` trimmed) + rendered path; a template that
  is not a path (`//host`, a scheme) is refused when the tool is saved.
- **Body.** With a body template, each hole outside a JSON string is replaced
  by the argument's JSON encoding (`null` when absent), each hole inside a
  string by the value's JSON-escaped text, and the result must parse as JSON.
  With no template, a POST, PUT or PATCH sends the arguments no path, query or
  header hole used as a JSON object (omitted when empty); GET and DELETE send
  no body.
- **Headers.** Group headers, then the tool's (holes rendered as text), then
  the auth header — added last so no tool header can replace it.
- **A hole naming no argument** of the schema is refused when the tool is
  saved; a required argument missing at call time returns an in-band tool
  error naming it.

### 4. Making the request

- `httpx.AsyncClient`, one per call, `follow_redirects=False` (a 3xx is
  returned to the agent as a result, never followed — the auth header is not
  carried to a place nobody configured), timeout `timeout_seconds`.
- The body is read by streaming and cut at **1 MiB**; the result says it was
  truncated.
- The result is one text content: `HTTP <status> <reason>`, a blank line and
  the body as text. A status of 400 or more sets `isError`. A connection
  failure is an in-band error naming the host and the error class; a timeout
  raises `UpstreamTimeout`, so the invocation log records `timeout`.
- **The secret is masked.** Any occurrence of the secret's value in the
  returned text is replaced with `***` before it leaves the adapter; the value
  is never in a description, schema, log line, invocation row or audit record.
- **SSRF.** The base URL is an endpoint the user configures as their own, like
  an HTTP MCP upstream, so calls to it are exempt from the SSRF guard
  (Principles → Network defaults). Fetching an OpenAPI document **from a URL
  typed into the import form** is a fetch on the user's behalf and goes
  through `ssrf_guard` first; a spec on a private host is imported as a file.
  The fetch is capped at 5 MiB and 20 s, and follows no redirect to a host the
  guard refuses.

### 5. The secret boundary

The destination is the group (`kind="mcp_server"`, its uid, its name) and the
**target** is `http_api <base_url>`; the slot is the auth header's name. So a
new binding, a moved base URL and a renamed header each ask a person again.
A standalone secret is never "freshly supplied", so binding one always waits
for an approval (unless the protection is off). The adapter is built by the
supervisor, which already materialises refs through the guarded resolver with
the destination; a withheld secret surfaces to the agent as
`SECRET_BINDING_PENDING`, and to the page as the group's
`secret_state: "pending_approval"` with the approval ids. Test in the drawer
resolves through the same resolver and destination.

### 6. The per-tool gate in the gateway

`application/mcp/gateway_tool_gate.py` computes, per session call, the
namespaced names hidden from this agent: every `http_api` tool switched off,
and every tool whose override does not admit the session's agent. `tools/list`
and `coffer__search_tools` drop them; `tools/call` on one records `denied` and
answers TOOL_DISABLED, exactly as a disabled capability does (spec mcp-gateway
"Toggle individual capabilities").

### 7. Annotations

`DiscoveredTool` gains `annotations`, read from each upstream tool and written
into the gateway's `tools/list` entry. The HTTP API adapter sets
`readOnlyHint: true` for a tool that does not change data and
`readOnlyHint: false, destructiveHint: true` for one that does.

### 8. OpenAPI import

`domain/mcp/openapi_import.py` (pure) reads an OpenAPI 3.0 or 3.1 document
already parsed into a mapping: `servers[0].url` (joined to the source URL when
relative) is the suggested base URL; the first `http`/`bearer` or `apiKey` in
`header` security scheme is the suggested auth header and prefix; each
operation becomes a draft tool — name from `operationId` (snake_cased, 40
characters, de-duplicated with a numeric suffix; `<method>_<path words>` when
absent), description from `summary`/`description`, path and query holes from
the parameters, local `#/components/...` `$ref`s resolved (a cycle is cut to
`{}`), and a JSON request body as one `body` argument with the body template
`{body}`. Path-level and operation-level parameters merge. Header and cookie
parameters are left to the group's headers. Operation key: `"<METHOD> <path>"`.

**Re-import.** Added = operations in the document that are neither a tool's
`operation` nor in `source.skipped`; removed = tools whose `operation` is no
longer in the document (a hand-made tool is never removed); kept = the rest.
The preview lists all three and changes nothing. Applying it deletes the
removed tools (and their reach rows), adds the chosen added operations as
tools (switched on) and records the others as skipped, refreshes each kept
tool's request from the document while keeping its switch, changes-data flag
and reach override, and stamps `fetched_at`. A `file` source needs the file
again; a `url` source is fetched again.

### 9. Surfaces

REST (owned by mcp-gateway), all under `/api/v1`, groups addressed by their
fixed **name**:

| Route | Does |
| --- | --- |
| `GET /custom-tools` | every group, failing first (`CustomToolGroupListOut`) |
| `POST /custom-tools` | create a group, with its tools (`CustomToolGroupIn` → 201 `CustomToolGroupOut`) |
| `GET /custom-tools/{name}` | one group, with its 24-hour summary and tools |
| `PATCH /custom-tools/{name}` | description, base URL, headers, auth, timeout |
| `DELETE /custom-tools/{name}` | delete the group (204) |
| `POST /custom-tools/{name}/tools` | add one tool |
| `PATCH /custom-tools/{name}/tools/{tool}` | change one tool (request, switch, flag) |
| `DELETE /custom-tools/{name}/tools/{tool}` | remove one tool |
| `PUT /custom-tools/{name}/tools/{tool}/reach` | `{agents: [uid] \| null}` — set or clear the override |
| `POST /custom-tools/{name}/test` | `{tool, arguments}` — run a draft tool once, save nothing |
| `POST /custom-tools/openapi` | `{url}` or `{document, filename}` — read a spec into draft tools |
| `POST /custom-tools/{name}/reimport/preview` | `{document?}` — added / removed / kept |
| `POST /custom-tools/{name}/reimport` | `{document?, add: [key]}` — apply |

Enable/disable and the group's reach use the kind-agnostic resource routes a
server already uses (`/resources/mcp_server/{uid}/enable|disable|scope`).

A group's **health** is `off` (disabled), `failing` (its last call in 24 h
failed or timed out), `attention` (its secret is missing or waits for
approval), `healthy` (its last call succeeded) or `idle` (no call in 24 h);
the list sorts failing, attention, healthy, idle, off. The summary is calls and
failures in the last 24 hours, per group and per tool, from `mcp_invocations`.

CLI (`coffer tool`, following the kind grammar in the CLI reference: a group
per kind, the lifecycle verbs, a nested group for the parts):
`list`, `show`, `add` (with `--openapi URL|FILE` to import), `edit`, `rm`,
`enable`, `disable`, `scope`, `reimport`, and `coffer tool op add|edit|rm|
enable|disable|scope|test` for one tool. A change that waits for an approval
exits 9, or waits with `--wait`, as every other `add`/`edit` does.

The MCP servers page and `coffer mcp` keep listing every `mcp_server`; the web
list and its Add dialog leave `http_api` servers out, and an `http_api`
server's MCP-server address redirects to its Custom tools page.

## Risks

- **An agent can register a group whose base URL it controls and bind a
  secret to it.** That is exactly the case the boundary holds for a person.
- **A body can echo the secret in a transformed form** (base64, split). Masking
  covers the exact value only; the header is sent to the configured base URL
  and nowhere else.
- **DNS rebinding on the OpenAPI fetch** — the residual risk accepted for the
  SSRF guard everywhere (Security → Outbound requests).
