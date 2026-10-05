## MODIFIED Requirements

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
  Conversations    /conversations     — every agent's sessions, wherever they started, each opened in the agent's own terminal
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

### Requirement: Group the sidebar by what the user comes to do
The sidebar MUST be grouped by what the user comes to Coffer to do, so that each
heading names one intent and a new entry has one obvious home. There are five
groups, under headings in this order:

- **AGENTS** — set up the agents and the models they run on: Agents, then Model
  providers. Agents come first because they are the subject of the product; a
  provider is the endpoint and key each agent's model is served from.
- **RUN** — see and start what agents are working on, and set up the IM bots that put them
  to work: Conversations, then Channels.
- **CAPABILITIES** — give agents things they can do: MCP servers, Custom tools,
  Skills, then CLIs.
- **CONTEXT** — give agents things they know: Knowledge, then Memory.
- **SYSTEM** — look after Coffer and what every other part shares: Secrets,
  Activity, then Sync.

Settings sits in no group: it is machine-level configuration visited rarely, so
it opens as a modal from the sidebar footer rather than taking an entry (see
"Open Settings as a modal from the sidebar footer").

**Overview**, the landing page, MUST sit above the five groups under no heading:
it summarises all of them, so filing it under one would misname it.

A new entry MUST join the group that names what the user comes to it for, and no
group may grow past five entries; growth that is more of an existing thing — one
more agent, channel or custom tool — is a row inside that thing's page, not an
entry. A group whose every entry is left out (see "Keep the sidebar to its
fourteen entries") MUST leave its heading out too, so no heading stands over
nothing. The decision and the options it was weighed against are in
[The Sidebar Is Grouped by What the Person Comes to Do](../../../docs/decisions/sidebar-grouped-by-what-the-person-comes-to-do.md).

#### Scenario: the sidebar groups entries by what the user comes to do
- **GIVEN** the app shell is rendered with every experimental feature switched on
- **WHEN** the sidebar lists its entries
- **THEN** Overview comes first, under no heading, and the rest sit under five headings in the order Agents, Run, Capabilities, Context, System
- **AND** Agents holds Agents then Model providers, Run holds Conversations then Channels, Capabilities holds MCP servers, Custom tools, Skills and CLIs, Context holds Knowledge then Memory, and System holds Secrets, Activity and Sync

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
  agent in that agent's Change model dialog (spec
  [provider-switching](../provider-switching/spec.md) "Offer every connection operation over REST and in the web UI").
- **Channels** is filed under Run, beside Conversations and not merged into it:
  Conversations is where a person finds every session of every agent — a channel's among
  them — and opens or starts one in the terminal, while a channel is an IM bot set up once
  and revisited rarely. The conversations a channel carries are listed on the Conversations
  page with its badge (spec [chat](../chat/spec.md) "Show every agent's sessions on the
  Conversations page"), reached from the channel's Overview by one link; the Channels page
  holds setup, status and settings only.
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
- **AND** the MCP servers and Custom tools entries open `/mcp-servers` and `/custom-tools`, and a custom-tool group is not listed on the MCP servers page
- **AND** no heading reads "Resources"
