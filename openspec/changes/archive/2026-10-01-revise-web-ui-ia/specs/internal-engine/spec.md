## REMOVED Requirements

### Requirement: Show and change the engine in Settings → Coffer's model
**Reason**: Settings no longer has a Coffer's model tab; Coffer's model is a section of
Settings › General, with a provider-then-model picker for the engine and for speech to text.
**Migration**: See "Show and change Coffer's model in Settings › General". The acceptance marker
for "Settings → Coffer's model shows and changes both halves" moves to "the general tab's
coffer's model section shows and changes both halves".

## MODIFIED Requirements

### Requirement: Change the bound and the speech-to-text model one value at a time
`PUT /api/v1/internal-engine-config/timeout` (`null` returns to the built-in
default; outside the floor–ceiling range is refused, not clamped) and
`PUT /api/v1/internal-engine-config/transcribe-model` (`null` or empty clears
it, which stops transcription) MUST each change one value and leave the rest of
the row alone, audited like any other write to it (see "Audit every write to
the engine settings"). A CLI MUST show, set and return-to-default the bound —
`coffer config get | set <seconds> | unset engine.timeout`, where `get` prints the chosen bound
beside the default and `unset` returns to the built-in one — and show, set and clear the
speech-to-text model — `coffer config get | set <id> | unset transcribe.model` — with the same
effects, refusals and audit entries as the routes. The Coffer's model section of Settings ›
General MUST show and change both.

#### Scenario: the bound and the speech-to-text model change one value at a time
- **GIVEN** a settings row with a chosen engine model and a pass switched off,
- **WHEN** the operator sets the bound and the speech-to-text model through the
  routes, and then again through `coffer config set engine.timeout` and
  `coffer config set transcribe.model`,
- **THEN** each write changes only its own value and the engine model and the
  pass's switch are left as they stood,
- **AND** every one of those writes is recorded as an `internal_engine_model_set`
  audit entry.

### Requirement: Report and change the curation owner from every surface
The settings row MUST carry the curation owner — the one machine allowed to run
the `curate` pass, or none — and every surface that shows the engine MUST report
and change it, applying the four-state rule of
[vault-sync](../vault-sync/spec.md) "Report and change the rewriter's owner":

- `GET /api/v1/internal-engine-config` MUST report the owner as
  `curate_owner_machine_id`, the raw machine id or `null` while none is named.
  The settings read MUST NOT resolve it against the machine registry; a reader
  resolves it against `GET /api/v1/sync/machines`.
- `PUT /api/v1/internal-engine-config/curation-owner` MUST set the owner from
  `{"machine_id": …}` and leave the rest of the row alone; `null` or a blank id
  MUST clear it. The id MUST NOT be validated against the registry, because a
  vault that has never converged has no registry and must still be able to name
  its own machine. The write MUST be audited like any other write to the row
  (see "Audit every write to the engine settings").
- A CLI MUST show, set and clear the owner through the key `engine.curate_owner` —
  `coffer config get engine.curate_owner [--json]`,
  `coffer config set engine.curate_owner this|<machine_id>` and
  `coffer config unset engine.curate_owner`, whose default is no owner — where `this` names this
  machine, `get` and `set` print which of the four states the owner is in, `get --json` carries
  `curate_owner_machine_id`, `state` and `this_machine_id`, and an owner no machine in a
  non-empty registry claims is printed as the fault it is together with how to take the pass
  back.
- The Knowledge page's Automatic popover MUST show the owner as "Curation runs on" once the
  vault's registry (`GET /api/v1/sync/machines`) names more than one machine, with a picker of
  the known machines that names a new owner; an owner no known machine claims MUST be shown
  even while the registry names one machine or none, and read as the fault it is.

#### Scenario: the route names and clears the curation owner
- **GIVEN** the internal-engine settings row with a chosen engine model and no
  curation owner,
- **WHEN** the operator names a machine through
  `PUT /api/v1/internal-engine-config/curation-owner`, and then sends `null`,
- **THEN** the first answer and the next `GET /api/v1/internal-engine-config`
  report that machine id as `curate_owner_machine_id` while the engine model
  stays as it was, and the second answer reports `null`,
- **AND** each write records an `internal_engine_model_set` audit entry naming
  the actor, whose details carry the owner as it stands after that write.

#### Scenario: the command line shows, sets and clears the curation owner
- **GIVEN** the daemon is running on a vault that has named no curation owner,
- **WHEN** the operator runs `coffer config get engine.curate_owner`, then
  `coffer config set engine.curate_owner this`, then
  `coffer config get engine.curate_owner --json`, then
  `coffer config unset engine.curate_owner`,
- **THEN** the first prints that no owner is named and the pass runs wherever
  the vault is read, `set` names this machine and prints it as this machine,
  the JSON carries this machine's id with state `self`, and `unset` prints the
  unowned line again,
- **AND** the settings route reports the owner that each step left.

## ADDED Requirements

### Requirement: Show and change Coffer's model in Settings › General
The Coffer's model section of Settings › General
([web-ui](../web-ui/spec.md) "Choose Coffer's model in Settings › General") MUST show and change
what Coffer's own machinery runs on: the connection and model the engine runs on, the
connection and model speech to text runs on. Edits MUST save on their own — a picker on
selection — with no Save button. The section MUST NOT carry the unattended passes' switches and
intervals or the curation owner: those are shown and changed on the Knowledge and Memory pages,
whose content the passes upkeep.

- **Engine model** — a picker that chooses the connection flagged `internal_default` and then,
  from that connection's curated `text` models or its probed catalogue, the engine model; the
  call bound sits beside it, named with the default that applies while the operator has chosen
  none, and a bound outside the permitted range is reported where it was typed rather than
  saved.
- **Speech to text** — the same pair for the connection flagged `transcribe_default` and its
  own model, saying plainly that with either half unset Coffer transcribes nothing and the agent
  receives the audio file.
- **Test** — beside each picker, one probe of the chosen pair: for the engine one
  `POST /api/v1/models/test-connection` with the chosen connection and model; for speech to
  text one `POST /api/v1/models/list-models` for the chosen connection, which passes when the
  listing names the chosen model, because a chat probe fails on a speech model even on a
  healthy endpoint. A failure MUST show the endpoint's error inline and change nothing. A
  picker whose last test in this visit failed reads as failing until a test of the same pair
  passes, and choosing another connection or model drops the result; a picker with either half
  unset reads as not set, and for the engine says that no internal pass runs (see "Make every
  internal pass a clean no-op when nothing is configured").

#### Scenario: the general tab's coffer's model section shows and changes both halves
- **GIVEN** Settings › General rendered with an internal-default connection,
- **WHEN** the section renders and the operator picks an engine model and a speech-to-text model,
- **THEN** the Engine model and Speech to text pickers show the chosen connections and models,
  each edit saves on its own without a Save button, only the edited value is written, and the
  section shows no upkeep switch, interval or curation owner (TypeScript acceptance test).

#### Scenario: a failed test leaves coffer's model as it was
- **GIVEN** a speech-to-text model chosen on a connection whose endpoint is unreachable
- **WHEN** the operator chooses Test beside the Speech to text picker
- **THEN** the picker reads as failing with the error inline
- **AND** no write is sent and the chosen pair stays as it was
