## MODIFIED Requirements

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
- **AND** the MCP servers and Custom tools entries open `/mcp-servers` and `/custom-tools`, and a custom-tool group is not listed on the MCP servers page
- **AND** no heading reads "Resources"

