## MODIFIED Requirements

### Requirement: Use one shared table for every list surface
Every list surface — agents, MCP servers, skills, knowledge, memory, model
providers, channels, each Activity tab, Sync's Runs tab — MUST use one shared
searchable, filterable, paginated table, and a row click MUST open that item's
detail page. Sync's Setup tab is not a list surface: it is configuration cards,
and the machine registry it carries is a small plain table.

#### Scenario: a row click opens the item's detail page
- **GIVEN** a list surface showing at least one row
- **WHEN** the user clicks the row, or presses Enter on it
- **THEN** the app navigates to that item's detail page
