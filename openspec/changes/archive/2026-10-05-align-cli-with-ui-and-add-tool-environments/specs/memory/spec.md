## REMOVED Requirements

### Requirement: Manage memory in the web UI
**Reason**: The owner decided (2026-10-05) that every management operation a person can do in the web UI or the desktop app has a `coffer` command, so an agent can do it too; the rule that a web UI operation owes no command is withdrawn.
**Migration**: Nothing to migrate: the routes are unchanged and the new `coffer memory` commands call them; `coffer memory hook` stays hidden.

## ADDED Requirements

### Requirement: Manage memory in the web UI and on the command line
People MUST manage memory in the web UI: browse partitions and the memories in them, open a memory in their editor (see "Edit a memory in the person's own editor"), delete a memory (see "Delete a memory by hand"), run **Update memory** (see "Update memory in one action"), hand a partition's tidying to the agent (see "Hand a partition's tidying to the agent"), read a partition's Delivered view (see "Show what each agent is given at session start"), and read what was retired. The REST family under `/api/v1/memory` serves the web UI and the `coffer memory` commands, which call the same routes: it carries what that page needs and no route that no page calls — no route writes a note's text, and no requirement promises it to anything else. The one route another program calls is `POST /api/v1/memory/hook`, which answers one fire of the memory hook, whose session-start answer is the composed session context. Installing, inspecting and removing an agent's delivery hook are part of that agent's Coffer connection (spec agent-registry "Connect an agent to Coffer in one action") and are not in this family.

The `coffer memory` commands MUST list partitions and, per partition, its notes, files, Delivered view and retired notes, read which agents' memory Coffer reads, run Update memory and print the tidy hand-off; no command reads, writes or deletes a note's text, and there is no `coffer path` target for memory. `coffer memory hook`, the command every installed memory hook entry runs, MUST be hidden from `coffer --help`, the group's help and the CLI reference, because a person never types it. A partition's notes, its index and its retirement record are plain files (see "Keep notes readable as plain files"), so the way to them is the memory root that session-start delivery names (see "Expose no memory tool and name the memory root at session start"), not a command.

#### Scenario: memory is managed on the command line, its notes as files
- **GIVEN** a running daemon with a distilled partition
- **WHEN** the command tree of `coffer` is listed, including its hidden commands
- **THEN** the `memory` group offers partitions, notes, files, delivered, retired, reading and sync, no command reads, writes or deletes a note, and `hook` is hidden from the help output and the CLI reference
- **AND** there is no `path memory` target

#### Scenario: a path segment that escapes the memory root is refused
- **GIVEN** a request on the memory family naming a partition or a note slug that is `..`, holds a path separator or is hidden
- **WHEN** the route runs
- **THEN** it is refused with `MEMORY_UNSAFE_PATH` (400) and nothing outside the partition is read or written

#### Scenario: the delivery state of an agent is read on the agent's page
- **GIVEN** two registered agents, one connected to Coffer and one not
- **WHEN** the agent's detail data is read for each
- **THEN** the first's `coffer_connection` is `connected` with its `memory_hook` part installed, the second's is `disconnected`, and neither carries a last-fired time

