## ADDED Requirements

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
failing calls (with **View calls**, which opens Activity on its calls, and the daemon's hand-off), a group that is
off (Turn on), a secret missing (Add secret, Choose another, no hand-off) and a
secret waiting for approval (Open approvals, the only button). Re-import is a
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
secret's own name, as Set, Missing or Waiting for approval with a View in
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

## MODIFIED Requirements

### Requirement: Add MCP servers from one paste box
The MCP servers page MUST carry one **Add server** action, and no separate
paste-JSON action. It opens a modal whose first step is one paste box that
recognises what was pasted, so the user can paste whatever an MCP server's
README gives them:

- an `mcpServers` JSON block, or a single server object, holding one server or
  many;
- Codex TOML `[mcp_servers.<name>]` tables, one or many;
- a command line, including `claude mcp add …` and `codex mcp add …`, which
  becomes a stdio server — its name, environment (`-e` / `--env`) and command
  taken from the command, a plain command's name suggested from its package;
- a URL, which becomes a Streamable HTTP server, its name suggested from the
  host.

One recognised server MUST open the manual form prefilled with it; several MUST
open the review step. The same dialog carries **Import from agents** as a link,
which lists the direct MCP entries in the agents' own config files to adopt
([agent-registry](../agent-registry/spec.md) "Adopt a direct MCP entry into Coffer"); it is not a
second button on the page. The dialog adds MCP servers only: it offers no
custom tool (an HTTP API imported from an OpenAPI document or defined by hand),
which is added on the Custom tools page (see "Manage custom tool groups on their
own page").

The review step covers every server's environment values and, for an HTTP
server, the values of its `headers` too, read with the same secret detection as
the environment rather than ignored (a header and an environment entry of the
same name are one header, the `headers` value winning). The user confirms which
values are secrets; secrets MUST be lifted into the encrypted secret store
with only their refs kept in the resource config, and each server MUST be
registered before its secrets are written, so a failed registration leaves no
orphan secret entry. The user also chooses the servers' reach there.

The review step MUST show each server's name as the name it will keep: it
cannot be changed after registration
([mcp-gateway](../mcp-gateway/spec.md) "Manage MCP servers as resources"). Each
name is taken from its key, table or command, normalised to the pattern
mcp-gateway allows — lower case, other characters turned into hyphens — and can
be corrected in the review before it is added. A name longer than 24
characters MUST be flagged, before submit, with a message naming the limit, and
the dialog MUST NOT send that server's registration until the name is shortened.

#### Scenario: MCP server registration round-trip via JSON import
- **GIVEN** the user opens the Add server dialog from the MCP servers page
- **WHEN** they paste the standard `mcpServers` JSON holding one server and add it from the prefilled form
- **THEN** the app posts the server to `/api/v1/resources`, then writes any secret env values to `/api/v1/secrets` (register-first ordering avoids orphan secret entries when registration fails)
- **AND** on success the dialog closes and the app navigates to the server's detail page `/mcp-servers/<name>` showing the Overview tab
- **AND** the new server appears on the MCP servers list with health "unknown" then "healthy" within 10 seconds

#### Scenario: add-server form navigates to detail then back to list shows card
- **GIVEN** the user completes the Add server dialog for a new MCP server
- **WHEN** they are taken to the server's detail page and then navigate back to `/mcp-servers`
- **THEN** the server appears in the MCP servers list

#### Scenario: a pasted HTTP server's headers are reviewed for secrets
- **GIVEN** the user pastes an `mcpServers` block holding an HTTP server with a `headers` object that carries an `Authorization` value
- **WHEN** the review step is shown and confirmed
- **THEN** the header is offered as a secret, its value is written to the secret store, and the registered server keeps only its ref (`secret_refs`), never the value in `headers`

#### Scenario: the import review shows each server's fixed name
- **GIVEN** the user pastes an `mcpServers` block holding one server keyed `My Server` and one keyed with a 30-character name
- **WHEN** the review step is shown
- **THEN** each server's name is shown with a note that it cannot be changed after registration, the first normalised to `my-server`, and the 30-character name is flagged with the 24-character limit
- **AND** no request is sent to `/api/v1/resources` for the flagged server until its name is shortened in the review

#### Scenario: pasting JSON with three servers opens the review
- **GIVEN** the Add server dialog open on its paste box
- **WHEN** the user pastes an `mcpServers` block holding three servers
- **THEN** the dialog recognises three servers and opens the review step listing all three with their detected secrets and a reach choice
- **AND** confirming registers the three servers, each before its secrets are written

#### Scenario: pasting a command line prefills a stdio server
- **GIVEN** the Add server dialog open on its paste box
- **WHEN** the user pastes `claude mcp add github -e GITHUB_TOKEN=ghp_x -- npx -y @modelcontextprotocol/server-github`
- **THEN** the manual form opens prefilled as a stdio server named `github` with command `npx`, arguments `-y @modelcontextprotocol/server-github` and `GITHUB_TOKEN` offered as a secret

#### Scenario: pasting a URL prefills a Streamable HTTP server
- **GIVEN** the Add server dialog open on its paste box
- **WHEN** the user pastes `https://mcp.example.com/mcp`
- **THEN** the manual form opens prefilled as a Streamable HTTP server with that URL and a name suggested from the host

#### Scenario: pasting Codex TOML reads its server tables
- **GIVEN** the Add server dialog open on its paste box
- **WHEN** the user pastes a `[mcp_servers.docs]` table with a command, arguments and an `env` table
- **THEN** the manual form opens prefilled as a stdio server named `docs` with that command, arguments and environment, the secret-looking values offered as secrets

#### Scenario: the add dialog links to importing from agents
- **GIVEN** the MCP servers page
- **WHEN** it renders and the user opens Add server
- **THEN** the page carries one Add server action and no separate paste-JSON action, and the dialog carries an Import from agents link
- **AND** the dialog offers no custom tool, neither an OpenAPI import nor a hand-made HTTP request

### Requirement: Lay out every detail page's tabs alike
Every detail page MUST lay its tabs out the same way as every other. What a tab
shows belongs to the capability that owns that kind — the agent detail page's
tabs are [agent-registry](../agent-registry/spec.md)'s; this capability owns
only that they are tabs on a detail page laid out like every other.

Every detail page MUST put its tab in the path: `/<kind>/<id>/<tab>`, with the
default tab at the bare `/<kind>/<id>`, never in a `?tab=` query. A list page
with no detail to nest under (Sync, Activity) carries its tab in the query
instead, as `?tab=`, with the default tab at the bare address. The `<id>` is
the resource's name where the kind's name is fixed and unique within the kind —
skills (`/skills/<name>`), MCP servers (`/mcp-servers/<name>`) and custom tool
groups (`/custom-tools/<group>`), which are `mcp_server` resources — the agent's
type for agents (`/agents/<type>`), and the command for CLIs (`/clis/<command>`).
A kind whose name can be renamed — model providers, channels, knowledge
collections, memory partitions — MUST keep its immutable `uid` as the `<id>`
(`/model-providers/<uid>`), because a renamed name would break every
address to it. A page opened from a tab (a plugin, a direct MCP entry, an
unmanaged skill) nests under that tab's path.

#### Scenario: detail pages share one tab layout
- **GIVEN** two detail pages of different kinds
- **WHEN** each is opened with a tab named in its URL
- **THEN** each renders its tabs in the shared tab strip with that tab selected
- **AND** switching tab rewrites the URL the same way on both

#### Scenario: a detail tab lives in the path
- **GIVEN** a skill named `release-notes` and an MCP server named `github`
- **WHEN** the user opens the skill's Delivery tab and the server's Tools tab
- **THEN** the addresses read `/skills/release-notes/delivery` and `/mcp-servers/github/tools`
- **AND** `/skills/release-notes` and `/mcp-servers/github` open each page on its default tab

#### Scenario: a renamable kind keeps its uid in the address
- **GIVEN** a model provider renamed from `work` to `work-proxy`
- **WHEN** the user follows an address to it saved before the rename
- **THEN** the address still opens that provider, because it carries the uid and not the name

### Requirement: Keep the sidebar to its fourteen entries
The sidebar's entries MUST be exactly these, at these routes: one ungrouped entry
and five groups — fourteen today, and no fifteenth without a spec change.
Settings is not an entry: it is a modal opened from the sidebar footer (see
"Open Settings as a modal from the sidebar footer"). Usage is not an entry:
it is a tab of Model providers (see provider-switching "Show metered usage on a
Usage tab of Model providers"). Custom
tools and CLIs are specified by "Manage custom tool groups on their own page" and "Show
every CLI a skill requires on the CLIs page". An
entry whose experimental feature is switched off (spec
[experimental-features](../experimental-features/spec.md) "Close every surface of a switched-off feature")
MUST be left out, and MUST appear on the next render after the feature is
switched on. Model providers, Usage tab included, belongs to `models`, Knowledge to `knowledge`,
Memory to `memory` and Sync to `sync`; every other entry, Conversations and
Channels included, is owned by no feature and is always there:

```
  Overview         /                  — the landing page
 AGENTS
  Agents           /agents            — the consumers (Bot icon)
  Model providers  /model-providers   — the endpoints agents' models are served from, and what requests through Coffer cost (tabs Providers | Usage)
 RUN
  Conversations    /conversations     — the conversations the IM bots started, each opened in the agent's own terminal
  Channels         /channels          — the IM bots agents answer on
 CAPABILITIES
  MCP servers      /mcp-servers       — the aggregated upstream servers
  Custom tools     /custom-tools      — HTTP APIs Coffer serves to agents as tools, in groups
  Skills           /skills            — what Coffer delivers to agents
  CLIs             /clis              — the command-line tools skills require
 CONTEXT
  Knowledge        /knowledge         — the collections under ~/.coffer/vault/knowledge/
  Memory           /memory            — the partitions aggregated from the agents' own stores
 SYSTEM
  Secrets          /secrets           — every stored secret and what uses it
  Activity         /activity          — what changed, what was called, what broke
  Sync             /sync              — converging this vault with a git remote
```

#### Scenario: cold-start renders authenticated content
- **GIVEN** the user has never opened Coffer (localStorage is empty, no daemon.json in user HOME yet)
- **AND** every experimental feature is switched on
- **AND** `coffer daemon start` is running (so daemon.json exists in user HOME)
- **WHEN** they navigate to `http://localhost:5173/` in a real browser
- **THEN** the index renders the Overview page at `/`, with the sidebar and main content area, within 2 seconds
- **AND** the main content shows the Overview page (no generic error card)
- **AND** the sidebar lists exactly Coffer's operational surfaces — Overview; Agents, Model providers; Conversations, Channels; MCP servers, Custom tools, Skills, CLIs; Knowledge, Memory; Secrets, Activity, Sync — with Overview under no heading and the rest grouped under "Agents", "Run", "Capabilities", "Context" and "System" headings, with no other entry
- **AND** no navigation entry is Settings; a labelled Settings row sits at the bottom of the sidebar

#### Scenario: a switched-off feature leaves the sidebar
- **GIVEN** a sidebar entry owned by a registered experimental feature that is switched off
- **WHEN** the app shell is rendered
- **THEN** the sidebar leaves that entry out and lists every other entry under its heading
- **AND** with every feature switched on, the sidebar lists all fourteen entries
- **AND** with the four features switched off, it lists only Overview, Agents, Conversations, Channels, MCP servers, Custom tools, Skills, CLIs, Secrets and Activity

## REMOVED Requirements

### Requirement: Manage custom tool groups on one page
**Reason**: Renamed to "Manage custom tool groups on their own page": the group's page has Overview and Tools tabs again, its Overview showing what an MCP server's does and its Tools tab each tool's exposure.
**Migration**: Cite the new title.
