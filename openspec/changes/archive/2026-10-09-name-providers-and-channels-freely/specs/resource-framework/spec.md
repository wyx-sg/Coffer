## MODIFIED Requirements

### Requirement: Name a provider or a channel with free text
The `provider` and `channel` kinds MUST name a resource with **free text**: whatever a person types
(spaces, capitals and any script), under one rule. The name is trimmed of surrounding whitespace and
Unicode NFC-normalised, and then MUST be 1 to 80 characters, MUST contain no control character
(a line break included) and MUST NOT start with `-`. A name that breaks the rule MUST be refused as a
validation error (422) on registration, on rename and on any change to the resource's file, with
nothing changed. Within the kind a name MUST be unique **ignoring case**: registering, or renaming to,
a name another resource of the kind holds in any casing MUST be refused with `RESOURCE_ALREADY_EXISTS`
(409), while a rename that only changes the case of the resource's own name MUST be allowed. The name
is renamed through the kind-agnostic update (`PATCH /api/v1/resources/{uid}` with `name`) and is
audited like any rename. No kind carries a separate `title`: the name is the one label a person
chose, and every surface (the web UI, the command line, the audit log) shows it wherever the resource
is listed or shown. Every other kind keeps the slug rule — letters, digits, `_`, `.` and `-`, at most
64 characters — and `mcp_server`, `skill` and `agent` keep their fixed names ("Treat a resource's name
as a mutable label").

A provider's or a channel's file MUST be `resources/<kind>/<uid>.json` (a provider's in the vault, a
channel's under `local/`), because a free-text name is not a safe file name; a rename MUST rewrite the
`name` key and MUST NOT move the file. Every other kind's file keeps its name-derived path.

A provider or channel file written with the earlier shape — a non-blank `title` beside a slug `name` —
MUST be migrated once on daemon start, before the resource store first reads: the title becomes the name
(when it clashes ignoring case with another name of the kind, ` (2)`, ` (3)`… is appended, and a name
kept unchanged wins over a title that would take it), the `title` key is dropped and the file moves to
`<uid>.json`. The migration is a pure function of the files, so two machines migrating the same vault
write the same commit; it runs on every start and does nothing once the files are migrated.

#### Scenario: a free-text name is stored as typed and renamed in place
- **GIVEN** the daemon is running
- **WHEN** a client registers a provider named "  Team 搜索 / EU  " and then lists the kind
- **THEN** the resource is registered under the trimmed, NFC-normalised name "Team 搜索 / EU", the list and the read carry it as `name` with no `title`, and the web UI shows that name wherever the resource appears
- **AND** the resource's file is `resources/provider/<uid>.json`, and after a rename to "Team search" it is still that file with the `name` key changed

#### Scenario: a name that breaks the rule is refused
- **GIVEN** a registered channel named "Phone bot"
- **WHEN** the user submits a name of 81 characters, a name holding a line break, a name starting with `-` and an empty name through the update route
- **THEN** each is refused as a validation error (422) and the channel is still named "Phone bot"
- **AND** nothing is audited and its file is unchanged

#### Scenario: two free-text names clash ignoring case
- **GIVEN** a provider named "Work"
- **WHEN** a client registers another provider named "work", and renames a second provider to "WORK"
- **THEN** both are refused with 409 `RESOURCE_ALREADY_EXISTS` and nothing changes

#### Scenario: a rename that only changes case is allowed
- **GIVEN** a provider named "work"
- **WHEN** the user renames it to "Work"
- **THEN** the rename is accepted and audited, and the provider keeps its uid and its file

#### Scenario: a rename does not move the file
- **GIVEN** a channel named "Phone bot" filed as `local/resources/channel/<uid>.json`
- **WHEN** the user renames it to "Office bot"
- **THEN** the file is still `local/resources/channel/<uid>.json` and its `name` key reads "Office bot"
- **AND** the channel keeps its uid, reach and enabled state

#### Scenario: a title becomes the name on the first start
- **GIVEN** a vault holding provider files `resources/provider/acme.json` (name `acme`, title "Acme EU") and `resources/provider/acme2.json` (name `acme2`, title "acme eu"), and a third with the name `plain` and no title
- **WHEN** the daemon starts
- **THEN** the first is named "Acme EU", the second "acme eu (2)" (the file that sorts later takes the suffix), and the third keeps `plain`, none of the files has a `title` key, and each is now `<uid>.json`
- **AND** a second start changes nothing

#### Scenario: a kept name wins over a title that would take it
- **GIVEN** a provider with no title named "Work" and another with the name `work-2` and the title "work"
- **WHEN** the daemon starts
- **THEN** the first keeps "Work" and the second is named "work (2)"

#### Scenario: a kind that is not free-text refuses a name with a space
- **GIVEN** a registered MCP server and a registered skill
- **WHEN** the user registers an MCP server named "My Server"
- **THEN** it is refused as a validation error and nothing is stored

### Requirement: Address every resource by an immutable uid through one kind-agnostic surface
The system MUST model every managed thing as a *resource* identified by an immutable,
opaque **`uid`** ([A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](../../../docs/decisions/identity-is-the-uid-inside-the-file.md)),
and MUST expose one kind-agnostic REST surface, `/api/v1/resources*`, to list, read, update,
enable, disable and delete any of them without the caller knowing the kind. Every route and
every stored reference from one resource to another MUST address the uid. A uid MUST be minted
once and never reused, and MUST be the same value on every machine that holds the resource, so
that two machines can tell "the same thing" from "a different thing with the same name" without
asking each other.

The lifecycle controls of the web UI are exactly these routes: list, read, update — the
description, the name where the kind lets it change ("Treat a resource's name as a mutable label"),
and the kind's own fields — enable, disable and delete, plus the reach pair ("Carry a
per-agent reach on every resource"). Creating is not one of them: a kind registers through its own
seam (see "Keep creation a per-kind seam"). A request a kind does not support MUST be refused rather
than ignored (see "Keep creation a per-kind seam" and "Carry a per-agent reach on every resource").

A kind MAY declare that its resources cannot be disabled — `knowledge`, `memory` and `agent` do.
Every resource of such a kind MUST read as enabled, whatever its stored reach holds (a resource disabled before its kind became non-toggleable reads enabled from then on), and enabling or disabling one through the
kind-agnostic surface MUST be refused with `RESOURCE_NOT_TOGGLEABLE` (409), changing
nothing. The resource read carries the kind's answer as `toggleable`, so a surface can
leave the switch out rather than offer one that is refused.

A kind exists only because the composition root registered it; a request naming an
unregistered kind MUST be refused rather than bringing one into being.

#### Scenario: the kind-agnostic surface serves every kind
- **GIVEN** resources of more than one registered kind exist,
- **WHEN** the user lists resources without naming a kind, reads one back by its uid, then disables and re-enables it,
- **THEN** every kind's resources appear in the one list, each carrying its uid, kind, name, config, reach and enabled flag,
- **AND** the enable/disable round trip is served by the same route for every kind, and each step is audited.

#### Scenario: every kind answers the same lifecycle routes
- **GIVEN** one registered kind that can be disabled and supports reach, and one that does neither
- **WHEN** each resource is read with `GET /api/v1/resources/{uid}`, given a new description with `PATCH /api/v1/resources/{uid}`, and sent a non-null scope with `PUT /api/v1/resources/{uid}/scope`, and `POST /api/v1/resources/{uid}/disable`
- **THEN** both kinds answer the read and the description update through the same routes, and the kind that supports no reach or cannot be disabled refuses that request and changes nothing
- **AND** the first kind's disable changes it through the kind-agnostic route and is audited

#### Scenario: a non-toggleable kind refuses to be disabled
- **GIVEN** a `knowledge` collection, a `memory` partition and an `agent`
- **WHEN** each is disabled through `/api/v1/resources` and read back
- **THEN** all three requests are refused with 409 `RESOURCE_NOT_TOGGLEABLE`
- **AND** all three still read back enabled, with `toggleable` false
- **AND** an agent whose stored reach says off, left from before the kind was non-toggleable, reads back enabled

### Requirement: Treat a resource's name as a mutable label
A resource's `name` is a **label**, unique within its kind (ignoring case for a kind whose name is free text, "Name a provider or a channel with free text") and nothing more. For every kind
except those that declare their name fixed, renaming MUST be an ordinary field of the
kind-agnostic update — at the same level as editing a description — and MUST NOT require any other record to be
rewritten, because nothing else holds the name: the resource keeps its identity, its config,
its reach, its enabled state and its audit trail, with the entries written before the change
still saying what it was called then. The same name rules MUST apply to a rename as to a
registration, a collision within the kind MUST be refused before anything moves, and renaming
to the name it already has MUST change nothing and record nothing. A resource file that is named after the resource MUST move to the new name in the same vault commit that
records the rename ([vault-storage](../vault-storage/spec.md) "Identify a resource by the uid inside its file");
a provider's or a channel's file is named by its uid and never moves. A kind that keeps an on-disk
artifact named after the resource MUST be given the chance to move it, with a failure aborting
the rename rather than leaving the two disagreeing: a file that cannot be written is refused
before the hook runs, and a write that fails after it asks the kind to move the artifact back.

A kind whose name is visible outside Coffer MUST declare its name fixed, because agents and the
files they read quote that name. Today these are `mcp_server`, whose name prefixes every tool
name an agent sees, and `skill`, whose name is the folder an agent loads it from. A kind MAY
also derive the name from the resource's config, which fixes it too: `agent`, whose name is its
type's ([agent-registry](../agent-registry/spec.md) "Keep one agent per type, named by it"), and
registration MUST refuse any other name for such a kind as a validation error. For a fixed-name
kind, an update whose `name` differs from the current one MUST be refused as a conflict with the
code `NAME_IMMUTABLE`, whichever surface it came through, with nothing moved and nothing
audited. The refusal message MUST say that the resource has to be deleted and registered again
under the new name, and MUST name what a re-registration resets — or, for a derived name, that
the name is the resource's type. None of these kinds carries a title: the fixed name is what every surface shows.

#### Scenario: renaming a resource is an ordinary edit
- **GIVEN** a resource of a kind whose name is not fixed, with a reach set, a secret cited by its
  config, and rows in a table its kind owns,
- **WHEN** the user changes its name through the kind-agnostic update,
- **THEN** the resource is the same resource — its identity, its reach, its
  secret and its kind-owned rows are untouched — and its audit trail comes
  back whole, with the rows written before the change still saying what it was
  called then,
- **AND** a name another resource of that kind already holds is refused with
  nothing moved, as is a name the rules would have refused at registration, and
  submitting the name it already has changes nothing.

#### Scenario: a kind whose name is a directory moves it with the rename
- **GIVEN** a resource of a renamable kind that keeps an on-disk artifact named after it —
  a knowledge collection's directory, a memory partition's directory,
- **WHEN** the user renames it,
- **THEN** the artifact is at the new name with its contents intact and is
  served from there,
- **AND** a rename the kind cannot carry out — something already occupies the
  destination — is refused with the resource and the artifact both untouched, rather
  than leaving a resource pointing at a directory that is not there or merging
  into one that was never its own,
- **AND** a resource file that cannot be written (an unsettled edit on disk) is refused before
  the artifact moves, and a write that fails after the artifact moved puts it back.

#### Scenario: a fixed name refuses a rename
- **GIVEN** a registered MCP server and a registered skill
- **WHEN** the user submits a different name for each through the kind-agnostic update
- **THEN** every attempt is refused as a conflict with the code `NAME_IMMUTABLE`, with a message saying to delete and register the resource again and naming what that resets
- **AND** each resource keeps its name, its on-disk artifact and its audit trail, and no audit entry is written

#### Scenario: a rename moves the resource's file in one commit
- **GIVEN** a resource of a renamable kind whose file is named after it (not a provider or a channel), filed as `resources/<kind>/old.json`
- **WHEN** the user renames it to `new`
- **THEN** one vault commit removes `resources/<kind>/old.json` and adds `resources/<kind>/new.json`, and the resource keeps its uid

### Requirement: Read the audit log from the command line
The system MUST let a terminal read the audit log with `coffer log audit`, over the same route
the web UI reads (`GET /api/v1/audit`). It MUST take the filters that route affords,
`--kind`, `--name`, `--event-type`, `--since` and `--limit`, and the route's cursor as
`--cursor`, and MUST print the entries newest first. Each entry MUST show its time, actor,
event type, and the label the resource carried at that moment; when more entries follow the
page, the output MUST end with the `--cursor` value that reads the next one. With `--json` it
MUST print the route's answer — its entries and its `next_cursor` — as one parseable document
with no human-readable framing.

#### Scenario: the command line reads the audit log
- **GIVEN** the user has disabled a resource and then renamed another resource
- **WHEN** they run `coffer log audit --limit 2`, and then `coffer log audit --kind <kind> --json`
- **THEN** the first prints both changes newest first, each with its time, actor, event type and label
- **AND** the second prints a parseable JSON document holding only that kind's entries

#### Scenario: the command line pages the audit log by cursor
- **GIVEN** three audit entries
- **WHEN** the user runs `coffer log audit --limit 2 --json` and then `coffer log audit --limit 2 --cursor <next_cursor> --json` with the cursor the first printed
- **THEN** the first prints the two newest entries and a `next_cursor`, and the second prints the oldest entry and a `null` `next_cursor`

### Requirement: Announce every write to a resource as an in-process hint
Every change to a resource MUST emit an in-process hint naming the kind, the uid and
whether the resource still exists (`upsert` or `delete`) — whoever made the change: a
surface, a hand edit Coffer committed, or a sync checkout. The hint only brings the next
reconcile pass forward for the targets that follow that kind. No revision number is kept:
nothing compares one, and a hint is an accelerator that is cheap to repeat. A resource's
`updated_at` is the modification time of its file on this machine, so reading a resource
writes nothing.

#### Scenario: every write to a resource is hinted
- **GIVEN** a newly registered resource
- **WHEN** its config, its enabled flag, its description, its scope and its name are changed in turn, and it is then deleted
- **THEN** each write emitted one hint for that uid, the last one marked `delete`
- **AND** a read of the resource emitted none

### Requirement: Validate every registration and persist nothing on failure
The system MUST validate every registration against its kind's schema and the kind's own
pre-write validators, MUST reject a duplicate name within a kind (ignoring case for a kind whose name is free text), and MUST persist
nothing on a validation failure — not a resource file with a rejected config, not a
half-written reach, not an audit entry for a change that did not happen, and no kind-owned side
effect: a registration that fails validation leaves the vault, this machine's reach record and the
audit log exactly as they were before the attempt. This is the contract every kind inherits, which is why it is stated
once here rather than once per kind.

#### Scenario: reject an invalid registration and persist nothing
- **GIVEN** a registered kind with a config schema,
- **WHEN** a registration arrives whose config fails that schema, or whose name is already taken within the same kind,
- **THEN** it is refused with a message naming the cause — a validation error for the schema failure, a conflict for the duplicate,
- **AND** no resource file, no reach record, no audit entry and no kind-owned side effect is left behind.

## RENAMED Requirements

- FROM: `### Requirement: Carry an optional editable title on the kinds that have one`
- TO: `### Requirement: Name a provider or a channel with free text`
