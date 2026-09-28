## ADDED Requirements

### Requirement: Keep every engine setting under one key namespace
Every setting this capability owns MUST be read and changed on the command line through the
generic `coffer config list|get|set|unset` command of
[resource-framework](../resource-framework/spec.md) (one key registry, typed validation,
`unset` returns a key to its default, `config list` shows each key's type, default and help).
The keys MUST be `engine.provider` (the connection the engine borrows, whose flag is
[provider-switching](../provider-switching/spec.md) "Set the internal-engine default"),
`engine.model`, `engine.timeout`, `engine.curate_owner`, `engine.upkeep.<pass>.enabled` and
`engine.upkeep.<pass>.interval` for each of `aggregate`, `distil` and `curate`, plus
`transcribe.provider` (the connection flagged by
[provider-switching](../provider-switching/spec.md) "Keep an independent speech-to-text default")
and `transcribe.model`. Each key MUST have the same effect, the same refusals and the same audit
entry as the route that stores it; the routes under `/api/v1/internal-engine-config` are
unchanged. `coffer engine` is not a command.

#### Scenario: the command line lists every engine setting under one namespace
- **GIVEN** the daemon is running with a connection flagged as the internal default, a chosen
  engine model and no other engine setting chosen,
- **WHEN** the operator runs `coffer config list engine.` and `coffer config list transcribe.`,
- **THEN** the first lists `engine.provider`, `engine.model`, `engine.timeout`,
  `engine.curate_owner` and an `enabled` and an `interval` key for each of `aggregate`, `distil`
  and `curate`, each with its current value, its default and its help,
- **AND** the second lists `transcribe.provider` and `transcribe.model`, and
  `coffer engine model show` is refused as an unknown command.

## MODIFIED Requirements

### Requirement: Show, set and clear the engine model from the CLI
A CLI MUST show, set and clear the engine model — `coffer config get engine.model`,
`coffer config set engine.model <id>` and `coffer config unset engine.model` — with the same effect
and the same audit entry as the HTTP route, so a terminal-only operator can see and change which
model Coffer thinks with. `unset` leaves the model unchosen, which makes every internal pass a clean
no-op (see "Make every internal pass a clean no-op when nothing is configured").

#### Scenario: the command line shows and sets the engine model
- **GIVEN** the daemon is running and a connection is the internal default,
- **WHEN** the operator runs `coffer config set engine.model <id>`, then
  `coffer config get engine.model`, then `coffer config unset engine.model`,
- **THEN** each has the same effect as the HTTP route — the model is stored,
  reported and cleared — and the audit entry is the same one the route records.

### Requirement: List and change each unattended pass from the CLI
A CLI MUST list every pass's switch, chosen interval and default interval —
`coffer config list engine.upkeep. [--json]`, printing the default that runs when none is chosen
so the terminal shows what the page shows — and change one value of one pass per invocation —
`coffer config set engine.upkeep.<pass>.enabled on|off` and
`coffer config set engine.upkeep.<pass>.interval <seconds>`, where `<pass>` is one of `aggregate`,
`distil`, `curate`. `coffer config unset engine.upkeep.<pass>.interval` MUST return that pass to its
default interval, and `coffer config unset engine.upkeep.<pass>.enabled` MUST switch it back on, the
shipped state (see "Ship every unattended pass switched on"). It MUST refuse an interval below the
floor with the same error the route gives, and a key naming a pass Coffer does not run MUST be
refused as an unknown key before any route is called.

#### Scenario: the command line lists and changes each unattended pass
- **GIVEN** the daemon is running,
- **WHEN** the operator runs `coffer config list engine.upkeep. --json`, then
  `coffer config set engine.upkeep.curate.enabled off`, then
  `coffer config set engine.upkeep.distil.interval 900`, then
  `coffer config unset engine.upkeep.distil.interval`,
- **THEN** the listing is machine-readable and names each pass's switch, its
  chosen interval and the default that runs while none is chosen; each `set`
  changes one value of one pass only; `unset` returns `distil` to its default interval;
  and an interval below the floor or a key naming an unknown pass is refused,
  the first with the same error the route gives.

### Requirement: Carry the bound on one model call
The row MUST carry the bound on ONE call to Coffer's own model, where `NULL`
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
effects, refusals and audit entries as the routes. Settings → Coffer's model MUST show
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
- **WHEN** the operator runs `coffer config get engine.curate_owner`, then
  `coffer config set engine.curate_owner this`, then
  `coffer config get engine.curate_owner --json`, then
  `coffer config unset engine.curate_owner`,
- **THEN** the first prints that no owner is named and the pass runs wherever
  the vault is read, `set` names this machine and prints it as this machine,
  the JSON carries this machine's id with state `self`, and `unset` prints the
  unowned line again,
- **AND** the settings route reports the owner that each step left.
