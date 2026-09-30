## MODIFIED Requirements

### Requirement: Install delivery hooks explicitly and removably
For an agent the developer drives themselves, delivery MUST go through that agent's own hook mechanism, invoking Coffer's existing CLI **by absolute path**. An agent runs its hooks under a shell that need not have `~/.coffer/bin` on its `PATH`: Codex runs them under `/bin/zsh` without the user's rc files, and Claude Code started from the Dock does not inherit the login shell's `PATH`. The bare name is used only when the build cannot locate its own CLI.

Coffer's hook is **four entries**, one on each moment memory reaches a session, for both supported agents: `SessionStart` (matched on `startup|resume|clear|compact`), `UserPromptSubmit`, and `PreToolUse` and `PostToolUse` matched on the `Bash` tool. Every entry runs the same command, `coffer memory hook --agent-uid <uid> --cwd "$PWD"`, which reads the event the agent hands its hook on stdin and prints that event's JSON `hookSpecificOutput` — `additionalContext` to add context, `permissionDecision: "deny"` with a reason to hold a command — which both agents read on every event. Nothing once-per-session MAY be keyed on a process id: every session of one Codex app-server shares a parent pid, so it is keyed on the hook's `session_id`.

Installation MUST be an **explicit act** on Coffer's surface: connecting the agent to Coffer, of which the hook is one part (spec agent-registry "Connect an agent to Coffer in one action"), or a person applying the missing hook's reconcile item. It MUST be marker-scoped, idempotent, and removable without disturbing entries Coffer did not write. An install or a remove MUST take out Coffer's marked entries on **every** event first, so a marked entry on any other event is never left behind beside the new ones. Coffer MUST NOT install the hook silently, and MUST NOT write into any file that is an agent's *memory*: a hook lives in the agent's settings, which is a different thing.

#### Scenario: hook installation is marker-scoped and removable
- **GIVEN** an agent whose settings file already carries a foreign hook on the same lifecycle events, other events' hooks, and unrelated top-level keys
- **WHEN** delivery is installed, installed a second time, and then removed
- **THEN** install adds exactly **one** entry carrying Coffer's marker on each of `SessionStart`, `UserPromptSubmit`, `PreToolUse` and `PostToolUse`, all running `coffer memory hook` by absolute path, a second install leaves one on each, and every foreign hook, every other event and every unrelated key is untouched
- **AND** remove takes out only the marked entries — dropping an event array and the top-level hooks key once they are empty — and with nothing installed it is a clean no-op that writes no file and records no audit event (see "Install delivery hooks explicitly and removably")

#### Scenario: a Codex hook fire prints the session-start JSON Codex reads
- **GIVEN** a partition with notes and a registered agent
- **WHEN** `coffer memory hook --agent-uid <uid>` runs with a Codex `SessionStart` event on stdin whose `cwd` is the partition's repository
- **THEN** it prints one JSON object whose `hookSpecificOutput` names `SessionStart` as its `hookEventName` and carries the composed index as `additionalContext`
- **AND** the fire is recorded

#### Scenario: both agents' hook fires answer in the JSON each reads
- **GIVEN** a Claude Code agent and a Codex agent connected on a fake home, a distilled partition, and an armed `block` trigger
- **WHEN** each agent's installed command is run with that agent's own `UserPromptSubmit` and `PreToolUse` input on stdin
- **THEN** each prints `hookSpecificOutput` with `additionalContext` for the prompt and `permissionDecision: "deny"` with the note as `permissionDecisionReason` for the command

### Requirement: Repair stale delivery hooks
An installed hook MUST be repaired when what Coffer would write is no longer what is installed, without waiting for a user to notice. This is the delivery-hook target of the unified reconciler ([resource-framework](../resource-framework/spec.md) "Converge what Coffer writes outside its database with one reconciler"), and it runs on every pass, not only at daemon start.

A hook is a string left in somebody else's settings file, and the CLI it invokes ships in a binary that keeps moving. When the command a hook runs stops taking an option, every hook already on disk keeps passing it. The agent prints a usage error at the start of every session, and this layer never reaches it again. Nothing reports the failure, because detection is marker-scoped and never reads the arguments. That same marker scoping is what lets a reinstall replace an entry in place, and it is why a stale entry reads as installed.

The target therefore judges a hook by the **set of events** its entries sit on and their **whole commands**, both against what would be installed now, and rewrites a hook that differs into the four current entries. One unreadable settings file MUST be reported as blocked without stranding the others.

For an agent that runs a hook only after the user has approved it (Codex), the target MUST also read whether the agent will run **every** installed entry. A current hook the agent will not run MUST be **reported, never written**, with the reason and the remedy (approve it with `/hooks` in Codex). Coffer MUST NOT write the agent's approval record: approving a hook is the user's act in the agent (spec agent-registry/codex "Leave Codex's internal-state tables untouched").

The hooks wanted are those of every connected agent and of every agent that already carries one. A pass — at boot or on its period — MUST NOT install a hook for an agent that has none; only a person applying that item, or connecting the agent, installs it. Otherwise the missing hook is reported and the agent's connection reads partial. A repair that added the hook would be an install Coffer made silently, which "Install delivery hooks explicitly and removably" forbids.

#### Scenario: a hook whose command went stale is repaired without being asked
- **GIVEN** an agent with Coffer's hook installed, and a Coffer build whose delivery command is no longer the one in that agent's settings file,
- **WHEN** a reconcile pass runs — at daemon start or on its period,
- **THEN** the entries are rewritten in place to the ones this build would install, so the next session is served rather than shown a usage error,
- **AND** an agent whose hook is already current is left untouched, and an agent with no hook is not given one.

#### Scenario: a current Codex hook Codex has not approved is reported, not written
- **GIVEN** a connected Codex agent carrying the current hook, and no approval for its entries in Codex's `config.toml`
- **WHEN** a reconcile pass runs on its period, and again when a person applies it
- **THEN** the only difference is `trust`, and it is reported as `hook_untrusted` with the remedy "run /hooks in Codex"; nothing is written, and Coffer records no approval
- **AND** once `config.toml` records Codex's approval of every one of those entries, the next pass finds nothing to do

#### Scenario: an older build's Codex hook is moved to SessionStart
- **GIVEN** a connected Codex agent whose `hooks.json` carries an older build's Coffer entry on `UserPromptSubmit` (bare `coffer`, a `$PPID` guard) beside a foreign hook on that event
- **WHEN** a reconcile pass runs on its period
- **THEN** the difference is a modification of `command` and `event` and is repaired: Coffer's entries now sit on `SessionStart`, `UserPromptSubmit`, `PreToolUse` and `PostToolUse` and call the CLI by absolute path
- **AND** the foreign `UserPromptSubmit` hook is untouched and no older Coffer entry is left beside it

### Requirement: Cover memory management on REST and the CLI
A REST family under `/api/v1/memory` MUST cover: list partitions and notes, show one note with its provenance, browse a partition's own directory and read one file from it, update memory (see "Update memory in one action"), answer one fire of the memory hook (`POST /hook`, whose session-start answer is the composed session context), manage triggers (see "Keep triggers in the vault, armed only by a person"), read the delivery overview and a partition's Delivered view (see "Count what memory delivered and what was read", "Show what each agent is given at session start"), and read what has been retired. The `coffer memory` CLI group MUST offer `list`, `show`, `edit`, `rm`, `sync` (update memory: an aggregation, then a distil pass over every partition that gained entries, see "Update memory in one action"), `hook` (the command every installed memory hook entry runs), `trigger` (`list`, `add`, `arm`, `disarm`, `delete`) and `delivered` (the overview, or one partition's Delivered view). It offers no `add`, because partitions are created only by aggregation (see "Provision partitions only from aggregation"), and no `enable` or `disable`, because a partition has no switch (see "Serve every partition to every agent"). A partition's notes, its index, its retirement record and its file tree are plain files (see "Keep notes readable as plain files"), so on the command line `coffer path memory [<partition>]` prints the absolute path of the memory root or of one partition, and they are read on disk; the `coffer memory` group carries no command that lists or prints a note or a file. Installing, inspecting and removing an agent's delivery hook are part of that agent's Coffer connection (spec agent-registry "Connect an agent to Coffer in one action") and are not in this family: on the command line they are `coffer agent connect|disconnect <agent>`, and `coffer agent show <agent>` carries the hook as a part of its `coffer_connection`.

#### Scenario: a partition's own directory is browsable as a file tree
- **GIVEN** a distilled partition
- **WHEN** its file tree is requested, and then one file out of it
- **THEN** the tree's root carries the partition directory's absolute path and holds `MEMORY.md`, a `notes/` directory listing one Markdown file per note, and `RETIRED.md` when anything has been retired; reading `notes/<slug>.md` returns its text — not binary, not truncated — with the absolute path of the file and of the folder holding it
- **AND** `.raw/` is not in the tree and reading a path under it is refused, the family is read-only (a write is refused with 405), and a path escaping the partition is refused with `MEMORY_UNSAFE_PATH` (400) (see "Present partitions as a table and a file tree", "Confine reads to registered agents' memory paths")

#### Scenario: locate a partition's notes from the command line
- **GIVEN** a distilled partition named `coffer`
- **WHEN** `coffer path memory coffer` runs, and then `coffer path memory` with no partition
- **THEN** the first prints the absolute path of the partition directory, which holds `MEMORY.md` and `notes/`, and the second prints the absolute memory root that holds it
- **AND** `coffer memory` offers no `partitions`, `notes`, `note`, `retired`, `ls`, `read`, `distil`, `delivery`, `delivery-install`, `delivery-remove` or `context` command

#### Scenario: the agent's command-line view reports delivery state
- **GIVEN** two registered agents, one connected by `coffer agent connect <agent>` and one not
- **WHEN** `coffer agent show <name> --json` runs for each
- **THEN** the first's `coffer_connection` is `connected` with its `memory_hook` part installed, the second's is `disconnected`, and neither carries a last-fired time
