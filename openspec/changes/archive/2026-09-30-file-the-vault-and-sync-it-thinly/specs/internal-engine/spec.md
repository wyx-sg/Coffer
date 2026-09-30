## MODIFIED Requirements

### Requirement: Keep the engine's settings in one global row
The system MUST keep Coffer's own operating settings — the engine model, the
speech-to-text model, the bound on one model call, each unattended pass's
switch and optional interval, and the curation owner — in one vault document at
one fixed path, `state/settings/internal-engine.json` ([vault-storage](../vault-storage/spec.md) "Keep every vault document a JSON object that preserves what it does not know"),
so a second copy is unrepresentable whatever writes it. The time of the last
write is not in the document, because two machines stamping it would conflict
on every edit: it is this machine's own record, `~/.coffer/local/engine.json`.
An absent key or `null` means "the built-in default" for an interval and for
the bound, "unchosen" for a model, and "no owner named" for the curation owner.

#### Scenario: a second engine settings row is unrepresentable
- **GIVEN** the internal-engine settings document exists,
- **WHEN** the settings are written again,
- **THEN** the vault still holds exactly one settings document, at
  `state/settings/internal-engine.json`, so "which settings does the engine
  use?" cannot become a question with two answers.

### Requirement: Report and set the engine model over HTTP
`GET /api/v1/internal-engine-config` MUST report the engine model, the
speech-to-text model, the chosen call bound beside the default that applies
while none is chosen, when this machine last wrote the settings, and every pass's switch,
chosen interval and default interval. `PUT /api/v1/internal-engine-config` MUST
set the model, treating a blank or null value as clearing it.

#### Scenario: choose the model the internal engine runs on
- **GIVEN** a connection is the internal default,
- **WHEN** the operator sets a model on the global internal-engine config
  (`PUT /api/v1/internal-engine-config`),
- **THEN** `GET /api/v1/internal-engine-config` returns that model, an
  `internal_engine_model_set` audit entry is recorded, and
  `resolve_internal_connection()` pairs the chosen model with the resolved
  internal-default connection.

### Requirement: Resolve the engine's connection and model together
`resolve_internal_connection()` MUST return the connection flagged
`internal_default` ([provider-switching](../provider-switching/spec.md) "Keep at most one internal default connection") paired with the engine model,
or `None` when no connection is flagged or no model is chosen. The connection
carries no model of its own to fall back to, so the two halves resolve together
or not at all.

#### Scenario: pair the flagged connection with the chosen engine model
- **GIVEN** two connections, one flagged `internal_default`, and an engine model
  chosen in the settings,
- **WHEN** a consumer asks the engine which connection to run on,
- **THEN** it is answered with the flagged connection's endpoint and protocol
  paired with the chosen engine model — never the other connection,
- **AND** a model chosen after wiring is the one the next answer carries.

### Requirement: Audit every write to the engine settings
Every write to the settings MUST record an `internal_engine_model_set` audit
entry naming the actor and carrying the values after the write. A change another
machine made arrives as a sync commit to the settings document, and is as visible
in that document's history as one made here ([vault-storage](../vault-storage/spec.md) "Show, compare and restore any version of a vault file").

#### Scenario: record every settings write with its actor and values
- **GIVEN** the internal-engine settings,
- **WHEN** the model, one pass's switch, the call bound and the speech-to-text
  model are each written by an actor,
- **THEN** each write records an `internal_engine_model_set` audit entry naming
  that actor,
- **AND** each entry's details carry the value as it stands after that write.

### Requirement: Carry a switch and interval for each unattended pass
The same document MUST carry a switch and an interval for each of the three passes
Coffer runs on its own behalf — `aggregate` (reads the agents' own memory into
the derived tree, [memory](../memory/spec.md) "Aggregate on an interval and on demand"), `distil` (lets the model rewrite that
derived digest, [memory](../memory/spec.md) "Distil incrementally in two stages") and `curate` (derives the knowledge documents
agents read from the sources a person writes, [knowledge](../knowledge/spec.md) "Curate through a fenced four-tool pass"). This
capability owns only whether and how often they run, one switch and interval
per pass rather than per target.

#### Scenario: report a switch and interval for each of the three passes
- **GIVEN** a vault,
- **WHEN** `GET /api/v1/internal-engine-config` is read,
- **THEN** its upkeep block names exactly `aggregate`, `distil` and `curate`,
  each with a switch, a chosen interval and a default interval,
- **AND** a switch and an interval written for one of them are what the next
  read reports for it.

### Requirement: Converge the settings as the `settings` state area
The settings MUST travel as sync state area `settings`, document
`state/settings/internal-engine.json` ([vault-sync](../vault-sync/spec.md) "Converge shared state areas"), carrying the model, the call
bound, the speech-to-text model, the curation owner and every pass's switch and
interval — Coffer's passes behave the same everywhere only when they run on the
same model, switching a rewriter off is exactly the decision a second machine
must not be left out of, and the owner only means anything when every machine
holds the same one. The document is the
settings, with no second copy on this machine: a key it does not carry MUST read
as that key's default, and a key this build does not know MUST survive every
write this build makes.

#### Scenario: the engine's settings converge and a deletion means the defaults
- **GIVEN** a machine that has chosen nothing, whose settings read as the defaults
  with no settings document in the vault,
- **WHEN** it chooses an engine model, switches `curate` off with an interval and
  sets the call bound,
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
- **AND** once a non-default model is chosen, exactly one
  `internal-engine` document is published.

### Requirement: Reset to the defaults when the document is deleted
Deleting the document MUST put this machine on the defaults at once, with
nothing written here: the absence of the document is the defaults. The deletion
is itself the commit that removed the document — a sync commit naming the
machine that made it, when it came from another one.

#### Scenario: deleting the settings document resets this machine to the defaults
- **GIVEN** a machine holding a chosen model, a switched-off pass, a chosen
  bound and a chosen speech-to-text model,
- **WHEN** a sync commit deletes the settings document,
- **THEN** every one of those returns to its default,
- **AND** nothing is written back, so the vault holds no settings document.

### Requirement: Carry the bound on one model call
The settings document MUST carry the bound on ONE call to Coffer's own model, where `NULL`
means the built-in default. The default MUST live in one place in the code
rather than be copied into each vault, exactly as an unchosen interval's does
(see "Report an unchosen interval beside its default"), so raising it later
reaches every vault that never chose. `GET /api/v1/internal-engine-config` MUST
report the chosen bound and that default together, and so MUST
`coffer config get engine.timeout` and `coffer config list engine.`.

#### Scenario: bound how long one call to Coffer's own model may take
- **GIVEN** the engine has a connection and a model, and no bound has been
  chosen,
- **WHEN** the operator reads the bound, sets one, and returns it to the default
  (`PUT /api/v1/internal-engine-config/timeout`, or `coffer config get | set | unset
  engine.timeout`),
- **THEN** an unchosen bound is reported as unchosen beside the built-in default
  that applies, a chosen one is what every internal model call runs under — the
  distil pass, knowledge ingestion's description step, curation's agentic turns
  and speech-to-text alike — a value outside the permitted range is refused by
  the route and by the CLI with the same error, and a value already stored
  outside that range is clamped by a background pass rather than taking it down.

### Requirement: Transcribe speech on its own connection and model
The settings document MUST carry the speech-to-text model, separate from the engine model. The
connection it runs on MUST be the one flagged `transcribe_default`
([provider-switching](../provider-switching/spec.md) "Keep an independent speech-to-text default"), and the pair MUST resolve exactly as the
engine's does: both halves or `None`. There MUST be NO fallback between the two
pairs — an unflagged connection or an unchosen speech-to-text model MUST NOT
cause the engine's own connection or model to be used for transcription, but
MUST answer `None`, which [chat](../chat/spec.md) "Transcribe audio attachments when transcription is configured" turns into handing the agent the audio
file with nothing uploaded. The model MUST NOT be read from the environment: the
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
  handed to the agent as a file rather than uploaded; the engine's own
  `internal_default` connection is never borrowed for it; and moving the flag
  drops the speech-to-text model unless the newly flagged connection curates it,
  leaving the engine model untouched.

## REMOVED Requirements

### Requirement: Leave settings alone for keys an incoming document omits
**Reason**: There is no copy of the settings on this machine for an absent key to leave alone: the vault document is the settings, so a key it does not carry reads as its default, and a key a newer build wrote survives this build's writes.
**Migration**: "Converge the settings as the `settings` state area".
