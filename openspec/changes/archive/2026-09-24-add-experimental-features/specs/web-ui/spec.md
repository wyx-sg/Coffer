## MODIFIED Requirements

### Requirement: Keep the sidebar to its eleven entries
The sidebar's entries MUST be exactly these, in these three groups and at these
routes — eleven today, and no twelfth. An entry whose
experimental feature is switched off (spec
[experimental-features](../experimental-features/spec.md) "Close every surface of a switched-off feature")
MUST be left out — Knowledge for `knowledge`, Memory for `memory`, Sync for
`vault_sync` — and MUST appear on the next render after the feature is switched
on:

```
 AGENTS
  Agents           /agents            — the consumers (Bot icon)
  Chat             /chat              — a conversation with one of them
 RESOURCES
  MCP servers      /mcp-servers       — the aggregated upstream servers
  Skills           /skills            — what Coffer delivers to agents
  Knowledge        /knowledge         — the collections under ~/.coffer/knowledge/
  Memory           /memory            — the partitions aggregated from the agents' own stores
  Model providers  /model-providers   — credentialed vendor endpoints
  Channels         /channels          — the IM transports agents answer on
 SYSTEM
  Activity         /activity          — what changed, what was called, what broke
  Sync             /sync              — converging this vault with a git remote
  Settings         /settings
```

#### Scenario: cold-start renders authenticated content
- **GIVEN** the user has never opened Coffer (localStorage is empty, no daemon.json in user HOME yet)
- **AND** every experimental feature is switched on
- **AND** `coffer daemon start` is running (so daemon.json exists in user HOME)
- **WHEN** they navigate to `http://localhost:5173/` in a real browser
- **THEN** the index redirects to `/agents` and the page renders the sidebar + main content area within 2 seconds
- **AND** the main content shows the Agents welcome view (no generic error card)
- **AND** the sidebar lists exactly Coffer's operational surfaces — Agents, Chat; MCP servers, Skills, Knowledge, Memory, Model providers, Channels; Activity, Sync, Settings — grouped under "Agents", "Resources", and "System" headings, with no other entry

#### Scenario: a switched-off feature leaves the sidebar
- **GIVEN** `knowledge` and `vault_sync` switched off
- **WHEN** the app shell is rendered
- **THEN** the sidebar lists Agents, Chat; MCP servers, Skills, Memory, Model providers, Channels; Activity, Settings — with no Knowledge and no Sync entry

### Requirement: Organise Settings into five tabs
Settings MUST carry exactly five tabs, in this order, grouped by what they
manage rather than by how Coffer is built — **General** (display preferences, when the daemon runs, and which
experimental features are switched on),
**Coffer's model** (at `/settings/engine` — Coffer's own machinery: the internal
LLM connection and model its own passes run on, the speech-to-text connection
and model voice messages are transcribed on, and the switch and interval of each
of those passes), **Data** (retention policy and manual prune), **Security**
(where the master encryption key lives — beside the database, or in the OS
keychain), and **About** (version, license, source) — and MUST open on General.
Clicking a tab swaps the right pane without a full page reload.

#### Scenario: settings layout uses the redesigned tabbed sidebar
- **GIVEN** the user navigates to `/settings`
- **WHEN** the page resolves
- **THEN** it lands on the General tab
- **AND** the settings sidebar shows General, Coffer's model, Data, Security, and About — exactly those five, in that order — with the current route highlighted
- **AND** clicking a tab swaps the right pane content without a full page reload
