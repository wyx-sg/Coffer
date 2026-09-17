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
whatever writes it (FR-001).

| Field | Type | Constraints / Notes |
|---|---|---|
| `model` | `str \| None` | The model Coffer's own passes run on. `None` until chosen, and while it is `None` `resolve_internal_connection()` answers `None` and every pass is a clean no-op (FR-004/FR-005). An empty or blank value on write is normalised to `None`. |
| `auto_aggregate_enabled` | `bool` | The `aggregate` pass's switch. Ships **ON**: it writes only the derived tree (FR-014). |
| `aggregate_interval_s` | `int \| None` | `None` = the pass's own default interval (FR-011). |
| `auto_distil_enabled` | `bool` | The `distil` pass's switch. Ships **ON** — it rewrites a derived digest that deleting and re-running reproduces. |
| `distil_interval_s` | `int \| None` | As above. |
| `auto_tidy_enabled` | `bool` | The `tidy` pass's switch. Ships **OFF**: it rewrites the only copy of the user's own writing (FR-014). |
| `tidy_interval_s` | `int \| None` | As above. |
| `updated_at` | `datetime` | Last write, reported so a surface can say when the settings last moved. |

`upkeep(pass_name)` is the single read seam: a surface asks for a pass by name
and gets an `UpkeepSetting`, so adding a pass adds one entry here instead of a
branch in every reader. An unknown name raises rather than defaulting, which is
what FR-012's refusal is built on.

### `UpkeepSetting`

```python
@dataclass(frozen=True)
class UpkeepSetting:
    enabled: bool
    interval_s: int | None = None
```

`interval_s = None` means "whatever this pass's own default is". The default is
NOT copied into the row — it lives with the pass, so raising it later reaches
every vault that never chose one (FR-011).

### Pass names

`AGGREGATE = "aggregate"`, `ORGANISE = "distil"`, `TIDY = "tidy"` — named in
the domain rather than in the workers, so a surface can offer exactly these
three without importing three application modules. These are the words every
surface uses: the route enum, the CLI's `<pass>` argument, the synced document's
`upkeep` block and the Settings page's rows.

### Known defect — `tidy_owner_machine_id`

The row also carries `tidy_owner_machine_id`, a column that is written, synced
and audited but that no code reads to make a decision: the machine axis it
belonged to was removed. It has no requirement in this spec on purpose — it is
either dead state to be dropped with its own migration, or state that needs an
FR. Recorded here so the next reader does not take its absence from the field
table above for an omission.

## Ports (`backend/coffer/application/engine_ports.py`)

The engine's consumers depend on these two Protocols and on nothing else of the
engine's (FR-008). The composition root satisfies both.

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
| `get()` | The row, or an unset default (`model=None`, ship-on/ship-off switches). |
| `update(model, upkeep, actor)` | Normalise, persist, audit. The one write path — sync's import and delete both go through it, so a converged change is audited exactly like a local one (FR-003, FR-018). |
| `set_upkeep(pass_name, setting, actor)` | Change ONE pass, leaving the others as they stand (FR-010). |

### Resolution and the drop rule

- `resolve_internal_connection()` pairs the connection flagged
  `internal_default` with `get().model`, or answers `None` (FR-004). There is no
  fallback to a model on the connection, because a connection carries none.
- `build_chat_model(resolved, …)` builds the engine's chat model from that pair,
  dispatched by protocol (FR-006). It is the only model builder; Coffer keeps no
  second registry.
- The drop rule (FR-007) is the engine's: when the internal-default connection
  moves, the engine model is cleared unless the newly chosen connection's
  curated `models` already lists that id. Spec provider-switching's
  internal-default operation triggers it through a port rather than an import —
  the flag is a column on a provider row, the model is a column on this row, and
  neither package reaches into the other.

### The schedule (`backend/coffer/application/upkeep_schedule.py`)

`wait_for_next_pass()` takes the wait in slices and re-reads the interval each
slice, so a change lands within one slice instead of after the six hours a
worker was already asleep (FR-013). `DEFAULT_INTERVALS` holds each pass's own
interval, used while the operator has chosen none, and is what
`default_interval_s` reports over the wire (FR-011).

## Audit events

| Value | When emitted |
|---|---|
| `internal_engine_model_set` | every write to the settings row — the model, a pass's switch, a pass's interval, and sync's import or reset |

The details blob carries every field after the write, so nothing is lost; the
event NAME, however, says "model set" for a write that may have changed only a
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

The document carries `model` and an `upkeep` map of `{enabled, interval_s}` per
pass. A machine still holding the defaults publishes nothing (FR-016); a
document with no `upkeep` block leaves this machine's passes alone (FR-017); the
document's deletion resets this machine to the defaults, written through the
service and audited with actor `sync` (FR-018).

## SQLite schema

One table, `internal_engine_config`, created by the migration that introduced
the engine's settings and extended once per pass switch/interval pair added
since. No other table is this spec's.

| Column | Notes |
|---|---|
| `id` | primary key, `CheckConstraint("id = 1")` |
| `model` | nullable |
| `auto_tidy_enabled` | not null, default false |
| `auto_aggregate_enabled` | not null, default true |
| `auto_distil_enabled` | not null, default true |
| `aggregate_interval_s` / `distil_interval_s` / `tidy_interval_s` | nullable |
| `tidy_owner_machine_id` | nullable — see the known defect above |
| `updated_at` | not null |

## Constraints summary

- A second settings row MUST be impossible at the database level, not only in
  the service.
- A write MUST be audited, whoever made it — a local operator, a CLI, or a
  converge round.
- A read of the engine's connection MUST NOT touch the network, and MUST answer
  `None` rather than raise when either half is missing.
- One request, one pass: an upkeep write MUST NOT be able to carry a stale copy
  of a pass it did not name.
