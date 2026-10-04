## MODIFIED Requirements

### Requirement: Choose how each tool is exposed
A person MUST be able to set, per tool of a server, how it is exposed to agents: `auto` (the default) leaves the decision to the tool-listing budget, so the most-used tools stay in `tools/list` and the rest are reached through `coffer__search_tools`; `listed` pins the tool into the list; `search` leaves it to `coffer__search_tools` only. The setting is the person's, kept per (server, tool) in the server's preference document in the vault, and survives a restart and switching the tool off and on; `auto` clears it. It changes only how a tool is listed, never whether it can be called. `PATCH /api/v1/resources/mcp_server/{uid}/tools/{tool}/exposure` sets one tool and `PATCH .../tools/exposure` sets several in one call (`{tools, mode}`); an unknown tool or a set containing one is refused with 404 and nothing changes, and a mode other than the three with 422. The server's tiering read reports each tool's setting, whether it is effectively listed or behind search, and why (`pinned`, `search_only`, `within_budget`, `top_by_use`, `low_use`). Each change is audited as `tool_exposure_changed`.

The server page's Tools tab MUST list every tool, not only a first page: fifty rows are shown with "Showing 50 of N" and **Show N more** reveals the rest, and its search runs over all of them, matching tool names only. Each tool row carries its exposure as a choice that reads, for example, "Auto · Listed" or "Auto · Behind search". The Resources and Prompts tabs MUST be listed in full the same way, with a search over every item's name.

#### Scenario: a server's Tools tab lists every tool
- **GIVEN** a server with 78 tools
- **WHEN** the user opens its Tools tab and chooses Show 28 more
- **THEN** 50 rows are shown first with "Showing 50 of 78", then all 78 with "Showing 78 of 78" and no Show more button
- **AND** searching for one tool's name finds it among all 78

#### Scenario: a server's resources and prompts are listed in full
- **GIVEN** a server with 120 prompts
- **WHEN** the user opens its Prompts tab and chooses Show more until none is left
- **THEN** all 120 are listed with "Showing 120 of 120", and searching for the last one's name finds it

#### Scenario: a tool's exposure is chosen by the person
- **GIVEN** a budget of two and a server with tools `a`, `b` and `c`, where `b` is the most used
- **WHEN** the person sets `c` to `listed`
- **THEN** the tiering read reports `c` as mode `listed`, effectively listed because it is pinned, `b` as `auto` and listed, and `a` as `auto` and behind search for low use
- **AND** the Tools tab shows each tool's choice, such as "Auto · Listed" or "Auto · Behind search"
