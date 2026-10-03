## ADDED Requirements

### Requirement: Manage memory in the web UI
People MUST manage memory in the web UI: browse partitions and the memories in them, edit a memory (see "Edit a memory in the web UI or on disk"), run **Update memory** (see "Update memory in one action"), read the delivery statistics and a partition's Delivered view (see "Count what memory delivered and what was read", "Show what each agent is given at session start"), and read what was retired. The REST family under `/api/v1/memory` is the web UI's own interface: it carries what that page needs and no route that no page calls, and no requirement promises it to anything else. The one route another program calls is `POST /api/v1/memory/hook`, which answers one fire of the memory hook, whose session-start answer is the composed session context. Installing, inspecting and removing an agent's delivery hook are part of that agent's Coffer connection (spec agent-registry "Connect an agent to Coffer in one action") and are not in this family.

There MUST be no `coffer memory` command group and no `coffer path memory`. The single exception is `coffer memory hook`, the command every installed memory hook entry runs: it MUST be hidden from `coffer --help` and from the CLI reference, because a person never types it. A partition's notes, its index and its retirement record are plain files (see "Keep notes readable as plain files"), so the way to them is the memory root that session-start delivery names (see "Expose no memory tool and name the memory root at session start"), not a command.

#### Scenario: memory is managed from the web UI and has no command group
- **GIVEN** a running daemon with a distilled partition
- **WHEN** the command tree of `coffer` is listed, including its hidden commands
- **THEN** the only command under `memory` is `hook`, it is absent from the help output and the CLI reference, and there is no `path memory` target
- **AND** the memory page lists the partition and its memories, runs Update memory and shows the Delivered view without any command

#### Scenario: a path segment that escapes the memory root is refused
- **GIVEN** a request on the memory family naming a partition or a note slug that is `..`, holds a path separator or is hidden
- **WHEN** the route runs
- **THEN** it is refused with `MEMORY_UNSAFE_PATH` (400) and nothing outside the partition is read or written

#### Scenario: the delivery state of an agent is read on the agent's page
- **GIVEN** two registered agents, one connected to Coffer and one not
- **WHEN** the agent's detail data is read for each
- **THEN** the first's `coffer_connection` is `connected` with its `memory_hook` part installed, the second's is `disconnected`, and neither carries a last-fired time

### Requirement: Edit a memory in the web UI or on disk
A person MUST be able to edit a memory in the web UI or in their own editor. `PUT /api/v1/memory/partitions/{uid}/notes/{slug}` MUST replace the note's **body** with the text it is given, keep the note's frontmatter, stamp `updated_at`, and take the fingerprint the note's read returned. A note that changed since — distil rewrote it, or it was edited on disk — MUST be refused with `MEMORY_NOTE_CONFLICT` (409) and left untouched, and the refusal MUST carry what an editor needs to recover without a second save over the note: `saved: false`, and the note as it is now, its body and its fingerprint. An accepted save MUST record a `memory_note_edited` audit event naming the partition, the note and the user. Editing the file under `notes/` with any other tool needs no Coffer surface: the note is the file.

An edited note is the note, not a suggestion. It is the current body the distil writing stage receives the next time an entry is routed to it, so the edit persists until newer or better-evidenced material revises it (see "Judge a contradiction by evidence, not by who wrote it"). The derived tree stays disposable: deleting it and rebuilding reproduces the notes from the agents' own memory and loses every edit, and the guide says so.

#### Scenario: a save replaces the body and keeps the frontmatter
- **GIVEN** a note read with its fingerprint
- **WHEN** a new body is saved with that fingerprint
- **THEN** the note's body is the saved text, its `title`, `description`, `type` and provenance are unchanged, its `updated_at` is stamped, and the answer carries the new fingerprint
- **AND** a `memory_note_edited` event names the partition, the note and the user

#### Scenario: a save over a note that changed is refused with the current text
- **GIVEN** a note read with its fingerprint, and a distil pass that then rewrote it
- **WHEN** the save arrives with the fingerprint the editor loaded
- **THEN** it is refused with 409 `MEMORY_NOTE_CONFLICT` with `saved` false and the body and fingerprint the note has now
- **AND** the file still holds the distil pass's text, and saving the user's text again needs the new fingerprint

#### Scenario: an edited note is the body distil's writing stage receives
- **GIVEN** a note a person edited, and a new raw entry routed to that note
- **WHEN** the distil pass runs with an internal connection that records its requests
- **THEN** the writing request carries the edited body as the note's current body
- **AND** a note left alone by routing keeps the edited text byte for byte

#### Scenario: an edit made on disk needs no Coffer surface
- **GIVEN** a note's file under `notes/`
- **WHEN** a person changes its body in their own editor
- **THEN** the next read of the note, the index line rendered from it and the next session's delivery carry the changed text
- **AND** deleting the derived tree and rebuilding it gives back a note without that edit

### Requirement: Judge a contradiction by evidence, not by who wrote it
When a distil pass finds two statements that disagree — a note's body and a raw entry, or an edited note and newer material — the newer statement MUST win unless the older one is shown to be right: by a source, a date, a command's output or the code. The writing stage's instruction MUST say so, and MUST NOT exempt a statement because a person or an agent edited it. A statement that is superseded MUST stay legible: retired through "Record retirements so they stick" with the reason and the note that replaced it, or kept in the rewritten body with the date it changed.

#### Scenario: a newer entry revises an edited note
- **GIVEN** a note a person edited, and a newer raw entry that contradicts the edit and names a command's output as its evidence
- **WHEN** the distil pass runs with an internal connection
- **THEN** the writing request's instruction states the newer-or-better-evidenced rule and does not mark the body as untouchable
- **AND** the note's rewritten body follows the entry and still shows the date the statement changed

#### Scenario: an older entry does not overwrite a person's edit
- **GIVEN** a note a person edited today, and a raw entry from last month that disagrees with the edit and carries no evidence
- **WHEN** the distil pass runs
- **THEN** the note's body still holds the edited statement

## MODIFIED Requirements

### Requirement: Deliver to channel turns through the system prompt
A **channel-driven turn** MUST receive the same payload through the system-prompt append the turn platform already composes ([channels](../channels/spec.md)). It MUST NOT require a hook, since Coffer owns that context itself, and the delivery MUST be audited as a `session_start` fire of the answering agent with the conversation as the session (see "Audit every delivery fire").

The agent process Coffer spawns for a channel turn still loads the agent's own settings, so an installed delivery hook fires inside it as well. Coffer MUST mark that process's environment, and in a marked process the hook MUST answer nothing, and record nothing, on `SessionStart` and `UserPromptSubmit`: those two moments belong to the turn, so the index and the prompt's notes each arrive once and are counted once. A turn the developer drives MUST NOT be marked.

#### Scenario: a channel turn carries the index without a hook
- **GIVEN** a channel-driven conversation on a registered agent with a working directory, and no delivery hook installed anywhere
- **WHEN** a turn is taken
- **THEN** the index arrives in the **system-prompt append** the turn platform already composes, resolved once per turn from that agent's key and the conversation's own cwd
- **AND** when there is nothing to deliver the turn carries no memory header at all, rather than an empty one (see "Deliver to channel turns through the system prompt")

#### Scenario: a channel turn's own hook leaves the index and the notes to the turn
- **GIVEN** a connected agent whose delivery hook is installed and trusted, a channel-driven conversation on it, and a conversation the developer drives on the same agent
- **WHEN** the channel turn's agent process fires the hook on `SessionStart` and `UserPromptSubmit`
- **THEN** the hook answers nothing and records nothing, and the index and the prompt's notes reach the agent once, from the turn, each audited as one fire with event `ChannelTurn` (`session_start` and `prompt`)
- **AND** the developer-driven conversation's process is not marked, and its hook answers both

### Requirement: Install delivery hooks explicitly and removably
For an agent the developer drives themselves, delivery MUST go through that agent's own hook mechanism, invoking Coffer's existing CLI **by absolute path**. An agent runs its hooks under a shell that need not have `~/.coffer/bin` on its `PATH`: Codex runs them under `/bin/zsh` without the user's rc files, and Claude Code started from the Dock does not inherit the login shell's `PATH`. The bare name is used only when the build cannot locate its own CLI.

Coffer's hook is **two entries**, one on each moment memory reaches a session, for both supported agents: `SessionStart` (matched on `startup|resume|clear|compact`), which adds the bounded index, and `UserPromptSubmit`, which adds the notes the prompt names. Both entries run the same command, `coffer memory hook --agent-uid <uid> --cwd "$PWD"`, which reads the event the agent hands its hook on stdin and prints that event's JSON `hookSpecificOutput` with `additionalContext`, which both agents read on every event. Nothing once-per-session MAY be keyed on a process id: every session of one Codex app-server shares a parent pid, so it is keyed on the hook's `session_id`. The command is an internal entry point, hidden from help and from the CLI reference (see "Manage memory in the web UI").

Installation MUST be an **explicit act** on Coffer's surface: connecting the agent to Coffer, of which the hook is one part (spec agent-registry "Connect an agent to Coffer in one action"), or a person applying the missing hook's reconcile item. It MUST be marker-scoped, idempotent, and removable without disturbing entries Coffer did not write. An install or a remove MUST take out Coffer's marked entries on **every** event first, so a marked entry on any other event — a `PreToolUse` or `PostToolUse` entry an earlier version wrote, for one — is never left behind beside the new ones. Coffer MUST NOT install the hook silently, and MUST NOT write into any file that is an agent's *memory*: a hook lives in the agent's settings, which is a different thing.

#### Scenario: hook installation is marker-scoped and removable
- **GIVEN** an agent whose settings file already carries a foreign hook on the same lifecycle events, other events' hooks, and unrelated top-level keys
- **WHEN** delivery is installed, installed a second time, and then removed
- **THEN** install adds exactly **one** entry carrying Coffer's marker on each of `SessionStart` and `UserPromptSubmit`, both running `coffer memory hook` by absolute path, a second install leaves one on each, and every foreign hook, every other event and every unrelated key is untouched
- **AND** remove takes out only the marked entries — dropping an event array and the top-level hooks key once they are empty — and with nothing installed it is a clean no-op that writes no file and records no audit event (see "Install delivery hooks explicitly and removably")

#### Scenario: an install clears marked entries on events it no longer uses
- **GIVEN** an agent whose settings carry Coffer's marked entries on `SessionStart`, `UserPromptSubmit`, `PreToolUse` and `PostToolUse`, and a foreign `PreToolUse` hook
- **WHEN** delivery is installed
- **THEN** the marked `PreToolUse` and `PostToolUse` entries are gone, the foreign `PreToolUse` hook is untouched, and exactly one marked entry sits on each of `SessionStart` and `UserPromptSubmit`

#### Scenario: a Codex hook fire prints the session-start JSON Codex reads
- **GIVEN** a partition with notes and a registered agent
- **WHEN** `coffer memory hook --agent-uid <uid>` runs with a Codex `SessionStart` event on stdin whose `cwd` is the partition's repository
- **THEN** it prints one JSON object whose `hookSpecificOutput` names `SessionStart` as its `hookEventName` and carries the composed index as `additionalContext`
- **AND** the fire is recorded

#### Scenario: both agents' hook fires answer in the JSON each reads
- **GIVEN** a Claude Code agent and a Codex agent connected on a fake home, and a distilled partition
- **WHEN** each agent's installed command is run with that agent's own `SessionStart` and `UserPromptSubmit` input on stdin
- **THEN** each prints `hookSpecificOutput` with `additionalContext` for the session start and for the prompt
- **AND** neither prints a `permissionDecision` for any input

### Requirement: Repair stale delivery hooks
An installed hook MUST be repaired when what Coffer would write is no longer what is installed, without waiting for a user to notice. This is the delivery-hook target of the unified reconciler ([resource-framework](../resource-framework/spec.md) "Converge what Coffer writes outside its database with one reconciler"), and it runs on every pass, not only at daemon start.

A hook is a string left in somebody else's settings file, and the CLI it invokes ships in a binary that keeps moving. When the command a hook runs stops taking an option, every hook already on disk keeps passing it. The agent prints a usage error at the start of every session, and this layer never reaches it again. Nothing reports the failure, because detection is marker-scoped and never reads the arguments. That same marker scoping is what lets a reinstall replace an entry in place, and it is why a stale entry reads as installed.

The target therefore judges a hook by the **set of events** its entries sit on and their **whole commands**, both against what would be installed now, and rewrites a hook that differs into the two current entries — which includes a hook an earlier version installed on four events, whose `PreToolUse` and `PostToolUse` entries are removed. The two kept entries keep their command and their position, so the approval Codex recorded for each still holds. One unreadable settings file MUST be reported as blocked without stranding the others.

For an agent that runs a hook only after the user has approved it (Codex), the target MUST also read whether the agent will run **every** installed entry. A current hook the agent will not run MUST be **reported, never written**, with the reason and the remedy (approve it with `/hooks` in Codex). Coffer MUST NOT write the agent's approval record: approving a hook is the user's act in the agent (spec agent-registry/codex "Leave Codex's internal-state tables untouched").

The hooks wanted are those of every connected agent and of every agent that already carries one. A pass — at boot or on its period — MUST NOT install a hook for an agent that has none; only a person applying that item, or connecting the agent, installs it. Otherwise the missing hook is reported and the agent's connection reads partial. A repair that added the hook would be an install Coffer made silently, which "Install delivery hooks explicitly and removably" forbids.

#### Scenario: a hook whose command went stale is repaired without being asked
- **GIVEN** an agent with Coffer's hook installed, and a Coffer build whose delivery command is no longer the one in that agent's settings file,
- **WHEN** a reconcile pass runs — at daemon start or on its period,
- **THEN** the entries are rewritten in place to the ones this build would install, so the next session is served rather than shown a usage error,
- **AND** an agent whose hook is already current is left untouched, and an agent with no hook is not given one.

#### Scenario: a four-entry hook is rewritten to two without losing Codex's approvals
- **GIVEN** a connected Codex agent carrying Coffer's hook on `SessionStart`, `UserPromptSubmit`, `PreToolUse` and `PostToolUse`, with `config.toml` recording its approval of all four
- **WHEN** a reconcile pass runs
- **THEN** the hook is two entries, on `SessionStart` and `UserPromptSubmit`, with the commands and positions they had
- **AND** the two kept entries' approvals in `config.toml` still match, so the next pass reports no `hook_untrusted`, and Coffer wrote no approval

#### Scenario: a current Codex hook Codex has not approved is reported, not written
- **GIVEN** a connected Codex agent carrying the current hook, and no approval for its entries in Codex's `config.toml`
- **WHEN** a reconcile pass runs on its period, and again when a person applies it
- **THEN** the only difference is `trust`, and it is reported as `hook_untrusted` with the remedy "run /hooks in Codex"; nothing is written, and Coffer records no approval
- **AND** once `config.toml` records Codex's approval of every one of those entries, the next pass finds nothing to do

### Requirement: Audit every delivery fire
Coffer MUST record **an audit event for every delivery fire**, so that whether delivery is actually happening is answerable after the fact: every session start, and every prompt fire that delivered a note. The event MUST name its moment (`session_start` or `prompt`), the session, and the notes it carried — never their text. A fire is an event, not a property of the agent: the hook's per-agent status MUST report installation only, and MUST NOT carry a last-fired timestamp.

#### Scenario: every hook fire is recorded in the audit log
- **GIVEN** an agent for which delivery has been installed
- **WHEN** the installed hook fires and the served context is recorded as a delivery
- **THEN** exactly one audit event is written naming that agent as both the resource and the actor
- **AND** the per-agent installed state is unchanged by a fire, and neither installing nor reading status records a fire of its own (see "Audit every delivery fire")

#### Scenario: a prompt and a guard fire each name their moment and notes
- **GIVEN** a session that is given the index at its start and a note at a prompt
- **WHEN** the audit log is read
- **THEN** one `memory_delivery_fired` event names moment `session_start`, and another names moment `prompt` and the note, and neither carries the note's text

### Requirement: Present a partition as its memories
The web UI MUST present partitions **as a table** once any exists; with none, it shows the first-run welcome every other empty surface shows — *Nothing distilled yet*, with **Update memory** and the connected agents whose memory Coffer found on this machine, or, with no agent connected, saying there is nothing to read and offering **Open Agents** to connect one. Each row MUST carry the partition's path ("Every project" for `global`), a sample memory — or, before a first distil, how many entries were read from which agents and are waiting to distil — how many memories it holds, its sources (the agents it came from, "All agents" when every agent that contributed anywhere contributed here) and its state, in a column headed **Distilled**: when it was last distilled, "Not distilled yet", "Distilling…" while a pass over it runs, or "Repository missing". Healthy rows are grey: only **Repository missing** is coloured, and only that row offers a Delete, which asks first because it cannot be undone (a confirmation naming the partition, with Cancel and Delete partition). The partitions section's title carries no count of partitions or memories. A partition's page MUST have no back link, and no Automatic control: its title is the partition's name alone, and its description line carries the path, the memory count and when it was last distilled (*~/code/coffer · 38 memories · distilled 2 h ago*). Its ⋯ menu holds **Reveal partition folder**, **Copy path**, **Distil history in Activity** and, only when its repository is gone, **Delete partition**. A partition not yet distilled shows no memory list: its Memories tab shows only the empty state, which offers no Update memory of its own because the header has one. While Coffer's engine is not set, a banner on the partition's page MUST say *Coffer’s engine isn’t set, so each agent’s entry stays its own memory* until it is set in Settings › General, with **Open Settings**. Each memory in its list MUST name the agents it was learned from ("All agents" when that is every agent the partition came from). The partition listing MUST carry when its newest memory was last updated (`updated_at`, absent for a partition holding no memory), which the Overview's Memory tile words as "Last update 14 min ago". One partition's page MUST carry two tabs. **Memories** (the default) lists its memories — the web UI's label for what this spec and the disk call notes (中文 记忆条目) — beside the selected memory, with the partition's retired memories in a collapsed, read-only **Retired** group, each with the reason it was retired. The selected memory MUST be rendered with a meta line naming the agents it was learned from and when it was last updated, taken from its provenance ("Record provenance and merge by meaning"), and its frontmatter MUST be shown as that metadata, not rendered as body text. The page MUST NOT show the agents' own memory: no native paths, no original agent text, no `.raw/` entry, no `MEMORY.md` index or `RETIRED.md` file, and no file tree — those stay in the data and on disk, and only this page leaves them out. The memory's own files are reached through the partition's ⋯ menu (**Reveal partition folder**, **Copy path**), not from each memory. The list and the memory MUST extend to the bottom of the window and scroll inside. The selected memory MUST offer one per-memory action, **Edit** (see "Edit a memory in the web UI or on disk"), and no other: a memory is derived by distillation and is not deleted from the page. A retired memory offers none. The Memory page's title carries the **Experimental** tag ([experimental-features](../experimental-features/spec.md)); a partition's page does not. **Delivered** (`/memory/<uid>/delivered`) shows, read-only, the exact session-start text each agent receives in the partition's project, with a switch between agents ([web-ui](../web-ui/spec.md) "Show memory delivery on the Memory page"); it shows no hook state.

#### Scenario: browse a partition's memories with a read-only preview
- **GIVEN** the memory pages, with no partitions and then with one distilled partition that holds raw entries, a memory learned from Claude Code and Codex, and one retired memory
- **WHEN** the partitions page and the partition's page render and the memory is chosen
- **THEN** the partitions page shows the first-run welcome with none and the table with one, and the partition's page lists its memories beside the chosen one, whose meta line names Claude Code and Codex and when it was updated and whose frontmatter is not in the rendered body
- **AND** the retired memory is in a collapsed Retired group with its reason, the page shows no file tree, no `MEMORY.md`, `RETIRED.md` or `.raw/`, no native path and no agent's original text, and the chosen memory offers Edit and no delete action

#### Scenario: the selected memory is edited in place
- **GIVEN** a partition's page with a memory selected
- **WHEN** the user chooses Edit, changes the body and saves
- **THEN** the memory renders the saved body with a refreshed update time, and a save refused as changed offers the current text so nothing is lost (see "Edit a memory in the web UI or on disk")
- **AND** a retired memory in the Retired group offers no Edit

#### Scenario: a partition lists when its newest memory was updated
- **GIVEN** a partition holding a memory
- **WHEN** the partitions are listed over REST
- **THEN** the partition carries the time its newest memory was last updated as `updated_at`

#### Scenario: provenance paths stay in the data, not on the page
- **GIVEN** a memory whose provenance names a Claude Code fact file by its native path
- **WHEN** the memory is read over the REST note route and shown on the partition's page
- **THEN** the route's provenance still carries the agent, the native path and the read time, while the page shows only the agent's name and the update time

#### Scenario: a partition's page names the partition and offers no way back
- **GIVEN** a distilled partition for a repository, with 38 memories
- **WHEN** its page renders
- **THEN** the title is the partition's name with no Experimental tag and no back link, the description line carries the path, *38 memories* and when it was distilled, and there is no Automatic control
- **AND** with Coffer's engine not set a banner names it, says each agent's entry stays its own memory and offers Open Settings

#### Scenario: deleting a partition still asks
- **GIVEN** a partition whose repository is gone
- **WHEN** the user chooses Delete on its row
- **THEN** a confirmation names the partition and nothing is deleted until the user chooses Delete partition

#### Scenario: a partition has a memories tab and a delivered tab
- **GIVEN** a partition with memories and two connected agents
- **WHEN** the user opens the partition and then its Delivered tab
- **THEN** the page opens on Memories, and Delivered shows each agent's session-start text read-only with an agent switch and no hook state

#### Scenario: the partitions table names each partition's sample, sources and distil state
- **GIVEN** a distilled partition learned from every agent, a partition holding entries read from Codex that no pass has distilled, and a partition whose repository is gone
- **WHEN** the partitions page renders
- **THEN** the Distilled column's first row shows when it was distilled, the second reads "Not distilled yet", and the third reads "Repository missing", the only coloured one and the only one with Delete
- **AND** the first row shows a sample memory and "All agents", and the second says its entries from Codex are waiting

### Requirement: Audit every lifecycle act
Every lifecycle act — aggregation, distil, retirement, a memory edited, delivery installed, removed or fired — MUST record an audit event with its actor.

#### Scenario: audit a requested aggregation and distil with their actor
- **GIVEN** a registered agent with native memory and a partition to distil
- **WHEN** a user updates memory, which requests an aggregation and then a distil pass
- **THEN** exactly one aggregation audit event and one distil audit event name that user as their actor, beside any the daemon's own worker recorded under its own actor

### Requirement: Expose no memory tool and name the memory root at session start
The MCP gateway MUST expose no built-in tool for this layer: no tool that locates, reads, searches or records a note. An agent records something the way it already does, and Coffer reads it on the next pass. An agent finds a note the way it finds any file: session-start delivery (see "Deliver the index and the notes path at session start") MUST name the **absolute memory root** and state that every partition's notes are Markdown files under `<root>/<partition>/notes/`, so an agent looking for a note in a partition the session was not opened in searches that one directory with its own tools. The memory root is one directory, so one search covers every partition. No command prints the root: the session-start payload is where it is named.

#### Scenario: no memory tool is listed, and delivery names the memory root
- **GIVEN** a running daemon, a partition holding notes, and a `global` partition holding more
- **WHEN** an agent lists the gateway's tools, and the session context is composed for a cwd inside that partition's repository
- **THEN** no `coffer__recall`, no `coffer__remember` and no other memory tool is listed
- **AND** the payload names the absolute memory root and states that each partition's notes are Markdown files under `<root>/<partition>/notes/` to be searched with the agent's own tools

### Requirement: Provision partitions only from aggregation
Partitions MUST be **created by aggregation**, not by the user, and MUST NOT be created by an agent's working directory at read time.

#### Scenario: compose context and locate the memory root without creating a partition
- **GIVEN** a memory root with no partitions and a working directory inside a git repository
- **WHEN** the session context is composed for that working directory
- **THEN** no partition directory and no `memory` Resource exists afterwards

### Requirement: Update memory in one action
`POST /api/v1/memory/sync` MUST run an aggregation (see "Aggregate on an interval and on demand") and then a distil pass over every partition with something to distil — raw entries it has not yet distilled (see "Distil incrementally in two stages"), or a note none of whose raw entries is left (see "Retire a note whose raw entries are all gone") — and MUST answer with what the aggregation wrote and which partitions were distilled. A distil pass already running over a partition MUST NOT fail the action: that partition is reported as skipped. The web UI MUST offer this as one **Update memory** button — the partitions page's primary action, beside the **Automatic · hourly** control whose popover holds the switch and the interval, and also on a partition's page — and MUST NOT offer aggregation or distillation as separate buttons.

#### Scenario: one action reads new agent memory and distils it
- **GIVEN** a registered agent whose native memory gained an entry about a repository with a distilled partition
- **WHEN** `POST /api/v1/memory/sync` is called
- **THEN** the entry is written under that partition's `.raw/` and the same call distils it into the partition's notes
- **AND** the answer names that partition among the distilled ones

#### Scenario: a partition whose only change is a deleted source is still distilled
- **GIVEN** a partition whose single note was built from a native memory file the agent has since deleted, so its raw entries are gone and nothing new arrived
- **WHEN** memory is updated
- **THEN** the note is retired and the answer names that partition among the distilled ones

### Requirement: Fail open when Coffer cannot answer
Every memory hook MUST fail open: when the daemon is not running, does not answer within the hook's own short timeout, or answers with an error, the hook MUST print nothing and exit 0, so memory never stops a prompt because Coffer is down. A fire that can deliver nothing — a trivial prompt — MUST be answered without contacting the daemon.

#### Scenario: the hook prints nothing and exits 0 with no daemon
- **GIVEN** no daemon running
- **WHEN** `coffer memory hook` is given a `SessionStart` and a `UserPromptSubmit` event on stdin
- **THEN** each run prints nothing and exits 0

### Requirement: Word delivered notes as provenance plus fact
Every note delivered at a prompt MUST read as **provenance plus fact**: it names the note's file, and states the note's substance as "the user's standing rule is: …" for a `feedback` note and as "a fact they recorded: …" otherwise. Delivered text MUST NOT be phrased as an instruction to the agent.

#### Scenario: a delivered note names its file and reads as a standing rule
- **GIVEN** a `feedback` note and a `project` note that both match a prompt
- **WHEN** the prompt's delivery is composed
- **THEN** the `feedback` note's line names its absolute path and reads "the user's standing rule is: …", and the `project` note's reads "a fact they recorded: …"

### Requirement: Count what memory delivered and what was read
`GET /api/v1/memory/deliveries` MUST report, for every registered agent with a delivery hook, over the last **seven days**: the number of delivery fires recorded in the audit log, the same count by moment (`session_start`, `prompt`), when memory last reached it, and how many **distinct notes** its sessions opened. The overview is the web UI's delivery statistics. The last is read off the file paths the agent's tool calls named — a path under the memory root naming a note — and never off what a note, a tool result or a message says; when the agent's transcripts cannot be read it MUST be reported as `unavailable` rather than as zero. The report MUST NOT carry whether a hook is installed or trusted.

#### Scenario: the overview counts a week of deliveries and the notes read
- **GIVEN** a Claude Code agent with five delivery fires in the last week and one older than that, and a transcript from this week whose tool calls read two distinct notes, one of them twice
- **WHEN** the overview is read
- **THEN** it reports five deliveries split by moment, the time of the newest, and two notes read
- **AND** it carries no field saying whether the hook is installed or trusted

#### Scenario: notes read is unavailable without transcripts
- **GIVEN** a registered Codex agent whose config directory has no `sessions/` directory
- **WHEN** the overview is read
- **THEN** its notes read is `null` with status `unavailable`, and its delivery count is still reported

### Requirement: Show what each agent is given at session start
`GET /api/v1/memory/partitions/{uid}/delivered` MUST return, for every registered agent with a delivery hook, the **exact text** that agent's session-start hook would add in that partition's repository — composed by the same function and under the same ceiling the hook uses — read only, and without whether a hook is installed or trusted. The web UI's partition page shows it on its Delivered tab.

#### Scenario: the Delivered view carries each agent's exact session-start text
- **GIVEN** a distilled repository partition and a registered Claude Code and Codex agent
- **WHEN** the partition's Delivered view is read
- **THEN** each agent's entry carries `SessionStart` and text equal to what `POST /api/v1/memory/hook` answers a `SessionStart` fire from that repository with
- **AND** nothing is audited and no hook state is carried

### Requirement: Remember what a session was given across daemon restarts
What each session was given — the notes delivered at its prompts — MUST survive a daemon restart, so a restart does not bring a note into a session again. The record MUST be the audit log's delivery fires (see "Audit every delivery fire"), which already name each fire's session and notes: the daemon MUST rebuild the per-session record from the fires of the last **seven days** before it answers its first prompt, and MUST add no table for it (see "Add no table of its own"). A session idle for longer than that is treated as new. A rebuild that fails MUST be logged and leave the record empty rather than stop delivery.

#### Scenario: a daemon restart gives a session nothing twice
- **GIVEN** a session that was given a note at a prompt, and then the daemon is restarted
- **WHEN** the same session sends the same prompt, and a new session sends it too
- **THEN** the first session is given nothing
- **AND** the new session is given the note

### Requirement: Report the last read of the agents' memory
`GET /api/v1/memory/reading` MUST answer when Coffer last read the agents' memory
(`read_at`, `null` before the first read) and, for each agent whose memory that read could not
parse, the agent, the source path, the reason and when that agent's memory was last read with
nothing failing, if known. The answer MUST be read from the `memory_aggregated` audit events,
which therefore carry each failure's agent, path and reason, so it is the same whoever started
the read — the timer or Update memory — and survives a daemon restart. Only
the newest read decides what failed. The Memory page's header MUST say "Read 14 min ago", with
"· 1 agent failed" when the last read left an agent unread, and the page MUST then show a
warning banner naming the agent and the path, saying that agent's memories stay as its last full read
left them, with **Retry** (Update memory) and **Ask an agent ▾**, whose prompt asks the agent to fix
the path's read permission.

#### Scenario: the last read and an agent it could not read are reported
- **GIVEN** three reads recorded, the newest two unable to parse Codex's memory and the oldest
  reading every agent
- **WHEN** the last read is asked for
- **THEN** it is the newest read's time, with one failure naming Codex, its path and its reason
- **AND** that failure's last full read is the oldest read's time

## REMOVED Requirements

### Requirement: Cover memory management on REST and the CLI
**Reason**: Memory is managed in the web UI, and its REST routes are that page's private interface. The `coffer memory` group was run mostly by agents through their shell, and the parity rule that kept it level with REST grew the CLI with every page. Agents read and edit the notes as files.
**Migration**: Use the web UI, or read and edit the files under the memory root that session-start delivery names. `coffer memory hook` stays as the hidden entry point the installed hook runs; see "Manage memory in the web UI".

### Requirement: Guard a known trap once per session
**Reason**: Triggers are removed. None was ever armed — the web UI had no place to arm one — and one matched browser tool names against shell commands, where it could never match what it meant.
**Migration**: A one-time migration deletes `vault/memory-triggers/`, and the reconciler rewrites each installed memory hook from four entries to two, removing the `PreToolUse` and `PostToolUse` entries. A known trap stays a note, delivered at session start and at a prompt that names it.

### Requirement: Keep triggers in the vault, armed only by a person
**Reason**: Triggers are removed along with the guard that used them, so nothing reads `vault/memory-triggers/`, and the distil pass no longer proposes one.
**Migration**: A one-time migration deletes `vault/memory-triggers/`; the deletion syncs like any other vault deletion, and the files come back from the vault's history if ever wanted. The `memory_trigger_*` audit events are no longer recorded.
