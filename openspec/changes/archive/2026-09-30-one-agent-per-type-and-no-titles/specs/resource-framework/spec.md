## RENAMED Requirements

- FROM: `### Requirement: Carry an optional editable title on every resource`
- TO: `### Requirement: Carry an optional editable title on the kinds that have one`

## MODIFIED Requirements

### Requirement: Carry an optional editable title on the kinds that have one
A resource of a kind that carries a title MUST carry an optional **`title`**: free text of at
most 80 characters that a person chooses for display, separate from the resource's `name`. The
kinds with a title are those whose name is a label a person chose — `provider`, `channel`,
`knowledge` and `memory`. `agent`, `mcp_server` and `skill` carry none: each is shown by its fixed
name, and a non-empty title for one MUST be refused as a validation error (422) on registration
and on update, with nothing changed. On a kind that carries one, the title MUST be editable
through the kind-agnostic update (`PATCH /api/v1/resources/{uid}`) and through
`coffer <kind> edit <name> --title <text>`. An empty title MUST clear it. A title longer than 80
characters MUST be refused as a validation error with nothing changed. A title change MUST be
audited like any other update. The web UI and the CLI MUST show the title in place of the name
wherever a resource is listed or shown when a title is set, and the name when it is not. The
title MUST travel with the resource to the user's other machines through vault-sync, and a
resource that arrives without one MUST keep its title empty.

#### Scenario: a title is shown in place of the name
- **GIVEN** a resource of a kind that carries a title, with no title
- **WHEN** the user runs `coffer <kind> edit <name> --title "Team search"` and then lists that kind
- **THEN** the list and `coffer <kind> show` print "Team search" where the name was shown, and `--json` carries both `name` and `title`
- **AND** the change is audited as an update, and the resource's name, uid, reach and enabled state are unchanged

#### Scenario: an over-long title is refused
- **GIVEN** a resource with a title set
- **WHEN** the user submits a title of 81 characters through the update route, and then an empty title
- **THEN** the first is refused as a validation error and the stored title is unchanged
- **AND** the second clears the title, and surfaces show the name again

#### Scenario: a kind without a title refuses one
- **GIVEN** a registered MCP server, a registered skill and a registered agent
- **WHEN** the user submits a title for each through the kind-agnostic update, and registers an MCP server with a title
- **THEN** each is refused as a validation error (422) and nothing is stored
- **AND** `coffer mcp edit` and `coffer mcp add` offer no `--title`, and `coffer skill` offers no `edit`

### Requirement: Address every resource by an immutable uid through one kind-agnostic surface
The system MUST model every managed thing as a *resource* identified by an immutable,
opaque **`uid`** ([Resource Identity Is an Immutable `uid`](../../../docs/decisions/resource-identity-is-an-immutable-uid.md)),
and MUST expose one kind-agnostic REST surface, `/api/v1/resources*`, to list, read, update,
enable, disable and delete any of them without the caller knowing the kind. Every route and
every stored reference from one resource to another MUST address the uid. A uid MUST be minted
once and never reused, and MUST be the same value on every machine that holds the resource, so
that two machines can tell "the same thing" from "a different thing with the same name" without
asking each other.

On the command line, every kind's group MUST offer the same lifecycle verbs, generated from the
kind registry and served by the kind-agnostic routes: `list`, `show`, `edit`, `rm`,
`enable`, `disable` and `scope`. `add` is not one of them: a group offers `add` only when its
kind supplies one of its own (see "Keep creation a per-kind seam"). A verb the kind does not support MUST be absent from its group
rather than refused when run (see "Keep creation a per-kind seam" and "Carry a per-agent reach
on every resource"); a kind that cannot be disabled offers no `enable` or `disable`, and a kind
with nothing on its record a person may edit — `skill`, whose name is fixed and whose description
is its SKILL.md's — offers no `edit`. `show` MUST resolve either a name or a uid. `edit` MUST take
`--description`, and `--title` on a kind that carries one ("Carry an optional editable title on
the kinds that have one"), plus the kind's own flags. Every `list` and `show` MUST support
`--json`. A group MAY add commands that are unique to its kind, and MUST NOT add a second
spelling of a lifecycle verb.

A kind MAY declare that its resources cannot be disabled — `knowledge` and `memory` do.
Every resource of such a kind MUST be enabled, and enabling or disabling one through the
kind-agnostic surface MUST be refused with `RESOURCE_NOT_TOGGLEABLE` (409), changing
nothing. The resource read carries the kind's answer as `toggleable`, so a surface can
leave the switch out rather than offer one that is refused.

A kind exists only because the composition root registered it; a request naming an
unregistered kind MUST be refused rather than bringing one into being.

#### Scenario: the kind-agnostic surface serves every kind
- **GIVEN** resources of more than one registered kind exist,
- **WHEN** the user lists resources without naming a kind, reads one back by its uid, then disables and re-enables it,
- **THEN** every kind's resources appear in the one list, each carrying its uid, kind, name, title, config, reach and enabled flag,
- **AND** the enable/disable round trip is served by the same route for every kind, and each step is audited.

#### Scenario: every kind's group offers the same lifecycle verbs
- **GIVEN** the CLI's command tree
- **WHEN** each registered kind's group is read
- **THEN** each offers `list`, `show` and `rm`, offers `edit` only where the kind has something to edit and `--title` only where it carries a title, offers `enable` and `disable` only where the kind can be disabled, offers `add` only where the kind can be created from that group, and offers `scope` only where the kind supports reach
- **AND** `coffer <kind> disable <name>` and `coffer <kind> disable <uid>` disable the same resource through the kind-agnostic route, and the change is audited

#### Scenario: a non-toggleable kind refuses to be disabled
- **GIVEN** a `knowledge` collection and a `memory` partition
- **WHEN** each is disabled through `/api/v1/resources` and read back
- **THEN** both requests are refused with 409 `RESOURCE_NOT_TOGGLEABLE`
- **AND** both still read back enabled, with `toggleable` false, and neither `coffer knowledge` nor `coffer memory` offers `enable` or `disable`

### Requirement: Treat a resource's name as a mutable label
A resource's `name` is a **label**, unique within its kind and nothing more. For every kind
except those that declare their name fixed, renaming MUST be an ordinary field of the
kind-agnostic update — at the same level as editing a description, and reached on the command
line as `coffer <kind> edit <name> --name <new>` — and MUST NOT require any other record to be
rewritten, because nothing else holds the name: the resource keeps its identity, its config,
its reach, its enabled state and its audit trail, with the entries written before the change
still saying what it was called then. The same name rules MUST apply to a rename as to a
registration, a collision within the kind MUST be refused before anything moves, and renaming
to the name it already has MUST change nothing and record nothing. A kind that keeps an on-disk
artifact named after the resource MUST be given the chance to move it, with a failure aborting
the rename rather than leaving the two disagreeing.

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
the name is the resource's type. None of these kinds carries a title ("Carry an optional
editable title on the kinds that have one"): the fixed name is what every surface shows.

#### Scenario: renaming a resource is an ordinary edit
- **GIVEN** a resource of a kind whose name is not fixed, with a reach set, a credential cited by its
  config, and rows in a table its kind owns,
- **WHEN** the user changes its name through the kind-agnostic update,
- **THEN** the resource is the same resource — its identity, its reach, its
  credential and its kind-owned rows are untouched — and its audit trail comes
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
  destination — is refused with the row and the artifact both untouched, rather
  than leaving a resource pointing at a directory that is not there or merging
  into one that was never its own.

#### Scenario: a fixed name refuses a rename
- **GIVEN** a registered MCP server and a registered skill
- **WHEN** the user submits a different name for each through the kind-agnostic update, and through `coffer <kind> edit <name> --name <new>`
- **THEN** every attempt is refused as a conflict with the code `NAME_IMMUTABLE`, and the command line exits non-zero with a message saying to delete and register the resource again and naming what that resets
- **AND** each resource keeps its name, its on-disk artifact and its audit trail, and no audit entry is written
