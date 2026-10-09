## MODIFIED Requirements

### Requirement: Jump to any page or object from a command palette
The shell MUST offer a command palette, opened with ⌘K on macOS and Ctrl+K
elsewhere from any page, and from a search control in the sidebar. It MUST do
one thing — take the user somewhere — and MUST NOT carry an action that changes
state: no create, delete, enable, reach or run entry.

It lists two kinds of entry, filtered together by what the user types:

- **Pages** — every sidebar entry and every Settings tab, by the names the
  sidebar and the tabs use (see "Call a surface by one name everywhere"). A
  Settings tab opens in the Settings modal over the current page.
- **Objects** — the agents, the resources of every kind
  with a list surface (custom tools included), the CLIs and the stored secrets
  (by ref, never a value), matched by name — each
  opening its detail page; a secret, which has none, opens the Secrets page.

With an empty query it MUST show **Recent** — the last few entries chosen in
this browser, a convenience that is safe to lose — above every page. Under a
query it MUST show the single best hit as **Best match** (an exact name first,
then a match at the start of a name), then the other matching pages, then the
matching objects in one group per kind, named as the kind's sidebar entry and
in sidebar order, each group holding a few; typing more narrows them. Recent is
not shown under a query: the list holds only what matches it. A skill's row
names the agents it is delivered to (by their display names, from the skill's
own list row), as a secret's row names who uses it.

A page or object of a switched-off experimental feature MUST NOT appear. The
palette MUST read the list routes the pages already read and add no route of its
own. Arrow keys MUST move the selection, Enter MUST open it, and Escape MUST
close the palette and return focus where it was.

Pages MUST be usable at once, whatever the daemon's state. While the objects
are loading, the palette MUST say so; a kind whose list fails MUST show a
readable error in its own group and leave the other groups working; while the
daemon cannot be reached, the palette MUST list Pages only and say that objects
need the daemon. A query that matches nothing MUST say so, and what the palette
searches, rather than show an empty panel.

#### Scenario: the palette jumps to a page
- **GIVEN** the app open on any page
- **WHEN** the user presses ⌘K, types "act" and presses Enter
- **THEN** the app navigates to `/activity` and the palette closes

#### Scenario: the palette jumps to an object
- **GIVEN** a registered provider named "Team search (EU)"
- **WHEN** the user opens the palette and types part of the provider's name
- **THEN** the query lists the provider as the best match, named "Team search (EU)" and marked as a provider
- **AND** choosing it opens that provider's page and closes the palette

#### Scenario: the palette offers no actions
- **GIVEN** the palette open with an empty query, and then with queries naming objects
- **WHEN** every entry it lists is read
- **THEN** each entry is a page or an object that navigates somewhere
- **AND** choosing any of them sends no request that changes state

#### Scenario: an empty query shows recent choices above every page
- **GIVEN** the user chose an MCP server and then the Secrets page from the palette
- **WHEN** they open the palette again with an empty query
- **THEN** Recent lists Secrets and then the server, and every page is listed below it

#### Scenario: a skill result names the agents that get it
- **GIVEN** a skill delivered to Claude Code and Codex
- **WHEN** the user types part of the skill's name in the palette
- **THEN** its row reads "Skill" and "Claude Code · Codex"

#### Scenario: a query lists only its matches
- **GIVEN** an entry chosen earlier from the palette, so Recent has it
- **WHEN** the user types a query that entry does not match
- **THEN** no Recent group is shown and the entry is not listed

#### Scenario: the palette leaves out switched-off features
- **GIVEN** a registered experimental feature that is switched off, owning a sidebar entry
- **WHEN** the user searches the palette for the entry's name
- **THEN** the entry's page is not listed, and it is listed once the feature is switched on

#### Scenario: the palette lists pages while objects load
- **GIVEN** the palette opened before the object lists have answered
- **WHEN** the user types a page's name
- **THEN** the page is listed and can be opened
- **AND** the palette says the objects are loading

#### Scenario: a failing kind leaves the rest of the palette working
- **GIVEN** the skills list route failing and the MCP servers list answering
- **WHEN** the user opens the palette
- **THEN** the skills group shows a readable error
- **AND** MCP servers and every page are still listed and can be opened

#### Scenario: the palette with the daemon offline
- **GIVEN** the daemon cannot be reached
- **WHEN** the user opens the palette
- **THEN** it lists Pages only and says that objects need the daemon

#### Scenario: the palette says when nothing matches
- **GIVEN** the palette open
- **WHEN** the user types a query no page or object matches
- **THEN** the palette says there are no results
