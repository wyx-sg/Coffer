## MODIFIED Requirements

### Requirement: Show the Coffer connection on the agent pages
An agent has one unconnected state, **Not connected**, and one word per other state: **Connected**, **Needs repair** (the `partial` state), **Hook not approved** (on the agent's own page: Codex has not approved, or approved an earlier command of, Coffer's memory hook), **Config left behind** and, for an added agent whose program and directory are both gone, **Not found**. A newly found agent that was never added and an agent that was disconnected are the same state, so both read Not connected and both offer **Connect**; the list has no "Not added" or "Detected" word and no Add action. Each row of the Agents list MUST show the agent's state and the one action that state calls for: **Connect** for one not connected — which, for a newly found agent, registers it under its default config directory first — **Repair** for one that needs repair, and none for one that is connected, whose ⋯ menu carries **Disconnect**. An agent whose program is not on this machine has no fix Coffer can make: its row offers the daemon's install prompt as the hand-off split button **Ask an agent ▾** before its ⋯ menu (web-ui "Hand a machine-dependent problem to an agent with one split button"), and its own page offers it in the Overview. The same states offer the same actions on the agent's own page, in the Overview's Connection section (**Connect** and **Repair** as solid buttons, **Check again** as an outline one while Codex has not approved Coffer's hook), never in the page header. The ⋯ menu, on the row and on the page, holds **Use a different config directory…**, **Reveal config directory**, **Copy uid**, and **Disconnect** while a part is installed, in that order, and never repeats a visible action — the install prompt included.

Connect, Repair and Disconnect MUST each open **Review changes** first — every file it will write and the lines it adds or removes, the connection test as the daemon reports it — and write nothing until the user applies it; **Use a different config directory…** on a connected agent moves Coffer's entry and hook to the new directory through the same review, and on an agent not yet added it registers the directory without connecting. The list has two rows, so it carries no row selection and no bulk bar. Which parts a connection installs MUST be explained behind a help affordance beside the action rather than as inline text. The Memory tab MUST NOT carry a separate install or remove action for the memory delivery hook beyond the Repair of "Show what Coffer manages for an agent in one row".

#### Scenario: the Overview offers the action the state calls for
- **GIVEN** an agent's page for an agent that is not connected, one that is connected, and one whose connection is partial
- **WHEN** each Overview's Connection section renders
- **THEN** the unconnected agent offers Connect, the connected one offers no button and has Disconnect in its ⋯ menu, and the partial one reads Needs repair and offers Repair
- **AND** the agent's Memory tab offers no action on the delivery hook while it is healthy

#### Scenario: connecting an agent previews the change first
- **GIVEN** the Codex row reading Not connected, never added
- **WHEN** the user chooses Connect
- **THEN** Review changes lists each file the connect will write and the lines it adds, and nothing is written yet
- **AND** applying registers Codex under its default config directory, connects it, and the row reads Connected

#### Scenario: repairing a partial connection previews the missing parts
- **GIVEN** a Claude Code agent whose Coffer connection is partial
- **WHEN** the user chooses Repair on its row
- **THEN** Review changes lists only the missing parts, and applying installs them and the row reads Connected

#### Scenario: moving a connected agent's config directory goes through Review changes
- **GIVEN** a connected Codex agent at `~/.codex`
- **WHEN** the user chooses Use a different config directory… and picks another directory
- **THEN** Review changes shows Coffer's lines leaving the old directory and arriving in the new one, and nothing moves until the user applies it
- **AND** applying leaves the agent connected at the new directory

### Requirement: List the supported agents as fixed rows on the Agents page
The Agents page MUST list exactly one row per supported agent type — today two, Claude Code and Codex — whether or not each is installed or added, in that order, so the page reads the same on every machine and a first-time user sees at once what Coffer can manage. Each row is found automatically from the detection state of "Detect an agent by its program and its config directory": an `installed_active` type's row reads as its Coffer state ("Show the Coffer connection on the agent pages") with its config directory and version; an `installed_never_run` type reads Not connected too, with its config directory marked as not created, and offers Connect, whose review names the directory it creates and the only entries Coffer needs in it; a `config_only` type reads as config left behind — program not found — and a `missing` type as not installed, each with no Connect and the daemon's prompt that hands reinstalling or installing it to an agent (see "Hand installing an agent's program to an agent") as the split button **Ask an agent ▾** beside its ⋯ menu — Copy prompt behind the chevron, and Copy prompt alone while no other agent can run it. A row whose program is missing shows no version, and its second line says "Not on this Mac" or what is left in the directory. The page MUST NOT show an install command, and carries no Remove action. On first run, with neither agent connected and both connectable, the page MUST offer **Connect both**, which reviews and connects every connectable agent in one confirmation. An agent is named by its type everywhere in the web UI; the page offers no field to name or title one.

Overview's Needs you lists only agents that need the person: an agent that needs repair, one whose config directory is left behind, one whose Coffer memory hook the agent will not run (reported once, by the reconciler's memory-hook target), and one whose hook it runs but has never fired ("Report an agent whose Coffer hook never fires"). Not installed, Not connected and a first run raise none.

#### Scenario: the agents page shows both supported agents on first run
- **GIVEN** a fresh Coffer with Claude Code and Codex both installed and neither connected
- **WHEN** the user opens the Agents page
- **THEN** it shows exactly two rows, Claude Code then Codex, each reading Not connected with a Connect action, and a Connect both action, and Overview lists neither as needing the person
- **AND** choosing Connect both reviews the writes for both agents and, on apply, registers and connects both

#### Scenario: an agent that is not installed shows how to install it
- **GIVEN** Codex not installed on the machine
- **WHEN** the Agents page renders
- **THEN** the Codex row reads as not installed and offers the hand-off split button carrying the daemon's prompt that hands installing Codex to an agent, shows no install command, and has no Connect action
- **AND** its ⋯ menu offers neither Copy prompt nor Ask an agent

#### Scenario: an installed agent that has never run can be added
- **GIVEN** Codex's program installed and `~/.codex` not created
- **WHEN** the Agents page renders and the user chooses Connect on the Codex row
- **THEN** the row reads Not connected, with `~/.codex` marked not created
- **AND** the review names `~/.codex` as created and lists only the entries Coffer adds, and nothing is written until the user applies it

#### Scenario: a leftover config directory reads as config left behind
- **GIVEN** `~/.codex` present and the Codex program not on the agent's `PATH`
- **WHEN** the Agents page renders
- **THEN** the Codex row reads as config left behind — program not found — offering the hand-off split button with the daemon's reinstall prompt, no install command, and no Connect action
- **AND** Overview's Needs you lists it

#### Scenario: a row's menu offers a different config directory
- **GIVEN** a Claude Code row on the Agents page
- **WHEN** the user opens the row's menu
- **THEN** it offers Use a different config directory…, and the page carries no Add agent dialog, no Remove action and no name or title field
