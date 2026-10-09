## MODIFIED Requirements

### Requirement: Audit every write to the engine settings
Every write to the settings MUST record an `internal_engine_model_set` audit
entry naming the actor and carrying the values after the write — the speech-to-text
model (`transcribe_model`) and the memory sync's switch and interval
(`memory_sync_enabled`, `memory_sync_interval_s`). A change another
machine made arrives as a sync commit to the settings document, and is as visible
in that document's history as one made here ([vault-storage](../vault-storage/spec.md) "Keep the vault a git repository whether or not it syncs").

#### Scenario: record every settings write with its actor and values
- **GIVEN** the internal-engine settings,
- **WHEN** the memory sync's switch and the speech-to-text model are each
  written by an actor,
- **THEN** each write records an `internal_engine_model_set` audit entry naming
  that actor,
- **AND** each entry's details carry the value as it stands after that write.

### Requirement: Change one unattended pass per write
`PUT /api/v1/internal-engine-config/upkeep` MUST change exactly one named pass —
today the only one is `memory_sync`, the memory sync.
An omitted half MUST leave that half alone, and any other pass MUST be left
exactly as it stands — a body carrying both would make every toggle a
chance to write back a stale copy of the other, on settings another machine
may be changing too. `use_default_interval` returns that pass to its own
default, which a null interval cannot express.

#### Scenario: switch off and re-time the passes Coffer runs unattended
- **GIVEN** a fresh vault, where the memory sync runs on its own timer,
- **WHEN** the operator switches the memory sync on or off, or gives it an interval, or
  returns it to its own default (`PUT /api/v1/internal-engine-config/upkeep`,
  one pass per request),
- **THEN** that pass's switch and interval change and nothing else does, the
  reported default interval says what runs while none is chosen, an interval
  below the floor and an unknown pass name are both refused, and the running
  worker picks the change up without a restart.

### Requirement: Refuse an interval below the floor or an unknown pass
An interval below the floor MUST be refused, because it would busy-loop a pass
over the user's files, and so MUST a pass name Coffer does not run — the
retired `aggregate`, `distil` and `curate` among them.

#### Scenario: refuse an interval below the floor or an unknown pass
- **GIVEN** the upkeep settings as they stand,
- **WHEN** the operator asks for an interval below the floor, or names a pass
  Coffer does not run,
- **THEN** both requests are refused with a validation error,
- **AND** every pass's switch and interval are left exactly as they stood.

### Requirement: Ship every unattended pass switched on
The memory sync (`memory_sync`) MUST ship ON, on its default interval of one
hour. Shipping it on is safe because the first sync on a machine, and any large
one, writes nothing into an agent until the person confirms a preview
([memory](../memory/spec.md) "Preview a first or large sync").

#### Scenario: a fresh vault runs every unattended pass
- **GIVEN** a fresh vault where nobody has touched the engine settings,
- **WHEN** the settings are read, and when the document is first written by a
  speech-to-text model choice alone,
- **THEN** `memory_sync` is switched on, with no chosen interval and a default
  interval of one hour.

### Requirement: Converge the settings as the `settings` state area
The settings MUST travel as sync state area `settings`, document
`state/settings/internal-engine.json` ([vault-sync](../vault-sync/spec.md) "Converge shared state areas"), carrying the speech-to-text
model and every pass's switch and interval — Coffer's passes behave the same everywhere only when they share one
setting, and switching a pass off is exactly the decision a second machine
must not be left out of. The document is the
settings, with no second copy on this machine: a key it does not carry MUST read
as that key's default, and a key this build does not know MUST survive every
write this build makes.

#### Scenario: the engine's settings converge and a deletion means the defaults
- **GIVEN** a machine that has chosen nothing, whose settings read as the defaults
  with no settings document in the vault,
- **WHEN** it chooses a speech-to-text model, switches the memory sync off with an interval,
- **THEN** `state/settings/internal-engine.json` carries each of those decisions and
  no time of the write, which is in this machine's `local/engine.json`, and the
  settings read back as written,
- **AND** a key a newer build wrote into the document survives the next write,
  and once the document is deleted every setting reads as its default again.

### Requirement: Report when each unattended pass last ran and runs next
Each pass in the upkeep block of `GET /api/v1/internal-engine-config` (and of every answer
the settings routes give) MUST carry `last_pass_at` and `next_pass_at`. `last_pass_at` MUST be
when that pass last finished on this machine having changed something, whoever asked for it — the
timer, a button or a command — read from the audit event the pass records (`memory_synced`),
so it survives a daemon restart; it is `null` when the pass never ran.
`next_pass_at` MUST be when this machine's timer runs the pass next, counted from the moment
its worker began waiting against the interval as it stands now (a worker's start delay
counting as its first wait), so a shortened interval moves it earlier at once. It MUST be `null`
while the pass is switched off, while a pass is running, and while no worker on this daemon is
waiting on it — the surface never invents a time.

#### Scenario: each pass reports when it last ran and when it runs next
- **GIVEN** a memory sync that finished 14 minutes ago with its worker waiting on a
  30-minute interval
- **WHEN** the settings are read
- **THEN** `memory_sync` reports its last pass 14 minutes ago and its next one 30 minutes
  after its wait began
- **AND** a pass that never ran reports no last pass, and a pass switched off reports no
  next one

### Requirement: Report the engine settings over HTTP
`GET /api/v1/internal-engine-config` MUST report the speech-to-text model, when
this machine last wrote the settings, and every pass's switch, chosen
interval and default interval. The route family MUST carry no model for
Coffer's own passes, because Coffer runs no pass over a model of its own, and
no per-call time limit, because the one model call Coffer makes runs under a
fixed limit.

#### Scenario: read the engine settings
- **GIVEN** a vault whose settings hold a speech-to-text model and the memory sync switched off,
- **WHEN** `GET /api/v1/internal-engine-config` is read,
- **THEN** it returns that speech-to-text model, the time this machine last wrote the settings, and an upkeep block naming `memory_sync` alone, switched off, with a chosen interval and a default interval,
- **AND** the answer carries no engine model and no curation owner.

### Requirement: Ignore retired keys in the settings document
The system MUST accept a settings document that still carries the keys `model`,
`curate_owner_machine_id`, `model_timeout_s`, an `upkeep.curate` entry or an `upkeep.distil`
entry, and MUST ignore them on read: they change no setting, raise no error and appear in no answer. The next
write of the document MUST drop them. A key this build has never known MUST
still survive a write, so only the retired keys are removed. An `upkeep.aggregate` entry is
not ignored: it carries over to the memory sync (see "Carry a switch and interval for each
unattended pass").

#### Scenario: ignore retired keys when the settings are read
- **GIVEN** a settings document holding `model`, `curate_owner_machine_id`, `model_timeout_s`, an `upkeep.curate` entry, an `upkeep.distil` entry and a speech-to-text model,
- **WHEN** the settings are read,
- **THEN** the speech-to-text model is reported as stored and no answer carries a time limit,
- **AND** the upkeep block names `memory_sync` only, and nothing reports the retired keys.

#### Scenario: drop retired keys on the next write
- **GIVEN** a settings document holding the retired keys and a key a newer build wrote,
- **WHEN** the operator changes one value through any settings route,
- **THEN** the rewritten document holds no `model`, no `curate_owner_machine_id`, no `model_timeout_s`, no `upkeep.curate` and no `upkeep.distil`, and its upkeep block holds `memory_sync` alone,
- **AND** the newer build's key is still in the document.

### Requirement: Carry a switch and interval for each unattended pass
The same document MUST carry a switch and an interval for each pass Coffer runs
on its own behalf — today one, `memory_sync`, the memory sync
([memory](../memory/spec.md) "Sync on an interval and on demand"). This
capability owns only whether and how often it runs, one switch and interval per
pass rather than per target. The retired `aggregate` and `distil` passes are
gone. A document an older build wrote may still carry `upkeep.aggregate` and no
`upkeep.memory_sync`: the memory sync MUST then read its switch and interval
from `upkeep.aggregate`, so a person who had switched memory reading off does
not find memory syncing, and the next write MUST store them under `memory_sync`
and drop `aggregate`.

#### Scenario: report the memory sync's switch and interval
- **GIVEN** a vault,
- **WHEN** `GET /api/v1/internal-engine-config` is read,
- **THEN** its upkeep block names exactly `memory_sync`, with a switch, a chosen
  interval, a default interval and when it last ran and runs next,
- **AND** a switch and an interval written for it are what the next read reports.

#### Scenario: an older build's aggregation switch carries over to the memory sync
- **GIVEN** a settings document an older build wrote, whose `upkeep.aggregate` is
  switched off at a 900-second interval and which has no `upkeep.memory_sync`,
- **WHEN** the settings are read, and then written again by choosing a
  speech-to-text model,
- **THEN** the memory sync reads switched off at 900 seconds,
- **AND** the rewritten document holds that switch and interval under
  `memory_sync`, and no `aggregate`.

### Requirement: Show and change the memory passes on the Memory page
The web UI MUST show and change the memory sync on the page whose content it
keeps, not in Settings: the ▾ half of the Memory page header's **Sync now** split
button opens a popover. Edits MUST
save on their own — a switch on toggle, an interval on selection — through
`PUT /api/v1/internal-engine-config/upkeep` as one `memory_sync` request each,
and the interval's default option MUST name the real number. The popover's one
switch, "Sync memory automatically", writes the memory sync's switch; its
interval is the memory sync's interval; and it shows when the sync last ran and
runs next ("Last synced 14m ago · next in 46m").

The Knowledge page carries no automatic control, because its sweep has no switch or interval to
set.

#### Scenario: the memory popover switches and times the one memory_sync pass
- **GIVEN** the memory sync switched on, last synced 14 minutes ago and due again in 46 minutes
- **WHEN** the ▾ beside Sync now in the Memory header is opened and the operator switches it
  off and then picks an interval
- **THEN** the popover shows "Sync memory automatically" and "Last synced 14m ago · next in
  46m", switching it off writes `memory_sync` off as one request, and the interval writes the
  `memory_sync` interval as one request (TypeScript acceptance test)

## RENAMED Requirements

- FROM: `### Requirement: Carry a switch and interval for each of the two unattended passes`
- TO: `### Requirement: Carry a switch and interval for each unattended pass`
