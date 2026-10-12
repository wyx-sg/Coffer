## MODIFIED Requirements

### Requirement: Defer to Codex's own import from Claude Code
When Codex's own import from Claude Code is on with automatic updates on this machine, Coffer MUST NOT write Claude Code's memories into Codex on that machine, and Codex's Memory tab MUST say that Codex imports them itself. The other direction MUST continue.

#### Scenario: Codex's own import turns the Claude Code to Codex direction off
- **GIVEN** Codex's import from Claude Code on with automatic updates, and a hub entry from Claude Code
- **WHEN** memory syncs
- **THEN** no resource is written for it in Codex's extension folder, Codex's memories are still written into Claude Code, and Codex's Memory tab says Codex imports Claude Code's memories itself

### Requirement: Preview a first or large sync
The first sync on a machine, and any sync that would write more copies than a threshold (50 by default), MUST NOT write into any agent until the person confirms it on the Memory page, which lists per agent and project how many copies would be written, updated and removed, folded to those counts until opened (a group that removes anything starts open), and opened lists each memory with what the sync would do to its copy; a memory it would write or update opens in the memory drawer. Publishing to the hub MUST proceed without waiting.

#### Scenario: the first sync waits for the person
- **GIVEN** a machine that has never synced memory, with memories to write into both agents
- **WHEN** memory syncs
- **THEN** the hub is updated, nothing is written into either agent, and the Memory page counts the preview among what needs the person; its drawer lists each agent and project with its counts and, opened, each memory, with **Write** and **Cancel**
- **AND** choosing **Write** writes exactly what the preview listed

### Requirement: Show each agent's own curation and ask it to curate now
Each registered agent's Memory tab MUST show, while the memory feature is on, whether the agent's own memory and its own curation are on (Claude Code's auto memory and Auto Dream; Codex's memories feature), with a hint to turn either on when it is off, and the copies Coffer wrote into it on this machine (and how many the agent has since edited or removed), or why Coffer cannot write into it. The Memory page MUST NOT list the agents; it MUST count an agent Coffer cannot write into among what needs the person, linking to that agent's Memory tab. **Curate now** on an agent MUST start that agent without a terminal, in the person's home directory, with a prompt asking it to consolidate its own memory, and MUST record a `memory_curation_requested` event.

#### Scenario: an agent's curation state is shown
- **GIVEN** Claude Code with auto memory on and Auto Dream off, and Codex with memories on
- **WHEN** the person opens each agent's Memory tab
- **THEN** Claude Code's says auto memory is on and Auto Dream is off with a hint to turn it on, and Codex's says its memories are on
- **AND** the Memory page shows no row or chip per agent

### Requirement: Manage memory sync in the web UI and on the command line
The Memory page MUST show the sync switch and interval, **Sync now**, when memory last synced and the next sync, **Undo sync…**, and one banner counting what needs the person — a pending preview, each source the last sync could not read, each memory it withheld, each agent Coffer cannot write into — whose drawer lists them. Below, it MUST list the hub's scopes — global memories, then the hub's projects by short name with how many memories each holds, the ones not checked out on this machine grouped apart — beside the open scope's memories (`/memory?scope=`), each with its title and description, type, origin agent and machine and last change, filterable by text, type and origin agent (`?source=`). A memory's copy state MUST show on its row only when it waits for the next sync or the agent's curation edited or removed it. Opening a memory (`&memory=<id>`) MUST show, in the shared drawer, first one line per local agent with its copy's state, the file that holds it and Open / Reveal, then the memory's text, read only. The page MUST NOT offer to edit a memory's text: the person edits memory in the agent's own memory directory. The old addresses `/memory/projects/<folder>` and `/memory/global` MUST open that scope. Every operation of the page MUST also be a `coffer memory` command.

#### Scenario: a project's memories show where each was written
- **GIVEN** a project with two hub entries, one written into Claude Code and one whose copy Claude Code's curation removed
- **WHEN** the person opens the project on the Memory page
- **THEN** each memory shows its origin agent and machine, the first says nothing about its copy and the second reads removed by Claude Code

#### Scenario: a memory opens with its text and where each agent holds it
- **GIVEN** a Claude Code memory written into Codex
- **WHEN** the person opens it
- **THEN** the drawer lists Claude Code with its own file and Codex as written with the copy's file, each with Open and Reveal, above the memory's text
- **AND** an id the hub does not hold answers not found

#### Scenario: memory sync is managed on the command line
- **GIVEN** the `coffer memory` command group
- **WHEN** its commands are listed
- **THEN** they are `state`, `sync`, `preview-write`, `preview-cancel`, `undo`, `codex-import`, `entries`, `show` and `curate`, one per operation of the page, `show` reads one memory's text and none writes it
