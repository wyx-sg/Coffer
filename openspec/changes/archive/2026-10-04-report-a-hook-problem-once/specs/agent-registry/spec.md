## REMOVED Requirements

### Requirement: Report an agent whose Coffer hook needs the person
**Reason**: Its unapproved-hook case read the same trust record the reconciler's memory-hook target already reports as `hook_untrusted`, so Overview listed one problem twice. It is replaced by "Report an agent whose Coffer hook never fires", which keeps only the case nothing else reports.
**Migration**: None needed. An unapproved, disabled or unreadable hook stays on Overview as the reconciler's item, which opens the agent's Hooks tab.

## ADDED Requirements

### Requirement: Report an agent whose Coffer hook never fires
The attention list ([resource-framework](../resource-framework/spec.md) "Report what needs a person across every kind") MUST carry an `agent_hook_attention` item, at warning severity with the action of checking the agent, for a connected agent whose connection is otherwise complete when Coffer's memory hook is current and the agent runs it — it has no review step (trust `not_required`) or approved this definition (trust `trusted`) — yet the hook has never fired. A hook the agent will not run — trust `untrusted`, `modified`, `disabled` or `unknown` — produces no such item: the reconciler's memory-hook target reports it (`hook_untrusted`, `hook_disabled`, `hook_trust_unknown`), so one problem is listed once. A hook that has fired, or an agent that carries no memory hook, produces no such item either. The item is read from Coffer's own hook alone, without reading every hook file or plugin of the agent. It never replaces the more basic items: a partial connection or a missing program is reported first, one item per agent.

#### Scenario: a hook that never fired is a warning
- **GIVEN** a connected agent that runs every hook it finds and whose Coffer hook has never fired
- **WHEN** the attention list is read
- **THEN** it carries an `agent_hook_attention` item saying the hook has never fired

#### Scenario: a hook the agent will not run is left to the reconciler
- **GIVEN** a connected Codex agent whose Coffer memory hook is current but unapproved, approved for an earlier command, switched off, or whose trust record does not parse
- **WHEN** the attention list is read
- **THEN** it carries no `agent_hook_attention` item for the agent, and the reconciler's single item for that hook is the one on the list

#### Scenario: a healthy hook reports nothing
- **GIVEN** a connected agent whose Coffer hook is trusted and has fired, and one with no memory hook
- **WHEN** the attention list is read
- **THEN** neither of them carries an `agent_hook_attention` item

## MODIFIED Requirements

### Requirement: List the supported agents as fixed rows on the Agents page
The Agents page MUST list exactly one row per supported agent type — today two, Claude Code and Codex — whether or not each is installed or added, in that order, so the page reads the same on every machine and a first-time user sees at once what Coffer can manage. Each row is found automatically from the detection state of "Detect an agent by its program and its config directory": an `installed_active` type's row reads as its Coffer state ("Show the Coffer connection on the agent pages") with its config directory and version; an `installed_never_run` type reads Not connected too, with its config directory marked as not created, and offers Connect, whose review names the directory it creates and the only entries Coffer needs in it; a `config_only` type reads as config left behind — program not found — and a `missing` type as not installed, each with no button and the daemon's prompt that hands reinstalling or installing it to an agent (see "Hand installing an agent's program to an agent") at the head of its ⋯ menu — Copy prompt, then Ask an agent while another agent can run it. A row whose program is missing shows no version, and its second line says "Not on this Mac" or what is left in the directory. The page MUST NOT show an install command, and carries no Remove action. On first run, with neither agent connected and both connectable, the page MUST offer **Connect both**, which reviews and connects every connectable agent in one confirmation. An agent is named by its type everywhere in the web UI; the page offers no field to name or title one.

Overview's Needs you lists only agents that need the person: an agent that needs repair, one whose config directory is left behind, one whose Coffer memory hook the agent will not run (reported once, by the reconciler's memory-hook target), and one whose hook it runs but has never fired ("Report an agent whose Coffer hook never fires"). Not installed, Not connected and a first run raise none.

#### Scenario: the agents page shows both supported agents on first run
- **GIVEN** a fresh Coffer with Claude Code and Codex both installed and neither connected
- **WHEN** the user opens the Agents page
- **THEN** it shows exactly two rows, Claude Code then Codex, each reading Not connected with a Connect action, and a Connect both action, and Overview lists neither as needing the person
- **AND** choosing Connect both reviews the writes for both agents and, on apply, registers and connects both

#### Scenario: an agent that is not installed shows how to install it
- **GIVEN** Codex not installed on the machine
- **WHEN** the Agents page renders
- **THEN** the Codex row reads as not installed with no button, and its ⋯ menu leads with Copy prompt carrying the daemon's prompt that hands installing Codex to an agent, shows no install command, and has no Connect action

#### Scenario: an installed agent that has never run can be added
- **GIVEN** Codex's program installed and `~/.codex` not created
- **WHEN** the Agents page renders and the user chooses Connect on the Codex row
- **THEN** the row reads Not connected, with `~/.codex` marked not created
- **AND** the review names `~/.codex` as created and lists only the entries Coffer adds, and nothing is written until the user applies it

#### Scenario: a leftover config directory reads as config left behind
- **GIVEN** `~/.codex` present and the Codex program not on the agent's `PATH`
- **WHEN** the Agents page renders
- **THEN** the Codex row reads as config left behind — program not found — with no button, its ⋯ menu offering Copy prompt with the daemon's reinstall prompt, no install command, and no Connect action
- **AND** Overview's Needs you lists it

#### Scenario: a row's menu offers a different config directory
- **GIVEN** a Claude Code row on the Agents page
- **WHEN** the user opens the row's menu
- **THEN** it offers Use a different config directory…, and the page carries no Add agent dialog, no Remove action and no name or title field
