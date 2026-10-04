# Data Model — Internal Engine

The one global settings document that says what Coffer transcribes speech with
and what it does unattended. Depends on the
connection kind from spec [provider-switching](../provider-switching/spec.md)
for the transcription endpoint, and on spec vault-storage for the state document
it is stored as.

## Domain entities (`backend/coffer/domain/internal_engine_config.py`)

### `GlobalInternalEngineConfig`

Coffer's own operating settings: one document per vault,
`state/settings/internal-engine.json`, so a second copy has nowhere to be
(see "Keep the engine's settings in one vault document").

| Field | Type | Constraints / Notes |
|---|---|---|
| `auto_aggregate_enabled` | `bool` | The `aggregate` pass's switch. Ships **ON**: it writes only the derived tree (see "Ship every unattended pass switched on"). |
| `aggregate_interval_s` | `int \| None` | `None` = the pass's own default interval (see "Report an unchosen interval beside its default"). |
| `auto_distil_enabled` | `bool` | The `distil` pass's switch. Ships **ON** — it writes only a derived digest that deleting and re-running reproduces. |
| `distil_interval_s` | `int \| None` | As above. |
| `transcribe_model` | `str \| None` | The speech-to-text model, run on the connection flagged `transcribe_default` (see "Transcribe speech on its own connection and model"). `None` until chosen, and while it is `None` Coffer transcribes nothing and the agent receives the audio file. A blank value on write is normalised to `None`. |
| `updated_at` | `datetime` | When this machine last changed the settings (`local/engine.json`), reported so a surface can say when they last moved. Not in the vault document. |

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
NOT copied into the document — it lives with the pass, so raising it later reaches
every vault that never chose one (see "Report an unchosen interval beside its
default").

### Pass names

`AGGREGATE = "aggregate"`, `DISTIL = "distil"` — named in
the domain rather than in the workers, so a surface can offer exactly these
two without importing two application modules. These are the words every
surface uses: the route enum, the CLI's `<pass>` argument and the document's
`upkeep` block.

## Application services

### `InternalEngineConfigService`

| Method | Purpose |
|---|---|
| `get()` | The settings, or an unset default (ship-on switches, `transcribe_model=None`). |
| `set_upkeep(pass_name, setting, actor)` | Change ONE pass, leaving the others as they stand (see "Change one unattended pass per write"). |
| `set_transcribe_model(model, actor)` | Change the speech-to-text model the same way; blank normalises to `None`, which stops transcription rather than failing it (see "Transcribe speech on its own connection and model"). |

### Resolution and the drop rule

- `resolve_transcribe_connection()` pairs the connection flagged
  `transcribe_default` with `get().transcribe_model`, or answers `None`, through
  a port (`TranscribeConnectionPort`). Both halves must be set; a missing half
  answers `None`, which is the state spec chat already handles by handing the
  agent the audio file (see "Transcribe speech on its own connection and
  model"). Nothing is probed over the network.
- The drop rule (see "Drop the speech-to-text model when its connection
  moves"): moving `transcribe_default` clears `transcribe_model` unless the
  newly flagged connection's curated `models` already lists that id. Spec
  provider-switching's transcribe-default operation triggers it through a port
  rather than an import — the flag is in a provider's resource file, the model is
  in this document, and neither package reaches into the other.

### The call time limit (`backend/coffer/application/engine_timeout.py`)

`DEFAULT_MODEL_TIMEOUT_S` (60 seconds) is the limit one transcription call runs
under. It is a constant, not a setting: the transcriber factory passes it to
every transcriber it builds (see "Change the speech-to-text model on its own
route").

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
| `internal_engine_model_set` | every write to the settings through the service — a pass's switch, a pass's interval, the speech-to-text model |

The connection half of the speech-to-text pair is audited by spec
provider-switching: `provider_transcribe_default_set`.

The details blob carries the value or values that write changed, as they stand
after it: `set_upkeep` and `set_transcribe_model` each carry their own fields. The event NAME, however, says "model set" for a write that may have changed only a
switch. That is a known defect, recorded rather than fixed here: correcting it
needs either a second event type or a rename, and a rename is a migration over
the audit enum.

## Storage

The settings are not a resource, so they are a vault **state document** of
their own rather than a file under `resources/` (spec vault-storage), plus one
machine-local timestamp:

```
~/.coffer/
  vault/state/settings/internal-engine.json   # the settings; absent while they are the defaults
  local/engine.json                           # {"updated_at": "<iso>"} — when THIS machine last changed them
```

```json
{
  "format_version": 1,
  "transcribe_model": "<model id>",
  "upkeep": {
    "aggregate": { "enabled": true, "interval_s": null },
    "distil": { "enabled": true, "interval_s": null }
  }
}
```

| Key | Notes |
|---|---|
| `format_version` | the state document's format (1) |
| `transcribe_model` | `null` until chosen |
| `upkeep.<pass>.enabled` | a missing entry reads as on |
| `upkeep.<pass>.interval_s` | `null` = the pass's own default |

A document written by an older build may still carry `model`,
`curate_owner_machine_id`, `model_timeout_s` and an `upkeep.curate` entry. They are ignored on read
and dropped by the next write of the document, while every other key the
document holds is kept (see "Ignore retired keys in the settings document").

`VaultInternalEngineConfigRepo` (`infrastructure/persistence/internal_engine_repo.py`)
reads the document at `HEAD`. A vault that never chose anything has no document
and reads as the defaults (`get()` answers `None`); a change back to every
default removes the document, so "the defaults" is always the absence of one
(see "Publish no document while the defaults hold"). Each setter writes only
its own fields, read-modify-write against `HEAD` in one commit, so a change
restating fields the caller never looked at cannot undo an edit another machine
made meanwhile; keys the document holds that this build does not write are
kept in place. `updated_at` is not in the document — two machines stamping it
would conflict on every edit — so it is `local/engine.json`.

A change made on another machine arrives as a `sync` commit of the document and
takes effect on the next read; the vault's history is its record. Deleting the
document — here, by hand, or on another machine — resets this machine to the
defaults (see "Reset to the defaults when the document is deleted").

## Constraints summary

- There MUST be one settings document per vault, at one path.
- A write through the service MUST be audited, whoever made it — a local
  operator or a CLI; every change, a sync round's included, is a vault commit
  naming its writer.
- A read of the speech-to-text connection MUST NOT touch the network, and MUST
  answer `None` rather than raise when either half is missing.
- One request, one pass: an upkeep write MUST NOT be able to carry a stale copy
  of a pass it did not name. The speech-to-text model has a write of
  its own for the same reason.
- No transcription call MUST be unbounded.
