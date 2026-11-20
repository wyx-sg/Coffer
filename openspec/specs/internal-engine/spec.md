# Internal Engine

## Purpose

Coffer makes one kind of model call of its own: it transcribes a voice message. The
internal engine is the settings that hold what that call needs: the speech-to-text
model. It owns one settings document per vault, the surfaces that show and change it
(`/api/v1/internal-engine-config` and the Speech-to-text section of Settings ›
General), and its convergence between machines. The name is kept although there is no
longer an engine model: it is the identifier inbound links and the route family resolve.

Speech-to-text has its own connection (flagged `transcribe_default`) and its own
model, because the gateway that answers a chat completion commonly serves no
transcription endpoint at all. There is no engine model, no curate pass, no curation
owner machine, no unattended pass with a switch or interval, and no internal default
connection: judgement over knowledge and over memory is the person's own coding
agent's, reached through a Tidy hand-off ([knowledge](../knowledge/spec.md),
[memory](../memory/spec.md)). Chat's voice transcription supplies its own prompt and
owns its own results.

The speech-to-text call runs under one fixed 60 second limit: it is the only
model call Coffer makes, so the limit is a constant and not a setting. Keys an
older build wrote into the document (`model`, `curate_owner_machine_id`,
`model_timeout_s`, `upkeep`) are ignored on read and dropped on the next write.

Out of scope: creating, editing, activating or flagging a connection (`transcribe_default`
is provider-switching's field and route, `POST /api/v1/providers/{uid}/transcribe-default`);
the knowledge sweep, which has no switch or interval; and any model registry. Coffer runs
as a single-user tool behind the existing `X-Coffer-Token` gate.

## Requirements

### Requirement: Keep the engine's settings in one vault document
The system MUST keep Coffer's own operating settings — the speech-to-text model —
in one vault document at one fixed path,
`state/settings/internal-engine.json` ([vault-storage](../vault-storage/spec.md) "Keep every vault document a JSON object that preserves what it does not know"),
so a second copy is unrepresentable whatever writes it. The time of the last
write is not in the document, because two machines stamping it would conflict
on every edit: it is this machine's own record, `~/.coffer/local/engine.json`.
An absent key or `null` means the speech-to-text model is unchosen.

#### Scenario: a second engine settings document is unrepresentable
- **GIVEN** the internal-engine settings document exists,
- **WHEN** the settings are written again,
- **THEN** the vault still holds exactly one settings document, at
  `state/settings/internal-engine.json`, so "which settings does the engine
  use?" cannot become a question with two answers.

### Requirement: Audit every write to the engine settings
Every write to the settings MUST record an `internal_engine_model_set` audit
entry naming the actor and carrying the value after the write, the speech-to-text
model (`transcribe_model`). A change another
machine made arrives as a sync commit to the settings document, and is as visible
in that document's history as one made here ([vault-storage](../vault-storage/spec.md) "Keep the vault a git repository whether or not it syncs").

#### Scenario: record every settings write with its actor and values
- **GIVEN** the internal-engine settings,
- **WHEN** the speech-to-text model is written by an actor,
- **THEN** the write records an `internal_engine_model_set` audit entry naming
  that actor,
- **AND** the entry's details carry the value as it stands after the write.

### Requirement: Converge the settings as the `settings` state area
The settings MUST travel as sync state area `settings`, document
`state/settings/internal-engine.json` ([vault-sync](../vault-sync/spec.md) "Converge shared state areas"), carrying the speech-to-text
model, so every machine transcribes with the same choice. The document is the
settings, with no second copy on this machine: a key it does not carry MUST read
as that key's default, and a key this build does not know MUST survive every
write this build makes.

#### Scenario: the engine's settings converge and a deletion means the defaults
- **GIVEN** a machine that has chosen nothing, whose settings read as the defaults
  with no settings document in the vault,
- **WHEN** it chooses a speech-to-text model,
- **THEN** `state/settings/internal-engine.json` carries that decision and
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
- **GIVEN** a machine holding a chosen speech-to-text model,
- **WHEN** a sync commit deletes the settings document,
- **THEN** the model reads as unchosen again,
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

### Requirement: Report the engine settings over HTTP
`GET /api/v1/internal-engine-config` MUST report the speech-to-text model and when
this machine last wrote the settings. The route family MUST carry no model for
Coffer itself, because Coffer runs no work over a model of its own, and
no per-call time limit, because the one model call Coffer makes runs under a
fixed limit.

#### Scenario: read the engine settings
- **GIVEN** a vault whose settings hold a speech-to-text model,
- **WHEN** `GET /api/v1/internal-engine-config` is read,
- **THEN** it returns that speech-to-text model and the time this machine last wrote the settings,
- **AND** the answer carries no engine model, no curation owner and no upkeep block.

### Requirement: Ignore retired keys in the settings document
The system MUST accept a settings document that still carries the keys `model`,
`curate_owner_machine_id`, `model_timeout_s` or `upkeep`, and MUST ignore them on read: they change no setting, raise no error and appear in no answer. The next
write of the document MUST drop them. A key this build has never known MUST
still survive a write, so only the retired keys are removed.

#### Scenario: ignore retired keys when the settings are read
- **GIVEN** a settings document holding `model`, `curate_owner_machine_id`, `model_timeout_s`, an `upkeep` block and a speech-to-text model,
- **WHEN** the settings are read,
- **THEN** the speech-to-text model is reported as stored and no answer carries a time limit,
- **AND** nothing reports the retired keys.

#### Scenario: drop retired keys on the next write
- **GIVEN** a settings document holding the retired keys and a key a newer build wrote,
- **WHEN** the operator changes one value through any settings route,
- **THEN** the rewritten document holds no `model`, no `curate_owner_machine_id`, no `model_timeout_s` and no `upkeep`,
- **AND** the newer build's key is still in the document.

### Requirement: Change the speech-to-text model on its own route
`PUT /api/v1/internal-engine-config/transcribe-model` (`null` or empty clears
it, which stops transcription) MUST change the speech-to-text model and leave
the rest of the document alone, audited like any other write to it (see "Audit
every write to the engine settings"). Every model call Coffer makes —
speech-to-text transcription — MUST run under one fixed time limit that is not
a setting, because an unbounded call stalls the turn that is waiting on it.

#### Scenario: the speech-to-text model changes without touching the rest of the row
- **GIVEN** a settings document holding a key a newer build wrote,
- **WHEN** the operator sets the speech-to-text model through the route,
- **THEN** only the model changes and the newer build's key is left as it stood,
- **AND** the write is recorded as an `internal_engine_model_set` audit entry.

### Requirement: Show the speech-to-text pair in Settings › General
Settings › General MUST carry a **Speech-to-text** section that shows and changes
what Coffer transcribes voice with. Edits MUST save on their own — a picker on
selection — with no Save button.

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
- **AND** nothing else in the document is written (TypeScript acceptance test).

#### Scenario: a failed speech-to-text test leaves the pair as it was
- **GIVEN** a speech-to-text model chosen on a connection whose endpoint is unreachable
- **WHEN** the operator chooses Test beside the Speech to text picker
- **THEN** the picker reads as failing with the error inline
- **AND** no write is sent and the chosen pair stays as it was (TypeScript acceptance test)

