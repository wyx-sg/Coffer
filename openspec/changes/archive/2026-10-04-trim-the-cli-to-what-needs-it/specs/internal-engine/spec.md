## MODIFIED Requirements

### Requirement: Carry the bound on one model call
The settings document MUST carry the bound on ONE call to Coffer's own model, where `NULL`
means the built-in default. The default MUST live in one place in the code
rather than be copied into each vault, exactly as an unchosen interval's does
(see "Report an unchosen interval beside its default"), so raising it later
reaches every vault that never chose. `GET /api/v1/internal-engine-config` MUST
report the chosen bound and that default together.

#### Scenario: bound how long one call to Coffer's own model may take
- **GIVEN** the engine has a connection and a model, and no bound has been
  chosen,
- **WHEN** the operator reads the bound, sets one, and returns it to the default
  (`PUT /api/v1/internal-engine-config/timeout`),
- **THEN** an unchosen bound is reported as unchosen beside the built-in default
  that applies, a chosen one is what every internal model call runs under — the
  distil pass, knowledge ingestion's description step, curation's agentic turns
  and speech-to-text alike — a value outside the permitted range is refused by
  the route, and a value already stored
  outside that range is clamped by a background pass rather than taking it down.

### Requirement: Refuse an out-of-range bound at a surface and clamp it in a pass
A bound outside the permitted range MUST be refused by
`PUT /api/v1/internal-engine-config/timeout`,
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
the engine settings"). The Coffer's model section of Settings ›
General MUST show and change both.

#### Scenario: the bound and the speech-to-text model change one value at a time
- **GIVEN** a settings document with a chosen engine model and a pass switched off,
- **WHEN** the operator sets the bound and the speech-to-text model through the
  routes,
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
- **GIVEN** a vault whose registry names two machines and that has named no curation owner, and the Knowledge page's Automatic popover
- **WHEN** the operator opens the popover, picks this machine as "Curation runs on", and then clears the owner
- **THEN** the first state reads as no owner and the pass runs wherever the vault is read, the pick names this machine and reads as this machine, and clearing reads as the unowned state again,
- **AND** the settings route reports the owner that each step left.

### Requirement: Report when each unattended pass last ran and runs next
Each pass in the upkeep block of `GET /api/v1/internal-engine-config` (and of every answer
the settings routes give) MUST carry `last_pass_at` and `next_pass_at`. `last_pass_at` MUST be
when that pass last finished on this machine, whoever asked for it — the timer or a button —
read from the audit event the pass records (`memory_aggregated`, `memory_distilled`,
`knowledge_curated`), so it survives a daemon restart; it is `null` when the pass never ran.
`next_pass_at` MUST be when this machine's timer runs the pass next, counted from the moment
its worker began waiting against the interval as it stands now (a worker's start delay
counting as its first wait), so a shortened interval moves it earlier at once. It MUST be `null`
while the pass is switched off, while a pass is running, and while no worker on this daemon is
waiting on it — the surface never invents a time.

#### Scenario: each pass reports when it last ran and when it runs next
- **GIVEN** an aggregation that finished 14 minutes ago with its worker waiting on a
  30-minute interval, a distil pass that has never run and has no worker waiting, and curation
  switched off while its worker waits
- **WHEN** the settings are read
- **THEN** `aggregate` reports its last pass 14 minutes ago and its next one 30 minutes after
  its wait began
- **AND** `distil` reports neither time, and `curate` reports no next pass

## REMOVED Requirements

### Requirement: Show, set and clear the engine model from the CLI
**Reason**: the requirement defined only the `engine.model` keys of `coffer config`, which no longer exist; `coffer config` keeps only the settings read before the daemon binds.
**Migration**: show, set and clear the engine model in the Coffer's model section of Settings › General, or with `GET` and `PUT /api/v1/internal-engine-config` ("Report and set the engine model over HTTP").

### Requirement: List and change each unattended pass from the CLI
**Reason**: the requirement defined only the `engine.upkeep.*` keys of `coffer config`, which no longer exist.
**Migration**: use the Automatic control on the Knowledge and Memory pages, which writes through `PUT /api/v1/internal-engine-config/upkeep` ("Show and change the unattended passes on the pages they upkeep").

### Requirement: Keep every engine setting under one key namespace
**Reason**: the requirement defined only the `engine.*` and `transcribe.*` keys of `coffer config`, which no longer exist; every setting this capability owns is a control on the Settings page or a route under `/api/v1/internal-engine-config`.
**Migration**: use the Coffer's model section of Settings › General, or the routes under `/api/v1/internal-engine-config`.
