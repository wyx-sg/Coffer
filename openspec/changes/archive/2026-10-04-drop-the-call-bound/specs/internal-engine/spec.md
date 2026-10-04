## MODIFIED Requirements

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

## ADDED Requirements

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

## REMOVED Requirements

### Requirement: Carry the bound on one model call

### Requirement: Run every internal model call under the bound

### Requirement: Refuse an out-of-range bound at a surface and clamp it in a pass

### Requirement: Change the bound and the speech-to-text model one value at a time

### Requirement: Show the speech-to-text pair and the call bound in Settings › General
