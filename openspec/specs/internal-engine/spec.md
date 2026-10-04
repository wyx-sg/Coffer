# Internal Engine

## Purpose

Coffer makes one kind of model call of its own: it transcribes a voice message. The
internal engine is the settings that hold what that call needs and what Coffer's two
unattended memory passes need — the speech-to-text model, and the switch and
interval of the aggregate and distil passes. It owns one settings
document per vault, the surfaces that show and change it (`/api/v1/internal-engine-config`,
the Speech-to-text section of Settings › General and the Memory page's upkeep controls),
and its convergence between machines. The name is kept although there is no longer an
engine model: it is the identifier inbound links and the route family resolve.

Coffer does work on its own behalf: it aggregates the agents' memory, turns each new raw
entry into a note, sweeps the knowledge root, and transcribes a voice message. Only the
last needs an endpoint and a model. Speech-to-text has its own connection (flagged
`transcribe_default`) and its own model, because the gateway that answers a chat
completion commonly serves no transcription endpoint at all. Neither memory pass calls a
model, and there is no engine model, no curate pass, no curation owner machine and no
internal default connection: judgement over knowledge and memory is the person's own
coding agent's, reached through a Tidy hand-off ([knowledge](../knowledge/spec.md),
[memory](../memory/spec.md)). This capability supplies the speech-to-text model and
the two timers; chat's voice transcription supplies its own prompt and owns its
own results.

The speech-to-text call runs under one fixed 60 second limit: it is the only
model call Coffer makes, so the limit is a constant and not a setting. Keys an
older build wrote into the document (`model`, `curate_owner_machine_id`,
`model_timeout_s`, `upkeep.curate`) are ignored on read and dropped on the next
write.

Out of scope: creating, editing, activating or flagging a connection (`transcribe_default`
is provider-switching's field and route, `POST /api/v1/providers/{uid}/transcribe-default`);
what each pass does (memory's; the knowledge sweep has no switch or interval of its own);
`GET /api/v1/upkeep/runs`, a cross-kind read of what is in flight; any model registry; and
per-partition timers. Coffer runs as a single-user tool behind the existing
`X-Coffer-Token` gate.

The engine keeps resolving its connection whatever the features say. While `models` is
switched off the speech-to-text connection cannot be changed, and Settings › General omits
what depends on Models; while `memory` is off the distil and aggregate passes skip their
rounds, and the knowledge sweep skips its rounds while `knowledge` is off (spec
[experimental-features](../experimental-features/spec.md) "Keep dependencies between
features soft").

## Requirements

### Requirement: Keep the engine's settings in one vault document
The system MUST keep Coffer's own operating settings — the speech-to-text model
and the switch and optional interval of each unattended pass — in one vault document at one fixed path,
`state/settings/internal-engine.json` ([vault-storage](../vault-storage/spec.md) "Keep every vault document a JSON object that preserves what it does not know"),
so a second copy is unrepresentable whatever writes it. The time of the last
write is not in the document, because two machines stamping it would conflict
on every edit: it is this machine's own record, `~/.coffer/local/engine.json`.
An absent key or `null` means "the built-in default" for an interval and
"unchosen" for the speech-to-text model.

#### Scenario: a second engine settings document is unrepresentable
- **GIVEN** the internal-engine settings document exists,
- **WHEN** the settings are written again,
- **THEN** the vault still holds exactly one settings document, at
  `state/settings/internal-engine.json`, so "which settings does the engine
  use?" cannot become a question with two answers.

### Requirement: Audit every write to the engine settings
Every write to the settings MUST record an `internal_engine_model_set` audit
entry naming the actor and carrying the values after the write. A change another
machine made arrives as a sync commit to the settings document, and is as visible
in that document's history as one made here ([vault-storage](../vault-storage/spec.md) "Show, compare and restore any version of a vault file").

#### Scenario: record every settings write with its actor and values
- **GIVEN** the internal-engine settings,
- **WHEN** one pass's switch and the speech-to-text model are each
  written by an actor,
- **THEN** each write records an `internal_engine_model_set` audit entry naming
  that actor,
- **AND** each entry's details carry the value as it stands after that write.

### Requirement: Change one unattended pass per write
`PUT /api/v1/internal-engine-config/upkeep` MUST change exactly one named pass.
An omitted half MUST leave that half alone, and the other pass MUST be left
exactly as it stands — a body carrying both would make every toggle a
chance to write back a stale copy of the other, on settings another machine
may be changing too. `use_default_interval` returns that pass to its own
default, which a null interval cannot express.

#### Scenario: switch off and re-time the passes Coffer runs unattended
- **GIVEN** a fresh vault, where aggregation and distil run on their own
  timers,
- **WHEN** the operator switches one pass on or off, or gives it an interval, or
  returns it to its own default (`PUT /api/v1/internal-engine-config/upkeep`,
  one pass per request),
- **THEN** that pass's switch and interval change and no other pass's do, the
  reported default interval says what runs while none is chosen, an interval
  below the floor and an unknown pass name are both refused, and the running
  worker picks the change up without a restart.

### Requirement: Report an unchosen interval beside its default
An interval the operator has not chosen MUST be reported as unchosen ALONGSIDE
the default that runs in its place. The default MUST live in the worker that
owns the pass, not copied into each vault, so raising it later reaches every
vault that never chose one.

#### Scenario: report an unchosen interval beside the default that runs
- **GIVEN** a pass whose interval the operator chose and then returned to the
  default,
- **WHEN** the settings are read,
- **THEN** that pass's interval is reported as unchosen beside the default
  interval its worker runs at,
- **AND** the stored document holds no interval for it, so no default was copied
  into the vault.

### Requirement: Refuse an interval below the floor or an unknown pass
An interval below the floor MUST be refused, because it would busy-loop a pass
over the user's files, and so MUST a pass name Coffer does not run.

#### Scenario: refuse an interval below the floor or an unknown pass
- **GIVEN** the upkeep settings as they stand,
- **WHEN** the operator asks for an interval below the floor, or names a pass
  Coffer does not run,
- **THEN** both requests are refused with a validation error,
- **AND** every pass's switch and interval are left exactly as they stood.

### Requirement: Apply a changed switch or interval without a restart
A running worker MUST pick a switch or interval change up without a daemon
restart: the wait is taken in slices and the interval re-read each slice, and
the switch is read before each pass.

#### Scenario: a running worker picks up a changed switch and interval
- **GIVEN** a running pass worker reading its switch and interval from the
  settings document,
- **WHEN** the operator switches the pass off, and shortens its interval while
  the worker is already waiting,
- **THEN** the worker's next pass does not run while switched off,
- **AND** the wait already in progress ends at the new interval rather than the
  old one.

### Requirement: Ship every unattended pass switched on
Both unattended passes (`aggregate`, `distil`) MUST ship ON, because each
writes only derived files and deleting and re-running reproduces what it
writes.

#### Scenario: a fresh vault runs every unattended pass
- **GIVEN** a fresh vault where nobody has touched the engine settings,
- **WHEN** the settings are read, and when the document is first written by a
  speech-to-text model choice alone,
- **THEN** `aggregate` and `distil` are both switched on.

### Requirement: Converge the settings as the `settings` state area
The settings MUST travel as sync state area `settings`, document
`state/settings/internal-engine.json` ([vault-sync](../vault-sync/spec.md) "Converge shared state areas"), carrying the speech-to-text
model and every pass's switch and interval — Coffer's passes behave the same everywhere only when they share one
setting, and switching a pass off is exactly the decision a second machine
must not be left out of. The document is the
settings, with no second copy on this machine: a key it does not carry MUST read
as that key's default, and a key this build does not know MUST survive every
write this build makes.

#### Scenario: the engine's settings converge and a deletion means the defaults
- **GIVEN** a machine that has chosen nothing, whose settings read as the defaults
  with no settings document in the vault,
- **WHEN** it chooses a speech-to-text model, switches `distil` off with an interval,
- **THEN** `state/settings/internal-engine.json` carries each of those decisions and
  no time of the write, which is in this machine's `local/engine.json`, and the
  settings read back as written,
- **AND** a key a newer build wrote into the document survives the next write,
  and once the document is deleted every setting reads as its default again.

### Requirement: Publish no document while the defaults hold
A machine still holding the defaults MUST publish NO document: the area carries
a decision, not a row. The tree holds the document exactly while some machine
holds a non-default choice.

#### Scenario: a machine holding the defaults publishes no settings document
- **GIVEN** a machine that has never written the settings, and a machine whose
  settings were written but hold only the defaults,
- **WHEN** each machine's vault is read,
- **THEN** neither holds a settings document,
- **AND** once a non-default speech-to-text model is chosen, exactly one
  `internal-engine` document is published.

### Requirement: Reset to the defaults when the document is deleted
Deleting the document MUST put this machine on the defaults at once, with
nothing written here: the absence of the document is the defaults. The deletion
is itself the commit that removed the document — a sync commit naming the
machine that made it, when it came from another one.

#### Scenario: deleting the settings document resets this machine to the defaults
- **GIVEN** a machine holding a switched-off pass and a chosen
  speech-to-text model,
- **WHEN** a sync commit deletes the settings document,
- **THEN** every one of those returns to its default,
- **AND** nothing is written back, so the vault holds no settings document.

### Requirement: Transcribe speech on its own connection and model
The settings document MUST carry the speech-to-text model. The
connection it runs on MUST be the one flagged `transcribe_default`
([provider-switching](../provider-switching/spec.md) "Keep an independent speech-to-text default"), and the pair MUST resolve as both halves
or `None`. An unflagged connection or an unchosen speech-to-text model MUST
answer `None`, which [chat](../chat/spec.md) "Transcribe audio attachments when transcription is configured" turns into handing the agent the audio
file with nothing uploaded. Resolving the pair MUST NOT touch the network. The model MUST NOT be read from the environment: the
daemon is spawned detached from any shell, so an environment variable was
unreachable in a packaged install.

#### Scenario: speech-to-text runs on its own connection and its own model
- **GIVEN** a connection is flagged `transcribe_default` and a speech-to-text
  model is chosen,
- **WHEN** a turn carrying audio asks the engine what to transcribe with, and
  the operator then clears the model, or moves the flag to a connection that
  does not curate that model
  (`PUT /api/v1/internal-engine-config/transcribe-model`,
  `POST /api/v1/providers/{uid}/transcribe-default`),
- **THEN** the pair resolves to that connection and that model while both halves
  are set; with either half missing it resolves to `None` and the audio is
  handed to the agent as a file rather than uploaded; and moving the flag
  drops the speech-to-text model unless the newly flagged connection curates it.

### Requirement: Drop the speech-to-text model when its connection moves
A change of the `transcribe_default` connection MUST DROP the speech-to-text
model, unless the newly flagged connection's curated `models` already lists
that id — a curated list is that connection's own catalogue, so an id on it is
still servable. Nothing MUST be probed to decide: a settings write MUST NOT
depend on an endpoint being reachable. Re-flagging the connection that already
carries the flag MUST change nothing. The trigger is [provider-switching](../provider-switching/spec.md) "Keep an independent speech-to-text default", which notifies the
settings through a port; the rule and its exception are this capability's.

#### Scenario: moving the speech-to-text flag drops a model the new connection does not curate
- **GIVEN** connection A is flagged `transcribe_default`, a speech-to-text model
  is chosen, and connection B curates the speech-to-text model while
  connection C does not,
- **WHEN** the flag is re-set on A, then moved to B, then moved to C,
- **THEN** re-setting A and moving to B keep the speech-to-text model, moving to
  C clears it.

### Requirement: Report when each unattended pass last ran and runs next
Each pass in the upkeep block of `GET /api/v1/internal-engine-config` (and of every answer
the settings routes give) MUST carry `last_pass_at` and `next_pass_at`. `last_pass_at` MUST be
when that pass last finished on this machine, whoever asked for it — the timer or a button —
read from the audit event the pass records (`memory_aggregated`, `memory_distilled`),
so it survives a daemon restart; it is `null` when the pass never ran.
`next_pass_at` MUST be when this machine's timer runs the pass next, counted from the moment
its worker began waiting against the interval as it stands now (a worker's start delay
counting as its first wait), so a shortened interval moves it earlier at once. It MUST be `null`
while the pass is switched off, while a pass is running, and while no worker on this daemon is
waiting on it — the surface never invents a time.

#### Scenario: each pass reports when it last ran and when it runs next
- **GIVEN** an aggregation that finished 14 minutes ago with its worker waiting on a
  30-minute interval, and a distil pass that has never run and has no worker waiting
- **WHEN** the settings are read
- **THEN** `aggregate` reports its last pass 14 minutes ago and its next one 30 minutes after
  its wait began
- **AND** `distil` reports neither time

### Requirement: Report the engine settings over HTTP
`GET /api/v1/internal-engine-config` MUST report the speech-to-text model, when
this machine last wrote the settings, and every pass's switch, chosen
interval and default interval. The route family MUST carry no model for
Coffer's own passes, because Coffer runs no pass over a model of its own, and
no per-call time limit, because the one model call Coffer makes runs under a
fixed limit.

#### Scenario: read the engine settings
- **GIVEN** a vault whose settings hold a speech-to-text model and the aggregate pass switched off,
- **WHEN** `GET /api/v1/internal-engine-config` is read,
- **THEN** it returns that speech-to-text model, the time this machine last wrote the settings, and an upkeep block naming `aggregate` and `distil` with a switch, a chosen interval and a default interval each,
- **AND** the answer carries no engine model and no curation owner.

### Requirement: Ignore retired keys in the settings document
The system MUST accept a settings document that still carries the keys `model`,
`curate_owner_machine_id`, `model_timeout_s` or an `upkeep.curate` entry, and MUST ignore them on
read: they change no setting, raise no error and appear in no answer. The next
write of the document MUST drop them. A key this build has never known MUST
still survive a write, so only the retired keys are removed.

#### Scenario: ignore retired keys when the settings are read
- **GIVEN** a settings document holding `model`, `curate_owner_machine_id`, `model_timeout_s`, an `upkeep.curate` entry and a speech-to-text model,
- **WHEN** the settings are read,
- **THEN** the speech-to-text model is reported as stored and no answer carries a time limit,
- **AND** the upkeep block names `aggregate` and `distil` only, and nothing reports the retired keys.

#### Scenario: drop retired keys on the next write
- **GIVEN** a settings document holding the retired keys and a key a newer build wrote,
- **WHEN** the operator changes one value through any settings route,
- **THEN** the rewritten document holds no `model`, no `curate_owner_machine_id`, no `model_timeout_s` and no `upkeep.curate`,
- **AND** the newer build's key is still in the document.

### Requirement: Carry a switch and interval for each of the two unattended passes
The same document MUST carry a switch and an interval for each of the two passes
Coffer runs on its own behalf — `aggregate` (reads the agents' own memory into
the derived tree, [memory](../memory/spec.md) "Aggregate on an interval and on demand") and `distil` (turns each newly read entry into a note as it stands, and records the notes an agent retired). This
capability owns only whether and how often they run, one switch and interval
per pass rather than per target.

#### Scenario: report a switch and interval for each of the two unattended passes
- **GIVEN** a vault,
- **WHEN** `GET /api/v1/internal-engine-config` is read,
- **THEN** its upkeep block names exactly `aggregate` and `distil`,
  each with a switch, a chosen interval and a default interval,
- **AND** a switch and an interval written for one of them are what the next
  read reports for it.

### Requirement: Show and change the memory passes on the Memory page
The web UI MUST show and change each unattended pass on the page whose content it upkeeps,
not in Settings: an **Automatic** control in the page header reads "Automatic · hourly" (or
the chosen interval; "Automatic · off" while switched off) and opens a popover. Edits MUST save
on their own — a switch on toggle, an interval on selection — through
`PUT /api/v1/internal-engine-config/upkeep`, one pass per request, and the interval's default
option MUST name the real number.

- **Memory** — the popover's one switch, "Read memory automatically", MUST switch `aggregate`
  and `distil` together (two writes, one per pass) and read as on only while both are on; its
  interval is the `aggregate` interval, the cadence at which the agents' memory is read, while
  `distil` keeps its own slower interval and turns what was read into notes. The popover shows "Last
  read 14 min ago · next in 46 min" for `aggregate`. The control appears on the partitions page
  and on a partition's page, because reading needs no model.

The Knowledge page carries no Automatic control, because its sweep has no switch or interval to
set.

#### Scenario: the memory popover switches reading and distilling together
- **GIVEN** aggregation and distillation both switched on, aggregation read 14 minutes ago and due
  again in 46 minutes
- **WHEN** the Memory header's Automatic control is opened and the operator switches it off and
  then picks an interval
- **THEN** the popover shows "Read memory automatically", the interval and the last/next line,
  switching it off writes `aggregate` off and `distil` off as two requests, and the interval
  writes the `aggregate` interval alone (TypeScript acceptance test)

### Requirement: Change the speech-to-text model on its own route
`PUT /api/v1/internal-engine-config/transcribe-model` (`null` or empty clears
it, which stops transcription) MUST change the speech-to-text model and leave
the rest of the document alone, audited like any other write to it (see "Audit
every write to the engine settings"). Every model call Coffer makes —
speech-to-text transcription — MUST run under one fixed time limit that is not
a setting, because an unbounded call stalls the turn that is waiting on it.

#### Scenario: the speech-to-text model changes without touching the rest of the row
- **GIVEN** a settings document with a pass switched off,
- **WHEN** the operator sets the speech-to-text model through the route,
- **THEN** only the model changes and the pass's switch is left as it stood,
- **AND** the write is recorded as an `internal_engine_model_set` audit entry.

### Requirement: Show the speech-to-text pair in Settings › General
Settings › General MUST carry a **Speech-to-text** section that shows and changes
what Coffer transcribes voice with. Edits MUST save on their own — a picker on
selection — with no Save button. The section MUST NOT carry the unattended
passes' switches and intervals: those are shown and changed on the Memory page,
whose content the passes upkeep.

- **Speech to text** — the connection flagged `transcribe_default` and its own
  model, saying plainly that with either half unset Coffer transcribes nothing
  and the agent receives the audio file.
- **Test** — beside the picker, one `POST /api/v1/models/list-models` for the
  chosen connection, which passes when the listing names the chosen model,
  because a chat probe fails on a speech model even on a healthy endpoint. A
  failure MUST show the endpoint's error inline and change nothing. The picker
  reads as failing until a test of the same pair passes, and choosing another
  connection or model drops the result; a picker with either half unset reads
  as not set.

#### Scenario: the speech-to-text section shows and changes the pair
- **GIVEN** Settings › General rendered with a connection flagged `transcribe_default`,
- **WHEN** the section renders and the operator picks a speech-to-text model,
- **THEN** the Speech to text picker shows the chosen connection and model, the edit saves on its own without a Save button, and only the edited value is written,
- **AND** the section shows no upkeep switch or interval (TypeScript acceptance test).

#### Scenario: a failed speech-to-text test leaves the pair as it was
- **GIVEN** a speech-to-text model chosen on a connection whose endpoint is unreachable
- **WHEN** the operator chooses Test beside the Speech to text picker
- **THEN** the picker reads as failing with the error inline
- **AND** no write is sent and the chosen pair stays as it was (TypeScript acceptance test)
