## Why

The finished System design settles the behaviours every list and page shares,
and four of them contradict what the web-ui spec says today: a list's
selection, sorting and filter row are described per page rather than once; a
problem that needs the person has two hand-off buttons where the design has one
split button; and a banner on a page can only be ignored from Overview. The
design also moves the Experimental tag from the sidebar rows to page titles
(carried by `fold-usage-into-providers`).

## What Changes

- web-ui: "Use one shared table for every list surface" gains the shared
  behaviours: the filter row (search, pills, **Clear filters**, no counts), three-state
  sorting on number and time columns only, "Showing N of M · Show all" for long
  lists, relative times, and a selection bar ("N of M selected", header
  checkbox, no select-all inside it, Esc clears) for bulk actions; a row's detail
  opens in the one 640-wide right-hand drawer.
- web-ui: "Let the user ignore any item on Overview" also covers the × on a
  page's banner (the same Ignore, shared with Overview), the page header's
  "… — ignored on Overview. Show it again", and an ignored item returning when
  its situation changes.
- web-ui: new "Hand a machine-dependent problem to an agent with one split
  button": **Ask an agent ▾** with **Copy prompt** in its menu and a "Prompt
  copied" toast, and only **Copy prompt** when no managed agent exists.

## Impact

- Frontend only: the shared table, filter, drawer, bulk-bar and hand-off
  components, and every page that used the old two buttons. Wording elsewhere in
  the spec that names "Copy prompt" and "Ask an agent" as two controls reads
  as the split button's menu item and button.
