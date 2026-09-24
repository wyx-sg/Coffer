# Internal Engine

## Purpose

Coffer thinks with a model of its own. The internal engine is the settings that
say which one — the connection it borrows and the model it runs — plus the
switch and timer of every pass Coffer runs when nobody asked it to, the one
machine allowed to run curation, the bound on one call to that model, and the
speech-to-text model. It owns one global
settings row, the surfaces that show and change it (`/api/v1/internal-engine-config`,
`coffer engine …`, Settings → Coffer's model), its convergence between machines, and the
rule that a pass with nothing configured is a clean no-op rather than an error.

Coffer does work on its own behalf: it aggregates the agents' memory, lets a
model rewrite that derived digest, lets a model derive the knowledge documents
agents read from the sources a person writes, resolves a sync conflict, and
transcribes a voice message. All of them need an endpoint to call and a model to
name, and none belongs to the agent the user is chatting with. The engine
borrows its ENDPOINT and key from the connection flagged `internal_default` and
owns its MODEL; speech-to-text has its own connection (flagged
`transcribe_default`) and its own model, because the gateway that answers a chat
completion commonly serves no transcription endpoint at all. The four consumers
— vault-sync's conflict resolver, knowledge's curate, memory's distil and chat's
voice transcription — supply their own prompts and own their own results; this
capability supplies the connection, the model, the timer and the bound.

How long one call may take is the operator's number, because the right bound is
a property of their endpoint: against a gateway whose typical answer takes
25–30s, a fixed 60s bound leaves barely a factor of two and the passes fail
gracefully at a fraction of the rate they report. Out-of-range values are
refused at a surface, where an operator can read the rejection, and clamped in a
background pass, where the value came from an older build or a hand-edited
synced document.

Out of scope: creating, editing, activating or flagging a connection (both
`internal_default` and `transcribe_default` are provider-switching's fields and
routes, `POST /api/v1/providers/{uid}/internal-default` and
`POST /api/v1/providers/{uid}/transcribe-default`, and
`coffer provider internal-default|transcribe-default <name>`); what each pass
does (memory and knowledge); `GET /api/v1/upkeep/runs`, a cross-kind read of
what is in flight; any model registry; and per-collection or per-partition
timers. Coffer runs as a single-user tool behind the existing `X-Coffer-Token`
gate.

## Requirements

### Requirement: Keep the engine's settings in one global row
The system MUST keep Coffer's own operating settings — the engine model, the
speech-to-text model, the bound on one model call, each unattended pass's
switch and optional interval, and the curation owner, plus the timestamp of the
last write — in one global row whose primary key is fixed, with a database
constraint making a second row unrepresentable whatever writes it. `NULL` means
"the built-in default" for an interval and for the bound, "unchosen" for a
model, and "no owner named" for the curation owner.

#### Scenario: a second engine settings row is unrepresentable
- **GIVEN** the internal-engine settings row exists,
- **WHEN** a second row is inserted directly into the table,
- **THEN** the database refuses it, so "which settings does the engine use?"
  cannot become a question with two answers.

### Requirement: Report and set the engine model over HTTP
`GET /api/v1/internal-engine-config` MUST report the engine model, the
speech-to-text model, the chosen call bound beside the default that applies
while none is chosen, when the row was last written, and every pass's switch,
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

### Requirement: Audit every write to the engine settings
Every write to the row MUST record an `internal_engine_model_set` audit entry
naming the actor and carrying the values after the write, so a change made on
another machine and converged here is as visible as one made on this one.

#### Scenario: record every settings write with its actor and values
- **GIVEN** the internal-engine settings row,
- **WHEN** the model, one pass's switch, the call bound and the speech-to-text
  model are each written by an actor,
- **THEN** each write records an `internal_engine_model_set` audit entry naming
  that actor,
- **AND** each entry's details carry the value as it stands after that write.

### Requirement: Resolve the engine's connection and model together
`resolve_internal_connection()` MUST return the connection flagged
`internal_default` ([provider-switching](../provider-switching/spec.md) "Keep at most one internal-engine default") paired with the engine model,
or `None` when no connection is flagged or no model is chosen. The connection
carries no model of its own to fall back to, so the two halves resolve together
or not at all.

#### Scenario: pair the flagged connection with the chosen engine model
- **GIVEN** two connections, one flagged `internal_default`, and an engine model
  chosen on the settings row,
- **WHEN** a consumer asks the engine which connection to run on,
- **THEN** it is answered with the flagged connection's endpoint and protocol
  paired with the chosen engine model — never the other connection,
- **AND** a model chosen after wiring is the one the next answer carries.

### Requirement: Make every internal pass a clean no-op when nothing is configured
When `resolve_internal_connection()` answers `None`, every internal pass MUST be
a clean no-op rather than an error, on every consumer. Coffer is usable with no
connection at all, so a pass with nothing to run on simply does not run.

#### Scenario: nothing configured makes every internal pass a clean no-op
- **GIVEN** no connection is flagged `internal_default`, or no engine model is
  chosen,
- **WHEN** a consumer asks the engine for its connection,
- **THEN** it is answered `None`, the pass that asked does not run, and no error
  is raised or logged as a failure — the same answer for both missing halves.

### Requirement: Build the chat model from the resolved pair
Coffer MUST keep no second model registry and write down no model name of its
own: the engine builds its chat model from the resolved pair via
`build_chat_model(resolved, …)`, dispatched by protocol.

#### Scenario: build the engine's chat model from the resolved pair
- **GIVEN** a resolved pair of an Anthropic connection with one model, and one
  of an OpenAI-compatible connection with another,
- **WHEN** the engine builds a chat model from each,
- **THEN** each is the client for its connection's protocol, naming exactly the
  resolved model and pointed at the connection's own endpoint.

### Requirement: Drop the engine model when its connection moves
A change of the internal-default connection MUST DROP the engine model, unless
the newly chosen connection's curated `models` already lists that id — a curated
list is that connection's own catalogue, so an id on it is still servable.
Nothing MUST be probed to decide: a settings write MUST NOT depend on an
endpoint being reachable. Setting the connection that is already the internal
default MUST change nothing. The trigger is [provider-switching](../provider-switching/spec.md) "Set the internal-engine default", which
notifies the engine through a port; the rule and its exception are this
capability's.

#### Scenario: switching the internal engine's connection drops a model it does not serve
- **GIVEN** connection A is the internal default and the engine model is one of
  A's models,
- **WHEN** the operator makes connection B the internal default,
- **THEN** the engine model is cleared — so `resolve_internal_connection()` is
  `None` until a model is picked again — unless B's curated `models` already
  lists that id, in which case it is kept; nothing is probed over the network,
  and re-setting A, which is already the internal default, changes nothing.

### Requirement: Reach the engine only through its ports
Consumers MUST reach the engine only through `ModelSelectorPort` and
`LlmCompletionPort`, satisfied by the composition root. No consumer MUST import
the provider kind to get at the engine; that is what makes the engine
kind-agnostic substrate rather than a facet of the connection registry.

#### Scenario: consumers reach the engine without importing the provider kind
- **GIVEN** the engine's consumers — knowledge's ingestion and curation,
  memory's distil, vault-sync's conflict resolver and chat's voice transcription
  — and the engine package itself,
- **WHEN** their imports are read,
- **THEN** none of them imports the provider kind's application package,
- **AND** knowledge's and memory's consumers name `ModelSelectorPort` to reach
  the engine's connection.

### Requirement: Carry a switch and interval for each unattended pass
The same row MUST carry a switch and an interval for each of the three passes
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

### Requirement: Change one unattended pass per write
`PUT /api/v1/internal-engine-config/upkeep` MUST change exactly one named pass.
An omitted half MUST leave that half alone, and every other pass MUST be left
exactly as it stands — a body carrying all three would make every toggle a
chance to write back a stale copy of the other two, on settings another machine
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
- **AND** the stored row holds no interval for it, so no default was copied
  into the vault.

### Requirement: Refuse an interval below the floor or an unknown pass
An interval below the floor MUST be refused, because it would busy-loop a model
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
  settings row,
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
- **WHEN** the settings are read, and when the row is first written by a model
  choice alone,
- **THEN** `aggregate`, `distil` and `curate` are all switched on.

### Requirement: Converge the settings as the `settings` state area
The settings MUST travel as sync state area `settings`, document
`state/settings/internal-engine.yaml` (vault-sync), carrying the model, the call
bound, the speech-to-text model, the curation owner and every pass's switch and
interval — Coffer's passes behave the same everywhere only when they run on the
same model, switching a rewriter off is exactly the decision a second machine
must not be left out of, and the owner only means anything when every machine
holds the same one. A document that does not carry the owner MUST leave this
machine's owner alone, by the same rule as the other keys (see "Leave settings
alone for keys an incoming document omits").

#### Scenario: the engine's settings converge and a deletion means the defaults
- **GIVEN** one machine has chosen an engine model and switched `curate` off while
  a second machine still holds the defaults,
- **WHEN** a converge round runs,
- **THEN** the second machine takes both decisions from
  `state/settings/internal-engine.yaml`, which carries the call bound and the
  speech-to-text model beside them; a machine holding only the defaults
  publishes no document at all; a document carrying no upkeep block leaves this
  machine's switches alone, and one carrying neither of the two newer keys
  leaves this machine's bound and speech-to-text model alone for the same
  reason; and deleting the document resets this machine to the defaults with the
  write audited as `sync`.

### Requirement: Publish no document while the defaults hold
A machine still holding the defaults MUST publish NO document: the area carries
a decision, not a row. The tree holds the document exactly while some machine
holds a non-default choice.

#### Scenario: a machine holding the defaults publishes no settings document
- **GIVEN** a machine that has never written the settings row, and a machine
  whose row was written but holds only the defaults,
- **WHEN** each exports the `settings` area,
- **THEN** neither publishes a document,
- **AND** once a non-default model is chosen, exactly one
  `internal-engine` document is published.

### Requirement: Leave settings alone for keys an incoming document omits
An incoming document that carries no upkeep block MUST leave this machine's
switches and intervals alone rather than resetting them, and the same MUST hold
key by key for the call bound and the speech-to-text model: a key the document
does not carry is an older machine, not a decision. A key it carries —
including an explicit null — is authoritative.

#### Scenario: a document missing a key leaves this machine's value alone
- **GIVEN** a machine with a pass switched off, a chosen call bound and a chosen
  speech-to-text model,
- **WHEN** it imports a settings document carrying only a model,
- **THEN** the model is taken and the switch, the bound and the speech-to-text
  model are left as they were,
- **AND** a later document carrying an explicit null for the bound and the
  speech-to-text model clears both.

### Requirement: Reset to the defaults when the document is deleted
Deleting the document MUST reset this machine to the defaults, written through
the same service as any other change and audited as `sync`.

#### Scenario: deleting the settings document resets this machine to the defaults
- **GIVEN** a machine holding a chosen model, a switched-off pass, a chosen
  bound and a chosen speech-to-text model,
- **WHEN** a converge round reports the settings document deleted,
- **THEN** every one of those returns to its default,
- **AND** the reset is recorded as audit entries whose actor is `sync`, and the
  machine then publishes no document.

### Requirement: Show, set and clear the engine model from the CLI
A CLI MUST show, set and clear the engine model — `coffer engine model show |
set <id> | clear` — with the same effect and the same audit entry as the HTTP
route, so a terminal-only operator can see and change which model Coffer thinks
with.

#### Scenario: the command line shows and sets the engine model
- **GIVEN** the daemon is running and a connection is the internal default,
- **WHEN** the operator runs `coffer engine model set <id>`, then
  `coffer engine model show`, then `coffer engine model clear`,
- **THEN** each has the same effect as the HTTP route — the model is stored,
  reported and cleared — and the audit entry is the same one the route records.

### Requirement: List and change each unattended pass from the CLI
A CLI MUST list every pass's switch, chosen interval and default interval —
`coffer engine upkeep list [--json]`, printing the default that runs when none
is chosen so the terminal shows what the page shows — and change one pass per
invocation — `coffer engine upkeep set <pass> [--on | --off] [--interval
<seconds> | --default-interval]`, where `<pass>` is one of `aggregate`,
`distil`, `curate` — including returning that pass to its default interval. It
MUST refuse an interval below the floor and an unknown pass name with the same
errors the route gives.

#### Scenario: the command line lists and changes each unattended pass
- **GIVEN** the daemon is running,
- **WHEN** the operator runs `coffer engine upkeep list --json`, then
  `coffer engine upkeep set curate --off`, then
  `coffer engine upkeep set distil --interval 900`,
- **THEN** the listing is machine-readable and names each pass's switch, its
  chosen interval and the default that runs while none is chosen; each `set`
  changes one pass only; and an interval below the floor or an unknown pass name
  is refused with the same error the route gives.

### Requirement: Carry the bound on one model call
The row MUST carry the bound on ONE call to Coffer's own model, where `NULL`
means the built-in default. The default MUST live in one place in the code
rather than be copied into each vault, exactly as an unchosen interval's does
(see "Report an unchosen interval beside its default"), so raising it later
reaches every vault that never chose. `GET /api/v1/internal-engine-config` MUST
report the chosen bound and that default together.

#### Scenario: bound how long one call to Coffer's own model may take
- **GIVEN** the engine has a connection and a model, and no bound has been
  chosen,
- **WHEN** the operator reads the bound, sets one, and returns it to the default
  (`PUT /api/v1/internal-engine-config/timeout`, or `coffer engine timeout
  show | set | default`),
- **THEN** an unchosen bound is reported as unchosen beside the built-in default
  that applies, a chosen one is what every internal model call runs under — the
  distil pass, knowledge ingestion's description step, curation's agentic turns
  and speech-to-text alike — a value outside the permitted range is refused by
  the route and by the CLI with the same error, and a value already stored
  outside that range is clamped by a background pass rather than taking it down.

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
- **GIVEN** a chosen bound on the settings row,
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
- **GIVEN** a settings row holding a bound below the floor, written without
  going through a surface,
- **WHEN** a background pass reads the bound it should run under,
- **THEN** it runs under the floor rather than raising, and a stored bound above
  the ceiling runs under the ceiling,
- **AND** the same out-of-range values sent to
  `PUT /api/v1/internal-engine-config/timeout` are refused.

### Requirement: Transcribe speech on its own connection and model
The row MUST carry the speech-to-text model, separate from the engine model. The
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

### Requirement: Drop the speech-to-text model when its connection moves
A change of the `transcribe_default` connection MUST DROP the speech-to-text
model on the same rule as "Drop the engine model when its connection moves" —
kept only when the newly flagged connection's curated `models` already lists
that id, nothing probed, re-flagging the connection that already carries it
changing nothing — and MUST leave the engine model untouched. The two flags move
independently.

#### Scenario: moving the speech-to-text flag drops a model the new connection does not curate
- **GIVEN** connection A is flagged `transcribe_default`, a speech-to-text model
  and an engine model are both chosen, and connection B curates the
  speech-to-text model while connection C does not,
- **WHEN** the flag is re-set on A, then moved to B, then moved to C,
- **THEN** re-setting A and moving to B keep the speech-to-text model, moving to
  C clears it,
- **AND** the engine model is untouched throughout.

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
