## MODIFIED Requirements

### Requirement: Use one shared table for every list surface
Every list surface that is a table — agents, memory partitions, the rounds
on Sync's Status tab — MUST use one shared table. It is searchable, filterable
and paginated where its list needs that, and it behaves the same everywhere:

- the filter row is the search first (`/` focuses it), then the pills, then
  **Clear filters** while anything is set, and shows no result counts;
- only number and time columns sort, in three states (one direction, the other,
  then the page's own order);
- a long list shows a few rows and "Showing 5 of N · Show all";
- a time reads relative while recent ("3 h ago") and as a date ("Aug 12") after;
- rows are selected with the header checkbox, a bar over the table reads "N of M
  selected" with the actions that apply, it holds no select-all of its own, and
  **Esc** clears the selection;
- a row's detail that opens beside the list opens in the one right-hand drawer,
  640 wide over a dimmed page, closed by **Esc**, a click outside or its ✕, with
  focus returning to the row.

The rules above have their exceptions: Sync's rounds table, whose quiet rounds
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

#### Scenario: a selection bar counts the rows and Esc clears it
- **GIVEN** a list with several rows
- **WHEN** the user ticks two rows, and then presses Esc
- **THEN** a bar reads "2 of N selected" with the actions that apply and holds no select-all, and Esc leaves no row selected and no bar

#### Scenario: a row click opens the item's detail page
- **GIVEN** a list surface showing at least one row
- **WHEN** the user clicks the row, or presses Enter on it
- **THEN** the app navigates to that item's detail page

### Requirement: Let the user ignore any item on Overview
Every row of Needs you — whatever its severity — MUST carry a ⋯ menu whose last entry is
**Ignore**. The daemon MUST remember an ignored item on this machine, by the item's stable key
(its kind, resource and reason), and audit each ignore and each stop: `GET /api/v1/attention` then
lists it under `ignored`, out of `items` and `counts_by_kind`, so Needs you, the Agents health tile,
the sidebar's badges and the menu bar's count all leave it out alike. Overview MUST NOT list ignored
items or count them. A banner on the page an item belongs to MUST carry an **×** that is the same
Ignore, so ignoring from the page and from Overview are one act with one key; an
ignored item returns by itself when the situation it describes changes (a
different set of conflicts, say), because the key names the situation. The page an
ignored item belongs to (the page its name opens on Overview)
MUST show one muted line under its header — the item's reason, "ignored on Overview", and a
**Show it again** button that stops the ignore (`DELETE /api/v1/attention/ignored/{key}`) and
confirms with "Back on Overview". Ignoring changes nothing about the resource itself. Asking to ignore a key that
names no item in the list is refused with `ATTENTION_NOT_IGNORABLE`.

#### Scenario: an ignored item leaves needs you whatever its severity
- **GIVEN** Overview listing Codex as not connected and an MCP server that fails
- **WHEN** the user chooses Ignore in Codex's menu, then Ignore in the failing server's menu
- **THEN** each leaves Needs you in turn, and Overview shows no "ignored" line and no list of ignored items
- **AND** the daemon's attention list carries them only under `ignored`, its counts leave them out, and both changes are audited

#### Scenario: a page banner's × ignores the item on Overview too
- **GIVEN** a page banner for an item that Overview also lists
- **WHEN** the user presses the banner's ×
- **THEN** the banner goes, Overview and the sidebar badge stop listing and counting the item, and the page's header reads "… — ignored on Overview" with Show it again
- **AND** when the situation changes the item is listed again

#### Scenario: an ignored item can be shown again from its own page
- **GIVEN** an MCP server that fails and was ignored on Overview
- **WHEN** the user opens that server's page
- **THEN** under the header a muted line gives the reason and says it was ignored on Overview, with **Show it again**
- **AND** choosing it stops the ignore, the line goes, and the item is back on Overview

## ADDED Requirements

### Requirement: Hand a machine-dependent problem to an agent with one split button
Installing, setting up, logging in and troubleshooting depend on the machine, so a problem whose fix
is outside Coffer and for which the backend wrote a concrete prompt MUST be handed over with one split
button, **Ask an agent ▾**, never two buttons: pressing the button opens a draft conversation with
the prompt typed in and sends nothing until the person presses Send; the menu's one item, **Copy
prompt**, copies the daemon's prompt as given for an agent outside Coffer and answers with a
"Prompt copied" toast. With no Coffer-managed agent installed only **Copy prompt** is offered, with
the one-sentence help beside it. The split button sits after the state's own buttons (Check again,
Retry, View log), appears once per problem, never on a healthy, success or empty state, and never for
a missing secret or an approval, which only the person can give. Wherever another requirement names
Copy prompt and Ask an agent together, they are this button's menu item and button. On a Needs you
row they are items of the ⋯ menu beside Ignore.

#### Scenario: the split button hands a prompt over or copies it
- **GIVEN** a problem with a prompt and a managed agent installed
- **WHEN** the person presses Ask an agent, and separately opens its menu and chooses Copy prompt
- **THEN** a draft conversation opens with the prompt typed in and nothing sent, and the prompt is copied as given with a "Prompt copied" toast
- **AND** with no managed agent installed only Copy prompt is offered

