## MODIFIED Requirements

### Requirement: Manage custom tool groups on their own page
The Custom tools page (`/custom-tools`, under Capabilities) MUST manage custom
tools, which have one type in 1.0 — **HTTP API**: a tool is one HTTP request
Coffer makes on an agent's behalf — and MUST manage them in **groups**. A group
is one `mcp_server` resource of the HTTP API transport, served through the same
gateway as every other MCP server, and carries:

- a **name**, fixed once the group exists, which is the prefix every agent sees:
  a tool reaches agents as `<group>__<tool>`, under the same name rules as any
  MCP server ([mcp-gateway](../mcp-gateway/spec.md) "Manage MCP servers as resources");
- a **description** of what its API is for, which agents read when they search
  for a tool ([mcp-gateway](../mcp-gateway/spec.md) "Describe a custom-tool group"),
  shown first in the group's definition;
- a shared **base URL** its tools' paths are relative to;
- **header rows** — each a name and a value that is plain text or one stored
  secret holding the credential alone, behind the row's auth scheme (a bearer
  token is stored as `<token>` with the scheme **Bearer**), chosen by its name on the Secrets page
  or pasted to be saved there with the group (see "Choose secrets in one field
  and one set of rows"): Coffer's gateway adds each header when it calls the API,
  once a person has approved a secret for the group's host
  ([mcp-gateway](../mcp-gateway/spec.md) "Wait for approval before a custom tool
  sends its secret"), and neither a secret header's value nor the secret's
  reference is ever part of what an agent sees or sends;
- a **reach** (Off, All agents or Chosen agents), which every tool in it follows: a
  tool has no reach of its own.

Each tool in a group MUST carry its own **on/off** switch and a
**changes data** flag — on by default for every method but
GET, and editable — which the gateway passes to agents as the tool's MCP
annotations (`readOnlyHint` false and `destructiveHint` true when it changes
data, `readOnlyHint` true otherwise), so each agent's own approval prompts apply
to it. The page MUST list the groups under Needs attention, Healthy and Off, the failing
ones first, each showing what is wrong in place of its tools, and an Off group
leaves its reach column empty. Its header MUST carry one action, **Add custom tool**,
whose flow asks first for the group, in a select you can type into that starts
on **New group** and lists every existing group with its source, tool count and
description. An existing group MUST only take a request
added by hand, which uses that group's base URL and secret; only a **new** group
offers the two ways in:

- **Import an OpenAPI spec** — from a URL or a file, into the new group; the user
  ticks which operations become tools, reads ticked and operations that change
  data unticked, and a review lists the ticked ones as the tools to create and the
  rest as **Skipped** before **Create group with N tools**. A spec that cannot
  be read says where: an unparseable file shows the lines around the failure, and a
  URL that does not answer names the reason (not found, refused, timed out), keeps
  **Review tools** off and offers Retry and the daemon's hand-off. A group made by
  an import MUST offer **Re-import**, which reads the spec again and lists the
  change first — operations it would add (reads become tools, switched on;
  operations that change data are listed but not ticked), tools whose request
  the spec changed (each with the operation's old and new text), and tools it
  would remove — before anything changes;
  applying keeps every unchanged tool's switch as it was. The spec's own
  description starts the new group's description, which the user can change.
- **Add one request by hand** — the new group's name, description, base URL,
  header rows and reach, then its first request: method, path, headers, body template
  and arguments.

Every request form MUST end with a **Test** section, whose Run runs the request as the form
holds it once and shows the answer — the status and time in a block, the response
in a viewer under it — the API's error body, a timeout, a failed
connection (each of these two with the daemon's hand-off and, for a timeout,
**Change timeout**) or a response cut short; nothing — neither a new group nor a tool — is
saved until the form's **Add** or **Save**. A request of a group that is not saved
yet is tested without its secret (see [mcp-gateway](../mcp-gateway/spec.md) "Test
a custom tool request before its group is saved"). With no group yet the page
MUST show only a first-run panel, with Add custom tool in the header and in the
panel. A group's header MUST carry the same actions whatever its state — **Reach** (whose
Off turns the group off), **Edit group** and a **⋯** menu that holds only Delete
group… — and each problem is answered in a banner under it, never in the header:
failing calls (with **View calls**, which opens Activity on its calls, and the daemon's hand-off), a group that is
off (Turn on), a secret missing (Add secret, Choose another, no hand-off) and a
secret waiting for approval (Open approvals, the only button) and a secret
whose approval a person refused (Ask again, the only button: in the desktop app
it asks for Touch ID at once and approves, elsewhere the request goes back on
the approvals list). Re-import is a
button in the definition of an imported group.

A group's detail page (`/custom-tools/<group>/<tab>`) MUST carry, under its
header — its **reach** and a one-line summary of the last 24 hours (calls and
failures) — two tabs laid out like every other detail page's. **Overview** (the
default, at the bare `/custom-tools/<group>`) stacks the group's **definition**
(base URL, and the auth header with the name of the secret it is bound to), then
what an MCP server's Overview shows ("Open an MCP server on its Overview"):
**Last 24 hours** — the group's calls and errors with a table of the agents that
made them, and for a group that is on a View in Activity link to Activity's Tool
calls tab searching the group's name (for a group that is off, only its last
call and who made it); **Requires** — each secret its headers cite, named by the
secret's own name, as Set, Missing, Refused or Waiting for approval with a View in
Secrets link to `/secrets?q=<name>` (a group runs no command, so it has no
launcher row); and **Most-called tools** — the busiest four, read-only with no
switches, each marked when it sits behind search, with the rest one link away
("Show all N in Tools"). **Tools** (`/custom-tools/<group>/tools`) holds the
**tools table** — each tool's method and path, its switch, its changes-data flag
and its **exposure**, the same choice as an MCP server's Tools tab ("Auto ·
Listed", "Always listed", "Search only"; [mcp-gateway](../mcp-gateway/spec.md)
"Choose how each tool is exposed"), shown for a tool that is on while tool
tiering is on. The group's calls are read on the Activity page, not on the
group's page; the failing banner's View calls opens Activity's Tool calls tab
searching the group's name. Above the table one row
carries a search, which narrows the rows by tool name, and **Add request**, so
adding stays in view however many tools the group has. Tools are ticked with a
per-row checkbox (select-all in the header); while any is ticked a selection bar
replaces that row with **Turn on**, **Turn off** and, while the exposure column
shows, **Exposure**, acting on the ticked tools. Choosing
a tool opens its editor in a 640-wide **drawer** below the title bar, where the
request is edited — the headers the group already adds shown as "from the group",
no switch, which lives in the table — with **Delete tool** and Cancel
beside it, and its **Test** section under the fields runs the tool with sample
arguments and shows the response. Script tools are not offered: they are deferred past 1.0.
How the gateway runs an HTTP API tool is mcp-gateway's ([mcp-gateway](../mcp-gateway/spec.md)
"Serve an HTTP API as a group of custom tools", "Make a custom tool's request in
the gateway").

#### Scenario: importing an OpenAPI spec creates a group with the chosen operations
- **GIVEN** an OpenAPI document with five operations, three that read data and two that change it
- **WHEN** the user chooses Add custom tool and New group, imports the document as the group `invoices`, unticks one read, ticks one operation that changes data, and reviews
- **THEN** the reads started ticked and the operations that change data unticked, and the review lists the three ticked as the tools to create and the other two as Skipped
- **AND** nothing is created until Create group with 3 tools, which creates `invoices` with only those three and the spec's description, and opens its page

#### Scenario: re-importing a spec previews the operations it adds and removes
- **GIVEN** the `billing` group imported with three operations, one of them switched off
- **WHEN** the spec now has one of those operations removed and a new one added, and the user chooses Re-import
- **THEN** a preview lists the operation to add and the tool to remove, and nothing changes until the user confirms
- **AND** after confirming, the kept tools keep their switch
- **AND** an added operation that reads data becomes a tool, while one that changes data is listed but not added

#### Scenario: a hand-made request joins an existing group
- **GIVEN** the `billing` group
- **WHEN** the user chooses Add custom tool, defines one request by hand and picks `billing` as its group
- **THEN** the tool is added to `billing`, using its base URL and auth header
- **AND** the flow offers no Import an OpenAPI spec for `billing`, only for a new group

#### Scenario: a new group made by hand is saved with its first request
- **GIVEN** no group named `search-api`
- **WHEN** the user chooses Add custom tool, keeps New group and picks By hand, fills in `search-api`, its description and its base URL, chooses Create group, then fills in the first request and tests it
- **THEN** nothing is saved until the user chooses Add to search-api, which creates `search-api` with its description and that one tool
- **AND** the test ran without the group's secret

#### Scenario: the custom tools page with no group shows the first-run panel
- **GIVEN** no custom-tool group
- **WHEN** the user opens `/custom-tools`
- **THEN** the page shows no group list, only a first-run panel with Import an OpenAPI spec and Add one request by hand, and Add custom tool in the header and the panel

#### Scenario: an agent sees the group name as the tool prefix
- **GIVEN** the `billing` group with a tool named `list_invoices`, reaching Claude Code
- **WHEN** Claude Code lists or searches the gateway's tools
- **THEN** the tool is offered as `billing__list_invoices`

#### Scenario: the secret never reaches the agent
- **GIVEN** the `billing` group's auth header bound to a stored secret
- **WHEN** an agent calls `billing__list_invoices`
- **THEN** the gateway sends the request with the header's value added
- **AND** neither the tool's description and schema nor the result returned to the agent contains the secret's value or its reference

#### Scenario: the custom tools page lists groups by health
- **GIVEN** one group whose last call failed and two healthy groups
- **WHEN** the user opens `/custom-tools`
- **THEN** the failing group is listed first with its tools, and the page header carries one Add custom tool action whose flow asks for the group in a select that starts on New group and narrows the groups as the user types, and offers Import an OpenAPI spec and Add one request by hand, and no Script type

#### Scenario: a refused secret on a group's page offers Ask again
- **GIVEN** a group whose secret's approval a person refused
- **WHEN** its page is opened
- **THEN** a banner says the secret was refused, with Ask again as its only button, and no banner says it waits for approval
- **AND** pressing Ask again asks again for that approval

#### Scenario: a group's page has Overview and Tools tabs
- **GIVEN** the `billing` group with three tools and a call in the last 24 hours
- **WHEN** the user opens `/custom-tools/billing`, switches to Tools and chooses one tool
- **THEN** the page opens on Overview with the definition and the bound secret's name, under a header with the reach and a one-line 24-hour summary, and its tabs are Overview and Tools and no other
- **AND** Tools, at `/custom-tools/billing/tools`, shows the tools table, and the tool opens in a drawer with its request and Test without changing the address

#### Scenario: a group's Overview shows what it requires, its busiest tools and the last 24 hours
- **GIVEN** the `billing` group, on, whose `Authorization` header is bound to the stored secret `billing-token`, with 31 calls from Claude Code in 24 hours, most of them to `get_invoice`
- **WHEN** its Overview opens
- **THEN** it shows Last 24 hours with the totals, the table of the agents that called it and View in Activity opening `/activity?tab=mcp&q=billing`
- **AND** Requires lists `billing-token` as Set, linked to `/secrets?q=billing-token`, with no launcher row
- **AND** Most-called tools lists `get_invoice` first, without switches

#### Scenario: a custom tool's exposure is set on the group's Tools tab
- **GIVEN** the `billing` group, with tool tiering on, whose `get_invoice` is left to Auto and listed and whose `create_invoice` is pinned
- **WHEN** the user opens its Tools tab and sets `get_invoice` to Search only
- **THEN** the rows read "Auto · Listed" and "Always listed" before the change, and the change is saved as `get_invoice`'s exposure on the group without opening the tool's drawer

#### Scenario: a tool's drawer has no switch, and Delete tool is outlined
- **GIVEN** the `billing` group with a tool
- **WHEN** the user opens the tool
- **THEN** the drawer shows no On switch, shows the group's header as from the group, and offers Delete tool and Cancel

#### Scenario: a spec that does not parse shows the lines around the failure
- **GIVEN** the import step with a file whose YAML breaks on line 3
- **WHEN** the file is read
- **THEN** the step says it couldn't read the spec and why, and shows the file with line 3 marked

#### Scenario: an unreachable spec URL names the reason and keeps Review tools off
- **GIVEN** the import step with a URL the daemon cannot reach
- **WHEN** the user chooses Load
- **THEN** the step names the host and the reason, marks the URL invalid, offers Retry and a hand-off, and Review tools stays off

#### Scenario: a tool that changes data is annotated for the agent
- **GIVEN** a group with a `GET /invoices` tool and a `POST /refunds` tool, and the user turning the changes-data flag off on a third, `POST /search`
- **WHEN** an agent lists the group's tools
- **THEN** `refunds` carries `readOnlyHint` false and `destructiveHint` true, while `invoices` and `search` carry `readOnlyHint` true, so the agent's own approval applies to `refunds`

#### Scenario: the tools table has no reach column and is searched by name
- **GIVEN** the `billing` group with the tools `list_invoices`, `refund` and `void_invoice`
- **WHEN** the user types `invoice` in the search above the tools table
- **THEN** only `list_invoices` and `void_invoice` are listed, no row carries a reach control, and Add request sits beside the search above the table

### Requirement: Open an MCP server on its Overview
An MCP server's detail page MUST open on a primary "what is this server doing?"
Overview, before the per-capability tabs, and its tabs — Overview, Tools,
Resources, Prompts — MUST carry no counts. Under the banner the
Overview stacks **Last 24 hours** (the server's calls and errors, with a table of
the agents that made them and a line for a session that named no agent; for a
server that is off, only its last call and who made it; for a server that is on,
a View in Activity link to Activity's Tool calls tab searching the server's name; the server's page has no calls tab, because calls are read on the Activity page), **Requires** — what the
server's command and settings need from this machine (see mcp-gateway "Show what
an MCP server requires"): the launcher as a row reading "Found · <version>" or
"Not found" with a View in CLIs link to `/clis/<launcher>`, and each secret as
named by the secret's own name (the setting that carries it is its tooltip) as
Set, Missing, Refused or Waiting for approval with a View in Secrets link to
`/secrets?q=<name>`, the Secrets list searched for it —
and **Most-called tools**: the busiest four, read-only with no switches, each
marked when it sits behind search, with the rest one link away ("Show all N in
Tools").

#### Scenario: a server's detail page opens on its Overview
- **GIVEN** a registered MCP server
- **WHEN** its detail page is opened with no tab named in the URL
- **THEN** the Overview tab is the selected tab and its content is shown
- **AND** the Tools, Resources and Prompts tabs follow it, and no other tab

#### Scenario: the Overview stacks the last 24 hours by agent, what it requires and the busiest tools
- **GIVEN** a server with 312 calls in 24 hours, a launcher that is found, one secret that is missing and five tools
- **WHEN** its Overview opens
- **THEN** it shows the totals and the table of the agents that called it, then Requires with the launcher found and linked to its CLI page and the secret Missing under its own name and linked to Secrets searched for it, then the four busiest tools without switches and a link to all five
- **AND** no Agents section and no reach note sit on it

#### Scenario: the 24-hour block opens the server's own call history
- **GIVEN** a server named `sentry` that is on, with calls in the last 24 hours
- **WHEN** the user chooses View in Activity on its Overview
- **THEN** Activity opens on its Tool calls tab searching `sentry`, at `/activity?tab=mcp&q=sentry`
- **AND** the server's page offers no Invocations tab
