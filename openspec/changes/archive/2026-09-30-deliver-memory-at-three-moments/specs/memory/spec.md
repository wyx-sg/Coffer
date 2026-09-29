## ADDED Requirements

### Requirement: Retrieve the notes a prompt names
For every prompt the developer sends a hook-driven session, Coffer MUST rank the notes of the session's repository partition and of `global` against the prompt — each note's title, description, search terms and body — with a lexical ranker (BM25, CJK text as bigrams), and MUST add to the session the **top three** notes that score at or above a **relevance floor** and that this session has not already been given. Each is delivered as the absolute path of its file and its substance (see "Word delivered notes as provenance plus fact"), and the whole delivery MUST stay within **1,500 UTF-8 bytes**. A prompt of fewer than three words, or a bare nudge such as `continue`, `ok` or `继续`, MUST retrieve nothing. What a session was already given is remembered per `session_id` — the id the agent hands its hook, never a process id — for the daemon's lifetime.

The ranking index is derived: it is held in memory, rebuilt from the note files when a partition's `notes/` changes, and never written. Nothing chunks or embeds a note.

#### Scenario: a prompt brings in the notes it names
- **GIVEN** a repository partition holding a note about running `make verify` under Node 20 and unrelated notes, and a `global` partition
- **WHEN** a session opened in that repository sends the prompt "why does make verify fail with undici AbortSignal under node"
- **THEN** the hook answers with `additionalContext` naming the Node 20 note's absolute path, at most three notes in all, every one scoring at or above the floor
- **AND** the text is at most 1,500 UTF-8 bytes

#### Scenario: a short or trivial prompt retrieves nothing
- **GIVEN** a partition whose notes would match the words of the prompt
- **WHEN** the session sends `继续`, then `ok`, then a two-word prompt
- **THEN** the hook prints nothing for each, and no delivery is audited

#### Scenario: a note already delivered in the session is not delivered again
- **GIVEN** a session that was given a note for one prompt
- **WHEN** the same session sends a prompt that ranks the same note first, and a second session sends that prompt too
- **THEN** the first session is not given the note again, and the second session is

### Requirement: Guard a known trap once per session
Before a hook-driven session runs a shell command, Coffer MUST check the command against every **armed** `block` trigger whose note the session can reach — a `global` note's trigger in every session, a repository note's trigger only in that repository's sessions. The command pattern MUST be matched **from the start** of each shell segment that **executes** — the program's base name and its arguments, after any `VAR=value` prefix, or, when the program is an interpreter running a script (`bash`, `sh`, `zsh`, `python3`, `node`, …), the script's base name and its arguments — so a command that only mentions the pattern in an argument (`cat scripts/e2e.sh`) does not match while the command that runs it (`bash scripts/e2e.sh`) does; an `unless` pattern matching the whole command keeps the trigger quiet. The first matching command in a session MUST be **denied once**, through the agent's own deny decision, with the note as the reason and a line saying it is held once; the same trigger MUST NOT hold another command in that session, so the agent's next attempt passes. After a shell command, an armed `context` trigger whose error pattern the command's output shows MUST add the note as context, once per session, and MUST NOT block. A fire without a `session_id` holds nothing.

#### Scenario: a matching command is denied once with the note as the reason
- **GIVEN** an armed `block` trigger on a repository note whose command pattern matches `make verify` unless `v20` appears, and a session opened in that repository
- **WHEN** the session runs `make verify`, then runs `make verify` again
- **THEN** the first answer is `permissionDecision: "deny"` whose reason names the note's file and its rule and says it is held once
- **AND** the second answer is nothing, so the command runs, and `PATH=$HOME/.nvm/versions/node/v20.20.2/bin:$PATH make verify` in a fresh session is not held either

#### Scenario: a command that only mentions the pattern passes
- **GIVEN** an armed `block` trigger whose command pattern names `e2e`
- **WHEN** the session runs `cat scripts/e2e.sh`, then `bash scripts/e2e.sh`
- **THEN** the first is not held and the second is

#### Scenario: an error in a command's output adds the note without blocking
- **GIVEN** an armed `context` trigger whose error pattern is `timeout: command not found`
- **WHEN** a session's shell command finishes with that text in its output, and then again
- **THEN** the first `PostToolUse` answer carries the note as `additionalContext` and no deny, and the second answer is nothing

#### Scenario: a trigger on another repository's note stays quiet
- **GIVEN** an armed `block` trigger on a note in repository A's partition
- **WHEN** a session opened in repository B runs the matching command
- **THEN** nothing is held

### Requirement: Keep triggers in the vault, armed only by a person
A trigger MUST be one Markdown file in the vault, `vault/memory-triggers/<id>.md`, whose frontmatter names its note (`<partition>/<slug>`), its kind (`block` or `context`), its command, `unless` and error patterns, who proposed it, who armed it and when, and when it was created. It lives beside the derived memory tree, never inside it, so deleting and rebuilding that tree keeps every trigger, and it travels with the vault to the user's other machines ([vault-sync](../vault-sync/spec.md) "Apply knowledge, skill and memory-trigger file changes"). A trigger takes effect only while **armed**, and only a person arms one: a trigger a person writes (`POST /api/v1/memory/triggers`, `coffer memory trigger add`) is armed by that person as it is written, while a trigger the distil pass proposes for a note it judges a known trap tied to a command lands **unarmed** and does nothing until a person arms it. Triggers MUST be listed, armed, disarmed and deleted from both REST (`GET /api/v1/memory/triggers`, `POST …/{id}/arm`, `POST …/{id}/disarm`, `DELETE …/{id}`) and the CLI (`coffer memory trigger list|add|arm|disarm|delete`), each act an audit event naming the trigger and its note. Nothing is seeded: a vault has no trigger until a person writes one or distil proposes one.

#### Scenario: a proposed trigger does nothing until a person arms it
- **GIVEN** a distil pass whose writing stage returned a trigger for the note it wrote
- **WHEN** the pass finishes, and a session then runs the matching command
- **THEN** `vault/memory-triggers/` holds one file for it with `proposed_by: distil` and no `armed_by`, a `memory_trigger_proposed` event is recorded, and the command is not held
- **AND** once a person arms it with `coffer memory trigger arm <id>`, the matching command in a new session is held

#### Scenario: triggers are managed from REST and the command line
- **GIVEN** a running daemon and no triggers
- **WHEN** a person adds a trigger with `coffer memory trigger add`, disarms it over REST, arms it again from the CLI, and deletes it over REST
- **THEN** the listing shows it armed, then unarmed, then armed, then gone, its file follows each step, and `memory_trigger_added`, `memory_trigger_disarmed`, `memory_trigger_armed` and `memory_trigger_deleted` are recorded with that person as actor
- **AND** a trigger whose pattern does not compile is refused with `MEMORY_TRIGGER_INVALID` and no file is written

#### Scenario: a fresh vault has no triggers
- **GIVEN** a new vault on which memory has been aggregated and distilled without an internal connection
- **WHEN** the triggers are listed
- **THEN** there are none, and `vault/memory-triggers/` holds no file

### Requirement: Fail open when Coffer cannot answer
Every memory hook MUST fail open: when the daemon is not running, does not answer within the hook's own short timeout, or answers with an error, the hook MUST print nothing and exit 0, so memory never stops a prompt or a command because Coffer is down. A fire that can deliver nothing — a trivial prompt, a shell command no armed trigger matches — MUST be answered without contacting the daemon.

#### Scenario: the hook prints nothing and exits 0 with no daemon
- **GIVEN** no daemon running and an armed `block` trigger that matches `make verify`
- **WHEN** `coffer memory hook` is given a `SessionStart`, a `UserPromptSubmit` and a `PreToolUse` event for `make verify` on stdin
- **THEN** each run prints nothing and exits 0

### Requirement: Word delivered notes as provenance plus fact
Every note delivered at a prompt, before a command or after one MUST read as **provenance plus fact**: it names the note's file, and states the note's substance as "the user's standing rule is: …" for a `feedback` note and as "a fact they recorded: …" otherwise. Delivered text MUST NOT be phrased as an instruction to the agent.

#### Scenario: a delivered note names its file and reads as a standing rule
- **GIVEN** a `feedback` note and a `project` note that both match a prompt
- **WHEN** the prompt's delivery is composed
- **THEN** the `feedback` note's line names its absolute path and reads "the user's standing rule is: …", and the `project` note's reads "a fact they recorded: …"

### Requirement: Count what memory delivered and what was read
`GET /api/v1/memory/deliveries` and `coffer memory delivered` MUST report, for every registered agent with a delivery hook, over the last **seven days**: the number of delivery fires recorded in the audit log, the same count by moment (`session_start`, `prompt`, `guard`, `error`), when memory last reached it, and how many **distinct notes** its sessions opened. The last is read off the file paths the agent's tool calls named — a path under the memory root naming a note — and never off what a note, a tool result or a message says; when the agent's transcripts cannot be read it MUST be reported as `unavailable` rather than as zero. The report MUST NOT carry whether a hook is installed or trusted.

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
`GET /api/v1/memory/partitions/{uid}/delivered` and `coffer memory delivered <partition>` MUST return, for every registered agent with a delivery hook, the **exact text** that agent's session-start hook would add in that partition's repository — composed by the same function and under the same ceiling the hook uses — read only, and without whether a hook is installed or trusted.

#### Scenario: the Delivered view carries each agent's exact session-start text
- **GIVEN** a distilled repository partition and a registered Claude Code and Codex agent
- **WHEN** the partition's Delivered view is read
- **THEN** each agent's entry carries `SessionStart` and text equal to what `POST /api/v1/memory/hook` answers a `SessionStart` fire from that repository with
- **AND** nothing is audited and no hook state is carried

### Requirement: Leave per-turn rules to the agent's own instructions
Memory delivery MUST NOT be presented as the place for a rule about **every** turn — the language of every reply, a tone — which no retrieval or trigger addresses: such a rule belongs in the instructions the agent loads on every turn (`CLAUDE.md`, `AGENTS.md`), which the user owns. Installing or firing Coffer's memory hook MUST NOT write those files.

#### Scenario: connecting an agent leaves its instructions files untouched
- **GIVEN** a Claude Code agent with a `CLAUDE.md` and a Codex agent with an `AGENTS.md`
- **WHEN** both are connected with `memory` on and every one of their hooks fires
- **THEN** both instructions files are byte-identical afterwards

## MODIFIED Requirements

### Requirement: Read no transcripts or rollouts
Aggregation MUST NOT read session transcripts, rollouts or raw capture files. Both supported agents already distil their own; this layer starts from that output. The one reading of a transcript this layer does is the count of "Count what memory delivered and what was read", which looks only at the file paths an agent's tool calls named and never at what any message, tool result or note says.

#### Scenario: list no transcript or rollout as a source
- **GIVEN** a Claude Code config directory holding a session transcript beside a project's memory directory, and a Codex home holding session rollouts beside its memory files
- **WHEN** each reader lists its sources
- **THEN** no transcript, rollout or raw capture file is among them

### Requirement: Install delivery hooks explicitly and removably
For an agent the developer drives themselves, delivery MUST go through that agent's own hook mechanism, invoking Coffer's existing CLI **by absolute path**. An agent runs its hooks under a shell that need not have `~/.coffer/bin` on its `PATH`: Codex runs them under `/bin/zsh` without the user's rc files, and Claude Code started from the Dock does not inherit the login shell's `PATH`. The bare name is used only when the build cannot locate its own CLI.

Coffer's hook is **four entries**, one on each moment memory reaches a session, for both supported agents: `SessionStart` (matched on `startup|resume|clear|compact`), `UserPromptSubmit`, and `PreToolUse` and `PostToolUse` matched on the `Bash` tool. Every entry runs the same command, `coffer memory hook --agent-uid <uid> --cwd "$PWD"`, which reads the event the agent hands its hook on stdin and prints that event's JSON `hookSpecificOutput` — `additionalContext` to add context, `permissionDecision: "deny"` with a reason to hold a command — which both agents read on every event. Nothing once-per-session MAY be keyed on a process id: every session of one Codex app-server shares a parent pid, so it is keyed on the hook's `session_id`. `coffer memory context` stays the command that composes the session-start text alone.

Installation MUST be an **explicit act** on Coffer's surface: connecting the agent to Coffer, of which the hook is one part (spec agent-registry "Connect an agent to Coffer in one action"), or switching `memory` on while the agent is connected. It MUST be marker-scoped, idempotent, and removable without disturbing entries Coffer did not write. An install or a remove MUST take out Coffer's marked entries on **every** event first, so an older build's entry on another event is never left behind beside the new ones. Coffer MUST NOT install the hook silently, and MUST NOT write into any file that is an agent's *memory*: a hook lives in the agent's settings, which is a different thing.

#### Scenario: hook installation is marker-scoped and removable
- **GIVEN** an agent whose settings file already carries a foreign hook on the same lifecycle events, other events' hooks, and unrelated top-level keys
- **WHEN** delivery is installed, installed a second time, and then removed
- **THEN** install adds exactly **one** entry carrying Coffer's marker on each of `SessionStart`, `UserPromptSubmit`, `PreToolUse` and `PostToolUse`, all running `coffer memory hook` by absolute path, a second install leaves one on each, and every foreign hook, every other event and every unrelated key is untouched
- **AND** remove takes out only the marked entries — dropping an event array and the top-level hooks key once they are empty — and with nothing installed it is a clean no-op that writes no file and records no audit event (see "Install delivery hooks explicitly and removably")

#### Scenario: a Codex hook fire prints the session-start JSON Codex reads
- **GIVEN** a partition with notes and a registered agent
- **WHEN** `coffer memory context --agent-uid <uid> --cwd <repository> --hook-event SessionStart` runs, and `coffer memory hook --agent-uid <uid>` runs with a Codex `SessionStart` event on stdin
- **THEN** each prints one JSON object whose `hookSpecificOutput` names `SessionStart` as its `hookEventName` and carries the composed index as `additionalContext`
- **AND** each fire is recorded, exactly as a plain-text fire is

#### Scenario: both agents' hook fires answer in the JSON each reads
- **GIVEN** a Claude Code agent and a Codex agent connected on a fake home, a distilled partition, and an armed `block` trigger
- **WHEN** each agent's installed command is run with that agent's own `UserPromptSubmit` and `PreToolUse` input on stdin
- **THEN** each prints `hookSpecificOutput` with `additionalContext` for the prompt and `permissionDecision: "deny"` with the note as `permissionDecisionReason` for the command

### Requirement: Repair stale delivery hooks
An installed hook MUST be repaired when what Coffer would write is no longer what is installed, without waiting for a user to notice. This is the delivery-hook target of the unified reconciler ([resource-framework](../resource-framework/spec.md) "Converge what Coffer writes outside its database with one reconciler"), and it runs on every pass, not only at daemon start.

A hook is a string left in somebody else's settings file, and the CLI it invokes ships in a binary that keeps moving. When `coffer memory context` stopped taking `--agent` and started taking `--agent-uid`, every hook already on disk kept passing an option that no longer existed. The agent printed a usage error at the start of every session, and this layer never reached it again. Nothing reported the failure, because detection is marker-scoped and never reads the arguments. That same marker scoping is what lets a reinstall replace an entry in place, and it is why a stale entry reads as installed.

The target therefore judges a hook by the **set of events** its entries sit on and their **whole commands**, both against what would be installed now. An older build's single `SessionStart` entry, or an older Codex entry on `UserPromptSubmit`, is thereby rewritten into the four current entries by an ordinary pass. One unreadable settings file MUST be reported as blocked without stranding the others.

For an agent that runs a hook only after the user has approved it (Codex), the target MUST also read whether the agent will run **every** installed entry. A current hook the agent will not run MUST be **reported, never written**, with the reason and the remedy (approve it with `/hooks` in Codex). Coffer MUST NOT write the agent's approval record: approving a hook is the user's act in the agent (spec agent-registry/codex "Leave Codex's internal-state tables untouched").

With `memory` on, the hooks wanted are those of every connected agent and of every agent that already carries one. A pass MUST NOT install a hook for an agent that has none, unless it runs because `memory` was just switched on or because a person applied that item. Otherwise the missing hook is reported and the agent's connection reads partial. A repair that added the hook would be an install Coffer made silently, which "Install delivery hooks explicitly and removably" forbids.

#### Scenario: a hook whose command went stale is repaired without being asked
- **GIVEN** an agent with Coffer's hook installed, and a Coffer build whose delivery command is no longer the one in that agent's settings file,
- **WHEN** a reconcile pass runs — at daemon start or on its period,
- **THEN** the entries are rewritten in place to the ones this build would install, so the next session is served rather than shown a usage error,
- **AND** an agent whose hook is already current is left untouched, and an agent with no hook is not given one.

#### Scenario: an older build's Codex hook is moved to SessionStart
- **GIVEN** a connected Codex agent whose `hooks.json` carries an older build's Coffer entry on `UserPromptSubmit` (bare `coffer`, a `$PPID` guard) beside a foreign hook on that event
- **WHEN** a reconcile pass runs on its period
- **THEN** the difference is a modification of `command` and `event` and is repaired: Coffer's entries now sit on `SessionStart`, `UserPromptSubmit`, `PreToolUse` and `PostToolUse` and call the CLI by absolute path
- **AND** the foreign `UserPromptSubmit` hook is untouched and no older Coffer entry is left beside it

#### Scenario: a current Codex hook Codex has not approved is reported, not written
- **GIVEN** a connected Codex agent carrying the current hook, and no approval for its entries in Codex's `config.toml`
- **WHEN** a reconcile pass runs on its period, and again when a person applies it
- **THEN** the only difference is `trust`, and it is reported as `hook_untrusted` with the remedy "run /hooks in Codex"; nothing is written, and Coffer records no approval
- **AND** once `config.toml` records Codex's approval of every one of those entries, the next pass finds nothing to do

### Requirement: Audit every delivery fire
Coffer MUST record **an audit event for every delivery fire**, so that whether delivery is actually happening is answerable after the fact: every session start, and every prompt, guard and error fire that delivered a note. The event MUST name its moment (`session_start`, `prompt`, `guard`, `error`), the session, and the notes it carried (and, for a trigger, the trigger) — never their text. A fire is an event, not a property of the agent: the hook's per-agent status MUST report installation only, and MUST NOT carry a last-fired timestamp.

#### Scenario: every hook fire is recorded in the audit log
- **GIVEN** an agent for which delivery has been installed
- **WHEN** the installed hook fires and the served context is recorded as a delivery
- **THEN** exactly one audit event is written naming that agent as both the resource and the actor
- **AND** the per-agent installed state is unchanged by a fire, and neither installing nor reading status records a fire of its own (see "Audit every delivery fire")

#### Scenario: a prompt and a guard fire each name their moment and notes
- **GIVEN** a session that is given a note at a prompt and has a command held by a trigger
- **WHEN** the audit log is read
- **THEN** one `memory_delivery_fired` event names moment `prompt` and the note, and another names moment `guard`, the trigger and its note, and neither carries the note's text

### Requirement: Cover memory management on REST and the CLI
A REST family under `/api/v1/memory` MUST cover: list partitions and notes, show one note with its provenance, browse a partition's own directory and read one file from it, update memory (see "Update memory in one action"), compose the session context, answer one fire of the memory hook (`POST /hook`), manage triggers (see "Keep triggers in the vault, armed only by a person"), read the delivery overview and a partition's Delivered view (see "Count what memory delivered and what was read", "Show what each agent is given at session start"), and read what has been retired. The `coffer memory` CLI group MUST offer `list`, `show`, `edit`, `rm`, `sync` (update memory: an aggregation, then a distil pass over every partition that gained entries, see "Update memory in one action"), `context` (compose the session-start context), `hook` (the command every installed memory hook entry runs), `trigger` (`list`, `add`, `arm`, `disarm`, `delete`) and `delivered` (the overview, or one partition's Delivered view). It offers no `add`, because partitions are created only by aggregation (see "Provision partitions only from aggregation"), and no `enable` or `disable`, because a partition has no switch (see "Serve every partition to every agent"). A partition's notes, its index, its retirement record and its file tree are plain files (see "Keep notes readable as plain files"), so on the command line `coffer path memory [<partition>]` prints the absolute path of the memory root or of one partition, and they are read on disk; the `coffer memory` group carries no command that lists or prints a note or a file. Installing, inspecting and removing an agent's delivery hook are part of that agent's Coffer connection (spec agent-registry "Connect an agent to Coffer in one action") and are not in this family: on the command line they are `coffer agent connect|disconnect <agent>`, and `coffer agent show <agent>` carries the hook as a part of its `coffer_connection`.

#### Scenario: a partition's own directory is browsable as a file tree
- **GIVEN** a distilled partition
- **WHEN** its file tree is requested, and then one file out of it
- **THEN** the tree's root carries the partition directory's absolute path and holds `MEMORY.md`, a `notes/` directory listing one Markdown file per note, and `RETIRED.md` when anything has been retired; reading `notes/<slug>.md` returns its text — not binary, not truncated — with the absolute path of the file and of the folder holding it
- **AND** `.raw/` is not in the tree and reading a path under it is refused, the family is read-only (a write is refused with 405), and a path escaping the partition is refused with `MEMORY_UNSAFE_PATH` (400) (see "Present partitions as a table and a file tree", "Confine reads to registered agents' memory paths")

#### Scenario: locate a partition's notes from the command line
- **GIVEN** a distilled partition named `coffer`
- **WHEN** `coffer path memory coffer` runs, and then `coffer path memory` with no partition
- **THEN** the first prints the absolute path of the partition directory, which holds `MEMORY.md` and `notes/`, and the second prints the absolute memory root that holds it
- **AND** `coffer memory` offers no `partitions`, `notes`, `note`, `retired`, `ls`, `read`, `distil`, `delivery`, `delivery-install` or `delivery-remove` command, and `coffer memory context` is unchanged

#### Scenario: the agent's command-line view reports delivery state
- **GIVEN** the `memory` feature on and two registered agents, one connected by `coffer agent connect <agent>` and one not
- **WHEN** `coffer agent show <name> --json` runs for each
- **THEN** the first's `coffer_connection` is `connected` with its `memory_hook` part installed, the second's is `disconnected`, and neither carries a last-fired time
