## RENAMED Requirements

- FROM: `### Requirement: Keep the engine's settings in one global row`
- TO: `### Requirement: Keep the engine's settings in one vault document`

## MODIFIED Requirements

### Requirement: Keep the engine's settings in one vault document
The system MUST keep Coffer's own operating settings — the engine model, the
speech-to-text model, the bound on one model call, each unattended pass's
switch and optional interval, and the curation owner — in one vault document at
one fixed path, `state/settings/internal-engine.json` ([vault-storage](../vault-storage/spec.md) "Keep every vault document a JSON object that preserves what it does not know"),
so a second copy is unrepresentable whatever writes it. The time of the last
write is not in the document, because two machines stamping it would conflict
on every edit: it is this machine's own record, `~/.coffer/local/engine.json`.
An absent key or `null` means "the built-in default" for an interval and for
the bound, "unchosen" for a model, and "no owner named" for the curation owner.

#### Scenario: a second engine settings document is unrepresentable
- **GIVEN** the internal-engine settings document exists,
- **WHEN** the settings are written again,
- **THEN** the vault still holds exactly one settings document, at
  `state/settings/internal-engine.json`, so "which settings does the engine
  use?" cannot become a question with two answers.

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
The passes that write only derived files (`aggregate`, `distil`) MUST ship ON,
because deleting and re-running reproduces what they write — and `curate` MUST
ship ON too: it derives the knowledge documents agents read from sources it
never rewrites, it never reverts a person's edit, and a vault where it never
runs has its uploads and notes waiting unmerged in the inbox forever, so it
cannot ship OFF.

#### Scenario: a fresh vault runs every unattended pass
- **GIVEN** a fresh vault where nobody has touched the engine settings,
- **WHEN** the settings are read, and when the document is first written by a model
  choice alone,
- **THEN** `aggregate`, `distil` and `curate` are all switched on.

### Requirement: Run every internal model call under the bound
EVERY call the internal engine makes MUST run under that bound — the distil
pass's routing and writing, knowledge ingestion's description step, curation's
agentic turns and speech-to-text alike — because an unbounded call is how an
unattended pass stops being unattended. Curation's bound MUST be applied to the
model CLIENT rather than around the call, because its loop is one `await` from
the outside and wrapping it could only bound the whole conversation or nothing.
The bound MUST be read per call rather than captured at wiring time, so a
change — made here or converged from another machine — takes effect without a
daemon restart.

#### Scenario: every internal model call reads the current bound
- **GIVEN** a chosen bound on the settings document,
- **WHEN** knowledge ingestion describes a document, a voice message is
  transcribed, and a chat model is built for an agentic loop,
- **THEN** the description call and the transcriber run under the chosen bound
  and the chat model's client carries it,
- **AND** after the bound is changed, the next call runs under the new value
  with nothing rewired.

### Requirement: Refuse an out-of-range bound at a surface and clamp it in a pass
A bound outside the permitted range MUST be refused by
`PUT /api/v1/internal-engine-config/timeout` and by the CLI with the same error,
rather than a different number applied silently. A value already STORED outside
that range MUST be clamped by the background passes rather than raised on: the
surfaces refuse it on the way in, so a value found out there came from an older
build or a hand-edited synced document, and a pass that could have run is the
wrong place to discover it.

#### Scenario: a stored bound outside the range is clamped by a pass
- **GIVEN** a settings document holding a bound below the floor, written without
  going through a surface,
- **WHEN** a background pass reads the bound it should run under,
- **THEN** it runs under the floor rather than raising, and a stored bound above
  the ceiling runs under the ceiling,
- **AND** the same out-of-range values sent to
  `PUT /api/v1/internal-engine-config/timeout` are refused.

### Requirement: Change the bound and the speech-to-text model one value at a time
`PUT /api/v1/internal-engine-config/timeout` (`null` returns to the built-in
default; outside the floor–ceiling range is refused, not clamped) and
`PUT /api/v1/internal-engine-config/transcribe-model` (`null` or empty clears
it, which stops transcription) MUST each change one value and leave the rest of
the document alone, audited like any other write to it (see "Audit every write to
the engine settings"). A CLI MUST show, set and return-to-default the bound —
`coffer config get | set <seconds> | unset engine.timeout`, where `get` prints the chosen bound
beside the default and `unset` returns to the built-in one — and show, set and clear the
speech-to-text model — `coffer config get | set <id> | unset transcribe.model` — with the same
effects, refusals and audit entries as the routes. The Coffer's model section of Settings ›
General MUST show and change both.

#### Scenario: the bound and the speech-to-text model change one value at a time
- **GIVEN** a settings document with a chosen engine model and a pass switched off,
- **WHEN** the operator sets the bound and the speech-to-text model through the
  routes, and then again through `coffer config set engine.timeout` and
  `coffer config set transcribe.model`,
- **THEN** each write changes only its own value and the engine model and the
  pass's switch are left as they stood,
- **AND** every one of those writes is recorded as an `internal_engine_model_set`
  audit entry.

### Requirement: Report and change the curation owner from every surface
The settings document MUST carry the curation owner — the one machine allowed to run
the `curate` pass, or none — and every surface that shows the engine MUST report
and change it, applying the four-state rule of
[vault-sync](../vault-sync/spec.md) "Report and change the rewriter's owner":

- `GET /api/v1/internal-engine-config` MUST report the owner as
  `curate_owner_machine_id`, the raw machine id or `null` while none is named.
  The settings read MUST NOT resolve it against the machine registry; a reader
  resolves it against `GET /api/v1/sync/machines`.
- `PUT /api/v1/internal-engine-config/curation-owner` MUST set the owner from
  `{"machine_id": …}` and leave the rest of the document alone; `null` or a blank id
  MUST clear it. The id MUST NOT be validated against the registry, because a
  vault that has never converged has no registry and must still be able to name
  its own machine. The write MUST be audited like any other write to the document
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
- **GIVEN** the internal-engine settings document with a chosen engine model and no
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
