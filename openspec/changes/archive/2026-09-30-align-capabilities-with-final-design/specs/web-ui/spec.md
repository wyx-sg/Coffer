## MODIFIED Requirements

### Requirement: Keep the capability tabs uniform
The Tools, Resources and Prompts tabs MUST be uniform — each carrying its count of how many are on, a filter box, All on · All off and a per-row enable toggle, with each row's use in the last 24 hours — and MUST keep that chrome even when the upstream exposes none of that kind, saying so inside the tab rather than as a bare card. A tool row opens to its full description, its input parameters and the name agents see it by. The server list likewise carries a search box, a reach filter and a client-side pager so a large vault stays navigable; the skills list works the same way.

#### Scenario: capability toggle uses the redesigned tab layout
- **GIVEN** a registered MCP server with at least one tool and one resource
- **WHEN** the user opens the server's detail page and clicks the Tools tab
- **THEN** each tool renders as a row with its name, description, and an enabled/disabled switch
- **AND** toggling a tool's switch persists the change (capability preference) and re-fetches the tool list
- **AND** the same flow works for the Resources tab and the Prompts tab

#### Scenario: resource capability toggle works via the Resources tab
- **GIVEN** a registered MCP server that exposes at least one resource URI
- **WHEN** the user navigates to the Resources tab and disables a resource via its toggle
- **THEN** the resource switch reflects the disabled state

#### Scenario: prompt capability toggle works via the Prompts tab
- **GIVEN** a registered MCP server that exposes at least one prompt
- **WHEN** the user navigates to the Prompts tab and disables a prompt via its toggle
- **THEN** the prompt switch reflects the disabled state

#### Scenario: capability search box narrows the tool list
- **GIVEN** a registered MCP server with multiple tools
- **WHEN** the user types a partial name in the capability search box on the Tools tab
- **THEN** only matching tools remain visible and non-matching tools are hidden

## ADDED Requirements

### Requirement: Test a server in the Add dialog before adding it
The Add server dialog's one-server form MUST offer Test, which tests the
config as typed without saving it ([mcp-gateway](../mcp-gateway/spec.md) "Test
an unsaved server config before adding it"), and MUST show the result in the
form before Add server: the time it took, how many tools, resources and prompts
the server listed, the first tool names, a warning for a tool whose name agents
would see as longer than model APIs accept, and the stderr lines behind Show;
or, when it failed, why — the exit code of a process that stopped — and the
last lines it printed on stderr. Values typed into Secret rows are sent for
the test only and nothing is written to the keychain. An edit to the form
after a test retires its result. A stored secret picked for a row is not
released to the test, which says the server is tested once it is added.

#### Scenario: the add form tests the unsaved server before Add server
- **GIVEN** the Add server form prefilled from a pasted command with a secret environment value
- **WHEN** the user presses Test
- **THEN** the app posts the form's config to `/api/v1/resources/mcp_server/test-config` with the typed value in `secret_values`, and shows "Test passed in 1.4 s" with the tools it listed
- **AND** no resource is registered and no secret is written

### Requirement: Review an import from the agents before it is applied
Import from your agents MUST open the shared change preview of the daemon's
import plan ([agent-registry](../agent-registry/spec.md) "Plan an import of
agents' direct MCP entries") before anything is written: the servers found,
each ticked, with the agents that hold it and a note when two agents' entries
merge into one server or an entry duplicates a server Coffer already has;
what will happen to Coffer and to each agent; and each agent config file the
import edits, with its diff. A name the daemon cannot register is listed
unticked. Unticking a server re-plans without it. Import MUST apply the ticked
entries through the apply route, and the outcome MUST say which entries were
not imported and why.

#### Scenario: the import review shows each file's diff before it imports
- **GIVEN** an agent whose config file holds one direct MCP entry
- **WHEN** the user opens Import from your agents and presses Import 1 server
- **THEN** the dialog first shows the plan with that agent's file and its diff, and only then posts the ticked entries to `/api/v1/agents/mcp-import/apply`
- **AND** the entry is not adopted one by one through the agent's adopt route

### Requirement: Show the built-in coffer server read-only
The MCP servers list MUST end with a Built-in group holding Coffer's own
`coffer` server, and its detail MUST be read-only: no Test, Edit, Delete, Turn
off or ⋯ menu, its reach a fixed "All connected agents", a note that it cannot
be edited or removed because it is how agents reach the other servers, its
calls in the last 24 hours, and its tools, always on, with the names agents see
them by. It is described by the daemon ([mcp-gateway](../mcp-gateway/spec.md)
"Describe the built-in coffer server") and is not a registered resource.

#### Scenario: the built-in coffer server is listed last and opens read-only
- **GIVEN** the MCP servers page with one registered server
- **WHEN** it renders and the user opens the Built-in `coffer` row
- **THEN** the row sits under Built-in after the registered servers and its detail shows its tools with no Test, Edit or ⋯ menu

### Requirement: Show the Skills page as the final canvas draws it
The Skills page MUST follow canvas 4.3: a compact header (title, count, help) over the library beside a reading pane. A library row MUST show, in place of its description, the one thing that needs the reader; rows ticked for bulk actions MUST show the selection both as a bar under the filter and in the reading pane (which skills, Set reach…, Delete N skills…). The open skill's Files tab MUST be one card — the folder's files with SKILL.md first beside the open file's header bar and body — whose edit mode refuses a stale save while keeping the text. The Requires tab MUST only link each command to the CLIs page. A folder in the way of an agent's link, a delete Coffer refuses, a master folder that is gone and a Git source to change MUST each be answered where they are shown, with the choice confirmed before anything is written. The Add skill dialog MUST carry the Available to reach control.

#### Scenario: a library row says what needs attention in place of its description
- **GIVEN** a skill whose declared command is missing and a Git skill with an update waiting
- **WHEN** the user opens the Skills page
- **THEN** the first row reads "Needs <command> · not installed" and the second "Update available" where their descriptions would be

#### Scenario: selected skills are set or deleted together from the reading pane
- **GIVEN** the built-in skill and two of the user's skills
- **WHEN** the user ticks the two skills
- **THEN** the reading pane names both, says the built-in skill can't be selected, and Delete 2 skills… deletes both after one confirmation

#### Scenario: a skill file changed on disk refuses the save and keeps the text
- **GIVEN** a skill file open for editing
- **WHEN** the save is refused because the file changed on disk
- **THEN** the header says Not saved, the edited text is still there, Reload, Compare and Copy my text are offered, and Save stays off

#### Scenario: the requires tab only links to the CLIs page
- **GIVEN** a skill whose declared commands are missing or not logged in
- **WHEN** the user opens its Requires tab
- **THEN** each command shows its state and Open in CLIs, and the tab offers no install, copy-command or login step

#### Scenario: a folder in the way of a skill's link is resolved by a confirmed choice
- **GIVEN** a skill whose link in one agent is a real folder Coffer did not make
- **WHEN** the user opens Review… from the skill's banner and chooses Adopt this folder
- **THEN** the dialog shows the difference first, and only the confirm button resolves that agent's copy by keeping its version

#### Scenario: a delete refused because a copy is not Coffer's stays open and says why
- **GIVEN** a skill whose delete the daemon refuses because an agent's copy is not Coffer's link
- **WHEN** the user confirms the delete
- **THEN** the dialog stays open, names the folder, says Coffer won't remove it, and offers Try again

#### Scenario: a skill whose master folder is gone offers the ways forward
- **GIVEN** a skill whose master folder was removed outside Coffer
- **WHEN** the user opens it
- **THEN** a banner says the master folder is gone, and the Files tab offers Restore it from History (not available while a skill's versions are not recorded) and Remove the skill, which opens the delete confirmation

#### Scenario: a folder no skill claims is added in place or moved out
- **GIVEN** a folder in the skills store that no skill claims
- **WHEN** the user opens it under Not in your library
- **THEN** it shows its path, whether its SKILL.md is valid and its file count, Delete folder… asks first, and Add to library… adds it and opens the new skill

#### Scenario: changing a skill's source shows the change before anything is replaced
- **GIVEN** a skill added from Git
- **WHEN** the user opens Change source…, enters another repository and chooses Check source
- **THEN** the dialog shows the change against the current version with a button to take it, and cancelling applies nothing and drops the staged source

#### Scenario: a skill is added with the reach chosen in the dialog
- **GIVEN** the Add skill dialog with Available to set to Disabled or to chosen agents
- **WHEN** the user adds the skill
- **THEN** each added skill is turned off, or scoped to the chosen agents, and with every agent nothing more is written
