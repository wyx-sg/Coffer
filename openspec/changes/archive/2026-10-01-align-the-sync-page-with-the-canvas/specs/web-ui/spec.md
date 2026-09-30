## MODIFIED Requirements

### Requirement: List only shipped surfaces in the sidebar
The sidebar MUST list only surfaces that have shipped. It MUST NOT carry "not
yet implemented" placeholders — a sidebar full of "soon" entries reads as an
unfinished scaffold, not a product; an entry leaves the sidebar when its
feature does, and returns with it. **Machines** left the sidebar as a top-level
fleet view and came back under Sync's Machines tab, where a machine is one
participant in convergence rather than a surface of its own.

#### Scenario: the sidebar carries no placeholder entries
- **GIVEN** the app shell is rendered
- **WHEN** every sidebar entry is inspected
- **THEN** each is a link to a route the app serves
- **AND** none is marked as coming soon or not yet implemented


### Requirement: Use one shared table for every list surface
Every list surface that is a table — agents, memory partitions, the rounds
on Sync's Status tab — MUST use one shared table. It is searchable, filterable
and paginated where its list needs that; Sync's rounds table, whose quiet rounds
fold into one row, has no search or filter. A row click MUST open that item's
detail page, or for a sync round, its drawer. The Model providers, Channels, MCP
servers, Custom tools, Skills and CLIs pages are lists beside a reading pane
instead: a filterable list of rows, each a link that opens its item in the pane
at the item's own address, so a row click opens the item there; Knowledge is
its collection tree beside the pane in the same way. Activity's tabs share one
record list of their own, each row opening its record (see "Filter each
Activity tab and expand any row"). Sync's Remote tab is not a list surface: it
is the remote's settings, and the machine registry on its Machines tab is a
small plain table.

#### Scenario: a row click opens the item's detail page
- **GIVEN** a list surface showing at least one row
- **WHEN** the user clicks the row, or presses Enter on it
- **THEN** the app navigates to that item's detail page

