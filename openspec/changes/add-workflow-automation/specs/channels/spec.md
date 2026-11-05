## REMOVED Requirements

### Requirement: Keep scheduled tasks as machine-local resources
**Reason**: A scheduled task no longer needs a chat; the requirement moves to
[automation](../automation/spec.md) with the same title, gaining the workspace
target and the schedule timezone.
**Migration**: Acceptance markers move from `channels` to `automation`; the
task file and its fields are unchanged for a chat task.

### Requirement: Run a scheduled task at the times it names
**Reason**: Moves to [automation](../automation/spec.md) with the same title,
gaining the schedule timezone.
**Migration**: Acceptance markers move to `automation`.

### Requirement: Catch up a missed run once, within its grace
**Reason**: Moves to [automation](../automation/spec.md) with the same title.
**Migration**: Acceptance markers move to `automation`.

### Requirement: Keep every scheduled run in the task's history
**Reason**: Moves to [automation](../automation/spec.md) with the same title,
gaining the `no_change`, `deferred`, `unknown` and related outcomes; an
interrupted writing run is closed `unknown` instead of `failed`.
**Migration**: Existing rows keep their outcomes; acceptance markers move to
`automation`, including "a run's conversation opens from its history"; the
marker of "a run interrupted by a stop is closed on the next start" is renamed
to `automation` "a writing run interrupted by a stop is closed unknown on the
next start", whose assertion changes from `failed` to `unknown`.

## MODIFIED Requirements

### Requirement: Run a scheduled task in the chat it names
A task whose target is a chat ([automation](../automation/spec.md) "Keep
scheduled tasks as machine-local resources") MUST enter its chat the way a
message does: through the channel's turn driver, queued behind whatever that
conversation is doing, rendered by the same live surface, and answered in the
task's thread — but under the unattended permission mode
([automation](../automation/spec.md) "Run every scheduled turn unattended"),
not the full-permission mode a person's message gets. A task that `continue`s
runs in the chat thread's active conversation, which a run does not roll over
for being idle; a `fresh` task opens a new conversation with its own agent,
model and directory where it names them (the chat's settings otherwise), and
that conversation becomes the thread's active one, as `/new` would. A
follow-up's reply MUST mention the person who asked for it, where the
transport can. A run that cannot start — the channel is not running, the chat
is no longer paired, the conversation cannot be opened, the conversation's
queue is full — MUST be recorded `deferred` with the reason, and the chat told
in one line when it can still be reached. When a chat-target task is paused
([automation](../automation/spec.md) "Pause a task that keeps failing"),
including at once for a run whose result is unknown, its chat MUST be told
once, while its channel is running, that it was paused, why, and how to
resolve or resume it. A workspace task's notification to a chat
([automation](../automation/spec.md) "Keep a run's result local unless the
policy says to notify") is one message through the same binding, not a turn.

#### Scenario: a follow-up answers in its thread and mentions the asker
- **GIVEN** a follow-up Sam's question booked in a group thread
- **WHEN** it runs
- **THEN** the reply is posted in that thread, in the thread's conversation, mentioning Sam

#### Scenario: a fresh task opens a new conversation on its own agent
- **GIVEN** a task that runs `fresh` on Codex in `~/work/site`, in a direct chat whose conversation runs Claude Code
- **WHEN** it runs
- **THEN** a new conversation on Codex in `~/work/site` answers it and becomes the chat's active conversation

#### Scenario: a repeating task that keeps failing is paused
- **GIVEN** a daily task whose chat is no longer paired with its channel
- **WHEN** its third run in a row cannot start and is deferred for that reason
- **THEN** the task is switched off and the chat is told the task was paused and where to resume it

#### Scenario: a chat run of unknown result is told once in its chat
- **GIVEN** a chat-target task whose run was closed `unknown` after a daemon stop
- **WHEN** the channel is running again
- **THEN** the chat receives one message saying the task was paused because the run's result is unknown, with the reconcile command and Resume
- **AND** no further message is posted for later slots while it stays paused
