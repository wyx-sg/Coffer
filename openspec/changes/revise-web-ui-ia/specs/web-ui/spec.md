## RENAMED Requirements

- FROM: `### Requirement: Import MCP servers from pasted JSON`
- TO: `### Requirement: Add MCP servers from one paste box`

- FROM: `### Requirement: Reject malformed server JSON in the dialog`
- TO: `### Requirement: Explain unreadable pasted input in the dialog`

- FROM: `### Requirement: Keep the sidebar to its eleven entries`
- TO: `### Requirement: Keep the sidebar to its fifteen entries`

- FROM: `### Requirement: Keep retention and prune on the Data tab`
- TO: `### Requirement: Group the Data tab by what kind of data it is`

## REMOVED Requirements

### Requirement: Keep the daemon out of the user's view
**Reason**: A daemon that is never shown leaves the user no way to see which build is answering,
on which port, since when, or whether it will start at login, short of a terminal. The offline
banner reported only the failure case, and "healthy" could not be told apart from "not yet
known". The daemon's state is now shown at all times in the shell footer and on Settings →
Daemon; starting it stays automatic.
**Migration**: See "Show the daemon's state in the shell footer" and "Show and manage the daemon
on Settings → Daemon". The acceptance marker for "settings shows no daemon tab and no daemon
status" is deleted with this requirement.

### Requirement: Open the app on the Agents page
**Reason**: The app now lands on Overview, which shows the whole vault before any one part of it.
**Migration**: See "Open the app on Overview". `/agents` keeps its route. The acceptance marker for
"the index opens the Agents page" moves to "the index opens Overview".

### Requirement: Leave daemon controls to the CLI
**Reason**: Token rotation moves into Settings › Security and the port becomes editable on
Settings → Daemon now that the daemon is visible; only stopping the daemon stays on the command
line.
**Migration**: See "Keep daemon shutdown on the command line", "Show and manage the daemon on
Settings → Daemon" and "Show, copy and rotate the access token on Settings › Security". The acceptance marker for "settings drops the confusing controls" moves to
"settings offers no shutdown control".

### Requirement: Let the user choose when the daemon runs
**Reason**: The Start at login card moves from the General tab to the Daemon tab, beside the rest
of the daemon's state.
**Migration**: See "Set when the daemon runs on the Daemon tab". The acceptance marker for "the
general tab sets when the daemon runs" moves to "the settings daemon tab sets when the daemon runs".

### Requirement: Group the sidebar by role
**Reason**: Three role groups put seven entries under Resources once Secrets arrives, and nine
once Rules and Sources do; "resource" is the framework's word, not one a user navigates by. The
sidebar is now grouped by what the user comes to do, in five groups.
**Migration**: See "Group the sidebar by what the user comes to do". The acceptance marker for
"the sidebar groups agents, resources and system by role" moves to "the sidebar groups entries by
what the user comes to do".

### Requirement: Hold one Resources entry per listed resource kind
**Reason**: There is no Resources group any more; each listed resource kind still has one entry,
filed under the group that names what the user does with it.
**Migration**: See "Give each listed resource kind one sidebar entry". The acceptance marker for
"resources holds one entry per kind with a list" moves to "each listed resource kind has one
sidebar entry".

## MODIFIED Requirements

### Requirement: Keep the sidebar to its fifteen entries
The sidebar's entries MUST be exactly these, at these routes: one ungrouped entry
and five groups — fifteen today, and no sixteenth without a spec change.
Settings is not an entry: it is a modal opened from the sidebar footer (see
"Open Settings as a modal from the sidebar footer"). Usage's content is specified
with the change that meters it; this requirement fixes only its place. Custom
tools and CLIs are specified by "Manage custom tools on their own page" and "Show
every CLI a skill requires on the CLIs page". An
entry whose experimental feature is switched off (spec
[experimental-features](../experimental-features/spec.md) "Close every surface of a switched-off feature")
MUST be left out, and MUST appear on the next render after the feature is
switched on. Knowledge, Memory and Sync are ordinary entries, owned by no
experimental feature:

```
  Overview         /                  — the landing page
 AGENTS
  Agents           /agents            — the consumers (Bot icon)
  Model providers  /model-providers   — the endpoints agents' models are served from
 RUN
  Conversations    /conversations     — every conversation Coffer runs, from channels and from Coffer itself
  Channels         /channels          — the IM bots agents answer on
 CAPABILITIES
  MCP servers      /mcp-servers       — the aggregated upstream servers
  Custom tools     /custom-tools      — HTTP APIs Coffer serves to agents as tools, in groups
  Skills           /skills            — what Coffer delivers to agents
  CLIs             /clis              — the command-line tools skills require
 CONTEXT
  Knowledge        /knowledge         — the collections under ~/.coffer/knowledge/
  Memory           /memory            — the partitions aggregated from the agents' own stores
 SYSTEM
  Secrets          /secrets           — every stored secret and what uses it
  Activity         /activity          — what changed, what was called, what broke
  Usage            /usage             — token use and remaining quota per agent
  Sync             /sync              — converging this vault with a git remote
```

#### Scenario: cold-start renders authenticated content
- **GIVEN** the user has never opened Coffer (localStorage is empty, no daemon.json in user HOME yet)
- **AND** every experimental feature is switched on
- **AND** `coffer daemon start` is running (so daemon.json exists in user HOME)
- **WHEN** they navigate to `http://localhost:5173/` in a real browser
- **THEN** the index renders the Overview page at `/`, with the sidebar and main content area, within 2 seconds
- **AND** the main content shows the Overview page (no generic error card)
- **AND** the sidebar lists exactly Coffer's operational surfaces — Overview; Agents, Model providers; Conversations, Channels; MCP servers, Custom tools, Skills, CLIs; Knowledge, Memory; Secrets, Activity, Usage, Sync — with Overview under no heading and the rest grouped under "Agents", "Run", "Capabilities", "Context" and "System" headings, with no other entry
- **AND** no navigation entry is Settings; a labelled Settings row sits at the bottom of the sidebar, above the daemon status

#### Scenario: a switched-off feature leaves the sidebar
- **GIVEN** a sidebar entry owned by a registered experimental feature that is switched off
- **WHEN** the app shell is rendered
- **THEN** the sidebar leaves that entry out and lists every other entry under its heading
- **AND** with a registry that names no feature, the sidebar lists all fifteen entries

### Requirement: Give every scoped resource kind its own list surface
Every scoped resource kind MUST have its own list surface, so the navigation and
each list page carry no kind-specific branch.

#### Scenario: every resource entry opens a list page of its own
- **GIVEN** the sidebar's entries for resource kinds (see "Give each listed resource kind one sidebar entry")
- **WHEN** each entry's route is resolved against the app's route table
- **THEN** each resolves to its own list route rather than to "page not found"
- **AND** no two entries resolve to the same route

### Requirement: Call a surface by one name everywhere
A surface MUST carry one name in every place it is named — sidebar, page header,
welcome panel, command palette and dialogs — because a surface the user reaches
two ways must not have two names. The names are these, in English and 中文, and
nothing else:

| English | 中文 |
| --- | --- |
| Overview | 总览 |
| Agents (group and entry) | 智能体 |
| Model providers | 模型提供商 |
| Run (group) | 运行 |
| Conversations | 对话 |
| Channels | 消息渠道 |
| Capabilities (group) | 能力 |
| MCP servers | MCP 服务器 |
| Custom tools | 自定义工具 |
| Skills | 技能 |
| CLIs | 命令行工具 |
| Context (group) | 上下文 |
| Knowledge | 知识 |
| Memory | 记忆 |
| System (group) | 系统 |
| Secrets | 密钥 |
| Activity | 活动 |
| Usage | 用量 |
| Sync | 同步 |
| Settings | 设置 |

In Chinese an agent MUST be called **智能体** everywhere the UI names one —
headings, page titles, buttons, dialogs and prose — never "Agent" or 代理.

#### Scenario: a surface carries one name in the sidebar and on its page
- **GIVEN** the UI in English and then in 中文
- **WHEN** each sidebar entry's label is compared with the title its page shows
- **THEN** the two are the same words for every surface in both languages
- **AND** in 中文 the group headings read 智能体, 运行, 能力, 上下文 and 系统, and no zh string names an agent as "Agent"

### Requirement: Show a self-clearing offline banner
When the daemon's status probe stops answering while the app is open, the shell
MUST first try to reconnect without taking the page away: it retries after 1, 2,
4 and 8 seconds, and for the first 10 seconds of failures the page stays where
it was, dimmed and not interactive, under a reconnecting bar at the top of the
workspace that names the attempt, when the next one runs and that nothing is
lost, with a Retry now control. After that the page MUST make way for an
offline state in the workspace — the sidebar stays — naming the recovery the
host can offer: in a browser the `coffer daemon start` command, in the desktop
shell a Start daemon control, because only one of the two can spawn a daemon;
both with Retry, when the next check runs and when the daemon last answered.
Both MUST clear themselves once the daemon is reachable again, with no manual
page reload: every query is read again and a toast says the app reconnected.
The banner owns the failure case; the shell footer reports the daemon's state
at all times (see "Show the daemon's state in the shell footer"), and the two
MUST agree: the footer reads reconnecting under the bar and offline beside the
offline state, never running.

#### Scenario: daemon-offline banner appears when daemon is unreachable
- **GIVEN** the daemon is not running (no reachable `127.0.0.1:<port>` from `~/.coffer/daemon.json`, or the file is absent)
- **WHEN** the user has the app open and any authenticated request to the daemon fails to connect
- **THEN** the reconnecting bar shows first, and after 10 seconds of failures the offline state renders in the workspace naming the recovery the host can actually offer — in a browser, the `coffer daemon start` command to run, because the page cannot start a daemon; in the desktop shell, a Start daemon control, because it can
- **AND** the shell footer reads as offline for as long as the offline state is shown
- **AND** the offline state disappears automatically once the daemon becomes reachable again, without a manual page reload

#### Scenario: a daemon that comes back within seconds leaves the page in place
- **GIVEN** a page open with a running daemon
- **WHEN** the daemon stops answering and answers again within 10 seconds
- **THEN** the page stays mounted under the reconnecting bar, dimmed and not interactive, while the retries run
- **AND** once it answers the bar goes, every query is read again and a toast says the app reconnected

### Requirement: Organise Settings into five tabs
Settings — the modal of "Open Settings as a modal from the sidebar footer" —
MUST carry exactly five tabs, in this order, grouped by what they manage rather
than by how Coffer is built, and MUST open on General:

- **General** (`/settings/general`) — display preferences (the interface language
  and the theme, the default page size and the preferred external editor), the
  **Coffer's model** section: the
  model Coffer's own engine runs on and the speech-to-text model (see "Choose
  Coffer's model in Settings › General"), and — only while the registry names
  an experimental feature — the Experimental features card (spec
  [experimental-features](../experimental-features/spec.md) "List and switch the features on the General tab").
- **Security** (`/settings/security`) — what is about this machine only: where
  the master encryption key lives, beside the database or in the OS keychain,
  and the daemon's access token (see "Show, copy and rotate the access token on
  Settings › Security"). It lists and edits no stored secret; those are on the Secrets page (see
  "Manage stored secrets on the Secrets page").
- **Data** (`/settings/data`) — what Coffer stores, by kind: Vault, Local content, History
  and Rebuildable cache (see "Group the Data tab by what kind of data it is").
- **Daemon** (`/settings/daemon`) — the daemon's state and the controls a user
  needs for it (see "Show and manage the daemon on Settings → Daemon").
- **About** (`/settings/about`) — version, license, source, whether a newer
  version is available (see "Check for and install updates on Settings › About"),
  and a small **Copy diagnostics** action beside the version.

Clicking a tab
swaps the modal's right pane without a full page reload and without closing the
modal.

#### Scenario: settings layout uses the redesigned tabbed sidebar
- **GIVEN** the user navigates to `/settings`
- **WHEN** the route resolves
- **THEN** the Settings modal opens on the General tab
- **AND** the modal's tab list shows General, Security, Data, Daemon, and About — exactly those five, in that order — with the current route highlighted
- **AND** clicking a tab swaps the right pane content without a full page reload and the modal stays open

#### Scenario: the security tab keeps only machine-level settings
- **GIVEN** stored secrets cited by a registered MCP server and a model provider
- **WHEN** the user opens `/settings/security`
- **THEN** the tab shows where the master key lives and its move control, and the access token's Show, Copy and Rotate controls
- **AND** it lists no stored secret and offers no control that adds, reveals or deletes one

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
which is added on the Custom tools page (see "Manage custom tools on their own
page").

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

### Requirement: Explain unreadable pasted input in the dialog
Input the paste box cannot read as any of the recognised forms — malformed
JSON or TOML, a JSON or TOML document that does not match a server's shape, or
text that is neither a command line nor a URL — MUST keep the dialog open with a
readable message saying what was expected and, where it applies, the parse
location or the failing field, and MUST offer a manual choice of the server's
type (stdio or Streamable HTTP) that opens the empty form. It MUST NOT send a
request.

#### Scenario: JSON import shows readable error for malformed JSON
- **GIVEN** the user opens the Add server dialog
- **WHEN** they paste a payload that is not valid JSON (or a valid JSON document that does not match the `mcpServers` shape)
- **THEN** the dialog stays open and renders a readable error explaining what is wrong (parse error location for malformed JSON, or the failing field for shape-mismatch)
- **AND** no request is sent to `/api/v1/resources` or `/api/v1/secrets`
- **AND** the dialog never shows the literal text "unexpected error" or `INTERNAL_ERROR`

#### Scenario: unreadable input offers a manual type choice
- **GIVEN** the Add server dialog open on its paste box
- **WHEN** the user pastes text that is no recognised form, such as a sentence from a README
- **THEN** the dialog says it could not read a server from it and what it accepts, and offers stdio and Streamable HTTP as a manual choice
- **AND** choosing one opens the empty form for that type, and no request is sent

### Requirement: Welcome an empty list with one next action
A list with nothing in it MUST render a welcome card — a short pitch and one
primary action — and MUST NOT render an empty table or a placeholder ghost row.

#### Scenario: empty resources list renders a welcome view
- **GIVEN** the daemon is running and zero resources are registered
- **WHEN** the user opens `/mcp-servers`
- **THEN** the page renders a welcome card with a short pitch and a primary "Add server" button
- **AND** the welcome card does NOT show an empty table or a placeholder ghost row

### Requirement: Lay out every detail page's tabs alike
Every detail page MUST lay its tabs out the same way as every other. What a tab
shows belongs to the capability that owns that kind — the agent detail page's
tabs are [agent-registry](../agent-registry/spec.md)'s; this capability owns
only that they are tabs on a detail page laid out like every other.

Every detail page MUST put its tab in the path: `/<kind>/<id>/<tab>`, with the
default tab at the bare `/<kind>/<id>`, never in a `?tab=` query. The `<id>` is
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

### Requirement: Query only the visible Activity tab and isolate failures
Only the visible tab pages through records — Everything through all three
logs, each other tab through its own — and the count beside every other tab
MUST come from a read of one row (the audit and invocation answers carry their
`total`) or of the daemon log's bounded tail, never from paging a tab that is
not in front. A tab count follows the time window, the server and the status,
not the who or kind filters, and a tab with nothing in the window — or whose
log failed — shows no number. A record whose route fails MUST render its error
inside its own tab, leaving the other two working — one failing lane must not
take the other two down with it; on Everything the failing record is named
above the stream with its error and which records are still shown ("Showing
changes and daemon records only; they are complete."), the stream shows the
other two records, and the notice offers Retry. There MUST be no manual
refresh control and no Pause / Resume control: switching tab or changing a
filter refetches, and new records arrive on their own (see "Stream new Activity
records while the list is at the top").

#### Scenario: a failing record shows its error inside its own tab
- **GIVEN** one of the three routes is unavailable (an older daemon that does not serve it)
- **WHEN** the user opens `/activity`
- **THEN** the failing record's tab renders a readable error
- **AND** the other two tabs still render their rows

### Requirement: Group the Data tab by what kind of data it is
The Data tab MUST show what Coffer stores in four blocks, one per kind of data
([Storage Is Five Classes by Nature](../../../docs/decisions/storage-is-five-classes-by-nature.md)),
and no other — in particular no "This Mac only" block, since what is true of this
machine only is a setting shown on the tab it belongs to:

- **Vault** — the synced git repository of the user's configuration, skills and
  knowledge: its size, how many versions it holds, and **Open folder**.
- **Local content** — what is not synced and the user must back up themselves:
  chat and channel attachments and media only, with their size and **Open
  folder**, and a line saying so.
- **History** — the retention of each record kind — changes, MCP calls and
  conversations — Keep forever or a number of days, cleaned up by the retention
  worker's schedule (at daemon start and every six hours), with a
  **Clear expired now** action and a muted line naming `coffer config` for the
  other retention settings; a saved value survives a reload. Shortening a
  window (or turning Keep forever off) MUST ask first, and the confirmation
  MUST say how many records the shorter window deletes at the next cleanup and
  how many the table holds now and would hold after, counted by the daemon
  without deleting anything. A refused save MUST say so above the blocks with
  **Try again**, name the window still in place, and mark the row "Not saved".
- **Rebuildable cache** — Coffer's memory tree and the transcript summary cache
  (`cache/agent/`), which Coffer rebuilds on its own: one **Clear** action,
  behind a confirmation saying that memory is rebuilt from the agents' own
  memory on the next update, that an equivalent rebuild needs Coffer's model
  (without it each entry becomes a note of its own), and that notes whose
  sources are gone do not come back.

Edits auto-save, like every settings surface: there is no Save button.

#### Scenario: retention period persists across reload
- **GIVEN** the user opens the Data settings tab
- **WHEN** they turn off "Keep forever" for a record kind in History, set a specific number of retention days, and commit the field (blur or Enter), which auto-saves
- **THEN** reloading the page shows the same retention-days value that was saved

#### Scenario: the data tab shows four blocks and no this-mac block
- **GIVEN** a vault with versions, chat media on disk, and memory partitions
- **WHEN** the user opens `/settings/data`
- **THEN** it shows Vault (size, versions, Open folder), Local content (attachments and media, size, Open folder, not synced), History (retention for changes, MCP calls and conversations with Clear expired now) and Rebuildable cache (memory tree and transcript summary cache with Clear), and no This Mac only block

#### Scenario: shortening a retention window counts what it deletes
- **GIVEN** MCP calls kept for 30 days, some of them older than 7 days
- **WHEN** the user sets the MCP calls window to 7 days
- **THEN** a confirmation asks "Keep MCP calls for 7 days?", says how many calls older than 7 days the next cleanup deletes, and shows the count now and after
- **AND** nothing is deleted or saved until the user confirms

#### Scenario: clear expired now removes what retention has passed
- **GIVEN** MCP calls kept for 7 days and calls older than that
- **WHEN** the user chooses Clear expired now
- **THEN** the older calls are removed and the rest remain, as the scheduled cleanup would have done

#### Scenario: clearing the cache is confirmed and rebuilt
- **GIVEN** memory partitions with notes
- **WHEN** the user chooses Clear in Rebuildable cache and confirms
- **THEN** the memory tree and the transcript summary cache are cleared, and the next memory update rebuilds the partitions from the agents' own memory, with no vault or local content touched

### Requirement: Scope Activity's calls table to one server on its page
A server's **Invocations** tab MUST read the same invocation log Activity's MCP
calls tab reads, scoped to that one server, rather than a second record that
would have to be kept in step with the first. It renders the one calls list the
server's "Calls and server log" drawer renders: the calls the gateway proxied
for this server in the last 24 hours, newest first, All or Errors, one agent or
all, each row its time, tool, calling agent, result and duration, and the
chosen call (the newest by default) opened below with its result, how long it
took and its session — the account of what an agent did when the agent is the
thing that is broken. Activity's MCP calls tab reads every server's calls and
names each row's server.

#### Scenario: a server's invocations tab is the Activity calls table scoped to it
- **GIVEN** a registered MCP server
- **WHEN** its Invocations tab and Activity's MCP calls tab each render
- **THEN** the server's tab asks only for that server's calls, lists them without a server column and opens the newest below the list
- **AND** Activity's tab asks the cross-server route for every server's calls and names each row's server

### Requirement: Gather the three records on one Activity page
The three records Coffer keeps — the audit log (what changed in the vault, and
who changed it), the MCP invocation log (every call the gateway proxied, and
which agent's session made it) and the daemon log (what Coffer itself did,
including what broke) — MUST reach a person through one page at `/activity`,
under System, carrying four tabs, each with its count: **Everything**, the
default, merging the changes, the calls and the daemon's warnings and errors
into one newest-first stream, then one tab per record — **Changes**, **MCP
calls**, **Daemon log** — each a newest-first table with the columns that
record actually has: an activity line and who made it; a call's agent, server
and tool, duration and outcome; a log record's level, logger and message. Above
the rows a line says what the tab holds: on Everything and Changes the first
day with its errors and warnings in the window ("1 error and 1 warning in the
last hour"), or else how many records are loaded of how many there are; on MCP
calls the window with the calls, the failed and the denied calls in it
("182 calls · 7 failed · 1 denied"), each counted by the invocation route; on
the Daemon log the file the tail is read from, newest first, and whether the
list is following it, with **Open log file**. Each tab but the Daemon log pages
older records on request ("Load older") by the log's cursor; beside the button
it says how many the next page holds and from before when, and how long MCP
calls and changes are kept, linking to Settings › Data where that is set.

#### Scenario: activity gives each record its own tab
- **GIVEN** Coffer has recorded an audit entry, an MCP invocation and a daemon log record
- **WHEN** the user opens `/activity` and moves through its tabs
- **THEN** Everything shows all three newest first, and each other tab renders that record's own newest-first table with the columns that record has — an activity line and who made it; a call's agent, server and tool, duration and outcome; a log record's level, logger and message
- **AND** a change reads as a plain-language line, not a raw event code

#### Scenario: the daemon tab reads every writer in the log
- **GIVEN** `daemon.log` holds lines from several writers at once — Coffer's own JSON, an upstream's `LEVEL - logger - message` lines, uvicorn and rich — with a colour-escaped line among them and a traceback written under the record that raised it
- **WHEN** the user opens the Daemon tab
- **THEN** each row carries the time, level and logger its own line stated, and nothing carries a time or a level it never stated
- **AND** no message renders a terminal escape sequence as text
- **AND** the traceback rides with the record that raised it rather than becoming rows of its own
- **AND** the severity-floor filter judges each line by its own level rather than treating every non-JSON line as an error

### Requirement: Filter each Activity tab and expand any row
Every Activity tab MUST filter by free text and time range plus the filters its
own records afford — Everything: who (an agent, or a person, the command line
or Coffer itself), server and kind; Changes: who and the kind of resource
changed; MCP calls: agent, server and status; Daemon log: a severity floor and
a logger. The time range offers the last 15 minutes, hour, 24 hours and 7 days,
everything the retention settings keep, and a custom From / To (an empty To is
now); a tab opens on the last hour, the Daemon log on the last 24 hours, until
the user picks one. Who and kind choose several values at once, each listed
with how many loaded records carry it: who lists the agents, then the ones who
are not an agent — you (the web UI, the desktop app), the command line, Coffer
itself and sync; kind lists MCP calls, Changes with each kind of change under
it (a resource kind, or secrets, sync, settings and CLIs for a change that
names no resource), and daemon records. A record passes when it matches any
chosen value.

Selecting a row on Everything, Changes or MCP calls MUST open it in a detail
drawer beside the list, answer first — a failed call's error and how its server
has been doing (since when it has been failing, and its errors in the last 24
hours), a change's who and what, then its configuration before and after as a
diff, a daemon record's message and traceback — then the records written
within five minutes of it, ending in its raw underlying record, pretty-printed
in a monospace, scrollable block; the drawer steps to the previous or next
record without closing, and its footer holds the next step: open the resource,
read the daemon log about a failed call's server, or copy the record. A call's
drawer shows its metadata only, since Coffer stores no call's arguments or
results. A change whose event the page has no sentence for — a kind of record
added later — reads through the same facts and diff. On the Daemon log a row
opens in place under its own line instead, with its traceback, **Copy record**
(its raw record) and, when the record names a server and tool, **Show the MCP
call**, which opens the MCP calls tab looking for that call.

#### Scenario: activity row expands to its raw record
- **GIVEN** an Activity tab has at least one row
- **WHEN** the user clicks (or presses Enter/Space on) that row on Everything, Changes or MCP calls
- **THEN** a detail drawer opens beside the list and renders its raw record — the full underlying JSON, pretty-printed in a monospace, scrollable block

#### Scenario: a daemon log row opens in place
- **GIVEN** the Daemon log tab with an error record carrying a traceback and naming `server=github tool=search_issues`
- **WHEN** the user selects that row, then chooses Show the MCP call
- **THEN** the row opens under its own line with the traceback and Copy record, and no drawer opens
- **AND** Show the MCP call opens the MCP calls tab filtered to `github.search_issues`

#### Scenario: who and kind choose several values
- **GIVEN** Everything holding a call by an agent, a change made in the web UI, a change made from the command line and a daemon warning
- **WHEN** the user chooses the agent and "You" under Agent, then MCP calls and Changes under Kind
- **THEN** the list keeps the agent's call and the web UI's change and drops the others, the Kind pill reads "Calls, changes" and its list says "Everything except daemon records"
- **AND** the tab counts do not change

### Requirement: Read each Activity tab from its record owner's route
The Activity page MUST add no route of its own: each tab reads the read-only
route belonging to whichever capability owns that record (see Purpose) — the
Changes tab `GET /api/v1/audit`, the MCP calls tab `GET /api/v1/mcp/invocations`
and the Daemon tab `GET /api/v1/daemon/logs`, Everything all three — and its
filters list agents and servers from those kinds' own list routes. An agent or
a script that asks "what happened" reads the same three records from the
command line (see "Keep the command-line record readers").

#### Scenario: each activity tab reads its owner's route
- **GIVEN** a running daemon that has recorded an audit entry, an MCP invocation and a daemon log record
- **WHEN** the user opens each of the Activity tabs in turn
- **THEN** each tab shows only its own record's rows, read from that record's owner's route
- **AND** no tab requests a route of the Activity page's own

### Requirement: Use one shared table for every list surface
Every list surface — agents, knowledge, memory, model providers, channels, each
Activity tab, Sync's Runs tab — MUST use one shared searchable, filterable,
paginated table, and a row click MUST open that item's detail page. The MCP
servers and Skills pages are lists beside a reading pane instead: a filterable
list of rows, each a link that opens its item in the pane at the item's own
address, so a row click opens the item there. Sync's Setup tab is not a list
surface: it is configuration cards, and the machine registry it carries is a
small plain table.

#### Scenario: a row click opens the item's detail page
- **GIVEN** a list surface showing at least one row
- **WHEN** the user clicks the row, or presses Enter on it
- **THEN** the app navigates to that item's detail page

### Requirement: Show reach as a labelled button on every list and detail page
Every list surface of a scoped kind that is a table MUST carry a **reach** column — named for what
it holds, not for the on/off flag it replaced: one button labelled with the answer it already
holds — "Every agent", "2 agents", "Disabled", or "No agent selected" for a
scope narrowed to nobody — so the reader learns the reach by reading it rather
than by comparing which of three side-by-side segments looks pressed. A list
beside a reading pane (MCP servers, Skills) shows each row's reach as a mark
instead — Off, All agents, or the badges of the agents it reaches — and the
button is in the open item's header. Every detail page MUST carry the same
button in its header. A kind that declares no
scope — an agent, a knowledge collection, a memory partition — MUST carry neither
the column, the button, nor a bulk reach action; see "Offer reach as one choice in a panel".

#### Scenario: the reach button states the reach it holds
- **GIVEN** resources that reach every agent, two agents, nobody selected, and one that is disabled
- **WHEN** each one's reach button renders
- **THEN** they read "Every agent", "2 agents", "No agent selected" and "Disabled"
- **AND** each is one button rather than a row of segments

#### Scenario: a kind that cannot be disabled shows no status control
- **GIVEN** the knowledge and memory list pages and one collection's and one partition's page
- **WHEN** each renders
- **THEN** no list has a Status or Reach column and no header carries a reach or status button

### Requirement: Mount one reach control in three places
The reach control MUST be one component mounted in every place a reach is
changed — a table's row, the detail header and the multi-select bar — so they
can never drift into different answers to one question. On a list beside a
reading pane the row shows the reach as a mark and the header and the
selection bar carry the control.

#### Scenario: row, header and selection bar mount the same reach control
- **GIVEN** an MCP server that reaches every agent
- **WHEN** its list row, its detail header and the list's selection bar render
- **THEN** the row reads its reach and the header and the selection bar each carry the same reach button, which opens the same reach panel

## ADDED Requirements

### Requirement: Show, copy and rotate the access token on Settings › Security
Settings › Security MUST be the one place in the web UI that shows the daemon's access token. It
MUST be hidden until **Show** is chosen, offer **Copy**, and offer **Rotate**, which asks for
confirmation — saying that clients configured with the old token stop working — then calls
`POST /api/v1/daemon/rotate-token` (spec [daemon](../daemon/spec.md) "Rotate the token from REST or
the command line"). The page MUST install the token the call returns and carry on without a
reload; the confirmation MUST close only on success, and a failed rotation MUST leave the dialog
open with the error and the old token in use. While the daemon cannot be reached, the controls are
disabled.

#### Scenario: rotating the token from settings security keeps the page working
- **GIVEN** Settings › Security open on a running daemon
- **WHEN** the user rotates the token and confirms
- **THEN** one `POST /api/v1/daemon/rotate-token` is sent and the dialog closes
- **AND** the page's next requests carry the new token and succeed, with no reload

#### Scenario: a failed rotation from settings security keeps the old token
- **GIVEN** Settings › Security open, and a rotation that the daemon answers with `503`
- **WHEN** the user confirms the rotation
- **THEN** the dialog stays open with a readable error
- **AND** the page keeps using the old token, and its next request succeeds

#### Scenario: the token is hidden until shown
- **GIVEN** Settings › Security open
- **WHEN** it renders, and then the user chooses Show and Copy
- **THEN** the token is masked until Show, and Copy puts it on the clipboard

#### Scenario: copy diagnostics carries no secret
- **GIVEN** Settings › About open
- **WHEN** the user chooses Copy diagnostics beside the version
- **THEN** the clipboard holds the version, channel, host, daemon state and port and the enabled features, and no token or secret value

### Requirement: Group the sidebar by what the user comes to do
The sidebar MUST be grouped by what the user comes to Coffer to do, so that each
heading names one intent and a new entry has one obvious home. There are five
groups, under headings in this order:

- **AGENTS** — set up the agents and the models they run on: Agents, then Model
  providers. Agents come first because they are the subject of the product; a
  provider is the endpoint and key each agent's model is served from.
- **RUN** — put an agent to work, directly or through an IM bot: Conversations,
  then Channels.
- **CAPABILITIES** — give agents things they can do: MCP servers, Custom tools,
  Skills, then CLIs.
- **CONTEXT** — give agents things they know: Knowledge, then Memory.
- **SYSTEM** — look after Coffer and what every other part shares: Secrets,
  Activity, Usage, then Sync.

Settings sits in no group: it is machine-level configuration visited rarely, so
it opens as a modal from the sidebar footer rather than taking an entry (see
"Open Settings as a modal from the sidebar footer").

**Overview**, the landing page, MUST sit above the five groups under no heading:
it summarises all of them, so filing it under one would misname it.

A new entry MUST join the group that names what the user comes to it for, and no
group may grow past five entries; growth that is more of an existing thing — one
more agent, channel or custom tool — is a row inside that thing's page, not an
entry. A group whose every entry is left out (see "Keep the sidebar to its
fifteen entries") MUST leave its heading out too, so no heading stands over
nothing. The decision and the options it was weighed against are in
[The Sidebar Is Grouped by What the Person Comes to Do](../../../docs/decisions/sidebar-grouped-by-what-the-person-comes-to-do.md).

#### Scenario: the sidebar groups entries by what the user comes to do
- **GIVEN** the app shell is rendered with every experimental feature switched on
- **WHEN** the sidebar lists its entries
- **THEN** Overview comes first, under no heading, and the rest sit under five headings in the order Agents, Run, Capabilities, Context, System
- **AND** Agents holds Agents then Model providers, Run holds Conversations then Channels, Capabilities holds MCP servers, Custom tools, Skills and CLIs, Context holds Knowledge then Memory, and System holds Secrets, Activity, Usage and Sync

#### Scenario: a group with every entry switched off leaves the sidebar
- **GIVEN** a group whose every entry is owned by a registered experimental feature that is switched off
- **WHEN** the app shell is rendered
- **THEN** the sidebar shows no heading for that group, and the other headings and their entries are unchanged

### Requirement: Give each listed resource kind one sidebar entry
Every resource kind with a list UI MUST have exactly one sidebar entry — today six
kinds (`mcp_server`, `skill`, `knowledge`, `memory`, `provider`, `channel`), six
entries — filed by what the user comes to do with it rather than under one
Resources heading, because "resource" is the framework's storage word, not a
word a user navigates by:

- **Model providers** is filed under Agents, not Capabilities or Settings: a
  `provider` is `{protocol, base_url, secret_ref}`, the endpoint and key an
  agent's model is served from, and the connection and model are chosen per
  agent on that agent's page (spec
  [provider-switching](../provider-switching/spec.md) "Offer every connection operation on REST, CLI and web").
- **Channels** is filed under Run, beside Conversations and not merged into it:
  Conversations is where a person reads and continues every conversation, a
  channel is an IM bot set up once and revisited rarely, and the conversations a
  channel carries are listed on the Conversations page with its badge (spec
  [chat](../chat/spec.md) "Show every conversation on the Conversations page");
  the Channels page holds setup, status and settings only.
- **MCP servers** and **Skills** are filed under Capabilities; **Knowledge** and
  **Memory** under Context.
- **Custom tools** are `mcp_server` resources of the HTTP API transport, one per
  group of tools. They share the gateway's machinery with every
  other server but get their own entry under Capabilities, so a user looking for
  "make my own tool" finds it; the MCP servers entry lists the other servers and
  the Custom tools entry these, so each resource still appears under exactly one
  entry.

**CLIs** is not a resource kind: it lists the commands skills require, with their
presence, version and login state (see "Show every CLI a skill requires on the
CLIs page"), and sits under Capabilities beside Skills.

Agents are stored as resources of kind `agent` but are the consumers of the
others, so the Agents entry heads the Agents group and no agent is listed on a
Capabilities or Context page. **Secrets** is not a resource kind — it is the
secret store every kind cites into — and sits under System (see "Manage
stored secrets on the Secrets page").

#### Scenario: each listed resource kind has one sidebar entry
- **GIVEN** the app shell is rendered with every experimental feature switched on
- **WHEN** the entries for resource kinds are read
- **THEN** MCP servers, Custom tools, Skills, Knowledge, Memory, Model providers and Channels each appear exactly once, under Capabilities, Capabilities, Capabilities, Context, Context, Agents and Run respectively
- **AND** a custom tool is listed on the Custom tools page and not on the MCP servers page
- **AND** no heading reads "Resources"

### Requirement: Open the app on Overview
The app's index (`/`) MUST render the Overview page, the landing page, in place
rather than redirecting elsewhere, so a visitor lands on the whole of the vault
before any one part of it. This requirement fixes where the app lands; what the
Overview page shows is a requirement of its own. Agents live at `/agents` (list)
and `/agents/<type>` (detail, with each tab at `/agents/<type>/<tab>`), addressed
by the agent's type because an agent's name is fixed to its type, and
MUST NOT appear in the `/mcp-servers` kind browser.

#### Scenario: the index opens Overview
- **GIVEN** the app's route table
- **WHEN** the user opens `/`
- **THEN** the Overview page renders at `/` with no redirect, and the sidebar marks the Overview entry as current
- **AND** `/agents` still opens the Agents page, and the `/mcp-servers` list asks only for MCP servers, so no agent appears there

### Requirement: Keep daemon shutdown on the command line
No tab may expose a "Shutdown daemon" or "Stop daemon" control: stopping the
daemon from the web kills the very page it was asked from, and recovery then needs
a terminal anyway, where `coffer daemon stop` already is. Restarting is not
stopping — the desktop shell's restart waits for the replacement and hands the
page its connection (spec [desktop-app](../desktop-app/spec.md) "Restart by stopping the running daemon first").
The About tab MUST show the version (with the short commit a release build was
made from, when stamped), license, source, the data folder, the update check of "Check
for and install updates on Settings › About" and **Copy diagnostics** only, and no
release channel —
which copies the version, release channel, host, daemon state and port, and
the enabled experimental features as plain text, and never a token or a
secret — with no language picker (the
sidebar already switches language) and no installed-resource-kind list
(developer detail). Remaining jargon is rewritten in plain language (e.g.
"prune" is phrased as clearing expired data).

#### Scenario: settings offers no shutdown control
- **GIVEN** the user opens the Settings tabs
- **WHEN** each tab is fully rendered
- **THEN** no tab exposes a "Shutdown daemon" or "Stop daemon" control
- **AND** the About tab shows version / license / source / data folder, the update check and Copy diagnostics only — no language picker, no resource-kind list, no release channel

### Requirement: Set when the daemon runs on the Daemon tab
The Daemon tab MUST carry a card for when Coffer's daemon runs, with one control: a **Start at
login** switch. It MUST read and write it through
[daemon](../daemon/spec.md) "Change residency from the settings page or the command line".
A clicked switch MUST move to the clicked value at once and then settle on what the daemon reports:
the switch is disabled until the daemon has first answered, a successful write shows the value the
daemon answers with, the switch is shown unavailable rather than off on a host with no login
service, and a failed write MUST put the switch back to what the daemon last reported and show the
error beside it. The card MUST NOT offer an idle window or a stand-down choice, because the daemon
never stands down on its own.

#### Scenario: the settings daemon tab sets when the daemon runs
- **GIVEN** the daemon reports a login service that is supported and not installed
- **WHEN** the user turns on Start at login on the Daemon tab
- **THEN** one request is sent carrying `login_service_installed: true` and no idle window
- **AND** the card offers no idle-window or stand-down control
- **AND** when the request fails, the switch goes back to off and the error is shown beside it

### Requirement: Choose Coffer's model in Settings › General
Settings › General MUST carry a **Coffer's model** section that sets what Coffer's
own machinery runs on (spec [internal-engine](../internal-engine/spec.md) "Show and change Coffer's model in Settings › General").
It is machine-level configuration of Coffer itself rather than of any agent, so
it is a Settings section, not a tab of the Model providers page. The section
MUST carry two pickers — **Engine model** and **Speech to text** — each choosing
a provider first and then a model from that provider's list, and a **Test**
action for each that tries the chosen pair and shows the result beside it. Each
picker MUST show its state inline: *not set* (saying what Coffer does without
it — no internal pass runs; voice messages reach the agent as audio files),
*set*, or *failing* (the last test or call failed, with the error). The Model
providers page MUST carry no Coffer's model tab. Coffer has no embedding
configuration (search is literal-only), and the second picker is Speech to text.

#### Scenario: coffer's model is chosen in settings general
- **GIVEN** two connections, each with a list of models
- **WHEN** the user opens `/settings/general` and, in the Engine model picker, chooses a provider and then one of its models
- **THEN** the model list offers only the chosen provider's models, and the choice is saved without a Save button
- **AND** the Model providers page shows no Coffer's model tab

#### Scenario: an unset picker says what coffer does without it
- **GIVEN** no speech-to-text model chosen
- **WHEN** the Coffer's model section renders
- **THEN** the Speech to text picker reads as not set and says voice messages reach the agent as audio files

#### Scenario: testing a picker shows a failing pair inline
- **GIVEN** an engine model chosen on a connection whose endpoint rejects the key
- **WHEN** the user chooses Test beside the Engine model picker
- **THEN** the picker reads as failing with the endpoint's error beside it
- **AND** the chosen pair is kept as it was

### Requirement: Show the daemon's state in the shell footer
The shell MUST show the daemon's state at all times in a footer at the bottom of
the sidebar, read from the daemon's status probe (spec
[daemon](../daemon/spec.md) "Report the state the shell shows"). The footer MUST
name one of five states in plain words — connecting (no answer yet), running,
stopping (the daemon reports `draining`), reconnecting (the first seconds after
it stopped answering, see "Show a self-clearing offline banner") or offline (it
cannot be reached) — with the app's version beside it, and its accessible name
MUST carry, while running, the port it answers on. In the desktop shell, a
daemon from a different app version MUST read as running with a version
warning. Clicking the state MUST open the version menu above it: its head names
the version and the address the daemon answers on (or the state, when it is not
running) and opens the Settings modal on its Daemon tab over the current page;
below it the theme (Light, Dark, System, applied at once), the language (each
locale named in its own language, applied at once), Documentation (the docs
site) and Check for updates (Settings › About, where the desktop shell checks at
once). The labelled Settings row sits just above the state (see "Open Settings
as a modal from the sidebar footer"). On the collapsed icon rail the state MUST
shrink to an icon whose tooltip carries the same words, and the Settings row to
its gear. Showing the state MUST NOT make starting the daemon the user's job:
every surface that can start one still does so without asking.

#### Scenario: the footer shows a running daemon
- **GIVEN** a daemon answering its status probe with `status: "ready"` on port 8000
- **WHEN** the shell renders
- **THEN** the sidebar footer reads that the daemon is running, with the app's version, and its accessible name names port 8000
- **AND** clicking it opens the version menu, whose head names `127.0.0.1:8000` and opens the Settings modal on its Daemon tab at `/settings/daemon`, over the page the user was on

#### Scenario: the version menu switches theme and language at once
- **GIVEN** the version menu open from the footer
- **WHEN** the user picks Dark, then 简体中文
- **THEN** the whole shell turns dark and then reads in Chinese with no reload, each locale named in its own language
- **AND** Documentation opens the docs site and Check for updates opens Settings › About

#### Scenario: the footer says connecting before the first answer
- **GIVEN** the shell has rendered and the daemon's status probe has not answered yet
- **WHEN** the footer renders
- **THEN** it reads as connecting, not as offline and not as running

#### Scenario: the footer shows an offline daemon
- **GIVEN** the daemon cannot be reached
- **WHEN** the footer renders
- **THEN** it reads as offline while the offline banner is shown
- **AND** its version menu still opens Settings → Daemon, which names the host's recovery

#### Scenario: the footer shows a stopping daemon
- **GIVEN** a daemon whose status probe reports `status: "draining"`
- **WHEN** the footer renders
- **THEN** it reads as stopping

#### Scenario: the collapsed rail keeps the daemon state
- **GIVEN** the sidebar collapsed to its icon rail and a running daemon
- **WHEN** the rail renders
- **THEN** the footer is a state icon whose tooltip reads that the daemon is running on its port

### Requirement: Show and manage the daemon on Settings → Daemon
The Daemon tab MUST show the daemon's state and carry the controls a user needs
for it, and nothing that stops it:

- **Status** — state and the address it answers on, then one line: how long
  it has been up, its pid and how many agents carry Coffer's connection, all
  from the status probe. The version is on About and in the shell footer.
- **Restart** — a Restart control in both hosts: in the desktop shell it runs the
  shell's restart (spec [desktop-app](../desktop-app/spec.md) "Restart by stopping the running daemon first");
  in a browser it asks the daemon to restart itself (spec [daemon](../daemon/spec.md) "Restart itself on request"),
  shows that it is restarting while the page waits for the successor to answer, and
  then reloads the page from the successor's origin — on the new port when one
  was saved — which hands it the successor's token. A successor that does not
  answer within 90 seconds is reported beside the control.
- **Port** — the port the daemon answers on, editable (spec [daemon](../daemon/spec.md) "Bind a fixed, settable port"):
  a value MUST be a whole number from 1024 to 65535 and a port no other process
  holds, each refused in place otherwise, with Save disabled until the value is
  edited; saving writes it to the pre-database
  daemon config and the row then reads **takes effect after restart**, with
  **Restart now** — the same restart as the Restart control, in either host.
  Until the restart, the status keeps showing the port the daemon answers on.
- **Start at login** — see "Set when the daemon runs on the Daemon tab".

The tab has no token row (the token is on Settings › Security) and no
Troubleshooting section: the daemon log is read on Activity's Daemon tab, and
Copy diagnostics is on Settings › About.

While the status has not yet answered, the tab MUST keep its layout over
skeleton rows. While the daemon cannot be reached, the status card MUST read
offline and name the host's recovery — the Restart control in the desktop shell,
the `coffer daemon start` command in a browser — and the Start at login and
Port controls MUST be disabled.

#### Scenario: the settings daemon tab shows the running daemon
- **GIVEN** a running daemon
- **WHEN** the user opens `/settings/daemon`
- **THEN** the status card shows its state, port, uptime, pid and connected-agent count, matching `GET /api/v1/daemon/status`
- **AND** the tab carries no stop or shutdown control

#### Scenario: the settings daemon tab offers the host's restart
- **GIVEN** the Daemon tab open in a browser, and then in the desktop shell
- **WHEN** the restart row renders
- **THEN** both show a Restart control and neither shows a command to copy
- **AND** in the browser it asks the daemon to restart itself, and in the desktop shell it runs the shell's restart

#### Scenario: saving a valid port leaves it pending until restart
- **GIVEN** a daemon answering on port 8000, opened in the desktop shell
- **WHEN** the user sets the port to 8123 on the Daemon tab and saves
- **THEN** `~/.coffer/daemon-config.json` carries 8123, the row reads takes effect after restart with Restart now, and the status still shows 8000
- **AND** in a browser the row offers the same Restart now

#### Scenario: a browser restarts the daemon from the daemon tab
- **GIVEN** the Daemon tab open in a browser on a running daemon
- **WHEN** the user presses Restart
- **THEN** the page asks the daemon to restart itself, waits until its successor answers — a new start time on the same port, or an answer on the port that was saved — and reloads the page from the successor
- **AND** a successor that does not answer within 90 seconds is reported beside the control and nothing is reloaded

#### Scenario: a port in use is rejected
- **GIVEN** another process holding port 9000
- **WHEN** the user enters 9000, and then 80, on the Daemon tab
- **THEN** each is refused in place — 9000 as taken, naming what holds it, and 80 as outside 1024–65535 — and nothing is written

#### Scenario: the daemon tab has no token row and no troubleshooting section
- **GIVEN** the Daemon tab open on a running daemon
- **WHEN** it renders
- **THEN** it carries no token control, no daemon-log link and no Copy diagnostics

#### Scenario: the settings daemon tab keeps its layout while status loads
- **GIVEN** the Daemon tab opened before the status probe has answered
- **WHEN** the tab renders
- **THEN** it shows its page header and skeleton rows rather than a blank pane or an offline state

#### Scenario: the settings daemon tab with the daemon offline
- **GIVEN** the daemon cannot be reached
- **WHEN** the user opens the Daemon tab
- **THEN** the status card reads offline and names the host's recovery
- **AND** the Start at login and Port controls are disabled

### Requirement: Jump to any page or object from a command palette
The shell MUST offer a command palette, opened with ⌘K on macOS and Ctrl+K
elsewhere from any page, and from a search control in the sidebar. It MUST do
one thing — take the user somewhere — and MUST NOT carry an action that changes
state: no create, delete, enable, reach or run entry.

It lists two kinds of entry, filtered together by what the user types:

- **Pages** — every sidebar entry and every Settings tab, by the names the
  sidebar and the tabs use (see "Call a surface by one name everywhere"). A
  Settings tab opens in the Settings modal over the current page.
- **Objects** — the agents, the resources of every kind with a list surface
  (custom tools included) and the CLIs, matched by name — and also by title
  on the kinds that carry one ([resource-framework](../resource-framework/spec.md)
  "Carry an optional editable title on the kinds that have one") — each
  opening its detail page.

With an empty query it MUST show **Recent** — the last few entries chosen in
this browser, a convenience that is safe to lose — above every page. Under a
query it MUST show the single best hit as **Best match** (an exact name first,
then a match at the start of a name), then the other matching pages, then the
matching objects in one group per kind, named as the kind's sidebar entry and
in sidebar order, each group holding a few; typing more narrows them.

A page or object of a switched-off experimental feature MUST NOT appear. The
palette MUST read the list routes the pages already read and add no route of its
own. Arrow keys MUST move the selection, Enter MUST open it, and Escape MUST
close the palette and return focus where it was.

Pages MUST be usable at once, whatever the daemon's state. While the objects
are loading, the palette MUST say so; a kind whose list fails MUST show a
readable error in its own group and leave the other groups working; while the
daemon cannot be reached, the palette MUST list Pages only and say that objects
need the daemon. A query that matches nothing MUST say so, and what the palette
searches, rather than show an empty panel.

#### Scenario: the palette jumps to a page
- **GIVEN** the app open on any page
- **WHEN** the user presses ⌘K, types "act" and presses Enter
- **THEN** the app navigates to `/activity` and the palette closes

#### Scenario: the palette jumps to an object
- **GIVEN** a registered MCP server, and a model provider whose title differs from its name
- **WHEN** the user opens the palette and types part of the server's name, then part of the provider's name, then part of the provider's title
- **THEN** the first query lists the server, and the second and third each list the provider
- **AND** choosing the server opens `/mcp-servers/<name>`

#### Scenario: the palette offers no actions
- **GIVEN** the palette open with an empty query, and then with queries naming objects
- **WHEN** every entry it lists is read
- **THEN** each entry is a page or an object that navigates somewhere
- **AND** choosing any of them sends no request that changes state

#### Scenario: an empty query shows recent choices above every page
- **GIVEN** the user chose an MCP server and then the Usage page from the palette
- **WHEN** they open the palette again with an empty query
- **THEN** Recent lists Usage and then the server, and every page is listed below it

#### Scenario: the palette leaves out switched-off features
- **GIVEN** a registered experimental feature that is switched off, owning a sidebar entry and a kind with a resource on disk
- **WHEN** the user searches the palette for the entry's name and for the resource's name
- **THEN** neither the entry's page nor the resource is listed

#### Scenario: the palette lists pages while objects load
- **GIVEN** the palette opened before the object lists have answered
- **WHEN** the user types a page's name
- **THEN** the page is listed and can be opened
- **AND** the palette says the objects are loading

#### Scenario: a failing kind leaves the rest of the palette working
- **GIVEN** the skills list route failing and the MCP servers list answering
- **WHEN** the user opens the palette
- **THEN** the skills group shows a readable error
- **AND** MCP servers and every page are still listed and can be opened

#### Scenario: the palette with the daemon offline
- **GIVEN** the daemon cannot be reached
- **WHEN** the user opens the palette
- **THEN** it lists Pages only and says that objects need the daemon

#### Scenario: the palette says when nothing matches
- **GIVEN** the palette open
- **WHEN** the user types a query no page or object matches
- **THEN** the palette says there are no results

### Requirement: Manage stored secrets on the Secrets page
The Secrets page (`/secrets`, under the sidebar's System group) MUST be the one
page in the web UI that lists and manages stored secrets. A secret is shared
infrastructure data — one reference can be cited by MCP servers, model
providers, channels and skills at once (spec
[secret](../secret/spec.md) "Address a secret by an opaque reference") —
so it gets a page of its own rather than a section of any one kind's page, and
it is not a Settings tab, because it holds data the user manages rather than a
preference. A secret field inside a resource's own dialog stays there: a secret
is still entered where the thing that needs it is configured.

The page MUST carry:

- **List** — every secret the store reports, by its reference, with whether the
  store holds it, so a reference cited but missing reads as missing (spec
  [secret](../secret/spec.md) "List every cited reference with its presence").
- **Used by** — for each secret, what cites it, by kind and current name, each
  opening that thing's page; a secret nothing cites is marked unused.
- **Add and replace** — store a new secret, or replace the value of one that
  exists, without the value ever being shown back.
- **Reveal** — show one value behind an explicit action, which is an audited
  read (spec [secret](../secret/spec.md) "Audit every read of a secret value").
- **Delete** — refused while the secret is cited: the control MUST say what still
  uses it, naming each citer as the delete refusal does (spec
  [secret](../secret/spec.md) "Refuse to delete a secret still in use"), and
  the row MUST stay.
- **Migration assistant** — the entry point that moves plaintext secret files into
  the store, shown once that assistant ships.

This requirement fixes the page's place and its parts. What the store enumerates
beyond cited references, how each operation behaves, and the migration
assistant's steps are the secret capability's, specified with it.

#### Scenario: the secrets page lists each secret with what uses it
- **GIVEN** a registered MCP server citing a stored reference, and a model provider citing a reference the store does not hold
- **WHEN** the user opens `/secrets`
- **THEN** both references are listed, the first as present and the second as missing
- **AND** each row names its citer by kind and current name, and choosing it opens that resource's page

#### Scenario: a secret in use cannot be deleted from the secrets page
- **GIVEN** a stored secret cited by a registered channel
- **WHEN** the user tries to delete it from the Secrets page
- **THEN** the delete is refused with the channel named as what still uses it
- **AND** the secret's row is still listed

#### Scenario: revealing a secret is an explicit, audited read
- **GIVEN** a stored secret listed on the Secrets page
- **WHEN** the page renders, and then the user chooses Reveal on that row
- **THEN** no value is shown until Reveal is chosen
- **AND** the reveal records a `secret_read` audit entry carrying the reference only

### Requirement: Mark a sidebar entry whose kind needs attention
A sidebar entry MUST carry a count badge while the kind or tool behind it has
things that need the user, so they are seen from wherever the user is. The
sidebar speaks only through these badges, and only for things that need the
user — failures, drift, a held vault, a required CLI that is missing, too old or
not logged in; an informational count (how many servers, how many documents
waiting in a knowledge collection's inbox) MUST NOT become a badge. The badge
shows how many things need the user, toned danger while any of them is a
failure and warning otherwise, rendered by one shared component with an
accessible name that says the entry needs attention. On the collapsed icon rail
it MUST shrink to a dot of the same tone on the icon, and the row's tooltip
carries the count ("MCP servers · 1 failing").

What raises a signal and what clears it belongs to the capability that owns the
kind: the entries of Agents, MCP servers, Skills and Channels count the
non-informational items the cross-kind attention list reports for their kind
(spec [resource-framework](../resource-framework/spec.md) "Report what needs a
person across every kind"); Sync keeps its own signal, one situation cleared by
visiting the page (spec [vault-sync](../vault-sync/spec.md) "Say a vault needs a
human where the user already is"); CLIs counts the required commands that need
the user. Knowledge and Memory carry no badge. An entry whose kind declares no
signal MUST NOT carry a badge, and a signal that has not loaded, or whose read
failed, MUST leave no badge rather than an error in the sidebar.

#### Scenario: an entry whose kind needs attention carries a count badge
- **GIVEN** a sync round held for confirmation, and two MCP servers the attention list reports, one of them failing
- **WHEN** the user is on any page other than Sync
- **THEN** the Sync entry carries a badge of 1 and the MCP servers entry a danger badge of 2, each with an accessible name saying it needs attention
- **AND** no other entry carries one

#### Scenario: the attention dot stays on the collapsed rail
- **GIVEN** the MCP servers entry carrying a badge for one failing server
- **WHEN** the sidebar is collapsed to its icon rail
- **THEN** the MCP servers icon carries a dot of the same tone, and its tooltip reads "MCP servers · 1 failing"

#### Scenario: an entry without a signal never carries a badge
- **GIVEN** every attention signal the kinds declare is raised, and documents waiting in a knowledge collection's inbox
- **WHEN** the sidebar renders
- **THEN** only the entries whose kinds declare a signal carry a badge, and Knowledge carries none
- **AND** an informational item of the attention list raises no badge

#### Scenario: an unreadable signal leaves no badge
- **GIVEN** the route behind a kind's attention signal failing, or not yet answered
- **WHEN** the sidebar renders
- **THEN** that entry carries no badge and the sidebar shows no error

### Requirement: Open Settings as a modal from the sidebar footer
Settings MUST NOT be a navigation entry: it is not one of the sidebar's fifteen
entries and belongs to no group. It MUST open as a large modal over the current
page from three places: a labelled **Settings** row — a gear icon and the word
Settings, not an icon-only button — at the bottom of the sidebar, just above the
daemon status (see "Show the daemon's state in the shell footer"); the ⌘,
shortcut on macOS and Ctrl+, elsewhere, from any page; and the command palette's
Settings tabs. On the collapsed icon rail the row MUST shrink to the gear icon
with a tooltip reading Settings. The row MUST show as active only while the
modal is open, and never mark the page underneath as not current. The row and
the shortcut open it on General; the footer's daemon state opens it on Daemon. Settings is machine-level
configuration a user visits rarely, so it takes no place in the sidebar
beside the pages used every day, the convention of desktop applications' own
preferences windows.

The modal MUST stay addressable by route: each tab is `/settings/<tab>`
(General, Security, Data, Daemon, About — see "Organise Settings into five
tabs"), and while it is open the address bar and history carry that route,
so a deep link, a reload, a link from another page (such as the footer's link
to `/settings/daemon`) or the palette opens the modal on that tab.
Opening it from a page MUST keep that page rendered underneath, unchanged.
Closing it — the close control, Escape, or a click outside it — MUST return to
the page underneath at that page's own route. A deep link opened with no page
underneath, as on a fresh load of `/settings/daemon`, MUST render the modal over
Overview, and closing it lands on `/`. Browser Back from an open modal MUST
close it and return to the page underneath.

#### Scenario: the Settings row opens Settings over the current page
- **GIVEN** the user on `/mcp-servers`
- **WHEN** they click the labelled Settings row at the bottom of the sidebar, above the daemon status
- **THEN** the Settings modal opens on General, the URL reads `/settings/general`, and the MCP servers list stays rendered underneath
- **AND** the Settings row shows as active while the modal is open and not after it closes, and the fifteen navigation entries do not include Settings

#### Scenario: the collapsed rail keeps Settings as a gear with a tooltip
- **GIVEN** the sidebar collapsed to its icon rail
- **WHEN** the user hovers the gear icon above the daemon state and clicks it
- **THEN** a tooltip reads Settings, and the click opens the Settings modal on General

#### Scenario: the keyboard shortcut opens Settings
- **GIVEN** the app open on any page, with focus outside a text field
- **WHEN** the user presses ⌘, on macOS or Ctrl+, elsewhere
- **THEN** the Settings modal opens on General over that page

#### Scenario: closing Settings returns to the page underneath
- **GIVEN** the Settings modal opened from `/activity` and switched to its Data tab
- **WHEN** the user presses Escape, and again after reopening it and pressing browser Back
- **THEN** each time the modal closes and the app is on `/activity`, with the Activity page as it was

#### Scenario: a deep link opens a Settings tab
- **GIVEN** a fresh load of `/settings/daemon`
- **WHEN** the route resolves
- **THEN** the Settings modal opens on its Daemon tab over the Overview page
- **AND** closing it lands on `/`

#### Scenario: the palette opens a Settings tab over the current page
- **GIVEN** the user on `/skills`
- **WHEN** they open the palette, type "data" and press Enter
- **THEN** the Settings modal opens on its Data tab at `/settings/data`, with the Skills page underneath

### Requirement: Manage custom tools on their own page
The Custom tools page (`/custom-tools`, under Capabilities) MUST manage custom
tools, which have one type in 1.0 — **HTTP API**: a tool is one HTTP request
Coffer makes on an agent's behalf — and MUST manage them in **groups**. A group
is one `mcp_server` resource of the HTTP API transport, served through the same
gateway as every other MCP server, and carries:

- a **name**, fixed once the group exists, which is the prefix every agent sees:
  a tool reaches agents as `<group>__<tool>`, under the same name rules as any
  MCP server ([mcp-gateway](../mcp-gateway/spec.md) "Manage MCP servers as resources");
- a shared **base URL** its tools' paths are relative to;
- an optional **auth header** whose value is bound to a stored secret, chosen by
  its name on the Secrets page (see "Manage stored secrets on the Secrets
  page"): Coffer's gateway adds the header
  when it calls the API, and neither the header's value nor the secret's
  reference is ever part of what an agent sees or sends;
- a default **reach**, which each tool follows unless it overrides it.

Each tool in a group MUST carry its own **on/off** switch, an optional **reach
override**, and a **changes data** flag — on by default for every method but
GET, and editable — which the gateway passes to agents as the tool's MCP
annotations (`readOnlyHint` false and `destructiveHint` true when it changes
data, `readOnlyHint` true otherwise), so each agent's own approval prompts apply
to it. The page MUST list the groups grouped by health, the failing ones first,
each showing its tools. Its header MUST carry one action, **Add custom tool**,
whose flow asks first for the group. An existing group MUST only take a request
added by hand, which uses that group's base URL and secret; only a **new** group
offers the two ways in:

- **Import an OpenAPI spec** — from a URL or a file, into the new group; the user
  ticks which operations become tools, reads ticked and operations that change
  data unticked, and a review lists the ticked ones as the tools to create and the
  rest as **Skipped** before **Create group with N tools**. A group made by
  an import MUST offer **Re-import**, which reads the spec again and lists the
  change first — operations it would add (reads become tools, switched on;
  operations that change data are listed but not ticked), tools whose request
  the spec changed, and tools it would remove — before anything changes;
  applying keeps every unchanged tool's switch and reach override as they were.
- **Define one request by hand** — the new group's name, base URL, auth and
  default reach, then its first request: method, path, headers, body template
  and arguments.

Every request form MUST end with **Test**, which runs the request as the form
holds it once and shows the answer, the API's error body, a timeout, a failed
connection or a response cut short; nothing — neither a new group nor a tool — is
saved until the form's **Add** or **Save**. A request of a group that is not saved
yet is tested without its secret (see [mcp-gateway](../mcp-gateway/spec.md) "Test
a custom tool request before its group is saved"). With no group yet the page
MUST show only a first-run panel, with Add custom tool in the header and in the
panel. A group's **⋯** menu MUST offer Edit group, Re-import (for an imported
group), Turn off and Delete group.

A group's detail page (`/custom-tools/<group>`, and no other route) MUST be one
page with no tabs: the group's **definition** (base URL, and the auth header with
the name of the secret it is bound to), its **reach**, a one-line summary of the
last 24 hours (calls and failures), and the **tools table** — each tool's
method and path, its switch, its changes-data flag and its reach override. Choosing
a tool opens its editor in a **drawer** over the page, where the request is
edited and a **Test** action calls the tool with sample arguments and shows the
response. Script tools are not offered: they are deferred past 1.0.
How the gateway runs an HTTP API tool is specified with the change that adds the
transport.

#### Scenario: importing an OpenAPI spec creates a group with the chosen operations
- **GIVEN** an OpenAPI document with five operations
- **WHEN** the user chooses Add custom tool, imports the document, names the group `billing`, binds its auth header to a stored secret and picks three operations
- **THEN** one group `billing` is created with those three tools, each on and following the group's reach
- **AND** the group's detail page offers Re-import

#### Scenario: re-importing a spec previews the operations it adds and removes
- **GIVEN** the `billing` group imported with three operations, one of them switched off and one with a reach override
- **WHEN** the spec now has one of those operations removed and a new one added, and the user chooses Re-import
- **THEN** a preview lists the operation to add and the tool to remove, and nothing changes until the user confirms
- **AND** after confirming, the kept tools keep their switch and reach override
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

#### Scenario: a tool's reach override narrows one tool
- **GIVEN** the `billing` group reaching Claude Code and Codex
- **WHEN** the user overrides one tool's reach to Claude Code only
- **THEN** Codex no longer sees that tool and still sees the group's other tools
- **AND** Claude Code sees all of them

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
- **THEN** the failing group is listed first with its tools, and the page header carries one Add custom tool action whose flow asks for an existing or new group and offers Import an OpenAPI spec and Define one request by hand, and no Script type

#### Scenario: a group's page is one page with a tool drawer
- **GIVEN** the `billing` group with three tools
- **WHEN** the user opens `/custom-tools/billing` and chooses one tool
- **THEN** the page shows the definition with the bound secret's name, the reach, a one-line 24-hour summary and the tools table, with no tabs
- **AND** the tool opens in a drawer with its request and Test, and the address stays `/custom-tools/billing`

#### Scenario: a tool that changes data is annotated for the agent
- **GIVEN** a group with a `GET /invoices` tool and a `POST /refunds` tool, and the user turning the changes-data flag off on a third, `POST /search`
- **WHEN** an agent lists the group's tools
- **THEN** `refunds` carries `readOnlyHint` false and `destructiveHint` true, while `invoices` and `search` carry `readOnlyHint` true, so the agent's own approval applies to `refunds`

### Requirement: Show every CLI a skill requires on the CLIs page
The CLIs page (`/clis`, under Capabilities) MUST list one row per command that
any skill requires or any enabled stdio MCP server starts with (spec
skill-manager "Check every required command where the agent runs"), with the
version found beside the minimum the skills ask for, the login state where the
command has one, and how many MCP servers and skills need it, problems first —
missing, older than the minimum, or not logged in, grouped under Needs you above
Ready — as a split view with the selected CLI's detail beside the list
(`/clis/<command>`). The detail's Needed by MUST list the MCP servers started
with the command, each opening that server's page and naming its launcher, and
the skills that declare it, each opening that skill's Requires tab; each row
carries its kind when both need it. The app MUST NOT show an install, update or
login command, a "run it in a terminal" instruction, or run any of them: a CLI
that needs the user says what it costs in a plain sentence — which servers can't
start and which skills fail — and its detail page and the skill's Requires tab
MUST offer the daemon's hand-off prompt (spec skill-manager "Hand a required
command to an agent with a prompt") through **Copy prompt** and **Ask an agent**
— the latter opens a new conversation with a Coffer-managed agent chosen in the
New conversation dialog, with the prompt in the composer and nothing sent until
the user presses Send; with no managed agent available only Copy prompt is
offered. The detail page also offers **Check again**, which probes the command
afresh. A skill's detail page MUST link each requirement it declares to
that CLI's page, and Overview MUST show an attention item while any required CLI
is missing, outdated or not logged in. What a skill declares and how a command
is probed are specified by skill-manager; this page shows what they report.

#### Scenario: the CLIs page lists problems first
- **GIVEN** two skills requiring `gh` (minimum 2.40, found 2.30) and `jq` (found, no minimum), and one requiring `gcloud` (not logged in)
- **WHEN** the user opens `/clis`
- **THEN** `gh` and `gcloud` are listed before `jq`, `gh` shows 2.30 against 2.40, `gcloud` shows not logged in, and each row names the skills that need it

#### Scenario: a CLI that needs the user offers a prompt for an agent
- **GIVEN** a required CLI that is missing and a Coffer-managed agent
- **WHEN** the user opens its detail page and chooses Ask an agent, then that agent
- **THEN** a new conversation opens with the prompt in the composer, and nothing is sent until the user presses Send
- **AND** the page offers Copy prompt, shows no install command, and with no managed agent available offers only Copy prompt

#### Scenario: check again after logging in
- **GIVEN** a CLI's detail page showing not logged in, with the hand-off to an agent and no login command shown
- **WHEN** the user logs in and chooses Check again
- **THEN** the page probes the command afresh and shows it as logged in

#### Scenario: a CLI an MCP server starts with lists that server
- **GIVEN** `uv` missing, needed by the MCP server `duckdb` (started with `uvx`) and the skill `data-profiling`
- **WHEN** the user opens `/clis/uv`
- **THEN** the list row reads "Not found · duckdb needs it" with "1 server · 1 skill", the header reads "needed by 1 MCP server and 1 skill", and the banner says duckdb can't start and data-profiling fails at the step that calls uv
- **AND** Needed by lists `duckdb` (MCP server, "starts with uvx") opening `/mcp-servers/duckdb` and `data-profiling` (Skill) opening its Requires tab

#### Scenario: a skill's requirement links to its CLI
- **GIVEN** a skill that requires `gh`
- **WHEN** the user opens the skill's detail page and chooses the `gh` requirement
- **THEN** the app opens `/clis/gh`

#### Scenario: overview flags a required CLI that needs attention
- **GIVEN** a required CLI that is outdated
- **WHEN** the user opens Overview
- **THEN** an attention item names the CLI and the problem and opens its page
- **AND** once every required CLI is present, current and logged in, no such item is shown

### Requirement: Resize every split view by its divider
Every split view — a list beside its detail, a file tree beside its file, a
conversation list beside its thread, and the sidebar beside the workspace — MUST
be resizable by dragging the divider between its panes. Each pane MUST keep a
minimum width: a list pane at least 240px and a detail pane at least 480px, and
a list pane at most half the window; the expanded sidebar between 200px and
300px (the collapsed icon rail keeps its own fixed width, see "Collapse the
sidebar to a remembered icon rail"). A drag MUST stop at those bounds rather
than pass them. Double-clicking a divider MUST restore that split's default
width. A divider MUST be keyboard-focusable, with an accessible name saying what
it resizes, and while it has focus ← and → MUST move it by a fixed step within
the same bounds.

The chosen width MUST be remembered per page in that viewer's browser storage
and restored on the next visit. It is a convenience: when the storage is empty,
unreadable or blocked, the split opens at its default width and still works,
and a remembered width that no longer fits the window is clamped to the bounds.

#### Scenario: dragging a divider resizes and survives a reload
- **GIVEN** the Skills detail page with its file tree beside the file
- **WHEN** the user drags the divider to widen the tree, then reloads the page
- **THEN** the tree keeps the width it was dragged to, on that page only

#### Scenario: a divider cannot be dragged past a pane's minimum
- **GIVEN** the Conversations page with its list beside the conversation
- **WHEN** the user drags the divider towards the list until the list would be narrower than 240px, and then the other way until the thread would be narrower than 480px or the list wider than half the window
- **THEN** the divider stops at 240px, and at whichever of the other two bounds comes first

#### Scenario: double-clicking a divider restores the default
- **GIVEN** a split view whose divider was dragged to a remembered width
- **WHEN** the user double-clicks the divider
- **THEN** the split returns to its default width, and that default is what the next visit opens with

#### Scenario: a divider moves from the keyboard
- **GIVEN** the sidebar expanded at its default width
- **WHEN** the user tabs to the sidebar's divider and presses → three times, then ← once
- **THEN** the sidebar widens by two steps in total, never past 300px, and the divider announces what it resizes

#### Scenario: no stored width falls back to the default
- **GIVEN** browser storage that is blocked for the page
- **WHEN** a split view opens and the user drags its divider
- **THEN** the split opens at its default width, the drag still resizes it, and no error is shown

### Requirement: Show a knowledge document's history on its History tab
A knowledge document's pane MUST carry two tabs, **Document** (the default) and **History**. History
lists the document's versions newest first — who wrote each (the user, Coffer's curation naming the
agent whose item it curated, or sync) and when — and choosing a version shows its diff against the
one before, with **Restore this version**, which writes a new version rather than rewriting the
past (spec [knowledge](../knowledge/spec.md) "Keep every document's history and undo a pass as a
whole"). A history that cannot be read MUST say so in the tab with a retry, leaving the Document tab
working.

#### Scenario: the history tab lists versions with their writers
- **GIVEN** a document the user created, that curation then changed from a Claude Code item
- **WHEN** the user opens its History tab and chooses the older version
- **THEN** the tab lists both versions with their writers and times, shows the diff, and offers Restore this version

#### Scenario: a history that fails to load leaves the document readable
- **GIVEN** the history read failing
- **WHEN** the user opens the History tab
- **THEN** the tab says it could not load the history and offers a retry, and the Document tab still renders

### Requirement: Follow knowledge changes in Recent changes
The Knowledge page MUST carry a **Recent changes** view: one timeline across every collection, newest
first, of curation passes and of documents people and agents wrote or deleted, filterable to one
collection, with the items still waiting and a quiet **Curate now** beside them (spec
[knowledge](../knowledge/spec.md) "Run curation on a sweep and on demand"). Choosing a pass MUST show
what it changed — each document it wrote or retired, with a diff — and offer **Undo this pass**, which
asks first and undoes the whole pass, reporting a refusal that names the document changed since. The
wording is Curate / Curation (整理) throughout.

#### Scenario: recent changes shows a cross-collection timeline with waiting items
- **GIVEN** a pass in one collection, a person's edit in another, and two items waiting
- **WHEN** the user opens Recent changes
- **THEN** both changes are listed newest first with their collections, the two waiting items are shown with Curate now, and filtering to one collection leaves only its entries

#### Scenario: a pass is inspected and undone as a whole
- **GIVEN** a pass that changed two documents
- **WHEN** the user opens it in Recent changes, reviews the diffs and confirms Undo this pass
- **THEN** both documents are back as they were before it, and the timeline shows the undo as a new entry

### Requirement: Show memory delivery on the Memory page
The Memory page MUST show what memory delivery is doing, and the agent detail page MUST show only
the delivery hook's state:

- The **Memory overview** MUST list, for each agent, its deliveries in the last seven days — counted
  from the delivery-fire audit events (spec [memory](../memory/spec.md) "Audit every delivery fire")
  — how many distinct memories its sessions read in that time, counted from the file paths its
  transcripts record reading, never from their content, and when it was last delivered to. An agent
  with no delivery in that time reads **not delivered in the last 7 days**, with no hook detail; a
  count that cannot be computed reads as unavailable rather than zero.
- A **partition's page** has a **Delivered** tab (see memory "Present a partition as its memories")
  showing, read-only, the exact session-start text each agent receives in that partition's project
  (spec [memory](../memory/spec.md) "Deliver the index and the notes path at session start"), with a
  switch between agents.
- The delivery hook's state — installed and current, stale, missing, never fired, and Repair — MUST
  appear only on the agent detail page, on its Hooks tab and in the Overview's Coffer connection
  block ([agent-registry](../agent-registry/spec.md) "Show the Coffer connection on the agent pages"). The
  agent's Memory tab shows only the agent's own native memory stores.

#### Scenario: the memory overview lists deliveries per agent
- **GIVEN** Claude Code with 12 delivery fires in the last seven days, the last one an hour ago, and transcripts recording reads of 5 distinct memories, and Codex with no delivery in that time
- **WHEN** the user opens the Memory page
- **THEN** Claude Code reads 12 deliveries, 5 memories read and last delivered an hour ago, and Codex reads not delivered in the last 7 days with no hook detail

#### Scenario: a partition's delivered tab shows each agent's session-start text
- **GIVEN** a partition for the `coffer` repository and both agents connected
- **WHEN** the user opens the partition's Delivered tab and switches from Claude Code to Codex
- **THEN** the tab shows, read-only, the exact session-start text each agent receives in that project

#### Scenario: hook state appears only on the agent page
- **GIVEN** Claude Code's delivery hook stale
- **WHEN** the user opens the Memory page and then Claude Code's detail page
- **THEN** the Memory page shows no hook state, Claude Code's Hooks tab and Overview connection block show the hook as stale with Repair, and its Memory tab lists only its own native memory stores

### Requirement: Stream new Activity records while the list is at the top
The visible Activity tab MUST show new records as they are written, newest first, with no Pause /
Resume control. While the user is at the top of the list and has no record open, a new record MUST
be inserted at the top at once. While the user has scrolled down or has a record open, new records
MUST be held rather than inserted — so the row being read does not move — and a **N new** control
MUST appear, counting them; choosing it scrolls to the top and inserts them. Scrolling back to the
top by hand inserts them too. New records MUST honour the tab's filters: one the filters exclude is
neither inserted nor counted.

#### Scenario: new records stream in at the top
- **GIVEN** the MCP calls tab open at the top of its list, with no row open
- **WHEN** the gateway proxies two calls
- **THEN** both appear at the top of the table without any control being used, and the page has no Pause or Resume control

#### Scenario: new records are held while the user reads
- **GIVEN** the Changes tab scrolled down, or with one row expanded
- **WHEN** three new audit entries are written
- **THEN** the rows on screen do not move and a 3 new control appears
- **AND** choosing it scrolls to the top and inserts the three entries

### Requirement: Export the filtered Activity records from the overflow menu
The Activity page's overflow menu MUST offer **Export as JSON** and **Export as CSV**, which save the
records of the visible tab that match its current filters — free text, time range and the tab's own
filter — and nothing else. The page header MUST carry no export button of its own.

#### Scenario: export from the menu honours the filters
- **GIVEN** the MCP calls tab filtered to one server and to failed calls
- **WHEN** the user chooses Export as CSV from the page's overflow menu
- **THEN** the file holds exactly the calls that match those filters, one per row, and the header shows no export button
- **AND** Export as JSON saves the same records as JSON

### Requirement: Show what needs the user and each area's health on Overview
Overview MUST answer "is everything OK, and what needs me?" at a glance, from
the capabilities' own reads and never a route of its own. **Needs you** comes
first: one row per item of the attention list ([resource-framework](../resource-framework/spec.md)
"Report what needs a person across every kind"), most severe first and then
oldest, each with its resource and kind, the reason in a sentence, since when
where that is known, and exactly one action that opens the page — or the tab —
where the item is dealt with. A row whose item carries a hand-off MUST also
offer it in the row's ⋯ menu — Copy prompt, and Ask an agent while a managed
agent is available — with the daemon's prompt as given, the same hand-off the
item's page offers. An attention source that failed MUST be named
above the rows, saying that what it would report is missing. Rows MUST clear
themselves as problems resolve: the page follows the daemon's event stream and
rereads the list when an `attention` change arrives. **Health** follows: one
tile per sidebar area whose feature is switched on — Agents, MCP servers,
Skills, Knowledge, Memory, Model providers, Channels, Sync, Custom tools, CLIs,
Secrets and Usage, in that order (Conversations show in Recent activity) —
each with a status word drawn from that area's attention items (Secrets, which
has no attention source, words its own list: a secret missing on this machine,
one nothing uses; Usage shows its period and no health), a count from its own
list and a one-line summary, opening the area's page; an area with no backend
has no tile. Each tile loads and fails
on its own: a failed tile says so with Retry and a link to its page while the
rest of the page keeps working. **Recent activity** lists the last few changes
with a link to Activity. With nothing needing the user the list is a calm "all
good" card rather than an empty space. With no agent registered the page is
the first-run panel alone: the supported agents with their config folders and
whether each was found on this machine, the found ones ticked, and **Review
and connect** opening the connection review for the ticked ones (every file
change shown before Coffer writes it); with none found it says so and its first
step is **Scan again**; both offer adding an agent by hand, and the first step
for what agents share follows.

#### Scenario: overview lists what needs the user, most severe first
- **GIVEN** an MCP server whose last test failed a day ago, an agent not connected since an hour ago and a warning from sync
- **WHEN** the user opens Overview
- **THEN** Needs you lists the server first, then the sync item, then the agent, each with its reason, since when and one action opening its page

#### Scenario: a needs-you row offers the item's hand-off in its menu
- **GIVEN** an attention item carrying a hand-off prompt, and a managed agent available
- **WHEN** the user opens the row's ⋯ menu and chooses Copy prompt, then Ask an agent
- **THEN** the daemon's prompt is copied as given, and Ask an agent opens New conversation and then the draft with the prompt in its composer, unsent
- **AND** with no managed agent available the menu offers Copy prompt only, and a row whose item has no hand-off and cannot be ignored has no menu

#### Scenario: overview shows a calm card when nothing needs the user
- **GIVEN** an attention list with no items and no failed source
- **WHEN** the user opens Overview
- **THEN** Needs you shows "Nothing needs you" with when it was checked, and the health tiles show their areas as fine

#### Scenario: overview welcomes a first run with the agents to connect
- **GIVEN** a vault with no agent registered
- **WHEN** the user opens Overview
- **THEN** the page offers to connect the supported agents, naming which were found on this machine, followed by the first step for what they share
- **AND** with no supported agent found it says none was found and offers Scan again in place of connecting

#### Scenario: one area failing to load leaves the rest of overview working
- **GIVEN** the knowledge read fails while every other read answers
- **WHEN** the user opens Overview
- **THEN** the Knowledge tile says it could not load, with Retry and a link to Knowledge, and every other tile and the Needs you list render

#### Scenario: overview hides an area whose backend or feature is off
- **GIVEN** an area owned by a registered experimental feature that is switched off
- **WHEN** the user opens Overview
- **THEN** there is no tile for that area, while Custom tools, CLIs, Secrets and Usage each have one

#### Scenario: a resolved problem leaves overview on its own
- **GIVEN** Overview open with one item in Needs you
- **WHEN** the problem is resolved and the daemon announces an `attention` change
- **THEN** the page rereads the attention list and the row disappears without a reload
