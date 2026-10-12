## MODIFIED Requirements

### Requirement: Use one shared table for every list surface
Every list surface that is a table — agents, the rounds
on Sync's Status tab — MUST use one shared table. It is searchable, filterable
and paginated where its list needs that, and it behaves the same everywhere:

- the filter row is the search first (`/` focuses it), then the pills, then
  **Clear filters** while anything is set, and shows no result counts;
- only number and time columns sort, in three states (one direction, the other,
  then the page's own order);
- a list that is bounded in memory shows whole, and past 100 rows grows 100 at a time as its
  end scrolls into view, with no button to press and no page-size setting; a list that can
  outgrow that pages by cursor and loads on scroll;
- a time reads relative while recent ("3 h ago") and as a date ("Aug 12") after;
- rows are selected with the header checkbox, a bar over the table reads "N of M
  selected" with the actions that apply, it holds no select-all of its own, and
  **Esc** clears the selection;
- a row's detail that opens beside the list opens in the one right-hand drawer,
  640 wide over a dimmed page, resized by dragging its left edge and widened as
  far as it goes by its **Maximize** button until **Restore** or a drag, closed
  by **Esc**, a click outside or its ✕, with focus returning to the row.

The rules above have their exceptions: Sync's rounds table, whose quiet rounds
fold into one row, has no search or filter. A row click MUST open that item's
detail page, or for a sync round, its drawer. The Model providers, Channels, MCP
servers, Custom tools, Skills and CLIs pages are lists beside a reading pane
instead: a filterable list of rows, each a link that opens its item in the pane
at the item's own address, so a row click opens the item there; the same holds
for the rows of an agent's Skills, MCP servers and Plugins tabs, where the row
opens the dialog or page its name opens. A click anywhere on such a row MUST do
what a click on its name does, except when it lands on a control inside the row
(a button, link, switch, checkbox, menu item or input), carries a modifier key,
or ends a text selection; the name stays a real link or button, so keyboard
focus, Cmd/Ctrl-click and middle-click keep working. Knowledge is
its collection tree beside the pane in the same way, and Memory its scopes
beside the open scope's memories, each opening in the drawer. Activity's tabs share one
record list of their own, each row opening its record (see "Filter each
Activity tab and expand any row"). Sync's Remote tab is not a list surface: it
is the remote's settings, and the machine registry on its Machines tab is a
small plain table.

#### Scenario: a selection bar counts the rows and Esc clears it
- **GIVEN** a list with several rows
- **WHEN** the user ticks two rows, and then presses Esc
- **THEN** a bar reads "2 of N selected" with the actions that apply and holds no select-all, and Esc leaves no row selected and no bar

#### Scenario: a click anywhere on a list row opens its detail
- **GIVEN** the Skills library, the MCP servers list or an agent's Plugins tab showing at least one row
- **WHEN** the user clicks the row's empty space or a plain text cell, and then, on another row, clicks its switch or ⋯ menu
- **THEN** the first click opens that item's detail page or dialog, and the second only toggles or opens the menu without opening a detail

#### Scenario: a row click opens the item's detail page
- **GIVEN** a list surface showing at least one row
- **WHEN** the user clicks the row, or presses Enter on it
- **THEN** the app navigates to that item's detail page

#### Scenario: a drawer maximizes and restores
- **GIVEN** a record open in the shared drawer
- **WHEN** the user chooses Maximize, and then Restore
- **THEN** the drawer first takes the page's width but for a strip on the left, then returns to its dragged width
