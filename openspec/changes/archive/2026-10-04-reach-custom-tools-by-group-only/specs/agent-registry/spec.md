## MODIFIED Requirements

### Requirement: Show what Coffer manages for an agent in one row
The agent's Skills, MCP servers, Hooks and Memory tabs MUST each hold two parts in the same order: what Coffer manages for the agent first, then what the agent has of its own. There is no owner column, no owner mark on a row, and no filter that switches between the two.

On **Skills** and **MCP servers**, Coffer's part MUST be one **From Coffer** row — how many skills, or servers, Coffer delivers to or serves this agent, their first names, and a link (**Open Skills ›**, **Open MCP servers ›**) to that kind's own page narrowed to this agent (`/skills?agent=<uid>`, `/mcp-servers?agent=<uid>`) — and Coffer's items MUST NOT be listed one by one on the agent's tab. The MCP servers tab carries a second **From Coffer** row for custom-tool groups, which the MCP servers row does not count, linking to `/custom-tools?agent=<uid>` (**Open Custom tools ›**). Those global lists MUST accept the `agent` query parameter and show only what reaches that agent. The agent's own part is a section titled "<Agent>'s own skills" or "<Agent>'s own MCP servers" with a one-line explanation and a search; its items are listed with one state word each — Unmanaged, Invalid SKILL.md, Foreign link, Duplicate, Bypasses Coffer — and at most one button, the fix for that row, with the rest in its ⋯ menu:

- **Skills** — **Adopt** an agent's own skill ([skill-manager](../skill-manager/spec.md) "Adopt an unmanaged skill"), which opens a form asking for the skill's **name in Coffer** and its **reach** (every agent by default, only chosen agents, or off), and **Delete duplicate** on a skill folder that has the same name as a skill Coffer delivers to that agent, which deletes the agent's copy behind a confirmation. A row opens the unmanaged skill's own page, with its properties and its files in the shared file tree and viewer.
- **MCP servers** — **Adopt** a direct entry ("Adopt a direct MCP entry into Coffer"), and **Remove duplicate** on a direct entry that `matches_resource` a registered MCP server, which removes it from its source file ("Remove a direct MCP entry from its source file") because Coffer's gateway already serves it; any entry can be taken out of its file from its ⋯ menu. A config file that does not parse is named above the list, and its entries stay read-only.

On **Hooks**, Coffer's part is Coffer's memory hook and the agent's own is its other hooks ("List every hook in the agent's native config"). On **Memory**, Coffer's part is Coffer's memory for this agent, shown only while the `memory` feature is on, and the agent's own are its native memory stores. The **Plugins** tab has only the agent's own part, since Coffer installs no plugin.

#### Scenario: Coffer's part is one row and the agent's own items follow
- **GIVEN** an agent with one Coffer-managed skill and two of its own skill folders
- **WHEN** the user opens its Skills tab
- **THEN** one From Coffer row reads one skill from Coffer and links to `/skills?agent=<uid>`, and the agent's own section lists the two folders; the Coffer-managed skill is not listed
- **AND** the tab has no owner filter or owner mark

#### Scenario: adopting a skill asks for its name and reach
- **GIVEN** an unmanaged skill folder in the agent's skills directory
- **WHEN** the user chooses Adopt on its row
- **THEN** a form asks for the name in Coffer, prefilled with the skill's own, and the reach, defaulting to every agent
- **AND** confirming adopts it under that name with that reach, and an error stays inside the form

#### Scenario: a duplicate direct MCP entry can be removed
- **GIVEN** an agent whose config file carries a direct MCP entry that matches a registered MCP server
- **WHEN** the user chooses Remove duplicate on that row and confirms
- **THEN** the entry is removed from its source file, and the MCP servers tab counts the server once, as Coffer's

#### Scenario: the global lists narrow to one agent
- **GIVEN** a skill that reaches only Claude Code and another that reaches every agent
- **WHEN** the user opens `/skills?agent=<Codex uid>`
- **THEN** only the skill that reaches every agent is listed

#### Scenario: custom-tool groups have their own From Coffer row
- **GIVEN** an agent reached by one registered MCP server and one custom-tool group
- **WHEN** the user opens its MCP servers tab
- **THEN** the MCP servers row reads one server and links to `/mcp-servers?agent=<uid>`, and a second row reads one custom-tool group and links to `/custom-tools?agent=<uid>`
