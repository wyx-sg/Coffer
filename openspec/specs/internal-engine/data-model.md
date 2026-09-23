# Data Model — Internal Engine

The one global row that says what Coffer thinks with and what it does
unattended, plus the ports its consumers reach it through. Depends on the
connection kind from spec [provider-switching](../provider-switching/spec.md)
for the endpoint half, and on spec [vault-sync](../vault-sync/spec.md) for the
state area it travels in.

## Domain entities (`backend/coffer/domain/internal_engine_config.py`)

### `GlobalInternalEngineConfig`

Coffer's own operating settings. One row, fixed primary key `SINGLETON_ID = 1`,
with a `CheckConstraint("id = 1")` that makes a second row unrepresentable
whatever writes it (see "Keep the engine's settings in one global row").

| Field | Type | Constraints / Notes |
|---|---|---|
| `model` | `str \| None` | The model Coffer's own passes run on. `None` until chosen, and while it is `None` `resolve_internal_connection()` answers `None` and every pass is a clean no-op (see "Resolve the engine's connection and model together" and "Make every internal pass a clean no-op when nothing is configured"). An empty or blank value on write is normalised to `None`. |
| `auto_aggregate_enabled` | `bool` | The `aggregate` pass's switch. Ships **ON**: it writes only the derived tree (see "Ship every unattended pass switched on"). |
| `aggregate_interval_s` | `int \| None` | `None` = the pass's own default interval (see "Report an unchosen interval beside its default"). |
| `auto_distil_enabled` | `bool` | The `distil` pass's switch. Ships **ON** — it rewrites a derived digest that deleting and re-running reproduces. |
| `distil_interval_s` | `int \| None` | As above. |
| `auto_curate_enabled` | `bool` | The `curate` pass's switch. Ships **ON**: it merges each collection's inbox of new material into the documents an agent reads, and carries a person's out-of-band edit outward without ever reverting it (see "Ship every unattended pass switched on"). |
| `curate_interval_s` | `int \| None` | As above. |
| `model_timeout_s` | `int \| None` | How long ONE call to Coffer's own model may take (see "Carry the bound on one model call"). `None` = the built-in default, meaning exactly what an unchosen interval's `None` means and for the same reason — the default stays in one place, so raising it later reaches every vault that never chose. Between `MIN_MODEL_TIMEOUT_S` and `MAX_MODEL_TIMEOUT_S`: refused outside that range by the surfaces, clamped into it by the passes (see "Refuse an out-of-range bound at a surface and clamp it in a pass"). |
| `transcribe_model` | `str \| None` | The speech-to-text model, run on the connection flagged `transcribe_default` rather than on the engine's own (see "Transcribe speech on its own connection and model"). `None` until chosen, and while it is `None` Coffer transcribes nothing and the agent receives the audio file. Normalised from blank to `None` like `model`. |
| `curate_owner_machine_id` | `str \| None` | The one machine allowed to run the `curate` pass on a vault that spans several, because two machines folding the same sources into two different documents is a duplicate that git merges cleanly and no conflict can catch. `None` = no owner named, and the pass runs wherever the setting is read — the right answer for a single-machine vault. Read by `curate_runs_on(machine_id)` where the curation worker is wired, and resolved into one of four `CurationOwner` states by `curation_owner(machine_id, known)` (see "Report and change the curation owner from every surface"). Not validated against the machine registry on write. Blank normalises to `None`. |
| `updated_at` | `datetime` | Last write, reported so a surface can say when the settings last moved. |

`upkeep(pass_name)` is the single read seam: a surface asks for a pass by name
and gets an `UpkeepSetting`, so adding a pass adds one entry here instead of a
branch in every reader. An unknown name raises rather than defaulting, which is
what the refusal in "Refuse an interval below the floor or an unknown pass" is
built on.

### `UpkeepSetting`

```python
@dataclass(frozen=True)
class UpkeepSetting:
    enabled: bool
    interval_s: int | None = None
```

`interval_s = None` means "whatever this pass's own default is". The default is
NOT copied into the row — it lives with the pass, so raising it later reaches
every vault that never chose one (see "Report an unchosen interval beside its
default").

### Pass names

`AGGREGATE = "aggregate"`, `DISTIL = "distil"`, `CURATE = "curate"` — named in
the domain rather than in the workers, so a surface can offer exactly these
three without importing three application modules. These are the words every
surface uses: the route enum, the CLI's `<pass>` argument, the synced document's
`upkeep` block and the Settings page's rows.

### `CurationOwner`

`UNOWNED`, `SELF`, `OTHER`, `UNKNOWN` — what `curate_owner_machine_id` is from
this machine's point of view, derived from the field and the machine registry
and never stored (spec [vault-sync](../vault-sync/spec.md) "Report and change
the rewriter's owner"). `UNKNOWN` — an owner a non-empty registry does not
hold — is the only fault; an empty registry can never yield it. The CLI prints
these values as `state` in `coffer engine curate-owner show --json`.

## Ports (`backend/coffer/application/engine_ports.py`)

The engine's consumers depend on these two Protocols and on nothing else of the
engine's (see "Reach the engine only through its ports"). The composition root
satisfies both.

| Port | Method | Answer |
|---|---|---|
| `ModelSelectorPort` | `get_default()` | the engine's `ResolvedConnection`, or `None` |
| `LlmCompletionPort` | `complete(system, user, model, credential_resolver)` | one shot of a model, for the small jobs that are not an agentic loop |

`ResolvedConnection` is spec provider-switching's value object — a
`ProviderConfig` paired with the `model` to run on it. The ports name it in
annotations only, so no consumer executes the provider kind's code to use them.

## Application services

### `InternalEngineConfigService`

| Method | Purpose |
|---|---|
| `get()` | The row, or an unset default (`model=None`, ship-on switches, `model_timeout_s=None`, `transcribe_model=None`). |
| `update(model, curate_owner_machine_id, upkeep, actor)` | Normalise, persist, audit the model, the owner and every pass's switch and interval together. Sync's import and delete write through it for those fields, and through `set_model_timeout` and `set_transcribe_model` for the other two, so every converged change goes through the service and is audited exactly like a local one (see "Audit every write to the engine settings" and "Reset to the defaults when the document is deleted"). An owner of `None` leaves it alone and `""` clears it. |
| `set_upkeep(pass_name, setting, actor)` | Change ONE pass, leaving the others as they stand (see "Change one unattended pass per write"). |
| `set_model_timeout(seconds, actor)` | Change the call bound, leaving the rest of the row alone. Outside `MIN_MODEL_TIMEOUT_S … MAX_MODEL_TIMEOUT_S` raises `ConfigValidationError` — this is an operator asking for a number, and a request silently turned into a different number is worse than a rejection they can read (see "Refuse an out-of-range bound at a surface and clamp it in a pass"). `None` returns to the built-in default. |
| `set_transcribe_model(model, actor)` | Change the speech-to-text model the same way; blank normalises to `None`, which stops transcription rather than failing it (see "Transcribe speech on its own connection and model"). |
| `set_curation_owner(machine_id, actor)` | Change the curation owner alone, leaving the rest of the row as it stands; `None` or blank clears it. The id is not checked against the machine registry (see "Report and change the curation owner from every surface"). |

### Resolution and the drop rule

- `resolve_internal_connection()` pairs the connection flagged
  `internal_default` with `get().model`, or answers `None` (see "Resolve the
  engine's connection and model together"). There is no fallback to a model on
  the connection, because a connection carries none.
- `build_chat_model(resolved, …)` builds the engine's chat model from that pair,
  dispatched by protocol (see "Build the chat model from the resolved pair"). It
  is the only model builder; Coffer keeps no second registry.
- The drop rule ("Drop the engine model when its connection moves") is the
  engine's: when the internal-default connection moves, the engine model is
  cleared unless the newly chosen connection's curated `models` already lists
  that id. Spec provider-switching's internal-default operation triggers it
  through a port rather than an import — the flag is a column on a provider row,
  the model is a column on this row, and neither package reaches into the other.
- `resolve_transcribe_connection()` is the same question asked of the connection
  flagged `transcribe_default`, through a port of its own
  (`TranscribeConnectionPort`) rather than an argument on the first: the two
  answers come from two different rows, and a caller that could pass the wrong
  one eventually will. There is no fallback between them (see "Transcribe speech
  on its own connection and model") — a missing half answers `None`, which is
  the state spec chat already handles by handing the agent the audio file.
- The drop rule applies to each flag independently (see "Drop the speech-to-text
  model when its connection moves"): moving `transcribe_default` drops
  `transcribe_model` unless the newly flagged connection curates that id, and
  leaves `model` untouched.

### The call bound (`backend/coffer/application/engine_timeout.py`)

`resolve_timeout(read)` answers what one call should use right now.
`DEFAULT_MODEL_TIMEOUT_S` is what every call site carried before the setting
existed, so making the number configurable changed no vault's behaviour on its
own; `MIN_MODEL_TIMEOUT_S` keeps a bound from expiring before a healthy endpoint
can answer, and `MAX_MODEL_TIMEOUT_S` bounds what a typo can cost. The reader is
a `TimeoutReader` consulted per call rather than a value captured at wiring
time, for the same reason the schedule re-reads its interval: the row is a
singleton the operator may change here or on another machine (see "Run every
internal model call under the bound"). A reader of `None` — a unit test, or a
pass constructed before the singleton exists — gets the default. Out-of-range
values are CLAMPED here rather than raised on (see "Refuse an out-of-range bound
at a surface and clamp it in a pass").

### The schedule (`backend/coffer/application/upkeep_schedule.py`)

`wait_for_next_pass()` takes the wait in slices and re-reads the interval each
slice, so a change lands within one slice instead of after the six hours a
worker was already asleep (see "Apply a changed switch or interval without a
restart"). `DEFAULT_INTERVALS` holds each pass's own interval, used while the
operator has chosen none, and is what `default_interval_s` reports over the wire
(see "Report an unchosen interval beside its default").

## Audit events

| Value | When emitted |
|---|---|
| `internal_engine_model_set` | every write to the settings row — the model, a pass's switch, a pass's interval, the call bound, the speech-to-text model, the curation owner, and sync's import or reset |

The connection half of each pair is audited by spec provider-switching:
`provider_internal_default_set` and `provider_transcribe_default_set`.

The details blob carries the value or values that write changed, as they stand
after it: `update` carries the model, the owner and every pass's switch and
interval; `set_model_timeout`, `set_transcribe_model` and `set_curation_owner`
each carry their own one field. The event NAME, however, says "model set" for a write that may have changed only a
switch. That is a known defect, recorded rather than fixed here: correcting it
needs either a second event type or a rename, and a rename is a migration over
the audit enum.

## On-disk / sync layout

The settings are not a resource, so they travel as a state area rather than as a
document under `resources/`:

```
~/.coffer/sync/
  state/
    settings/
      internal-engine.yaml    # model + the upkeep block; absent while every
                              # machine holds the defaults
```

The document carries `model`, `model_timeout_s`, `transcribe_model`,
`curate_owner_machine_id` and an `upkeep` map of `{enabled, interval_s}` per
pass. A machine still holding the defaults publishes nothing (see "Publish no
document while the defaults hold") — and "the defaults" now includes both newer
fields being unset, so a vault that has only raised its call bound publishes a
document where it previously published none. A document with no `upkeep` block
leaves this machine's passes alone, and a document missing either newer key
leaves that value alone key by key, an explicit `null` being a decision where an
absent key is an older machine (see "Leave settings alone for keys an incoming
document omits"). The document's deletion resets this machine to the defaults,
written through the service and audited with actor `sync` (see "Reset to the
defaults when the document is deleted").

## SQLite schema

One table, `internal_engine_config`, created by the migration that introduced
the engine's settings and extended once per pass switch/interval pair added
since. No other table is this spec's.

| Column | Notes |
|---|---|
| `id` | primary key, `CheckConstraint("id = 1")` |
| `model` | nullable |
| `auto_curate_enabled` | not null, default true |
| `auto_aggregate_enabled` | not null, default true |
| `auto_distil_enabled` | not null, default true |
| `aggregate_interval_s` / `distil_interval_s` / `curate_interval_s` | nullable |
| `curate_owner_machine_id` | nullable — `NULL` means no owner named |
| `model_timeout_s` | nullable, added by migration `0087` — NULL is the built-in default |
| `transcribe_model` | nullable, added by migration `0087` — NULL means Coffer transcribes nothing |
| `updated_at` | not null |

Migration `0087` adds the last two columns, both nullable and both meaning the
built-in behaviour while unset, so it changes no vault's behaviour on its own.
There is nothing to migrate INTO `transcribe_model`: the value it replaces was
the environment variable `COFFER_TRANSCRIBE_MODEL`, which leaves no row, and a
vault that had exported one gets the same "transcribe nothing" default as any
other until a model is chosen.

## Constraints summary

- A second settings row MUST be impossible at the database level, not only in
  the service.
- A write MUST be audited, whoever made it — a local operator, a CLI, or a
  converge round.
- A read of the engine's connection MUST NOT touch the network, and MUST answer
  `None` rather than raise when either half is missing. The same holds for the
  speech-to-text connection, and neither read MUST fall back to the other.
- One request, one pass: an upkeep write MUST NOT be able to carry a stale copy
  of a pass it did not name. The same holds for the call bound and the
  speech-to-text model, each of which has a write of its own.
- No internal model call MUST be unbounded, and the bound MUST be read per call
  rather than captured at wiring time.
