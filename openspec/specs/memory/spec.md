# Memory

## Purpose

Every agent the developer runs would otherwise keep its own memory, which none of the others can see: the developer re-teaches each agent what another already knows, and again on the next machine. Coffer keeps **one memory for every agent**: Markdown files in the vault, one folder per repository, which every agent reads at the start of a session and writes with its own file tools. There is one way to read memory and one way to write it, the same for every agent Coffer supports, so a new agent needs a place for one hook and nothing else.

```
~/.coffer/vault/memory/
└── projects/<project>/       ← one folder per repository, the same name on every machine
    ├── testing.md            ← one topic per file
    └── release.md
```

**Memory is files the agents write themselves.** There is no memory tool and no memory API for an agent: an agent reads and writes `~/.coffer/vault/memory/projects/<project>/` with the file tools it already has, by the rules the coffer-guide skill states. Coffer writes nothing there of its own accord; it only records what the agents and the person changed in the vault's history, as it does every other vault file.

**The format is Coffer's, and fixed.** A file holds one **topic**: memories that belong together and are used together, one per line, under a frontmatter of `title`, `type` (`user`: who the developer is; `feedback`: how they want an agent to work; `project`: a project's state the repository does not record) and `updated`. An agent adds a line to the topic a memory belongs to and creates a new file only when none fits. The person does not edit these rules, unlike a knowledge collection's: memory is read by every agent at every session start, so its shape cannot vary by project. A file that breaks the format is still read and shown, flagged; a tidy fixes it, and Coffer never rewrites it by itself.

**Coffer's only delivery is a session-start hook.** While the memory feature is on, Coffer installs one hook in every registered agent that has a place for one (Claude Code's and Codex's `SessionStart`). The hook prints the current project's memories, in full up to a cap, and names by path the files that did not fit. Coffer's own turns (chat, channels, scheduled tasks) put the same text in the system prompt and tell the hook not to print it again. Coffer reads and writes no agent's own memory: whether an agent's own memory stays on is the person's choice, in the agent.

**The hub is vault content.** Vault sync carries it to the person's other machines. A project is named by its repository's normalised `origin`, so two clones on two machines share one folder. Two machines editing the same topic file can conflict in vault sync; for one person this is rare, and lines appended to the same file usually merge.

**Memory is about the person; knowledge is about the world.** Memory holds who the person is, how to work with them, and a project's current state. [Knowledge](../knowledge/spec.md) holds how outside systems, teams and processes work: what needs a source, goes stale or is worth sharing. A fixed sequence of steps is a [skill](../skill-manager/spec.md).

| | Memory | Knowledge |
| --- | --- | --- |
| Holds | the person, how to work with them, a project's state | outside systems, teams, processes, their pitfalls |
| Written by | agents, by Coffer's fixed rules | the person or an agent, by each collection's own rules |
| Partitioned by | project | collection |
| Reaches an agent by | **push**: the session-start hook | **pull**: the agent reaches for it |
| Tidied by | an agent on request (Tidy), or on a schedule the person sets up | an agent on request (Tidy) |

The Memory page lists the projects and their topic files, opens one with what breaks the format, lets the person edit or delete it, hands **Tidy** to an agent, shows every change in **History**, and offers to set up a periodic tidy as a [scheduled task](../scheduled-tasks/spec.md). `coffer memory` reads the same and opens and closes a tidy.

While the `memory` feature is switched off (spec [experimental-features](../experimental-features/spec.md)), the memory routes are closed, the hooks are removed from every agent, and the coffer-guide skill carries no memory rules; the files stay in the vault.

## Requirements

### Requirement: Keep memory in one place in the vault
The system MUST keep memory as Markdown files under `vault/memory/projects/<project>/`, one folder per project, each file one topic. `<project>` MUST be the project's key, its repository's normalised `origin` URL or the repository folder's name when it has no remote, with every character outside `[A-Za-z0-9._-]` turned into `-`. A topic file MUST be read leniently: a file missing its `title` is titled by its file name, and every way it breaks the format MUST be named, as one of `no_title`, `bad_type` (a `type` other than `user`, `feedback` or `project`), `no_updated`, `no_memories` and `long_line` (a line over 400 characters). The system MUST NOT rewrite a file because it breaks the format.

#### Scenario: a file that breaks the format is shown and flagged
- **GIVEN** a topic file with a title, a type and a date, and one with none of them and a line of 401 characters
- **WHEN** both are read
- **THEN** the first names no problem
- **AND** the second is still read, titled by its file name, and names `no_title`, `bad_type`, `no_updated` and `long_line`

#### Scenario: an older build's entries become topics
- **GIVEN** a hub file an older build published, with an `id` and an `origin` in its frontmatter
- **WHEN** the daemon starts
- **THEN** the file is rewritten in place with only `title`, `type` and `updated`, as one commit, and follows the format

### Requirement: Hand a session its project's memories at start
While the memory feature is on, the system MUST keep one hook of its own in every registered agent whose record names a place for one, under the agent's `SessionStart` event, running `coffer memory session-start`; while it is off, or once the agent is removed, it MUST remove that hook. Every other hook and key in the file MUST be kept. The command MUST read the session's working directory from the hook's input, and print, for the repository it is in, an opening that names the project's folder and the coffer-guide skill's "Memory" section, then the topics in full, `user` first, then `feedback`, then `project`, newest first within a type, up to 4 KB, and the path and title of each topic that did not fit. It MUST print nothing outside a repository, in the vault's own checkout, or when `COFFER_MEMORY_IN_PROMPT` is set, and MUST NOT fail a session on any error. A conversation Coffer runs itself MUST carry the same text at the start of its system prompt and set `COFFER_MEMORY_IN_PROMPT` for the agent it starts.

#### Scenario: the hook is installed while memory is on and removed when it is off
- **GIVEN** memory on, and Claude Code registered with a `settings.json` holding other keys
- **WHEN** the reconciler passes, and again after memory is switched off
- **THEN** the file first holds one `SessionStart` hook running `coffer memory session-start` beside its own keys
- **AND** then holds exactly what it held before

#### Scenario: the hook is added beside the agent's own hooks and removed alone
- **GIVEN** an agent's settings with a `SessionStart` hook and a `Stop` hook of the person's own
- **WHEN** Coffer's hook is added, added again, moved to another CLI path, and removed
- **THEN** the person's hooks and keys are unchanged throughout, there is one hook of Coffer's while it is installed, and removing it leaves the file as it was

#### Scenario: a session is handed its project's memories within the cap
- **GIVEN** a project with topics of each type, and one more topic that would pass the cap
- **WHEN** a session's text is rendered
- **THEN** the topics appear `user`, then `feedback` newest first, then `project`
- **AND** the topic that does not fit is named by its path and title only, and the text stays within the cap

#### Scenario: a session is handed its memories by the agent's hook
- **GIVEN** a repository whose `origin` names a project with a topic file
- **WHEN** `coffer memory session-start` reads the hook's input naming that repository
- **THEN** it prints the project's memories and names the project's folder

#### Scenario: a session outside a repository is handed nothing
- **GIVEN** a working directory in no repository
- **WHEN** its session's text is asked for
- **THEN** the answer is empty

#### Scenario: a Coffer-started session is not handed its memories twice
- **GIVEN** `COFFER_MEMORY_IN_PROMPT` set in the hook's environment
- **WHEN** `coffer memory session-start` runs in a project with memories
- **THEN** it prints nothing and succeeds; unreadable input also prints nothing and succeeds

#### Scenario: a conversation in Coffer carries the memories in its system prompt
- **GIVEN** a project with memories
- **WHEN** Coffer starts a turn in it, from the web UI or a channel
- **THEN** the system prompt starts with the project's memories and the agent's environment carries `COFFER_MEMORY_IN_PROMPT`

### Requirement: State the memory rules in the coffer-guide skill
While the memory feature is on, the coffer-guide skill MUST carry a "Memory" section: where memory lives, the format, when to write a memory and how (add to a fitting topic, else create one; replace a contradicted line), what does not belong in memory (secrets, what the repository says, a procedure, an outside system), how a tidy goes, and how the person allows writing outside the repository (a Claude Code `Edit` permission rule, a Codex `writable_roots` entry). While the feature is off, the section MUST be left out.

#### Scenario: the coffer-guide skill carries the memory rules while memory is on
- **GIVEN** the coffer-guide skill rendered with memory on and with memory off
- **WHEN** both are read
- **THEN** the first carries the "Memory" section naming the folder, the permission rule and `coffer memory tidy-start`
- **AND** the second names no memory command

### Requirement: Show and edit memory on the Memory page
The Memory page MUST list the projects with how many topic files each holds and how many break the format, list the open project's files with their title, first memory, type and `updated`, and open a file with what breaks the format. The person MUST be able to edit a file's whole text and delete a file; each MUST be one vault commit, and MUST be refused with `MEMORY_FILE_STALE` when the file changed since it was read. No memory is an empty state that says how agents write one.

#### Scenario: the Memory page lists projects and their topics
- **GIVEN** a project with a topic file that follows the format and one that does not
- **WHEN** the Memory page is opened
- **THEN** the project is listed with two files, one breaking the format
- **AND** its files are listed with their titles and types, the second flagged

#### Scenario: an edit from the Memory page refuses a stale file
- **GIVEN** a topic file read on the page
- **WHEN** the person saves an edit, then saves again quoting the digest they first read, then deletes the file
- **THEN** the first save is one commit, the second is refused `MEMORY_FILE_STALE`, and the delete removes the file

#### Scenario: an edit from the Memory page is saved as one change
- **GIVEN** a topic file open in the drawer
- **WHEN** the person edits its text and saves
- **THEN** the whole new text is sent with the digest the page read

### Requirement: Tidy memory as one change
**Tidy** on the Memory page MUST hand a prompt to the person's agent that names the memory folder and each project's file and problem counts, and tells the agent to read the coffer-guide skill's "Memory" section, run `coffer memory tidy-start`, merge and split topics, drop duplicated, stale and contradicted lines, move what is about an outside system into knowledge, fix every file that breaks the format, and run `coffer memory tidy-finish` with its report. Between start and finish, edits under `vault/memory/` MUST stay uncommitted, and finishing MUST commit them as one commit by the writer `agent` carrying the report. A tidy whose files have not changed for 30 minutes MUST be closed, committing what it did. The page's **History** MUST show every version of `memory/` with its diff and restore, so restoring the version before a tidy undoes it. While scheduled tasks are on, the page MUST offer **Set up periodic tidy…**, which opens a new scheduled task carrying the Tidy prompt for the person to schedule and save; there is no built-in timer.

#### Scenario: a tidy's edits land as one commit with its report
- **GIVEN** two topic files committed
- **WHEN** an agent runs `tidy-start`, merges them, the vault settles, and the agent runs `tidy-finish` with a report
- **THEN** nothing is committed before the finish, and the finish adds exactly one version
- **AND** finishing again with no tidy open commits nothing

#### Scenario: History shows every change to memory
- **GIVEN** the Memory page
- **WHEN** the person opens History
- **THEN** the versions of `memory/` take the place of the projects

#### Scenario: periodic tidy is a scheduled task the person sets up
- **GIVEN** scheduled tasks on
- **WHEN** the person chooses Set up periodic tidy…
- **THEN** a new scheduled task opens named "Tidy memory" with the Tidy prompt, for the person to schedule and save

### Requirement: Remove what an older build wrote into the agents
At every daemon start the system MUST remove what an older build wrote into an agent's own memory: the marked block in each Claude Code project's `MEMORY.md` (deleting a file left empty), each Codex `memories*/extensions/coffer/` folder, and the old sync's machine-local ledger and preview. Everything else in those files and folders MUST be left byte for byte.

#### Scenario: upgrading removes the old copies from the agents' own memory
- **GIVEN** a Claude Code `MEMORY.md` holding the person's own line and Coffer's block, one holding only Coffer's block, and a Codex `extensions/coffer/` folder beside a file of Codex's own
- **WHEN** the daemon starts with both agents registered
- **THEN** the first file holds only the person's line, the second is gone, the Codex folder is gone, and Codex's own file is unchanged

### Requirement: Manage memory on the command line
`coffer memory` MUST offer `state` (the projects, whether a tidy is open, the Tidy prompt), `topics <project>`, `show <project> <name>`, `tidy-start`, `tidy-finish` and `session-start`. A memory's text MUST NOT be written through a command: it is a file.

#### Scenario: memory is read and tidied on the command line
- **GIVEN** the command tree
- **WHEN** the `memory` group is listed
- **THEN** it holds exactly `state`, `topics`, `show`, `tidy-start`, `tidy-finish` and `session-start`, and no command that writes a file

### Requirement: Show memory events on the vault-wide audit surface
This layer MUST NOT carry an audit surface of its own. Its events (the hook installed in or removed from an agent, and the retired events old rows carry) are read on the vault-wide audit surface, and every one MUST be legible there rather than shown as a raw event code. A memory file's changes are the vault's history, not audit rows.

#### Scenario: label every memory event type on the audit surface
- **GIVEN** every audit event type the memory layer records
- **WHEN** each is rendered by the vault-wide audit surface's event labelling
- **THEN** each has a human-readable label in both interface languages rather than its raw event code

### Requirement: Add no table, resource kind or agent mechanism
This layer MUST add no table and no resource kind: memory is files in the vault. It MUST NOT read or write any agent's own memory, give agents a memory tool, run a model over memory itself, or keep a per-agent reader or writer; an agent's only memory mechanism is the place for its session-start hook on its record.

#### Scenario: keep memory as files only
- **GIVEN** a history database upgraded to head
- **WHEN** its tables and the resource kinds are listed
- **THEN** none is named for memory
