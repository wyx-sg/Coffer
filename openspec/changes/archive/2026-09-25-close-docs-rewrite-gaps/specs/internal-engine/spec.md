## REMOVED Requirements

### Requirement: Show and change the engine in Settings → Engine
**Reason**: The page is labelled "Coffer's model" in the app; the requirement and its scenario take that name in "Show and change the engine in Settings → Coffer's model", which carries the same rule unchanged. A scenario cannot be renamed inside a MODIFIED block, so the rename is a remove-and-add.
**Migration**: The TypeScript acceptance marker moves to the scenario "Settings → Coffer's model shows and changes both halves".

## ADDED Requirements

### Requirement: Show and change the engine in Settings → Coffer's model
Settings → Coffer's model MUST show and change both halves: the connection and model the
engine runs on, and each pass's switch and interval with its default named
rather than left blank. Edits MUST save on their own — the switch on toggle,
the interval on selection — with no Save button.

The page is three cards, because all three configure Coffer's own machinery
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

#### Scenario: Settings → Coffer's model shows and changes both halves
- **GIVEN** the Settings → Coffer's model page is rendered with an internal-default
  connection and the three passes,
- **WHEN** the page renders and the operator toggles one pass and picks an
  interval,
- **THEN** the model card shows the chosen connection and model, the upkeep card
  shows one row per pass with the default named rather than blank, each edit
  saves on its own without a Save button, and only the toggled pass is written
  (TypeScript acceptance test).

## MODIFIED Requirements

### Requirement: Change the bound and the speech-to-text model one value at a time
`PUT /api/v1/internal-engine-config/timeout` (`null` returns to the built-in
default; outside the floor–ceiling range is refused, not clamped) and
`PUT /api/v1/internal-engine-config/transcribe-model` (`null` or empty clears
it, which stops transcription) MUST each change one value and leave the rest of
the row alone, audited like any other write to it (see "Audit every write to
the engine settings"). A CLI MUST show, set and return-to-default the bound —
`coffer engine timeout show | set <seconds> | default`, where `timeout show`
prints the chosen bound beside the default and `timeout default` returns to the
built-in one — and show, set and clear the speech-to-text model —
`coffer engine transcribe-model show | set <id> | clear` — with the same
effects, refusals and audit entries as the routes. Settings → Coffer's model MUST show
and change both.

#### Scenario: the bound and the speech-to-text model change one value at a time
- **GIVEN** a settings row with a chosen engine model and a pass switched off,
- **WHEN** the operator sets the bound and the speech-to-text model through the
  routes, and then again through `coffer engine timeout set` and
  `coffer engine transcribe-model set`,
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
- A CLI MUST show, set and clear the owner — `coffer engine curate-owner show
  [--json] | set [<machine_id>] | clear` — where `set` with no id names this
  machine, `show` and `set` print which of the four states the owner is in,
  `show --json` carries `curate_owner_machine_id`, `state` and
  `this_machine_id`, and an owner no machine in a non-empty registry claims is
  printed as the fault it is together with how to take the pass back.
- Settings → Coffer's model MUST show the owner on a line under the `curate` row, with
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
- **WHEN** the operator runs `coffer engine curate-owner show`, then
  `coffer engine curate-owner set` with no id, then
  `coffer engine curate-owner show --json`, then
  `coffer engine curate-owner clear`,
- **THEN** the first prints that no owner is named and the pass runs wherever
  the vault is read, `set` names this machine and prints it as this machine,
  the JSON carries this machine's id with state `self`, and `clear` prints the
  unowned line again,
- **AND** the settings route reports the owner that each step left.
