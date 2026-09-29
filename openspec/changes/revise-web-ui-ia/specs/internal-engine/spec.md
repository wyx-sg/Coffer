## REMOVED Requirements

### Requirement: Show and change the engine in Settings → Coffer's model
**Reason**: Coffer's model leaves Settings for a tab on the Model providers page, beside the
providers it is chosen from.
**Migration**: See "Show and change the engine on the Coffer's model tab". The acceptance marker
for "Settings → Coffer's model shows and changes both halves" moves to "the Coffer's model tab
shows and changes both halves".

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
effects, refusals and audit entries as the routes. Model providers → Coffer's model MUST show
and change both.

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
- Model providers → Coffer's model MUST show the owner on a line under the `curate` row, with
  an action that takes the pass over for this machine and one that clears the
  owner after a confirmation.

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

### Requirement: Show and change the engine on the Coffer's model tab
The Coffer's model tab of the Model providers page
([web-ui](../web-ui/spec.md) "Show Coffer's model beside Model providers") MUST show and change
both halves: the connection and model the engine runs on, and each pass's switch and interval
with its default named rather than left blank. Edits MUST save on their own — the switch on toggle,
the interval on selection — with no Save button.

The tab is three cards, because all three configure Coffer's own machinery
rather than anything served to an agent:

- The model card picks the internal-default connection and, from that
  connection's curated `text` models or its probed catalogue, the engine model,
  and carries the call bound beside it, named with the default that applies
  while the operator has chosen none; a bound outside the permitted range is
  reported where it was typed rather than saved.
- The speech-to-text card is the same pair for the connection flagged
  `transcribe_default` and its own model, saying plainly that with either half
  unset Coffer transcribes nothing and the agent receives the audio file.
- The upkeep card is one row per pass: a switch, an interval select whose
  default option names the real number, and — for `curate` alone — a line
  saying it is Coffer's own model deriving documents from the user's sources,
  and the curation owner line under that row (see "Report and change the
  curation owner from every surface").

#### Scenario: the Coffer's model tab shows and changes both halves
- **GIVEN** the Model providers → Coffer's model tab is rendered with an internal-default
  connection and the three passes,
- **WHEN** the page renders and the operator toggles one pass and picks an
  interval,
- **THEN** the model card shows the chosen connection and model, the upkeep card
  shows one row per pass with the default named rather than blank, each edit
  saves on its own without a Save button, and only the toggled pass is written
  (TypeScript acceptance test).
