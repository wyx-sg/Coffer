## ADDED Requirements

### Requirement: Report when each unattended pass last ran and runs next
Each pass in the upkeep block of `GET /api/v1/internal-engine-config` (and of every answer
the settings routes give) MUST carry `last_pass_at` and `next_pass_at`. `last_pass_at` MUST be
when that pass last finished on this machine, whoever asked for it — the timer, a button or the
CLI — read from the audit event the pass records (`memory_aggregated`, `memory_distilled`,
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

### Requirement: Show and change the unattended passes on the pages they upkeep
The web UI MUST show and change each unattended pass on the page whose content it upkeeps,
not in Settings: an **Automatic** control in the page header reads "Automatic · hourly" (or
the chosen interval; "Automatic · off" while switched off) and opens a popover. Edits MUST save
on their own — a switch on toggle, an interval on selection — through
`PUT /api/v1/internal-engine-config/upkeep`, one pass per request, and the interval's default
option MUST name the real number.

- **Knowledge** — the popover carries the `curate` switch and interval, **Curate now** (every
  collection with items waiting, one after another, busy while a pass is in flight), and "Last
  pass 2 h ago · next in 58 min" from "Report when each unattended pass last ran and runs
  next". The control MUST NOT appear while Coffer's model is not set, because curation has
  nothing to run on. Once the vault's machine registry names more than one machine, the
  popover MUST show "Curation runs on" with a picker of the known machines and the line "One
  Mac curates; the others get the result through sync.", writing through
  `PUT /api/v1/internal-engine-config/curation-owner`; the owner is resolved by the four-state
  rule of "Report and change the curation owner from every surface", and an owner no known
  machine claims MUST read as that fault in the popover and on the header control, with the
  picker offering this machine to take the pass back. While another machine owns the pass the
  last/next line is not shown, because this machine's timer does not run it.
- **Memory** — the popover's one switch, "Read memory automatically", MUST switch `aggregate`
  and `distil` together (two writes, one per pass) and read as on only while both are on; its
  interval is the `aggregate` interval, the cadence at which the agents' memory is read, while
  `distil` keeps its own slower interval and distils what was read. The popover shows "Last
  read 14 min ago · next in 46 min" for `aggregate`. The control appears on the partitions page
  and on a partition's page, whether or not Coffer's model is set, because reading needs no
  model.

#### Scenario: the knowledge popover shows and changes curation
- **GIVEN** Coffer's model set, a curation pass that last ran two hours ago and runs next in 58
  minutes, and a registry naming two machines with this one the owner
- **WHEN** the Knowledge header's Automatic control is opened and the operator switches curation
  off and picks an interval
- **THEN** the popover shows the switch, the interval with its default named, "Curation runs on"
  this Mac and the last/next line, each edit writes one pass's half alone, and with Coffer's
  model unset the control is not in the header (TypeScript acceptance test)

#### Scenario: the curation owner's fault reads in the popover
- **GIVEN** a registry naming two machines and a curation owner neither of them claims
- **WHEN** the Knowledge header's Automatic control is opened
- **THEN** the control and the popover say curation runs on no machine, naming the unclaimed id,
  and choosing this Mac writes this machine as the owner (TypeScript acceptance test)

#### Scenario: the memory popover switches reading and distilling together
- **GIVEN** aggregation and distillation both switched on, aggregation read 14 minutes ago and due
  again in 46 minutes
- **WHEN** the Memory header's Automatic control is opened and the operator switches it off and
  then picks an interval
- **THEN** the popover shows "Read memory automatically", the interval and the last/next line,
  switching it off writes `aggregate` off and `distil` off as two requests, and the interval
  writes the `aggregate` interval alone (TypeScript acceptance test)
