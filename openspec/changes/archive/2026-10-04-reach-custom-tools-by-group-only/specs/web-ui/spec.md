## ADDED Requirements

### Requirement: Select several custom tool groups and narrow them to one agent
A custom-tool group's row MUST show its checkbox on hover or focus, and on every
row once any is ticked. Ticking a row puts the selection bar at the top of the
list in place of the search: "N of M selected", **Reach** (the bulk control of
"Apply reach to a whole selection"), **Delete** with its confirmation, and a clear
(×); a select-all row ticks every listed group, and Esc clears the selection.
Delete removes each group with everything in it, and a group whose page is open
closes. The list MUST accept the `agent` query parameter (`/custom-tools?agent=<uid>`)
and then list only the groups that reach that agent: a Reach filter under the
search — every group, or those reaching one agent — reads and writes it, as on the
MCP servers and Skills lists.

#### Scenario: ticking a group puts the selection bar at the top
- **GIVEN** the Custom tools list with three groups
- **WHEN** the user ticks two rows and chooses Reach, Off and Apply
- **THEN** the bar read "2 of 3 selected" with Reach, Delete and a clear control, both groups are now Off, and the selection is cleared

#### Scenario: the list narrows to one agent
- **GIVEN** a group that reaches only Claude Code and another that reaches every agent
- **WHEN** the user opens `/custom-tools?agent=<Codex uid>`
- **THEN** only the group that reaches every agent is listed, with Codex chosen in the Reach filter

### Requirement: Manage custom tool groups on their own page
The Custom tools page (`/custom-tools`, under Capabilities) MUST manage custom
tools, which have one type in 1.0 — **HTTP API**: a tool is one HTTP request
Coffer makes on an agent's behalf — and MUST manage them in **groups**. A group
is one `mcp_server` resource of the HTTP API transport, served through the same
gateway as every other MCP server, and carries:

- a **name**, fixed once the group exists, which is the prefix every agent sees:
  a tool reaches agents as `<group>__<tool>`, under the same name rules as any
  MCP server ([mcp-gateway](../mcp-gateway/spec.md) "Manage MCP servers as resources");
- a shared **base URL** its tools' paths are relative to;
- **header rows** — each a name and a value that is plain text or one stored
  secret holding the WHOLE header value (nothing is put around it, so a bearer
  token is stored as `Bearer <token>`), chosen by its name on the Secrets page
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
whose flow asks first for the group. An existing group MUST only take a request
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
  applying keeps every unchanged tool's switch as it was.
- **Add one request by hand** — the new group's name, base URL, header rows and
  reach, then its first request: method, path, headers, body template
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
failing calls (with a link to Activity and the daemon's hand-off), a group that is
off (Turn on), a secret missing (Add secret, Choose another, no hand-off) and a
secret waiting for approval (Open approvals, the only button). Re-import is a
button in the definition of an imported group.

A group's detail page (`/custom-tools/<group>`, and no other route) MUST be one
page with no tabs: the group's **definition** (base URL, and the auth header with
the name of the secret it is bound to), its **reach**, a one-line summary of the
last 24 hours (calls and failures), and the **tools table** — each tool's
method and path, its switch and its changes-data flag. Above the table one row
carries a search, which narrows the rows by tool name, and **Add request**, so
adding stays in view however many tools the group has; the count of tools that
are on and **All on** / **All off** keep acting on the whole group. Choosing
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
- **AND** nothing is created until Create group with 3 tools, which creates `invoices` with only those three and opens its page

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
- **WHEN** the user chooses Add custom tool, picks New group and By hand, fills in `search-api` and its base URL, chooses Create group, then fills in the first request and tests it
- **THEN** nothing is saved until the user chooses Add to search-api, which creates `search-api` with that one tool
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
- **THEN** the failing group is listed first with its tools, and the page header carries one Add custom tool action whose flow asks for an existing or new group and offers Import an OpenAPI spec and Add one request by hand, and no Script type

#### Scenario: a group's page is one page with a tool drawer
- **GIVEN** the `billing` group with three tools
- **WHEN** the user opens `/custom-tools/billing` and chooses one tool
- **THEN** the page shows the definition with the bound secret's name, the reach, a one-line 24-hour summary and the tools table, with no tabs
- **AND** the tool opens in a drawer with its request and Test, and the address stays `/custom-tools/billing`

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


## REMOVED Requirements

### Requirement: Reach an item inside a group through the group's reach
**Reason**: A custom tool no longer has a reach of its own; it follows its group (mcp-gateway "Switch off one custom tool").
**Migration**: None in the UI. A tool that must reach fewer agents than the rest of its group is switched off, or moved to a group of its own.

### Requirement: Manage custom tools on their own page
**Reason**: Restated as "Manage custom tool groups on their own page" without the tool's own reach (its reach scenarios go with it) and with the tools table's search and Add request above the table.
**Migration**: None; the page itself is unchanged apart from those.
