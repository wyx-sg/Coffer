## ADDED Requirements

### Requirement: Act on several of an agent's own items at once
On the agent's Skills, MCP servers and Plugins tabs, the agent's own part MUST let the person tick several items and act on them together; Coffer's part (the From Coffer row) MUST NOT. Each row carries a checkbox and a select-all box heads the list; select-all reaches only the rows the search shows, and a row that cannot be acted on in bulk (an MCP entry of a config file that does not parse) takes no checkbox. While any row is ticked, a selection bar reading "N of M selected" replaces the search row, with the actions — safe ones first, destructive last — and Clear; Escape clears the selection unless a dialog is open.

A bulk action MUST send the same request the single-item action sends, once per item and one after another, MUST NOT stop at the first failure, and MUST refresh the tab's lists once at the end. When every item went through, the person is told once and the selection clears. When some failed, the failures are listed by name with the reason, and Retry sends only them. An action that cannot apply to some of the ticked items MUST say how many it skips.

- **Skills** — **Adopt** acts on unmanaged folders only and opens one confirmation with a reach shared by every adopted skill (every agent by default); each skill keeps its folder name, and a name Coffer already has fails that skill alone. **Delete…** acts on every ticked folder behind one confirmation naming them.
- **MCP servers** — **Adopt** acts on entries that bypass Coffer only, under each entry's own name and with the default secret references; its confirmation says how many secret values move into the secret store. **Remove…** acts on every ticked entry behind one confirmation naming each entry and its file.
- **Plugins** — **Enable** and **Disable** need no confirmation and act on the plugins not yet in that state, saying how many were already; **Uninstall…** asks first and is disabled, with the reason, while the agent's program is not found.

#### Scenario: adopt or delete several of the agent's own skills at once
- **GIVEN** an agent with three unmanaged skill folders and one duplicate of a skill Coffer delivers
- **WHEN** the user ticks all four rows, chooses Adopt and confirms the shared reach
- **THEN** the three unmanaged folders are adopted one after another with that reach, the confirmation says the duplicate is skipped, and one toast reports three adopted
- **AND** a folder whose name Coffer already has is listed as failed with the others adopted, and Retry sends only it
- **AND** choosing Delete… over ticked rows deletes each ticked folder after one confirmation

#### Scenario: adopt or remove several of the agent's own MCP entries at once
- **GIVEN** an agent with two direct MCP entries that bypass Coffer, one of them with a secret-looking env value, and an entry of a config file that does not parse
- **WHEN** the user opens the tab
- **THEN** the unreadable entry has no checkbox
- **AND** ticking both readable entries and choosing Adopt shows a confirmation saying one secret value moves into the secret store, and confirming adopts each under its own name with its default secret reference
- **AND** Remove… removes each ticked entry from its source file after one confirmation naming the entries and their files

#### Scenario: enable, disable or uninstall several plugins at once
- **GIVEN** an agent with three plugins, two on and one off
- **WHEN** the user ticks all three and chooses Disable
- **THEN** the two plugins that are on are switched off without a confirmation and the toast says one was already off
- **AND** Uninstall… asks once for the ticked plugins and is disabled, with the reason, while the agent's program is not found
